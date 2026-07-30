# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""M7: organização transacional scan→plan→apply→rollback da biblioteca."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from steamzero.core import fs, paths, state, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain.library import LibraryOrganizer


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[tuple[state.StateStore, Path]]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    fs.ensure_state_layout()
    root = tmp_path / "roms"
    root.mkdir()
    store = state.open_state()
    yield store, root
    store.close()


@pytest.mark.integration
@pytest.mark.rt
def test_scan_plan_apply_and_rollback_byte_identical(
    env: tuple[state.StateStore, Path],
) -> None:
    store, root = env
    source = root / "loose" / "Game.nes"
    target = root / "nes" / "Game.nes"
    fs.write_atomic(source, b"synthetic-dump")
    original_hash = fs.hash_file(source)

    organizer = LibraryOrganizer(store)
    plan = organizer.plan(root, {"loose/Game.nes": "nes/Game.nes"})
    assert plan.kind == "library.organize"
    assert plan.rollback_guarantee == "G-FULL"
    assert source.exists() and not target.exists()  # plan é read-only sobre a biblioteca
    assert "loose/Game.nes" in plan.preview and "nes/Game.nes" in plan.preview

    result = organizer.apply(plan.plan_id, plan.confirm_token)
    assert result.status == "ok"
    assert not source.exists()
    assert fs.hash_file(target) == original_hash

    rollback = organizer.rollback(result.operation_id)
    assert rollback.status == "rolled-back"
    assert fs.hash_file(source) == original_hash
    assert not target.exists()
    # RB-3: rollback repetido não muda o resultado.
    assert organizer.rollback(result.operation_id).status == "rolled-back"
    assert fs.hash_file(source) == original_hash


@pytest.mark.integration
def test_apply_requires_confirmation(env: tuple[state.StateStore, Path]) -> None:
    store, root = env
    source = root / "game.nes"
    fs.write_atomic(source, b"x")
    plan = LibraryOrganizer(store).plan(root, {"game.nes": "nes/game.nes"})
    with pytest.raises(SteamZeroError) as error:
        LibraryOrganizer.apply(plan.plan_id, "wrong-token")
    assert error.value.code == "E-TX-CONFIRM-REQUIRED"
    assert source.exists()


@pytest.mark.integration
def test_dry_run_and_expired_confirmation(env: tuple[state.StateStore, Path]) -> None:
    store, root = env
    source = root / "game.nes"
    fs.write_atomic(source, b"x")
    organizer = LibraryOrganizer(store)
    plan = organizer.plan(root, {"game.nes": "nes/game.nes"})
    assert organizer.apply(plan.plan_id, plan.confirm_token, dry_run=True).status == "dry-run"
    assert source.exists()

    expired = transaction.plan_move_files(
        {source: root / "nes" / "expired.nes"}, root=root, ttl_s=-1
    )
    with pytest.raises(SteamZeroError) as error:
        organizer.apply(expired.plan_id, expired.confirm_token)
    assert error.value.code == "E-TX-CONFIRM-REQUIRED"


@pytest.mark.integration
def test_stale_source_or_destination_blocks_without_mutation(
    env: tuple[state.StateStore, Path],
) -> None:
    store, root = env
    source = root / "game.nes"
    target = root / "nes" / "game.nes"
    fs.write_atomic(source, b"planned")
    plan = LibraryOrganizer(store).plan(root, {"game.nes": "nes/game.nes"})
    fs.write_atomic(target, b"external")
    with pytest.raises(SteamZeroError) as error:
        LibraryOrganizer.apply(plan.plan_id, plan.confirm_token)
    assert error.value.code == "E-TX-STALE-PLAN"
    assert source.read_bytes() == b"planned"
    assert target.read_bytes() == b"external"


