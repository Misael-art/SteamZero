# SPDX-License-Identifier: GPL-3.0-or-later
"""Efeito transacional de clock SCLK sobre interfaces AMDGPU descobertas."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from steamzero.core import fs, ids
from steamzero.core.errors import SteamZeroError
from steamzero.privileged.host_effects import SysfsWriter, _write_sysfs

GpuCommandWriter = Callable[[Path, bytes], None]

_CLOCK_RE = re.compile(
    r"OD_SCLK:\s*\n\s*0:\s*(\d+)Mhz\s*\n\s*1:\s*(\d+)Mhz",
    re.MULTILINE,
)
_RANGE_RE = re.compile(r"OD_RANGE:.*?SCLK:\s*(\d+)Mhz\s+(\d+)Mhz", re.DOTALL)
_PERFORMANCE_LEVELS = frozenset(
    {
        "auto",
        "low",
        "high",
        "manual",
        "profile_standard",
        "profile_min_sclk",
        "profile_min_mclk",
        "profile_peak",
    }
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read_text(path: Path, *, detail: str) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="strict").strip("\x00\n")
    except (OSError, UnicodeError) as exc:
        raise SteamZeroError("E-PRIV-DENIED", detail=detail) from exc


def _clock_state(path: Path) -> tuple[int, int, int, int]:
    content = _read_text(path, detail="interface de clock GPU ilegível")
    clocks = _CLOCK_RE.search(content)
    limits = _RANGE_RE.search(content)
    if clocks is None or limits is None:
        raise SteamZeroError("E-PRIV-DENIED", detail="estado OD_SCLK AMDGPU incompleto")
    minimum, maximum, lower, upper = (int(value) for value in (*clocks.groups(), *limits.groups()))
    if not 100 <= lower <= minimum <= maximum <= upper <= 5000:
        raise SteamZeroError("E-PRIV-DENIED", detail="estado OD_SCLK AMDGPU fora dos limites")
    return minimum, maximum, lower, upper


def _performance_level(path: Path) -> str:
    level = _read_text(path, detail="nível de desempenho AMDGPU ilegível")
    if level not in _PERFORMANCE_LEVELS:
        raise SteamZeroError("E-PRIV-DENIED", detail="nível de desempenho AMDGPU desconhecido")
    return level


class GpuClockTransactionEngine:
    """Aplica SCLK fixo com snapshot, verify, rollback e recovery pós-interrupção."""

    def __init__(
        self,
        *,
        sys_root: Path = Path("/sys"),
        state_root: Path = Path("/var/lib/steamzero/admin/gpu-clock"),
        value_writer: SysfsWriter = _write_sysfs,
        command_writer: GpuCommandWriter = _write_sysfs,
    ) -> None:
        self._sys = sys_root
        self._state = state_root
        self._value_writer = value_writer
        self._command_writer = command_writer

    def apply(self, mhz: int) -> dict[str, Any]:
        if self._pending():
            raise SteamZeroError(
                "E-TX-LOCKED",
                detail="uma alteração de clock GPU interrompida precisa de recovery",
            )
        clock_path, level_path = self._interface()
        before_min, before_max, lower, upper = _clock_state(clock_path)
        if not lower <= mhz <= upper:
            raise SteamZeroError(
                "E-PRIV-DENIED",
                detail=f"clock GPU fora da capability observada: {lower}..{upper} MHz",
            )
        operation_id = ids.new_ulid()
        journal: dict[str, Any] = {
            "schemaVersion": 1,
            "operationId": operation_id,
            "state": "pending",
            "createdAt": _now(),
            "beforeMhz": [before_min, before_max],
            "beforePerformanceLevel": _performance_level(level_path),
            "desiredMhz": mhz,
        }
        self._save(journal)
        try:
            self._set_clock(clock_path, level_path, mhz, mhz)
            self._verify(clock_path, level_path, mhz, mhz, "manual")
        except Exception as exc:
            try:
                self._restore(journal)
            except Exception as rollback_exc:
                raise SteamZeroError(
                    "E-TX-ROLLBACK-FAILED",
                    detail="clock GPU não pôde ser restaurado após falha de apply",
                    operation_id=operation_id,
                ) from rollback_exc
            raise SteamZeroError(
                "E-TX-VERIFY-FAILED",
                detail="clock GPU não convergiu; estado anterior restaurado",
                operation_id=operation_id,
            ) from exc
        journal["state"] = "applied"
        journal["finishedAt"] = _now()
        self._save(journal)
        return {
            "operationId": operation_id,
            "state": "applied",
            "mhz": mhz,
            "rollbackAvailable": True,
        }

    def rollback(self, operation_id: str) -> dict[str, Any]:
        journal = self._load(operation_id)
        if journal["state"] == "rolled-back":
            return {"operationId": operation_id, "state": "noop"}
        if journal["state"] not in {"pending", "applied", "rollback-failed"}:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="journal de clock não restaurável")
        self._restore(journal)
        return {"operationId": operation_id, "state": "rolled-back"}

    def recover(self) -> dict[str, Any]:
        recovered: list[str] = []
        for journal in self._journals():
            if journal.get("state") in {"pending", "rollback-failed"}:
                self._restore(journal)
                recovered.append(str(journal["operationId"]))
        return {"state": "recovered" if recovered else "noop", "operations": recovered}

    def _restore(self, journal: dict[str, Any]) -> None:
        clock_path, level_path = self._interface()
        before = journal.get("beforeMhz")
        level = journal.get("beforePerformanceLevel")
        if (
            not isinstance(before, list)
            or len(before) != 2
            or not isinstance(level, str)
            or level not in _PERFORMANCE_LEVELS
        ):
            raise SteamZeroError("E-STATE-INTEGRITY", detail="snapshot de clock GPU inválido")
        minimum, maximum = int(before[0]), int(before[1])
        try:
            self._set_clock(clock_path, level_path, minimum, maximum)
            self._value_writer(level_path, level.encode("ascii"))
            self._verify(clock_path, level_path, minimum, maximum, level)
        except Exception as exc:
            journal["state"] = "rollback-failed"
            journal["finishedAt"] = _now()
            self._save(journal)
            raise SteamZeroError(
                "E-TX-ROLLBACK-FAILED",
                detail="snapshot de clock GPU não convergiu",
                operation_id=str(journal.get("operationId") or ""),
            ) from exc
        journal["state"] = "rolled-back"
        journal["finishedAt"] = _now()
        self._save(journal)

    def _interface(self) -> tuple[Path, Path]:
        drm = self._sys / "class/drm"
        try:
            cards = sorted(drm.glob("card[0-9]*"), key=lambda path: path.name)
        except OSError:
            cards = []
        for card in cards:
            clock_path = card / "device/pp_od_clk_voltage"
            level_path = card / "device/power_dpm_force_performance_level"
            try:
                _clock_state(clock_path)
                _performance_level(level_path)
            except SteamZeroError:
                continue
            return clock_path, level_path
        raise SteamZeroError("E-PRIV-DENIED", detail="interface AMDGPU OD_SCLK não encontrada")

    def _set_clock(self, clock: Path, level: Path, minimum: int, maximum: int) -> None:
        self._value_writer(level, b"manual")
        for command in (f"s 0 {minimum}", f"s 1 {maximum}", "c"):
            self._command_writer(clock, command.encode("ascii"))

    @staticmethod
    def _verify(clock: Path, level: Path, minimum: int, maximum: int, mode: str) -> None:
        current_min, current_max, _lower, _upper = _clock_state(clock)
        if (current_min, current_max) != (minimum, maximum):
            raise SteamZeroError("E-TX-VERIFY-FAILED", detail="OD_SCLK divergiu")
        if _performance_level(level) != mode:
            raise SteamZeroError("E-TX-VERIFY-FAILED", detail="modo AMDGPU divergiu")

    def _path(self, operation_id: str) -> Path:
        if not ids.is_ulid(operation_id):
            raise SteamZeroError("E-API-SCHEMA", detail="operationId de clock GPU inválido")
        return self._state / f"{operation_id}.json"

    def _save(self, journal: dict[str, Any]) -> None:
        fs.ensure_dir(self._state, mode=0o700)
        fs.write_atomic_text(
            self._path(str(journal["operationId"])),
            json.dumps(journal, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            mode=0o600,
        )

    def _load(self, operation_id: str) -> dict[str, Any]:
        path = self._path(operation_id)
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024:
                raise OSError("journal inseguro")
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SteamZeroError(
                "E-STATE-INTEGRITY", detail="journal de clock GPU ausente ou inválido"
            ) from exc
        if not isinstance(payload, dict) or payload.get("operationId") != operation_id:
            raise SteamZeroError(
                "E-STATE-INTEGRITY", detail="identidade do journal de clock divergiu"
            )
        return payload

    def _journals(self) -> list[dict[str, Any]]:
        try:
            paths = sorted(self._state.glob("*.json"))
        except OSError:
            return []
        return [self._load(path.stem) for path in paths if ids.is_ulid(path.stem)]

    def _pending(self) -> bool:
        return any(row.get("state") in {"pending", "rollback-failed"} for row in self._journals())
