# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Locks por recurso com lease + dono (SR-16, JOB-LIFECYCLE §Concorrência).

1 escrita mutável por recurso. O lock é um arquivo JSON (via core.fs) com dono
(pid, jobId), instante de aquisição e prazo do lease. Um lock cujo dono morreu
(pid inexistente) ou cujo lease expirou é considerado **órfão**: pode ser
quebrado, com registro (FI-15 — "lease expira; lock quebrado com registro; sem
deadlock"). Sem deadlock: aquisição não bloqueia — falha com E-TX-LOCKED.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from steamzero.core import fs, paths
from steamzero.core.errors import SteamZeroError

DEFAULT_LEASE_S = 300.0


def _locks_dir() -> Path:
    return paths.state_home() / "locks"


def _lock_path(resource: str) -> Path:
    safe = resource.replace("/", "__")
    return _locks_dir() / f"{safe}.lock"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # existe, mas de outro usuário
    return True


@dataclass(frozen=True)
class LockInfo:
    resource: str
    pid: int
    job_id: str | None
    acquired_at: float
    lease_seconds: float

    @property
    def expires_at(self) -> float:
        return self.acquired_at + self.lease_seconds

    def is_orphan(self, *, now: float | None = None) -> bool:
        """Órfão se o dono morreu ou o lease expirou."""
        now = time.time() if now is None else now
        return (not _pid_alive(self.pid)) or now >= self.expires_at

    def to_json(self) -> str:
        return json.dumps(
            {
                "resource": self.resource,
                "pid": self.pid,
                "jobId": self.job_id,
                "acquiredAt": self.acquired_at,
                "leaseSeconds": self.lease_seconds,
            },
            sort_keys=True,
        )

    @staticmethod
    def from_json(text: str) -> LockInfo:
        d = json.loads(text)
        return LockInfo(
            resource=d["resource"],
            pid=int(d["pid"]),
            job_id=d.get("jobId"),
            acquired_at=float(d["acquiredAt"]),
            lease_seconds=float(d["leaseSeconds"]),
        )


class ResourceLock:
    """Lock de um recurso. Use como context manager: ``with ResourceLock(r): ...``."""

    def __init__(
        self,
        resource: str,
        *,
        job_id: str | None = None,
        lease_seconds: float = DEFAULT_LEASE_S,
    ) -> None:
        self.resource = resource
        self.job_id = job_id
        self.lease_seconds = lease_seconds
        self._path = _lock_path(resource)
        self._held = False
        self._broke_orphan: LockInfo | None = None

    @property
    def broke_orphan(self) -> LockInfo | None:
        """Lock órfão que esta aquisição quebrou (para registro), se houver."""
        return self._broke_orphan

    def _read(self) -> LockInfo | None:
        if not self._path.exists():
            return None
        try:
            return LockInfo.from_json(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError, ValueError):
            return None  # lock corrompido = tratável como órfão

    def acquire(self) -> ResourceLock:
        """Adquire o lock ou levanta E-TX-LOCKED. Quebra locks órfãos com registro."""
        fs.ensure_dir(_locks_dir())
        existing = self._read()
        if existing is not None and not existing.is_orphan():
            raise SteamZeroError(
                "E-TX-LOCKED",
                detail=(
                    f"recurso {self.resource!r} em uso por pid={existing.pid} "
                    f"job={existing.job_id} há {time.time() - existing.acquired_at:.0f}s"
                ),
            )
        if existing is not None and existing.is_orphan():
            self._broke_orphan = existing
        info = LockInfo(
            resource=self.resource,
            pid=os.getpid(),
            job_id=self.job_id,
            acquired_at=time.time(),
            lease_seconds=self.lease_seconds,
        )
        fs.write_atomic_text(self._path, info.to_json())
        self._held = True
        return self

    def renew(self) -> None:
        """Renova o lease (heartbeat). Só se ainda somos o dono."""
        if not self._held:
            raise RuntimeError("renew() sem posse do lock")
        info = LockInfo(
            resource=self.resource,
            pid=os.getpid(),
            job_id=self.job_id,
            acquired_at=time.time(),
            lease_seconds=self.lease_seconds,
        )
        fs.write_atomic_text(self._path, info.to_json())

    def release(self) -> None:
        if self._held:
            fs.remove_file(self._path)
        self._held = False

    def __enter__(self) -> ResourceLock:
        return self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()
