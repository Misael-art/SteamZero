# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Storage Monitor (F-SD-03): volumes por UUID, FM-06.

Reconcilia os volumes reportados pela porta com o State Store. Volume conhecido
que some vira ``missing``; ao reinserir (mesmo UUID) volta a ``mounted``
automaticamente. ``resolve_write_path`` recusa escrita se o volume não estiver
montado AGORA (consulta a porta ao vivo) — garante "zero escrita no mountpoint
fantasma" (AC-SD-02, FI-07). Paths nunca absolutos no estado (STATE-MODEL §2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from steamzero.core import fs, ids
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore


@dataclass(frozen=True)
class VolumeInfo:
    uuid: str
    label: str | None
    fstype: str | None
    role: str  # internal | microsd | usb
    mountpoint: str | None  # None = não montado
    capacity: int | None = None
    free: int | None = None


class StoragePort(Protocol):
    """Capacidade de enumerar volumes por UUID (ex.: /dev/disk/by-uuid + /proc/mounts)."""

    def list_volumes(self) -> list[VolumeInfo]: ...


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class StorageMonitor:
    def __init__(self, port: StoragePort, store: StateStore) -> None:
        self._port = port
        self._store = store

    def scan(self) -> list[dict[str, object]]:
        """Reconcilia volumes vivos com o estado. Retorna os volumes persistidos."""
        live = {vi.uuid: vi for vi in self._port.list_volumes()}
        for uuid, vi in live.items():
            existing = self._store.get_volume_by_uuid(uuid)
            vol_id = existing["id"] if existing else ids.new_ulid()
            new_state = "mounted" if vi.mountpoint else "missing"
            prev_state = existing["state"] if existing else None
            self._store.save_volume(
                {
                    "id": vol_id,
                    "uuid": uuid,
                    "label": vi.label,
                    "fstype": vi.fstype,
                    "role": vi.role,
                    "state": new_state,
                    "capacity": vi.capacity,
                    "free": vi.free,
                    "last_seen": _now_iso(),
                }
            )
            if prev_state != new_state:
                self._store.append_event(
                    "entity.changed", entity=f"volume:{uuid}", payload={"state": new_state}
                )
        # volumes conhecidos ausentes na leitura viva -> missing (FM-06)
        for v in self._store.list_volumes():
            if v["uuid"] not in live and v["state"] != "missing":
                v["state"] = "missing"
                self._store.save_volume(v)
                self._store.append_event(
                    "entity.changed", entity=f"volume:{v['uuid']}", payload={"state": "missing"}
                )
        return self._store.list_volumes()

    def volume_state(self, uuid: str) -> str:
        v = self._store.get_volume_by_uuid(uuid)
        return v["state"] if v else "unknown"

    def is_available(self, uuid: str) -> bool:
        """True só se a porta reporta o volume montado AGORA (não do cache)."""
        return any(vi.uuid == uuid and vi.mountpoint for vi in self._port.list_volumes())

    def resolve_write_path(self, uuid: str, relpath: str) -> Path:
        """Path absoluto para escrita, ou E-STORAGE-MISSING se não montado agora.

        Nunca retorna caminho sob um mountpoint fantasma: valida ao vivo pela porta.
        """
        live = {vi.uuid: vi for vi in self._port.list_volumes()}
        vi = live.get(uuid)
        if vi is None or vi.mountpoint is None:
            known = self._store.get_volume_by_uuid(uuid)
            last_seen = known["last_seen"] if known else "nunca"
            raise SteamZeroError(
                "E-STORAGE-MISSING", detail=f"volume {uuid} não montado (visto: {last_seen})"
            )
        mount = Path(vi.mountpoint)
        rel = fs.validate_relative_entry(relpath)
        return fs.resolve_within(mount, mount / rel)
