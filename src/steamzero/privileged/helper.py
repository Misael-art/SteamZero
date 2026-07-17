# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""`steamzero-admin` — helper privilegiado (ADR-0009, AC-PR-01, ST-01).

Recebe uma ``Request``, valida rigorosamente e só então executa via um
``Effector`` injetado (em produção escreve sysfs/systemd; nas provas é dry).
Ordem de validação (fuzzing nunca chega ao efetor):

1. versão de protocolo (mismatch => E-PRIV-PROTO-MISMATCH);
2. ação na allowlist (senão E-PRIV-DENIED);
3. chaves de parâmetro sem extras (defesa contra injeção);
4. validador da ação (range/enum/UUID) — ParamError => E-PRIV-DENIED;
5. autorização (polkit-stand-in) => E-PRIV-DENIED;
6. execução + audit log append-only.

Nenhuma string de shell/path/conteúdo do chamador é executada.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from steamzero import __version__
from steamzero.core import fs
from steamzero.core.errors import SteamZeroError, build_error
from steamzero.privileged.gpu_effects import GpuClockTransactionEngine, GpuCommandWriter
from steamzero.privileged.host_effects import SysfsWriter, TdpTransactionEngine
from steamzero.privileged.protocol import (
    ACTIONS,
    PROTOCOL_VERSION,
    ParamError,
    Request,
    Response,
)


class Effector(Protocol):
    """Executa a ação privilegiada já validada. Em produção: sysfs/systemd."""

    def apply(self, action: str, params: dict[str, Any]) -> dict[str, Any]: ...


