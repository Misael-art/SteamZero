# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do Saves timeline (F-SV-01, AC-SV-01/03, P12)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from steamzero.core import fs, ids, paths, state
from steamzero.core.errors import SteamZeroError
from steamzero.domain.saves import SavesStore


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[tuple[state.StateStore, str]]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    fs.ensure_state_layout()
    s = state.open_state()
    s.save_platform({"id": "psx", "name": "PSX"})
    game_id = ids.new_ulid()
    s.save_game({"id": game_id, "platform_id": "psx", "title": "Jogo", "state": "ready"})
    yield s, game_id
    s.close()


def test_timeline_appends_and_restores_byte_identical(env: tuple[state.StateStore, str]) -> None:
    store, game_id = env
    saves = SavesStore(store)
    e1 = saves.record_save(game_id, b"progresso-v1")
    e2 = saves.record_save(game_id, b"progresso-v2")
    assert (e1.timeline_seq, e2.timeline_seq) == (1, 2)
    # AC-SV-03: qualquer versão recuperada byte-idêntica
    assert saves.restore(game_id, 1) == b"progresso-v1"
    assert saves.restore(game_id, 2) == b"progresso-v2"
    assert len(saves.timeline(game_id)) == 2


def test_dedupe_by_content(env: tuple[state.StateStore, str]) -> None:
    store, game_id = env
    saves = SavesStore(store)
    saves.record_save(game_id, b"igual")
    saves.record_save(game_id, b"igual")  # mesmo conteúdo
    blobs = list((paths.saves_dir() / "blobs").iterdir())
    assert len(blobs) == 1  # dedupe por hash
    assert len(saves.timeline(game_id)) == 2  # timeline ainda tem 2 entradas


def test_append_only_never_overwrites(env: tuple[state.StateStore, str]) -> None:
    store, game_id = env
    saves = SavesStore(store)
    for i in range(5):
        saves.record_save(game_id, f"v{i}".encode())
    seqs = [e.timeline_seq for e in saves.timeline(game_id)]
    assert seqs == [1, 2, 3, 4, 5]
    assert saves.restore(game_id, 1) == b"v0"  # a mais antiga ainda existe


def test_conflict_preserves_both(env: tuple[state.StateStore, str]) -> None:
    store, game_id = env
    saves = SavesStore(store)
    a, b = saves.record_conflict(game_id, b"local-progress", b"cloud-progress")
    # AC-SV-01: ambos preservados, mesmo conflict_group, nenhum sobrescrito
    assert a.conflict_group == b.conflict_group is not None
    assert saves.restore(game_id, a.timeline_seq) == b"local-progress"
    assert saves.restore(game_id, b.timeline_seq) == b"cloud-progress"
    assert saves.has_conflict(game_id) is True


def test_restore_missing_seq(env: tuple[state.StateStore, str]) -> None:
    store, game_id = env
    with pytest.raises(SteamZeroError) as ei:
        SavesStore(store).restore(game_id, 99)
    assert ei.value.code == "E-CONTENT-INCOMPLETE"


def test_restore_detects_corrupted_blob(env: tuple[state.StateStore, str]) -> None:
    store, game_id = env
    saves = SavesStore(store)
    entry = saves.record_save(game_id, b"conteudo")
    # corrompe o blob
    blob = paths.saves_dir() / "blobs" / entry.hash
    fs.write_atomic(blob, b"ADULTERADO")
    with pytest.raises(SteamZeroError) as ei:
        saves.restore(game_id, entry.timeline_seq)
    assert ei.value.code == "E-CONTENT-INCOMPLETE"


@pytest.mark.rt
def test_rt09_restore_failure_keeps_current_save_intact(
    env: tuple[state.StateStore, str], tmp_path: Path
) -> None:
    store, game_id = env
    saves = SavesStore(store)
    old = saves.record_save(game_id, b"timeline-version")
    active_root = tmp_path / "active"
    active_root.mkdir()
    active = active_root / "game.sav"
    fs.write_atomic(active, b"current-progress")
    current_hash = fs.hash_file(active)
    plan = saves.plan_restore(game_id, old.timeline_seq, target=active, root=active_root)

    def failed_validation() -> None:
        raise RuntimeError("emulador recusou o save restaurado")

    with pytest.raises(SteamZeroError) as error:
        saves.apply_restore(plan.plan_id, plan.confirm_token, smoke=failed_validation)
    assert error.value.code == "E-TX-VERIFY-FAILED"
    assert fs.hash_file(active) == current_hash
    assert active.read_bytes() == b"current-progress"


@pytest.mark.rt
def test_rt09_restore_apply_and_manual_rollback(
    env: tuple[state.StateStore, str], tmp_path: Path
) -> None:
    store, game_id = env
    saves = SavesStore(store)
    old = saves.record_save(game_id, b"timeline-version")
    active_root = tmp_path / "active"
    active_root.mkdir()
    active = active_root / "game.sav"
    fs.write_atomic(active, b"current-progress")
    plan = saves.plan_restore(game_id, old.timeline_seq, target=active, root=active_root)
    result = saves.apply_restore(plan.plan_id, plan.confirm_token)
    assert active.read_bytes() == b"timeline-version"
    assert saves.rollback_restore(result.operation_id).status == "rolled-back"
    assert active.read_bytes() == b"current-progress"
