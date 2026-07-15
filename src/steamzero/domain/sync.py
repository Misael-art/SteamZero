# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Cloud sync não-destrutivo com fila offline (F-SV-03, DF-4, J6, AC-SV-01).

Atrás de **feature flag** (``enabled``): desligado, tudo fica ``pending``. A fila
persiste em ``sync_queue`` (State Store); offline => permanece pending e retoma
com rede. Conflito remoto≠local => baixa a versão remota para a timeline como
versão paralela e marca ``conflicted`` — AMBOS preservados, nunca sobrescreve
(P12/AC-SV-01). O acesso à nuvem é uma **porta** injetada; o domínio não fala com
provedores diretamente (offline-first: sem I/O de rede no domínio — SYSTEM-ARCH §6).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from steamzero.core import ids
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain.saves import SavesStore


class CloudPort(Protocol):
    """Capacidade de sincronização remota (fila/rate limit aplicados pela porta)."""

    def available(self) -> bool: ...
    def upload(self, digest: str, data: bytes) -> str: ...  # retorna ref remota
    def fetch_divergent(self, game_id: str, local_digest: str) -> bytes | None: ...


@dataclass(frozen=True)
class DrainResult:
    uploaded: int
    conflicted: int
    pending: int


class SyncManager:
    def __init__(
        self, store: StateStore, saves: SavesStore, cloud: CloudPort, *, enabled: bool = False
    ) -> None:
        self._store = store
        self._saves = saves
        self._cloud = cloud
        self._enabled = enabled

    def enqueue_upload(self, save_entry_id: str) -> str:
        sync_id = ids.new_ulid()
        self._store.save_sync_entry(
            {
                "id": sync_id,
                "save_entry_id": save_entry_id,
                "direction": "upload",
                "state": "pending",
            }
        )
        return sync_id

    def drain(self) -> DrainResult:
        """Processa a fila. Offline/flag-off => tudo permanece pending."""
        uploaded = conflicted = 0
        # Recovery de crash: qualquer item que ficou in-flight volta à fila.
        for interrupted in self._store.list_sync_queue(state="in-flight"):
            self._store.set_sync_state(interrupted["id"], "pending")
        pending_rows = self._store.list_sync_queue(state="pending")
        if not self._enabled or not self._cloud.available():
            return DrainResult(0, 0, len(pending_rows))

        for row in pending_rows:
            save = self._store.get_save_entry(row["save_entry_id"])
            if save is None:
                self._store.set_sync_state(row["id"], "done")  # entrada órfã
                continue
            self._store.set_sync_state(row["id"], "in-flight")
            try:
                game_id = save["game_id"]
                local_digest = save["hash"]
                remote = self._cloud.fetch_divergent(game_id, local_digest)
                if remote is not None:
                    # DF-4/J6: baixa remoto como versão paralela; AMBOS preservados
                    local_bytes = self._saves.blob_bytes(local_digest)
                    self._saves.record_conflict(game_id, local_bytes, remote)
                    self._store.set_sync_state(row["id"], "conflicted")
                    conflicted += 1
                else:
                    self._cloud.upload(local_digest, self._saves.blob_bytes(local_digest))
                    self._store.set_sync_state(row["id"], "done")
                    uploaded += 1
            except Exception as exc:
                self._store.set_sync_state(row["id"], "pending")
                raise SteamZeroError(
                    "E-SUPPLY-REMOTE-FAILED",
                    detail="sync interrompido; item devolvido ao estado pending",
                ) from exc

        remaining = len(self._store.list_sync_queue(state="pending"))
        return DrainResult(uploaded, conflicted, remaining)
