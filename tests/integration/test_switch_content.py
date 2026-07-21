# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.core import fs
from steamzero.core.errors import SteamZeroError
from steamzero.domain.switch_content import SwitchContentManager


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[SwitchContentManager, Path]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    fs.ensure_state_layout()
    return SwitchContentManager(tmp_path / "shared"), tmp_path


def test_import_deduplicates_and_rolls_back_by_hash(
    env: tuple[SwitchContentManager, Path],
) -> None:
    manager, root = env
    source = root / "update.nsp"
    source.write_bytes(b"owned-update")

    decision = manager.plan_import(
        source, kind="update", title_id="0100000000010000", version="1.2.0"
    )
    assert decision.status == "planned" and decision.plan is not None
    with pytest.raises(SteamZeroError):
        manager.apply_import(decision.plan.plan_id, "wrong")
    applied = manager.apply_import(decision.plan.plan_id, decision.plan.confirm_token)
    assert decision.record.blob.read_bytes() == b"owned-update"
    duplicate = manager.plan_import(
        source, kind="update", title_id="0100000000010000", version="1.2.0"
    )
    assert duplicate.status == "duplicate" and duplicate.plan is None
    manager.rollback(applied.operation_id)
    assert not decision.record.blob.exists()
    assert source.read_bytes() == b"owned-update"


def test_shared_blob_links_to_consumer_transactionally(
    env: tuple[SwitchContentManager, Path],
) -> None:
    manager, root = env
    source = root / "dlc.nsp"
    source.write_bytes(b"owned-dlc")
    decision = manager.plan_import(source, kind="dlc", title_id="0100000000010000")
    assert decision.plan is not None
    manager.apply_import(decision.plan.plan_id, decision.plan.confirm_token)
    consumer = root / "eden"
    consumer.mkdir()
    plan = manager.plan_link(
        decision.record, consumer_root=consumer, consumer_relpath="contents/dlc.nsp"
    )
    applied = manager.apply_link(plan.plan_id, plan.confirm_token)
    linked = consumer / "contents" / "dlc.nsp"
    assert linked.is_symlink() and linked.read_bytes() == b"owned-dlc"
    manager.rollback(applied.operation_id)
    assert not linked.exists() and not linked.is_symlink()


def test_shader_invalidation_is_reversible(env: tuple[SwitchContentManager, Path]) -> None:
    _manager, root = env
    cache = root / "cache"
    cache.mkdir()
    shader = cache / "pipeline.bin"
    shader.write_bytes(b"shader")
    plan = SwitchContentManager.plan_invalidate_shader_cache(
        cache,
        ["pipeline.bin"],
        title_id="0100000000010000",
        compatibility_fingerprint="driver-1_emu-2",
    )
    applied = SwitchContentManager.apply_shader_invalidation(
        plan.plan_id, plan.confirm_token
    )
    invalidated = (
        cache
        / ".invalidated"
        / "0100000000010000"
        / "driver-1_emu-2"
        / "pipeline.bin"
    )
    assert invalidated.read_bytes() == b"shader"
    SwitchContentManager.rollback(applied.operation_id)
    assert shader.read_bytes() == b"shader"


def test_save_migration_preserves_source_and_rolls_back_target(
    env: tuple[SwitchContentManager, Path],
) -> None:
    _manager, root = env
    source_root = root / "eden-save"
    target_root = root / "ryujinx-save"
    source_root.mkdir()
    target_root.mkdir()
    source = source_root / "slot0.dat"
    source.write_bytes(b"save")
    plan = SwitchContentManager.plan_migrate_saves(
        source_root, target_root, {"slot0.dat": "user/save.dat"}
    )
    applied = SwitchContentManager.apply_save_migration(plan.plan_id, plan.confirm_token)
    target = target_root / "user" / "save.dat"
    assert source.read_bytes() == target.read_bytes() == b"save"
    SwitchContentManager.rollback(applied.operation_id)
    assert source.exists() and not target.exists()


def test_import_and_migration_reject_symlink_and_traversal(
    env: tuple[SwitchContentManager, Path],
) -> None:
    manager, root = env
    source = root / "real.nsp"
    source.write_bytes(b"owned")
    linked = root / "linked.nsp"
    linked.symlink_to(source)
    with pytest.raises(SteamZeroError):
        manager.plan_import(linked, kind="update")
    with pytest.raises(SteamZeroError):
        SwitchContentManager.plan_migrate_saves(root, root / "target", {"../real.nsp": "x"})
