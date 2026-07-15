# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do Cloud Sync (F-SV-03, J6, AC-SV-01): fila offline + conflito preservador."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from steamzero.core import fs, ids, state
from steamzero.domain.saves import SavesStore
from steamzero.domain.sync import SyncManager


class FakeCloudPort:
    def __init__(self, *, available: bool = True, divergent: bytes | None = None) -> None:
        self.is_available = available
        self.divergent = divergent
        self.uploads: list[str] = []

    def available(self) -> bool:
        return self.is_available

    def upload(self, digest: str, data: bytes) -> str:
        self.uploads.append(digest)
        return f"remote/{digest}"

    def fetch_divergent(self, game_id: str, local_digest: str) -> bytes | None:
        return self.divergent


@pytest.fixture
def env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[tuple[state.StateStore, SavesStore, str]]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    fs.ensure_state_layout()
    s = state.open_state()
    s.save_platform({"id": "psx", "name": "PSX"})
    game_id = ids.new_ulid()
    s.save_game({"id": game_id, "platform_id": "psx", "title": "Jogo", "state": "ready"})
    yield s, SavesStore(s), game_id
    s.close()


def _enqueue_one(
    store: state.StateStore, saves: SavesStore, game_id: str, cloud: FakeCloudPort, *, enabled: bool
) -> tuple[SyncManager, str]:
    entry = saves.record_save(game_id, b"progresso-local")
    mgr = SyncManager(store, saves, cloud, enabled=enabled)
    mgr.enqueue_upload(entry.id)
    return mgr, entry.id


def test_flag_off_keeps_pending(env: tuple[state.StateStore, SavesStore, str]) -> None:
    store, saves, game_id = env
    cloud = FakeCloudPort()
    mgr, _ = _enqueue_one(store, saves, game_id, cloud, enabled=False)
    result = mgr.drain()
    assert result.pending == 1
    assert cloud.uploads == []
    assert store.list_sync_queue(state="pending")[0]["state"] == "pending"


def test_offline_keeps_pending_then_drains(env: tuple[state.StateStore, SavesStore, str]) -> None:
    store, saves, game_id = env
    cloud = FakeCloudPort(available=False)
    mgr, _ = _enqueue_one(store, saves, game_id, cloud, enabled=True)
    assert mgr.drain().pending == 1  # offline
    assert cloud.uploads == []
    cloud.is_available = True  # rede volta
    result = mgr.drain()
    assert result.uploaded == 1
    assert result.pending == 0


def test_upload_when_online(env: tuple[state.StateStore, SavesStore, str]) -> None:
    store, saves, game_id = env
    cloud = FakeCloudPort()
    mgr, _ = _enqueue_one(store, saves, game_id, cloud, enabled=True)
    result = mgr.drain()
    assert result.uploaded == 1
    assert len(cloud.uploads) == 1
    assert store.list_sync_queue(state="done")


def test_conflict_preserves_both_j6(env: tuple[state.StateStore, SavesStore, str]) -> None:
    store, saves, game_id = env
    cloud = FakeCloudPort(divergent=b"progresso-nuvem-diferente")
    mgr, _ = _enqueue_one(store, saves, game_id, cloud, enabled=True)
    result = mgr.drain()
    # J6/AC-SV-01: conflito preserva ambos, marca conflicted, nunca sobrescreve
    assert result.conflicted == 1
    assert saves.has_conflict(game_id) is True
    assert cloud.uploads == []  # não sobe por cima
    contents = {saves.restore(game_id, e.timeline_seq) for e in saves.timeline(game_id)}
    assert b"progresso-local" in contents
    assert b"progresso-nuvem-diferente" in contents
    assert store.list_sync_queue(state="conflicted")
