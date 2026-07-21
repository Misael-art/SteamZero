# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""WI-5: biblioteca/mídia Switch — scan, DAT local, matching e rename seguro."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from steamzero.core import fs
from steamzero.core.errors import SteamZeroError
from steamzero.domain.switch_library import (
    DatIndex,
    SwitchLibraryOrganizer,
    SwitchLibraryScanner,
    SwitchMediaMatcher,
    SwitchRomMatch,
)


@pytest.fixture
def dat_fixture(tmp_path: Path) -> DatIndex:
    data = {
        "schemaVersion": 1,
        "platform": "switch",
        "source": "local-import",
        "entries": [
            {
                "sha256": "a" * 64,
                "name": "Synthetic Adventure",
                "titleId": "0100000000010000",
                "region": "USA",
            },
            {
                "sha256": "b" * 64,
                "name": "Synthetic Racer",
                "titleId": "0100000000020000",
                "region": "Europe",
            },
        ],
    }
    return DatIndex(data)


# --- DatIndex ---------------------------------------------------------------


def test_dat_index_accepts_valid_local_index() -> None:
    index = DatIndex(
        {
            "schemaVersion": 1,
            "platform": "switch",
            "source": "local-import",
            "entries": [
                {
                    "sha256": "a" * 64,
                    "name": "Demo",
                    "titleId": "0100000000000001",
                    "region": "USA",
                }
            ],
        }
    )
    assert index.platform == "switch"
    assert len(index.entries) == 1


def test_dat_index_rejects_remote_source() -> None:
    with pytest.raises(SteamZeroError):
        DatIndex(
            {
                "schemaVersion": 1,
                "platform": "switch",
                "source": "https://example.invalid/dat.dat",
                "entries": [],
            }
        )


def test_dat_index_match_returns_metadata(dat_fixture: DatIndex) -> None:
    match = dat_fixture.match("a" * 64)
    assert match is not None
    assert match.canonical_name == "Synthetic Adventure"
    assert match.title_id == "0100000000010000"
    assert match.region == "USA"


def test_dat_index_match_returns_none_for_unknown_hash(dat_fixture: DatIndex) -> None:
    assert dat_fixture.match("c" * 64) is None


def test_dat_index_rejects_divergent_duplicate_hash() -> None:
    with pytest.raises(SteamZeroError) as exc:
        DatIndex(
            {
                "schemaVersion": 1,
                "platform": "switch",
                "source": "local-import",
                "entries": [
                    {"sha256": "a" * 64, "name": "First"},
                    {"sha256": "a" * 64, "name": "Second"},
                ],
            }
        )
    assert exc.value.code == "E-API-SCHEMA"


@pytest.mark.parametrize("name", ["Unsafe\nName", "Hidden\u202eName"])
def test_dat_index_rejects_control_and_bidi_names(name: str) -> None:
    with pytest.raises(SteamZeroError):
        DatIndex(
            {
                "schemaVersion": 1,
                "platform": "switch",
                "source": "local-import",
                "entries": [{"sha256": "a" * 64, "name": name}],
            }
        )


