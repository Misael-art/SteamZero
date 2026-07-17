# SPDX-License-Identifier: GPL-3.0-or-later
"""Efeito transacional para a allowlist mínima de sysctls de desempenho."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from steamzero.core import fs, ids
from steamzero.core.errors import SteamZeroError
from steamzero.privileged.host_effects import SysfsWriter, _write_sysfs, transaction_lock
from steamzero.privileged.protocol import ALLOWED_SYSCTL

_SYSCTL_PATHS = {
    "vm.swappiness": Path("vm/swappiness"),
    "vm.compaction_proactiveness": Path("vm/compaction_proactiveness"),
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read_value(path: Path) -> int:
    try:
        value = int(path.read_text(encoding="utf-8", errors="strict").strip("\x00\n"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise SteamZeroError("E-PRIV-DENIED", detail="interface sysctl ilegível") from exc
    if not 0 <= value <= 1_000_000:
        raise SteamZeroError("E-PRIV-DENIED", detail="valor sysctl observado fora do limite")
    return value


class SysctlTransactionEngine:
    """Captura, aplica, verifica e restaura somente chaves compiladas no binário."""

    def __init__(
        self,
        *,
        proc_sys_root: Path = Path("/proc/sys"),
        state_root: Path = Path("/var/lib/steamzero/admin/sysctl"),
        writer: SysfsWriter = _write_sysfs,
    ) -> None:
        self._proc_sys = proc_sys_root
        self._state = state_root
        self._writer = writer

    def apply(self, key: str, value: int) -> dict[str, Any]:
        with transaction_lock(self._state):
            return self._apply(key, value)

    def _apply(self, key: str, value: int) -> dict[str, Any]:
        path = self._path_for_key(key)
        lower, upper = ALLOWED_SYSCTL[key]
        if not lower <= value <= upper:
            raise SteamZeroError(
                "E-PRIV-DENIED",
                detail=f"sysctl fora do limite compilado: {lower}..{upper}",
            )
        if self._pending():
            raise SteamZeroError(
                "E-TX-LOCKED", detail="uma alteração sysctl interrompida precisa de recovery"
            )
        operation_id = ids.new_ulid()
        journal: dict[str, Any] = {
            "schemaVersion": 1,
            "operationId": operation_id,
            "state": "pending",
            "createdAt": _now(),
            "key": key,
            "beforeValue": _read_value(path),
            "desiredValue": value,
        }
        self._save(journal)
        try:
            self._write_verify(path, value)
        except Exception as exc:
            try:
                self._restore(journal)
            except Exception as rollback_exc:
                raise SteamZeroError(
                    "E-TX-ROLLBACK-FAILED",
                    detail="sysctl não pôde ser restaurado após falha de apply",
                    operation_id=operation_id,
                ) from rollback_exc
            raise SteamZeroError(
                "E-TX-VERIFY-FAILED",
                detail="sysctl não convergiu; valor anterior restaurado",
                operation_id=operation_id,
            ) from exc
        journal["state"] = "applied"
        journal["finishedAt"] = _now()
        self._save(journal)
        return {
            "operationId": operation_id,
            "state": "applied",
            "key": key,
            "value": value,
            "rollbackAvailable": True,
        }

    def rollback(self, operation_id: str) -> dict[str, Any]:
        with transaction_lock(self._state):
            journal = self._load(operation_id)
            if journal["state"] == "rolled-back":
                return {"operationId": operation_id, "state": "noop"}
            if journal["state"] not in {"pending", "applied", "rollback-failed"}:
                raise SteamZeroError("E-STATE-INTEGRITY", detail="journal sysctl não restaurável")
            self._restore(journal)
            return {"operationId": operation_id, "state": "rolled-back"}

    def recover(self) -> dict[str, Any]:
        with transaction_lock(self._state):
            recovered: list[str] = []
            for journal in self._journals():
                if journal.get("state") in {"pending", "rollback-failed"}:
                    self._restore(journal)
                    recovered.append(str(journal["operationId"]))
            return {"state": "recovered" if recovered else "noop", "operations": recovered}

    def _restore(self, journal: dict[str, Any]) -> None:
        key = journal.get("key")
        before = journal.get("beforeValue")
        if not isinstance(key, str) or key not in _SYSCTL_PATHS or not isinstance(before, int):
            raise SteamZeroError("E-STATE-INTEGRITY", detail="snapshot sysctl inválido")
        path = self._path_for_key(key)
        try:
            self._write_verify(path, before)
        except Exception as exc:
            journal["state"] = "rollback-failed"
            journal["finishedAt"] = _now()
            self._save(journal)
            raise SteamZeroError(
                "E-TX-ROLLBACK-FAILED",
                detail="snapshot sysctl não convergiu",
                operation_id=str(journal.get("operationId") or ""),
            ) from exc
        journal["state"] = "rolled-back"
        journal["finishedAt"] = _now()
        self._save(journal)

    def _path_for_key(self, key: str) -> Path:
        relative = _SYSCTL_PATHS.get(key)
        if relative is None or key not in ALLOWED_SYSCTL:
            raise SteamZeroError("E-PRIV-DENIED", detail="chave sysctl fora da allowlist")
        path = self._proc_sys / relative
        try:
            if path.is_symlink() or not path.is_file():
                raise OSError("interface sysctl insegura")
        except OSError as exc:
            raise SteamZeroError("E-PRIV-DENIED", detail="interface sysctl ausente") from exc
        return path

    def _write_verify(self, path: Path, value: int) -> None:
        self._writer(path, str(value).encode("ascii"))
        if _read_value(path) != value:
            raise SteamZeroError("E-TX-VERIFY-FAILED", detail="sysctl observado divergiu")

    def _journal_path(self, operation_id: str) -> Path:
        if not ids.is_ulid(operation_id):
            raise SteamZeroError("E-API-SCHEMA", detail="operationId sysctl inválido")
        return self._state / f"{operation_id}.json"

    def _save(self, journal: dict[str, Any]) -> None:
        fs.ensure_dir(self._state, mode=0o700)
        fs.write_atomic_text(
            self._journal_path(str(journal["operationId"])),
            json.dumps(journal, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            mode=0o600,
        )

    def _load(self, operation_id: str) -> dict[str, Any]:
        path = self._journal_path(operation_id)
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024:
                raise OSError("journal inseguro")
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SteamZeroError(
                "E-STATE-INTEGRITY", detail="journal sysctl ausente ou inválido"
            ) from exc
        if not isinstance(payload, dict) or payload.get("operationId") != operation_id:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="identidade do journal divergiu")
        return payload

    def _journals(self) -> list[dict[str, Any]]:
        try:
            paths = sorted(self._state.glob("*.json"))
        except OSError:
            return []
        return [self._load(path.stem) for path in paths if ids.is_ulid(path.stem)]

    def _pending(self) -> bool:
        return any(row.get("state") in {"pending", "rollback-failed"} for row in self._journals())
