# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Saves store + timeline (F-SV-01, AC-SV-01/03, P12).

Timeline append-only: cada save vira uma entrada com ``timeline_seq`` monotônico
por jogo; nada é sobrescrito (GC por política, nunca por overwrite). Blobs são
endereçados por conteúdo (dedupe por hash) — base do backup incremental
(BACKUP-FORMAT §3). Restauração recupera qualquer versão byte-idêntica (AC-SV-03).
Conflito de saves divergentes preserva AMBOS (AC-SV-01) — nunca auto-resolve (P12).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from steamzero.core import fs, ids, paths
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _blobs_dir() -> Path:
    return paths.saves_dir() / "blobs"


@dataclass(frozen=True)
class SaveEntry:
    id: str
    game_id: str
    kind: str
    timeline_seq: int
    hash: str
    size: int
    origin: str
    conflict_group: str | None


class SavesStore:
    def __init__(self, store: StateStore) -> None:
        self._store = store

    def _write_blob(self, content: bytes) -> str:
        digest = fs.hash_bytes(content)
        blob = _blobs_dir() / digest
        if not blob.exists():  # dedupe por conteúdo
            fs.write_atomic(blob, content)
        return digest

    def record_save(
        self,
        game_id: str,
        content: bytes,
        *,
        kind: str = "save",
        origin: str = "local",
        device_id: str | None = None,
        conflict_group: str | None = None,
    ) -> SaveEntry:
        digest = self._write_blob(content)
        seq = self._store.max_timeline_seq(game_id) + 1
        entry_id = ids.new_ulid()
        self._store.save_save_entry(
            {
                "id": entry_id,
                "game_id": game_id,
                "kind": kind,
                "timeline_seq": seq,
                "created_at": _now_iso(),
                "device_id": device_id,
                "hash": digest,
                "size": len(content),
                "origin": origin,
                "conflict_group": conflict_group,
            }
        )
        self._store.append_event("entity.changed", entity=f"save:{game_id}", payload={"seq": seq})
        return SaveEntry(entry_id, game_id, kind, seq, digest, len(content), origin, conflict_group)

    def timeline(self, game_id: str) -> list[SaveEntry]:
        return [_to_entry(r) for r in self._store.list_saves(game_id)]

    def restore(self, game_id: str, timeline_seq: int) -> bytes:
        """Retorna os bytes exatos da versão ``timeline_seq`` (byte-idêntica, AC-SV-03)."""
        match = next(
            (r for r in self._store.list_saves(game_id) if r["timeline_seq"] == timeline_seq), None
        )
        if match is None:
            raise SteamZeroError(
                "E-CONTENT-INCOMPLETE", detail=f"save seq {timeline_seq} inexistente"
            )
        digest = str(match["hash"])
        blob = _blobs_dir() / digest
        if not blob.exists() or fs.hash_file(blob) != digest:
            raise SteamZeroError(
                "E-CONTENT-INCOMPLETE", detail="blob de save ausente ou corrompido"
            )
        return blob.read_bytes()

    def record_conflict(
        self, game_id: str, local: bytes, remote: bytes, *, device_id: str | None = None
    ) -> tuple[SaveEntry, SaveEntry]:
        """Preserva AMBAS as versões divergentes num mesmo conflict_group (AC-SV-01)."""
        group = ids.new_ulid()
        a = self.record_save(
            game_id, local, origin="local", device_id=device_id, conflict_group=group
        )
        b = self.record_save(game_id, remote, origin="cloud", conflict_group=group)
        self._store.append_event("alert", entity=f"save:{game_id}", payload={"conflict": group})
        return a, b

    def has_conflict(self, game_id: str) -> bool:
        groups = [
            r["conflict_group"] for r in self._store.list_saves(game_id) if r["conflict_group"]
        ]
        return len(groups) > 0


def _to_entry(row: dict[str, Any]) -> SaveEntry:
    return SaveEntry(
        id=str(row["id"]),
        game_id=str(row["game_id"]),
        kind=str(row["kind"]),
        timeline_seq=int(row["timeline_seq"]),
        hash=str(row["hash"]),
        size=int(row["size"]),
        origin=str(row["origin"]),
        conflict_group=row["conflict_group"] or None,
    )
