# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Gestão universal de conteúdo relacionado."""

from __future__ import annotations

import struct
from pathlib import Path

from steamzero.domain.library_management import LibraryRootManager


def _sfo(title: str, title_id: str) -> bytes:
    keys = b"TITLE_ID\0TITLE\0"
    title_bytes = title.encode()
    id_bytes = title_id.encode()
    key_offset = 52
    data_offset = key_offset + len(keys)
    entries = [
        (0, 0x0204, len(id_bytes) + 1, len(id_bytes) + 1, 0),
        (9, 0x0204, len(title_bytes) + 1, len(title_bytes) + 1, len(id_bytes) + 1),
    ]
    return (
        struct.pack("<4sIIII", b"\x00PSF", 0x101, key_offset, data_offset, 2)
        + b"".join(struct.pack("<HHIII", *entry) for entry in entries)
        + keys
        + id_bytes
        + b"\0"
        + title_bytes
        + b"\0"
    )


def test_audit_relates_directory_members_and_quarantines_only_selected_files(
    tmp_path: Path,
) -> None:
    root = tmp_path / "roms"
    app = root / "psvita" / "Title" / "app" / "PCSF00516"
    (app / "sce_sys").mkdir(parents=True)
    (app / "sce_sys" / "param.sfo").write_bytes(_sfo("Title", "PCSF00516"))
    (app / "eboot.bin").write_bytes(b"boot")
    (app / "sce_sys" / "manual").mkdir()
    (app / "sce_sys" / "manual" / "001.png").write_bytes(b"asset")

    audit = LibraryRootManager(root).audit()

    assert audit["counts"]["base"] == 1
    assert audit["counts"]["related"] >= 1
    member = next(
        item for item in audit["categories"]["related"] if item["relativePath"].endswith("001.png")
    )
    plan, quarantine_id = LibraryRootManager(root).plan_quarantine(audit, [member["relativePath"]])
    assert plan.kind == "library.quarantine"
    assert quarantine_id


def test_audit_keeps_unmatched_files_visible_but_excludes_managed_trees(
    tmp_path: Path,
) -> None:
    root = tmp_path / "roms"
    (root / "mystery-platform").mkdir(parents=True)
    (root / "mystery-platform" / "review-me.bin").write_bytes(b"review")
    (root / ".steamzero" / "derived").mkdir(parents=True)
    (root / ".steamzero" / "derived" / "generated.zip").write_bytes(b"managed")

    audit = LibraryRootManager(root).audit()
    unknown = {item["relativePath"] for item in audit["categories"]["unknown"]}

    assert "mystery-platform/review-me.bin" in unknown
    assert ".steamzero/derived/generated.zip" not in unknown


def test_plan_rename_is_universal_and_keeps_vita_identity_in_the_filename(
    tmp_path: Path,
) -> None:
    root = tmp_path / "roms"
    source = root / "psvita" / "PCSE00004.zip"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"vita")

    plan = LibraryRootManager(root).plan_rename(
        [
            {
                "path": str(source),
                "name": "ULTIMATE MARVEL VS. CAPCOM 3",
                "platform": "playstation-vita",
                "titleId": "PCSE00004",
                "contentKind": "base",
            }
        ]
    )

    assert plan.kind == "library.rename"
    assert len(plan.actions) == 1
    assert plan.actions[0].target.endswith("ULTIMATE MARVEL VS. CAPCOM 3 [PCSE00004].zip")
    assert source.is_file()


def test_plan_rename_resolves_collisions_without_overwrite_or_directory_touch(
    tmp_path: Path,
) -> None:
    root = tmp_path / "roms"
    first = root / "nes" / "a.nes"
    second = root / "nes" / "b.nes"
    directory_game = root / "psvita" / "PCSF00516"
    first.parent.mkdir(parents=True)
    directory_game.mkdir(parents=True)
    first.write_bytes(b"one")
    second.write_bytes(b"two")

    plan = LibraryRootManager(root).plan_rename(
        [
            {"path": str(first), "name": "Same Title", "platform": "nes"},
            {"path": str(second), "name": "Same Title", "platform": "nes"},
            {
                "path": str(directory_game),
                "name": "Directory Game",
                "platform": "playstation-vita",
            },
        ]
    )

    targets = {Path(action.target).name for action in plan.actions}
    assert targets == {"Same Title.nes", "Same Title (2).nes"}
    assert directory_game.is_dir()
