# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero.core import transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain.switch_roots import SwitchRootManager, validate_rom_root


def test_audit_classifies_content_without_following_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "roms"
    root.mkdir()
    (root / "Base [0100ABCDEF123000].nsp").write_bytes(b"base")
    (root / "Update [0100ABCDEF123800].nsp").write_bytes(b"update")
    (root / "DLC [0100ABCDEF124001].nsp").write_bytes(b"dlc")
    (root / "Base copy.nsp").write_bytes(b"base")
    (root / "broken.nsp").write_bytes(b"")
    (root / "archive.zip").write_bytes(b"archive")
    (root / "notes.txt").write_text("notes", encoding="utf-8")
    outside = tmp_path / "outside.nsp"
    outside.write_bytes(b"outside")
    (root / "linked.nsp").symlink_to(outside)

    audit = SwitchRootManager(root).audit()

    assert audit["counts"] == {
        "base": 1,
        "update": 1,
        "dlc": 1,
        "duplicate": 1,
        "incompatible": 1,
        "corrupted": 1,
        "unknown": 1,
    }
    assert audit["errors"] == [
        {"code": "E-CONTENT-UNSAFE-PATH", "entry": "linked.nsp"}
    ]


def test_quarantine_has_manifest_hashes_and_byte_identical_rollback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = tmp_path / "roms"
    root.mkdir()
    duplicate = root / "duplicate.nsp"
    (root / "base.nsp").write_bytes(b"same")
    duplicate.write_bytes(b"same")
    manager = SwitchRootManager(root)
    audit = manager.audit()

    plan, quarantine_id = manager.plan_quarantine(audit, ["duplicate.nsp"])
    applied = transaction.apply(plan.plan_id, plan.confirm_token)
    quarantine = root / ".steamzero-quarantine" / quarantine_id
    manifest = json.loads((quarantine / "manifest.json").read_text(encoding="utf-8"))

    assert not duplicate.exists()
    assert (quarantine / "duplicate.nsp").read_bytes() == b"same"
    assert manifest["operationId"] == quarantine_id
    assert manifest["entries"][0]["sha256"]
    transaction.rollback(applied.operation_id, reason="test")
    assert duplicate.read_bytes() == b"same"
    assert not (quarantine / "manifest.json").exists()
    assert not (quarantine / "duplicate.nsp").exists()


def test_quarantine_refuses_traversal_unapproved_and_changed_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = tmp_path / "roms"
    root.mkdir()
    unknown = root / "unknown.bin"
    unknown.write_bytes(b"before")
    manager = SwitchRootManager(root)
    audit = manager.audit()

    with pytest.raises(SteamZeroError) as traversal:
        manager.plan_quarantine(audit, ["../outside.bin"])
    assert traversal.value.code == "E-CONTENT-UNSAFE-PATH"
    with pytest.raises(SteamZeroError) as playable:
        manager.plan_quarantine(audit, ["missing.bin"])
    assert playable.value.code == "E-CONTENT-UNSAFE-PATH"

    plan, _quarantine_id = manager.plan_quarantine(audit, ["unknown.bin"])
    unknown.write_bytes(b"after")
    with pytest.raises(SteamZeroError) as stale:
        transaction.apply(plan.plan_id, plan.confirm_token)
    assert stale.value.code == "E-TX-STALE-PLAN"
    assert unknown.read_bytes() == b"after"


def test_validate_root_rejects_symlink_special_and_managed_directories(tmp_path: Path) -> None:
    root = tmp_path / "roms"
    root.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(root, target_is_directory=True)
    firmware = tmp_path / "Firmware"
    firmware.mkdir()
    managed = tmp_path / "managed"
    cache = managed / "cache"
    cache.mkdir(parents=True)

    assert validate_rom_root(root) == root
    for candidate, managed_roots in (
        (linked, ()),
        (firmware, ()),
        (cache, (managed,)),
    ):
        with pytest.raises(SteamZeroError) as exc:
            validate_rom_root(candidate, managed_roots=managed_roots)
        assert exc.value.code == "E-CONTENT-UNSAFE-PATH"