@pytest.mark.integration
@pytest.mark.rt
def test_mid_apply_failure_rolls_back_prior_moves(
    env: tuple[state.StateStore, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    store, root = env
    first = root / "first.nes"
    second = root / "second.nes"
    fs.write_atomic(first, b"first")
    fs.write_atomic(second, b"second")
    plan = LibraryOrganizer(store).plan(
        root,
        {"first.nes": "nes/first.nes", "second.nes": "nes/second.nes"},
    )
    real_move = fs.move_file
    calls = 0

    def fail_second(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("falha sintética no segundo movimento")
        real_move(source, target)

    monkeypatch.setattr(fs, "move_file", fail_second)
    with pytest.raises(OSError, match="falha sintética"):
        LibraryOrganizer.apply(plan.plan_id, plan.confirm_token)

    assert first.read_bytes() == b"first"
    assert second.read_bytes() == b"second"
    assert not (root / "nes" / "first.nes").exists()
    assert not (root / "nes" / "second.nes").exists()


@pytest.mark.integration
def test_plan_rejects_collision_and_traversal(env: tuple[state.StateStore, Path]) -> None:
    store, root = env
    fs.write_atomic(root / "a.nes", b"a")
    fs.write_atomic(root / "occupied.nes", b"b")
    organizer = LibraryOrganizer(store)
    with pytest.raises(SteamZeroError) as collision:
        organizer.plan(root, {"a.nes": "occupied.nes"})
    assert collision.value.code == "E-TX-STALE-PLAN"
    with pytest.raises(SteamZeroError) as traversal:
        organizer.plan(root, {"a.nes": "../escape.nes"})
    assert traversal.value.code == "E-CONTENT-UNSAFE-PATH"


@pytest.mark.integration
def test_move_plan_rejects_invalid_graphs(env: tuple[state.StateStore, Path]) -> None:
    _store, root = env
    first = root / "first.nes"
    second = root / "second.nes"
    fs.write_atomic(first, b"first")
    fs.write_atomic(second, b"second")

    noop = transaction.plan_move_files({first: first}, root=root)
    assert noop.actions == []
    with pytest.raises(SteamZeroError, match="origem inválida"):
        transaction.plan_move_files({root / "missing.nes": root / "x.nes"}, root=root)
    with pytest.raises(SteamZeroError, match="mesmo destino"):
        transaction.plan_move_files({first: root / "x.nes", second: root / "x.nes"}, root=root)
    with pytest.raises(SteamZeroError, match="cadeias/ciclos"):
        transaction.plan_move_files({first: second, second: root / "third.nes"}, root=root)


@pytest.mark.integration
@pytest.mark.rt
@pytest.mark.parametrize("changed", ["backup", "source", "target"])
def test_move_rollback_refuses_changed_user_data(
    env: tuple[state.StateStore, Path], changed: str
) -> None:
    store, root = env
    source = root / "game.nes"
    target = root / "nes" / "game.nes"
    fs.write_atomic(source, b"original")
    organizer = LibraryOrganizer(store)
    plan = organizer.plan(root, {"game.nes": "nes/game.nes"})
    result = organizer.apply(plan.plan_id, plan.confirm_token)

    if changed == "backup":
        fs.write_atomic(
            paths.backup_for(result.operation_id) / plan.actions[0].action_id, b"changed"
        )
    elif changed == "source":
        fs.write_atomic(source, b"new-user-data")
    else:
        fs.write_atomic(target, b"new-user-data")

    with pytest.raises(SteamZeroError) as error:
        organizer.rollback(result.operation_id)
    assert error.value.code == "E-TX-ROLLBACK-FAILED"
    if changed == "source":
        assert source.read_bytes() == b"new-user-data"
    if changed == "target":
        assert target.read_bytes() == b"new-user-data"


@pytest.mark.integration
@pytest.mark.fi
def test_crash_after_move_recovers_original(env: tuple[state.StateStore, Path]) -> None:
    store, root = env
    source = root / "game.nes"
    target = root / "nes" / "game.nes"
    fs.write_atomic(source, b"crash-safe")
    plan = LibraryOrganizer(store).plan(root, {"game.nes": "nes/game.nes"})

    def crash(stage: str) -> None:
        if stage == "apply.activate":
            raise transaction.SimulatedKill

    transaction.set_crash_hook(crash)
    try:
        with pytest.raises(transaction.SimulatedKill):
            LibraryOrganizer.apply(plan.plan_id, plan.confirm_token)
    finally:
        transaction.set_crash_hook(None)

    operation_id = next(paths.journal_dir().glob("*.jsonl")).stem
    recovered = transaction.recover_operation(operation_id)
    assert recovered.outcome == "rolled-back"
    assert source.read_bytes() == b"crash-safe"
    assert not target.exists()
    assert not paths.staging_for(operation_id).exists()


@pytest.mark.integration
@pytest.mark.slow
def test_10k_fixture_apply_and_rollback_benchmark(env: tuple[state.StateStore, Path]) -> None:
    """M7: pipeline completo e rollback sobre 10 mil fixtures sintéticas."""
    store, root = env
    moves: dict[str, str] = {}
    for index in range(10_000):
        name = f"incoming/game-{index:05d}.nes"
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(index.to_bytes(4, "big"))
        moves[name] = f"nes/game-{index:05d}.nes"

    plan = LibraryOrganizer(store).plan(root, moves)
    result = LibraryOrganizer.apply(plan.plan_id, plan.confirm_token)
    assert result.status == "ok"
    assert sum(1 for _ in fs.iter_files(root / "nes")) == 10_000
    assert not (root / "incoming" / "game-00000.nes").exists()

    rollback = LibraryOrganizer.rollback(result.operation_id)

    assert len(plan.actions) == 10_000
    assert rollback.status == "rolled-back"
    assert sum(1 for _ in fs.iter_files(root / "incoming")) == 10_000
    assert not (root / "nes" / "game-00000.nes").exists()
    assert not paths.staging_for(result.operation_id).exists()