def test_dat_index_from_path(dat_fixture: DatIndex, tmp_path: Path) -> None:
    path = tmp_path / "dat.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "platform": "switch",
                "source": "local-import",
                "entries": [
                    {
                        "sha256": "d" * 64,
                        "name": "From Path",
                        "titleId": "0100000000030000",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    loaded = DatIndex.from_path(path)
    match = loaded.match("d" * 64)
    assert match is not None
    assert match.canonical_name == "From Path"


# --- SwitchLibraryScanner ---------------------------------------------------


def test_scanner_lists_only_allowed_formats(tmp_path: Path) -> None:
    (tmp_path / "game.nsp").write_bytes(b"nsp")
    (tmp_path / "game.nsz").write_bytes(b"nsz")
    (tmp_path / "game.xci").write_bytes(b"xci")
    (tmp_path / "homebrew.nro").write_bytes(b"nro")
    (tmp_path / "readme.txt").write_bytes(b"txt")
    (tmp_path / "image.png").write_bytes(b"png")

    matches = SwitchLibraryScanner().scan(tmp_path)
    formats = {m.format for m in matches}
    assert formats == {"nsp", "nsz", "xci", "nro"}
    assert len(matches) == 4


def test_scanner_hashes_are_sha256(tmp_path: Path) -> None:
    rom = tmp_path / "game.nsp"
    rom.write_bytes(b"dump-bytes")
    matches = SwitchLibraryScanner().scan(tmp_path)
    assert len(matches) == 1
    assert matches[0].sha256 == fs.hash_file(rom, algo="sha256")


# --- SwitchMediaMatcher -----------------------------------------------------


def test_matcher_enriches_with_dat(dat_fixture: DatIndex, tmp_path: Path) -> None:
    rom = tmp_path / "game.nsp"
    rom.write_bytes(b"aa")  # hash não corresponde a 'a'*64, mas usamos o hash fixo
    raw = [
        replace(SwitchLibraryScanner().scan(tmp_path)[0], sha256="a" * 64),
    ]
    matched = SwitchMediaMatcher(dat_fixture).match(raw)
    assert len(matched) == 1
    assert matched[0].canonical_name == "Synthetic Adventure"
    assert matched[0].title_id == "0100000000010000"


def test_matcher_without_dat_passes_through(tmp_path: Path) -> None:
    (tmp_path / "game.nsp").write_bytes(b"dump")
    raw = SwitchLibraryScanner().scan(tmp_path)
    matched = SwitchMediaMatcher(None).match(raw)
    assert len(matched) == 1
    assert matched[0].canonical_name is None


# --- SwitchLibraryOrganizer -------------------------------------------------


def test_organizer_plan_rename_without_collision(tmp_path: Path) -> None:
    rom = tmp_path / "old.nsp"
    rom.write_bytes(b"dump")
    matches = [
        replace(
            SwitchLibraryScanner().scan(tmp_path)[0],
            sha256="a" * 64,
            canonical_name="Synthetic Adventure",
        )
    ]
    plan = SwitchLibraryOrganizer().preview_rename(tmp_path, matches)
    assert plan == {rom: tmp_path / "Synthetic Adventure.nsp"}


def test_organizer_plan_rename_resolves_collision(tmp_path: Path) -> None:
    (tmp_path / "a.nsp").write_bytes(b"dump-a")
    (tmp_path / "b.nsp").write_bytes(b"dump-b")
    scanner = SwitchLibraryScanner()
    roms = scanner.scan(tmp_path)
    matches = [
        replace(roms[0], sha256="a" * 64, canonical_name="Synthetic Adventure"),
        replace(roms[1], sha256="b" * 64, canonical_name="Synthetic Adventure"),
    ]
    plan = SwitchLibraryOrganizer().preview_rename(tmp_path, matches)
    targets = set(plan.values())
    assert len(targets) == 2
    assert all("Synthetic Adventure" in str(t) for t in targets)
    assert any(" (2)" in str(t) for t in targets)


def test_organizer_ignores_unmatched_roms(tmp_path: Path) -> None:
    rom = tmp_path / "old.nsp"
    rom.write_bytes(b"dump")
    matches = [SwitchLibraryScanner().scan(tmp_path)[0]]
    plan = SwitchLibraryOrganizer().preview_rename(tmp_path, matches)
    assert plan == {}


def test_organizer_keeps_original_when_already_canonical(tmp_path: Path) -> None:
    rom = tmp_path / "Synthetic Adventure.nsp"
    rom.write_bytes(b"dump")
    matches = [
        replace(
            SwitchLibraryScanner().scan(tmp_path)[0],
            sha256="a" * 64,
            canonical_name="Synthetic Adventure",
        )
    ]
    plan = SwitchLibraryOrganizer().preview_rename(tmp_path, matches)
    assert plan == {}


def test_organizer_avoids_existing_casefold_collision(tmp_path: Path) -> None:
    rom = tmp_path / "old.nsp"
    rom.write_bytes(b"dump")
    (tmp_path / "synthetic adventure.NSP").write_bytes(b"foreign")
    match = replace(SwitchLibraryScanner().scan(tmp_path)[0], canonical_name="Synthetic Adventure")

    preview = SwitchLibraryOrganizer().preview_rename(tmp_path, [match])

    assert preview == {rom: tmp_path / "Synthetic Adventure (2).nsp"}


def test_organizer_rejects_source_outside_root_and_symlink(tmp_path: Path) -> None:
    root = tmp_path / "library"
    root.mkdir()
    outside = tmp_path / "outside.nsp"
    outside.write_bytes(b"outside")
    linked = root / "linked.nsp"
    linked.symlink_to(outside)
    organizer = SwitchLibraryOrganizer()

    outside_match = replace(
        SwitchRomMatch(outside, "a" * 64, "nsp", None, None, None),
        canonical_name="Outside",
    )
    link_match = replace(outside_match, path=linked, canonical_name="Linked")
    with pytest.raises(SteamZeroError):
        organizer.preview_rename(root, [outside_match])
    with pytest.raises(SteamZeroError):
        organizer.preview_rename(root, [link_match])


def test_organizer_plan_apply_and_rollback(tmp_path: Path) -> None:
    rom = tmp_path / "old.nsp"
    rom.write_bytes(b"dump")
    match = replace(SwitchLibraryScanner().scan(tmp_path)[0], canonical_name="Synthetic Adventure")
    organizer = SwitchLibraryOrganizer()

    plan = organizer.plan_rename(tmp_path, [match])
    assert rom.exists()
    applied = organizer.apply(plan.plan_id, plan.confirm_token)
    renamed = tmp_path / "Synthetic Adventure.nsp"
    assert renamed.read_bytes() == b"dump"
    organizer.rollback(applied.operation_id)
    assert rom.read_bytes() == b"dump"
    assert not renamed.exists()


def test_organizer_rejects_collision_suffix_without_counter(tmp_path: Path) -> None:
    rom = tmp_path / "old.nsp"
    rom.write_bytes(b"dump")
    match = replace(SwitchLibraryScanner().scan(tmp_path)[0], canonical_name="Synthetic Adventure")

    with pytest.raises(SteamZeroError) as exc:
        SwitchLibraryOrganizer().preview_rename(tmp_path, [match], collision_suffix=" duplicate")

    assert exc.value.code == "E-API-SCHEMA"
