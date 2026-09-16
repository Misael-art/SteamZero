# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only multi-disc contract and resolver tests."""

from __future__ import annotations

from pathlib import Path

from steamzero.domain.multidisc import (
    DiscRecord,
    MultiDiscPart,
    MultiDiscPolicy,
    MultiDiscResolution,
    MultiDiscSet,
    parse_disc_marker,
    reconcile_multidisc_set,
    resolve_multidisc,
)


def _manifest(**multi_disc: object) -> dict[str, object]:
    return {"media": {"multiDisc": multi_disc}}


def _policy() -> MultiDiscPolicy:
    return MultiDiscPolicy.from_manifest(
        _manifest(
            enabled=True,
            descriptor="m3u",
            media=["img", "chd"],
            filenamePatterns=["disc", "disk", "cd"],
            requiresContinuousSequence=True,
        )
    )


def test_parser_removes_only_disc_marker_and_preserves_variant() -> None:
    parsed = parse_disc_marker("Chrono Cross (USA) (Disc 1) (Translated PtBr)", _policy())
    assert parsed is not None
    title, marker = parsed
    assert title == "Chrono Cross (USA) (Translated PtBr)"
    assert marker.number == 1


def test_resolver_keeps_platform_and_system_in_group_key(tmp_path: Path) -> None:
    files = [
        tmp_path / "Chrono Cross (USA) (Disc 1) (Translated PtBr).img",
        tmp_path / "Chrono Cross (USA) (Disc 2) (Translated PtBr).img",
    ]
    for path in files:
        path.write_bytes(b"disc")
    result = resolve_multidisc(
        "playstation",
        "psx",
        files,
        _manifest(
            enabled=True,
            descriptor="m3u",
            media=["img"],
            filenamePatterns=["disc"],
            requiresContinuousSequence=True,
        ),
    )
    assert len(result) == 1
    assert result[0].state == "ready"
    assert result[0].group_key.startswith("playstation:psx:")
    assert [part.number for part in result[0].parts] == [1, 2]
    assert all(part.content_hash for part in result[0].parts)


def test_snes_without_declared_contract_is_not_auto_generated(tmp_path: Path) -> None:
    files = [tmp_path / "Game (Disc 1).sfc", tmp_path / "Game (Disc 2).sfc"]
    for path in files:
        path.write_bytes(b"rom")
    result = resolve_multidisc(
        "snes",
        "snes",
        files,
        {"media": {"extensions": ["sfc"]}},
    )
    assert result[0].state == "needs-platform-contract"


def test_resolver_rejects_missing_duplicate_and_user_playlist_conflicts(tmp_path: Path) -> None:
    (tmp_path / "set-a").mkdir()
    (tmp_path / "set-b").mkdir()
    first = tmp_path / "set-a" / "Game (Disc 1).chd"
    duplicate = tmp_path / "set-b" / "Game (Disc 1).chd"
    missing_three = tmp_path / "Game (Disc 3).chd"
    for path in (first, duplicate, missing_three):
        path.write_bytes(b"rom")
    manifest = _manifest(
        enabled=True,
        descriptor="m3u",
        media=["chd"],
        filenamePatterns=["disc"],
        requiresContinuousSequence=True,
    )
    result = resolve_multidisc("playstation", "psx", [first, duplicate, missing_three], manifest)
    assert result[0].state == "ambiguous"
    user_descriptor = tmp_path / "Game.m3u"
    user_descriptor.write_text("disc-one.chd\n", encoding="utf-8")
    second = tmp_path / "Game (Disc 2).chd"
    second.write_bytes(b"rom")
    conflict = resolve_multidisc(
        "playstation",
        "psx",
        [first, second],
        manifest,
        existing_descriptor=user_descriptor,
    )
    assert conflict[0].state == "conflict"


def test_reconciliation_keeps_identity_when_img_becomes_chd(tmp_path: Path) -> None:
    old_path = tmp_path / "Game (Disc 1).img"
    new_path = tmp_path / "Game (Disc 1).chd"
    old_path.write_bytes(b"old")
    new_path.write_bytes(b"new")
    existing = MultiDiscSet(
        set_id="playstation:psx:game",
        platform_id="playstation",
        system_id="psx",
        normalized_title="game",
        discs=(
            DiscRecord(
                set_id="playstation:psx:game",
                disc_number=1,
                disc_total=2,
                format="img",
                path=old_path,
                content_hash="old-hash",
                accepted_formats=("chd", "img"),
                state="active",
            ),
        ),
    )
    resolution = MultiDiscResolution(
        state="ready",
        platform_id="playstation",
        system_id="psx",
        normalized_title="game",
        display_title="Game",
        group_key="playstation:psx:game",
        parts=(MultiDiscPart(new_path, 1, 2, "chd", "new-hash"),),
    )
    reconciled = reconcile_multidisc_set(resolution, existing)
    disc = reconciled.discs[0]
    assert disc.identity == "playstation:psx:game:disc-1"
    assert disc.state == "converted"
    assert disc.format == "chd"
    assert disc.path == new_path
    assert disc.conversion_history[0]["fromHash"] == "old-hash"


def test_archive_conversion_requires_extraction_when_adapter_declares_extract(
    tmp_path: Path,
) -> None:
    files = [tmp_path / "Game (Disc 1).zip", tmp_path / "Game (Disc 2).zip"]
    for path in files:
        path.write_bytes(b"archive")
    result = resolve_multidisc(
        "electron",
        "electron",
        files,
        {
            "media": {
                "containerPolicy": "extract",
                "multiDisc": {
                    "enabled": True,
                    "descriptor": "m3u",
                    "media": ["7z"],
                    "filenamePatterns": ["disc"],
                },
            }
        },
    )
    assert result[0].state == "needs-extraction"
