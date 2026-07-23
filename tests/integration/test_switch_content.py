# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.core import fs
from steamzero.core.errors import SteamZeroError
from steamzero.domain.switch_content import ContentRecord, SwitchContentManager


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


def test_remove_keeps_shared_blob_until_last_catalog_record(
    env: tuple[SwitchContentManager, Path],
) -> None:
    manager, root = env
    source = root / "owned-content.nsp"
    source.write_bytes(b"same-owned-content")
    first = manager.plan_import(
        source, kind="update", title_id="0100000000010000", version="1.0.0"
    )
    assert first.plan is not None
    manager.apply_import(first.plan.plan_id, first.plan.confirm_token)
    second = manager.plan_import(
        source, kind="dlc", title_id="0100000000010000", version="pack-a"
    )
    assert second.plan is not None
    manager.apply_import(second.plan.plan_id, second.plan.confirm_token)

    remove_first = manager.plan_remove(first.record.record_key)
    manager.apply_remove(remove_first.plan_id, remove_first.confirm_token)
    assert first.record.blob.read_bytes() == b"same-owned-content"
    assert [record.record_key for record in manager.list_records()] == [
        second.record.record_key
    ]

    remove_second = manager.plan_remove(second.record.record_key)
    manager.apply_remove(remove_second.plan_id, remove_second.confirm_token)
    assert not first.record.blob.exists()
    assert manager.list_records() == []


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
    applied = SwitchContentManager.apply_shader_invalidation(plan.plan_id, plan.confirm_token)
    invalidated = cache / ".invalidated" / "0100000000010000" / "driver-1_emu-2" / "pipeline.bin"
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
        manager.plan_import(linked, kind="mod")
    with pytest.raises(SteamZeroError):
        SwitchContentManager.plan_migrate_saves(root, root / "target", {"../real.nsp": "x"})


def _import(
    manager: SwitchContentManager,
    source: Path,
    *,
    kind: str,
    title_id: str,
    version: str,
) -> ContentRecord:
    decision = manager.plan_import(source, kind=kind, title_id=title_id, version=version)
    assert decision.plan is not None
    manager.apply_import(decision.plan.plan_id, decision.plan.confirm_token)
    return decision.record


def test_index_survives_restart_and_update_activation_is_exclusive(
    env: tuple[SwitchContentManager, Path],
) -> None:
    manager, root = env
    first_file = root / "update-1.nsp"
    second_file = root / "update-2.nsp"
    first_file.write_bytes(b"update-one")
    second_file.write_bytes(b"update-two")
    title_id = "0100000000010000"
    first = _import(manager, first_file, kind="update", title_id=title_id, version="1.1.0")
    second = _import(manager, second_file, kind="update", title_id=title_id, version="1.2.0")

    restarted = SwitchContentManager(root / "shared")
    records = restarted.list_records(title_id=title_id, kind="update")
    assert [record.version for record in records] == ["1.1.0", "1.2.0"]
    plan = restarted.plan_set_active(first.record_key, active=True)
    restarted.apply_state(plan.plan_id, plan.confirm_token)
    plan = restarted.plan_set_active(second.record_key, active=True)
    restarted.apply_state(plan.plan_id, plan.confirm_token)

    states = {record.version: record.state for record in restarted.list_records(kind="update")}
    assert states == {"1.1.0": "inactive", "1.2.0": "active"}


def test_dlc_can_be_enabled_and_disabled_independently(
    env: tuple[SwitchContentManager, Path],
) -> None:
    manager, root = env
    dlc_file = root / "dlc.nsp"
    dlc_file.write_bytes(b"dlc")
    record = _import(
        manager,
        dlc_file,
        kind="dlc",
        title_id="0100000000010000",
        version="pack-a",
    )

    enable = manager.plan_set_active(record.record_key, active=True)
    manager.apply_state(enable.plan_id, enable.confirm_token)
    assert manager.list_records(kind="dlc")[0].state == "active"
    disable = manager.plan_set_active(record.record_key, active=False)
    manager.apply_state(disable.plan_id, disable.confirm_token)
    assert manager.list_records(kind="dlc")[0].state == "inactive"


def test_update_and_dlc_require_title_id(
    env: tuple[SwitchContentManager, Path],
) -> None:
    manager, root = env
    source = root / "content.nsp"
    source.write_bytes(b"content")

    for kind in ("update", "dlc"):
        with pytest.raises(SteamZeroError) as exc:
            manager.plan_import(source, kind=kind)
        assert exc.value.code == "E-API-SCHEMA"


def test_index_recovery_marks_missing_blob_unavailable(
    env: tuple[SwitchContentManager, Path],
) -> None:
    manager, root = env
    source = root / "update.nsp"
    source.write_bytes(b"update")
    record = _import(
        manager,
        source,
        kind="update",
        title_id="0100000000010000",
        version="1.0.0",
    )
    record.blob.unlink()

    report = manager.integrity_report()
    assert report["state"] == "attention"
    plan = manager.plan_recover_index()
    manager.apply_recovery(plan.plan_id, plan.confirm_token)

    assert manager.list_records(kind="update")[0].state == "unavailable"
    with pytest.raises(SteamZeroError) as exc:
        manager.plan_set_active(record.record_key, active=True)
    assert exc.value.code == "E-CONTENT-INCOMPLETE"


@pytest.mark.parametrize("fingerprint", [".", ".."])
def test_shader_fingerprint_rejects_dot_entries(
    env: tuple[SwitchContentManager, Path], fingerprint: str
) -> None:
    _manager, root = env
    cache = root / "cache"
    cache.mkdir()
    (cache / "shader.bin").write_bytes(b"shader")

    with pytest.raises(SteamZeroError):
        SwitchContentManager.plan_invalidate_shader_cache(
            cache,
            ["shader.bin"],
            title_id="0100000000010000",
            compatibility_fingerprint=fingerprint,
        )