class DryEffector:
    """Efetor de prova: registra chamadas, não toca hardware."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def apply(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((action, dict(params)))
        return {"applied": True, "dry": True, "action": action}


class HostEffector:
    """Health público e motores de hardware ainda sem transporte mutável externo."""

    def __init__(
        self,
        *,
        sys_root: Path = Path("/sys"),
        state_root: Path = Path("/var/lib/steamzero/admin/tdp"),
        gpu_state_root: Path = Path("/var/lib/steamzero/admin/gpu-clock"),
        tdp_writer: SysfsWriter | None = None,
        gpu_value_writer: SysfsWriter | None = None,
        gpu_command_writer: GpuCommandWriter | None = None,
    ) -> None:
        self._sys_root = sys_root
        kwargs: dict[str, Any] = {"sys_root": sys_root, "state_root": state_root}
        if tdp_writer is not None:
            kwargs["writer"] = tdp_writer
        self._tdp = TdpTransactionEngine(**kwargs)
        gpu_kwargs: dict[str, Any] = {"sys_root": sys_root, "state_root": gpu_state_root}
        if gpu_value_writer is not None:
            gpu_kwargs["value_writer"] = gpu_value_writer
        if gpu_command_writer is not None:
            gpu_kwargs["command_writer"] = gpu_command_writer
        self._gpu_clock = GpuClockTransactionEngine(**gpu_kwargs)

    def apply(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        if action == "health" and not params:
            return {
                "healthy": True,
                "version": __version__,
                "protocolVersion": PROTOCOL_VERSION,
                "effectiveUid": os.geteuid(),
                "mutationsEnabled": False,
                "hardware": _hardware_capabilities(self._sys_root),
            }
        if action == "set-tdp":
            return self._tdp.apply(int(params["watts"]))
        if action == "rollback-tdp":
            return self._tdp.rollback(str(params["operationId"]))
        if action == "recover-tdp":
            return self._tdp.recover()
        if action == "set-gpu-clock":
            return self._gpu_clock.apply(int(params["mhz"]))
        if action == "rollback-gpu-clock":
            return self._gpu_clock.rollback(str(params["operationId"]))
        if action == "recover-gpu-clock":
            return self._gpu_clock.recover()
        raise SteamZeroError(
            "E-PRIV-DENIED",
            detail="efetor host ainda indisponível; nenhuma mutação foi executada",
        )


def _read_sysfs(path: Path, *, limit: int = 64 * 1024) -> str:
    try:
        if not path.is_file():
            return ""
        data = path.read_bytes()
    except OSError:
        return ""
    if len(data) > limit:
        return ""
    return data.decode("utf-8", errors="replace").replace("\x00", "").strip()


def _bounded_micro_watts(value: str) -> int | None:
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if 0 <= parsed <= 100_000_000 else None


def _tdp_capability(sys_root: Path) -> dict[str, Any]:
    base = sys_root / "class/hwmon"
    try:
        entries = sorted(base.iterdir(), key=lambda path: path.name)
    except OSError:
        entries = []
    for entry in entries:
        if _read_sysfs(entry / "name").casefold() != "amdgpu":
            continue
        labels = (_read_sysfs(entry / "power1_label"), _read_sysfs(entry / "power2_label"))
        if labels != ("slowPPT", "fastPPT"):
            continue
        current = tuple(
            _bounded_micro_watts(_read_sysfs(entry / f"power{index}_cap")) for index in (1, 2)
        )
        maximum = tuple(
            _bounded_micro_watts(_read_sysfs(entry / f"power{index}_cap_max")) for index in (1, 2)
        )
        default = tuple(
            _bounded_micro_watts(_read_sysfs(entry / f"power{index}_cap_default"))
            for index in (1, 2)
        )
        if any(value is None for value in (*current, *maximum, *default)):
            continue
        current_values = tuple(int(value) for value in current if value is not None)
        maximum_values = tuple(int(value) for value in maximum if value is not None)
        default_values = tuple(int(value) for value in default if value is not None)
        max_watts = min(30, *(value // 1_000_000 for value in maximum_values))
        return {
            "available": max_watts >= 3,
            "driver": "amdgpu",
            "minWatts": 3,
            "maxWatts": max_watts,
            "currentWatts": (
                current_values[0] / 1_000_000 if len(set(current_values)) == 1 else None
            ),
            "defaultWatts": min(default_values) / 1_000_000,
            "railsConverged": len(set(current_values)) == 1,
        }
    return {"available": False}


def _gpu_clock_capability(sys_root: Path) -> dict[str, Any]:
    drm = sys_root / "class/drm"
    try:
        cards = sorted(drm.glob("card[0-9]*"), key=lambda path: path.name)
    except OSError:
        cards = []
    for card in cards:
        content = _read_sysfs(card / "device/pp_od_clk_voltage")
        match = re.search(r"SCLK:\s*(\d+)Mhz\s+(\d+)Mhz", content)
        if match is None:
            continue
        minimum, maximum = (int(value) for value in match.groups())
        if 100 <= minimum <= maximum <= 5000:
            return {
                "available": True,
                "driver": "amdgpu",
                "minMhz": minimum,
                "maxMhz": maximum,
                "manualWriteEnabled": False,
            }
    return {"available": False}


def _hardware_capabilities(sys_root: Path) -> dict[str, Any]:
    return {
        "tdp": _tdp_capability(sys_root),
        "gpuClock": _gpu_clock_capability(sys_root),
    }


Authorizer = Callable[[str, str], bool]


def _allow_all(_action: str, _caller: str) -> bool:
    return True


class AdminHelper:
    def __init__(
        self,
        effector: Effector,
        *,
        authorizer: Authorizer = _allow_all,
        audit_path: Path | None = None,
    ) -> None:
        self._effector = effector
        self._authorizer = authorizer
        self._audit_path = audit_path

    def handle(self, request: Request) -> Response:
        if request.protocol_version != PROTOCOL_VERSION:
            return self._deny(
                request,
                "E-PRIV-PROTO-MISMATCH",
                f"protocolo {request.protocol_version} != {PROTOCOL_VERSION}",
            )

        spec = ACTIONS.get(request.action)
        if spec is None:
            return self._deny(request, "E-PRIV-DENIED", "ação fora da allowlist")

        extra = set(request.params) - spec.allowed_keys
        if extra:
            return self._deny(
                request, "E-PRIV-DENIED", f"parâmetros não permitidos: {sorted(extra)}"
            )

        try:
            spec.validate(request.params)
        except ParamError as exc:
            return self._deny(request, "E-PRIV-DENIED", str(exc))

        if not self._authorizer(request.action, request.caller):
            return self._deny(request, "E-PRIV-DENIED", "autorização negada (polkit)")

        try:
            result = self._effector.apply(request.action, request.params)
        except SteamZeroError as exc:
            self._audit(request, "denied", exc.code)
            return Response(ok=False, error=build_error(exc.code, detail=exc.detail))
        except Exception as exc:  # falha de execução privilegiada
            self._audit(request, "error", str(exc))
            return Response(ok=False, error=build_error("E-INTERNAL-UNEXPECTED", detail=str(exc)))

        self._audit(request, "allowed", "ok")
        return Response(ok=True, result=result)

    def _deny(self, request: Request, code: str, reason: str) -> Response:
        self._audit(request, "denied", reason)
        return Response(ok=False, error=build_error(code, detail=reason))

    def _audit(self, request: Request, outcome: str, reason: str) -> None:
        if self._audit_path is None:
            return
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "caller": request.caller,
            "action": request.action,
            "params": request.params,  # só ints/enums/uuid — sem segredos (SR-13)
            "outcome": outcome,
            "reason": reason,
        }
        with fs.AppendWriter(self._audit_path) as writer:
            writer.write_line(json.dumps(record, ensure_ascii=False, sort_keys=True), fsync=True)


def _response_json(response: Response) -> str:
    return json.dumps(
        {"ok": response.ok, "result": response.result, "error": response.error},
        ensure_ascii=False,
        sort_keys=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Helper privilegiado allowlisted do SteamZero")
    parser.add_argument("--health", action="store_true")
    args = parser.parse_args(argv)
    if not args.health:
        parser.error("somente --health está publicado neste incremento")
    if os.geteuid() != 0:
        response = Response(
            ok=False,
            error=build_error("E-PRIV-DENIED", detail="helper precisa ser ativado pelo Polkit"),
        )
    else:
        caller_uid = os.environ.get("PKEXEC_UID", "0")
        caller = f"uid:{caller_uid}" if caller_uid.isdecimal() else "uid:unknown"
        helper = AdminHelper(HostEffector(), audit_path=Path("/var/log/steamzero-admin.log"))
        response = helper.handle(Request(action="health", params={}, caller=caller))
    sys.stdout.write(_response_json(response) + "\n")
    return 0 if response.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
