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
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from steamzero import __version__
from steamzero.core import fs
from steamzero.core.errors import SteamZeroError, build_error
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
    """Efetor host conservador: somente health até os mutadores terem rollback."""

    def apply(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        if action == "health" and not params:
            return {
                "healthy": True,
                "version": __version__,
                "protocolVersion": PROTOCOL_VERSION,
                "effectiveUid": os.geteuid(),
                "mutationsEnabled": False,
            }
        raise SteamZeroError(
            "E-PRIV-DENIED",
            detail="efetor host ainda indisponível; nenhuma mutação foi executada",
        )


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
