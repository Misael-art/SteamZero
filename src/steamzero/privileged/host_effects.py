# SPDX-License-Identifier: GPL-3.0-or-later
"""Efeito TDP transacional sobre interfaces AMDGPU estritamente descobertas."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from steamzero.core import fs, ids
from steamzero.core.errors import SteamZeroError

SysfsWriter = Callable[[Path, bytes], None]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _read_int(path: Path) -> int:
    try:
        value = int(path.read_text(encoding="utf-8", errors="strict").strip("\x00\n"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise SteamZeroError("E-PRIV-DENIED", detail="interface TDP ilegível") from exc
    if not 0 <= value <= 100_000_000:
        raise SteamZeroError("E-PRIV-DENIED", detail="valor TDP fora do limite absoluto")
    return value


def _write_sysfs(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
        try:
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("escrita sysfs sem progresso")
                view = view[written:]
        finally:
            os.close(fd)
    except OSError as exc:
        raise SteamZeroError("E-PRIV-DENIED", detail="falha ao escrever interface TDP") from exc


class TdpTransactionEngine:
    """Captura, aplica, verifica e restaura as duas rails PPT como uma unidade."""

    def __init__(
        self,
        *,
        sys_root: Path = Path("/sys"),
        state_root: Path = Path("/var/lib/steamzero/admin/tdp"),
        writer: SysfsWriter = _write_sysfs,
    ) -> None:
        self._sys = sys_root
        self._state = state_root
        self._writer = writer

    def apply(self, watts: int) -> dict[str, Any]:
        if self._pending():
            raise SteamZeroError(
                "E-TX-LOCKED",
                detail="uma alteração TDP interrompida precisa de recovery",
            )
        slow, fast, maximum = self._interface()
        desired = watts * 1_000_000
        if desired < 3_000_000 or desired > maximum:
            raise SteamZeroError(
                "E-PRIV-DENIED",
                detail=f"TDP fora da capability observada: 3..{maximum // 1_000_000} W",
            )
        operation_id = ids.new_ulid()
        journal: dict[str, Any] = {
            "schemaVersion": 1,
            "operationId": operation_id,
            "state": "pending",
            "createdAt": _now(),
            "beforeMicroWatts": [_read_int(slow), _read_int(fast)],
            "desiredMicroWatts": desired,
        }
        self._save(journal)
        try:
            self._write_pair(slow, fast, desired, desired)
            self._verify(slow, fast, desired, desired)
        except Exception as exc:
            try:
                before = journal["beforeMicroWatts"]
                self._write_pair(slow, fast, int(before[0]), int(before[1]))
                self._verify(slow, fast, int(before[0]), int(before[1]))
                journal["state"] = "rolled-back"
                journal["finishedAt"] = _now()
                self._save(journal)
            except Exception as rollback_exc:
                journal["state"] = "rollback-failed"
                journal["finishedAt"] = _now()
                self._save(journal)
                raise SteamZeroError(
                    "E-TX-ROLLBACK-FAILED",
                    detail="TDP não pôde ser restaurado após falha de apply",
                    operation_id=operation_id,
                ) from rollback_exc
            raise SteamZeroError(
                "E-TX-VERIFY-FAILED",
                detail="TDP não convergiu; valores anteriores restaurados",
                operation_id=operation_id,
            ) from exc
        journal["state"] = "applied"
        journal["finishedAt"] = _now()
        self._save(journal)
        return {
            "operationId": operation_id,
            "state": "applied",
            "watts": watts,
            "rollbackAvailable": True,
        }

    def rollback(self, operation_id: str) -> dict[str, Any]:
        journal = self._load(operation_id)
        if journal["state"] == "rolled-back":
            return {"operationId": operation_id, "state": "noop"}
        if journal["state"] not in {"pending", "applied", "rollback-failed"}:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="journal TDP não restaurável")
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
        slow, fast, _maximum = self._interface()
        before = journal.get("beforeMicroWatts")
        if not isinstance(before, list) or len(before) != 2:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="snapshot TDP inválido")
        first, second = (int(before[0]), int(before[1]))
        try:
            self._write_pair(slow, fast, first, second)
            self._verify(slow, fast, first, second)
        except Exception as exc:
            journal["state"] = "rollback-failed"
            journal["finishedAt"] = _now()
            self._save(journal)
            raise SteamZeroError(
                "E-TX-ROLLBACK-FAILED",
                detail="snapshot TDP não convergiu",
                operation_id=str(journal.get("operationId") or ""),
            ) from exc
        journal["state"] = "rolled-back"
        journal["finishedAt"] = _now()
        self._save(journal)

    def _interface(self) -> tuple[Path, Path, int]:
        base = self._sys / "class/hwmon"
        try:
            entries = sorted(base.iterdir(), key=lambda path: path.name)
        except OSError:
            entries = []
        for entry in entries:
            try:
                name = (entry / "name").read_text(encoding="utf-8").strip()
                labels = tuple(
                    (entry / f"power{index}_label").read_text(encoding="utf-8").strip()
                    for index in (1, 2)
                )
            except OSError:
                continue
            if name != "amdgpu" or labels != ("slowPPT", "fastPPT"):
                continue
            slow = entry / "power1_cap"
            fast = entry / "power2_cap"
            maximum = min(
                _read_int(entry / "power1_cap_max"),
                _read_int(entry / "power2_cap_max"),
                30_000_000,
            )
            return slow, fast, maximum
        raise SteamZeroError("E-PRIV-DENIED", detail="interface AMDGPU PPT não encontrada")

    def _write_pair(self, slow: Path, fast: Path, first: int, second: int) -> None:
        self._writer(slow, str(first).encode("ascii"))
        self._writer(fast, str(second).encode("ascii"))

    @staticmethod
    def _verify(slow: Path, fast: Path, first: int, second: int) -> None:
        if (_read_int(slow), _read_int(fast)) != (first, second):
            raise SteamZeroError("E-TX-VERIFY-FAILED", detail="rails PPT divergiram")

    def _path(self, operation_id: str) -> Path:
        if not ids.is_ulid(operation_id):
            raise SteamZeroError("E-API-SCHEMA", detail="operationId TDP inválido")
        return self._state / f"{operation_id}.json"

    def _save(self, journal: dict[str, Any]) -> None:
        operation_id = str(journal["operationId"])
        fs.ensure_dir(self._state, mode=0o700)
        fs.write_atomic_text(
            self._path(operation_id),
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
                "E-STATE-INTEGRITY", detail="journal TDP ausente ou inválido"
            ) from exc
        if not isinstance(payload, dict) or payload.get("operationId") != operation_id:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="identidade do journal TDP divergiu")
        return payload

    def _journals(self) -> list[dict[str, Any]]:
        try:
            paths = sorted(self._state.glob("*.json"))
        except OSError:
            return []
        journals: list[dict[str, Any]] = []
        for path in paths:
            operation_id = path.stem
            if ids.is_ulid(operation_id):
                journals.append(self._load(operation_id))
        return journals

    def _pending(self) -> bool:
        return any(row.get("state") in {"pending", "rollback-failed"} for row in self._journals())
