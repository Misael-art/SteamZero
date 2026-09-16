# SPDX-License-Identifier: GPL-3.0-or-later
"""Archive-aware multi-disc fixtures for floppy platforms."""

from __future__ import annotations

import zipfile
from pathlib import Path

from steamzero.domain.multidisc import ArchiveAwareMultiDiscResolver, inspect_archive


def _manifest(
    *,
    media: list[str],
    patterns: list[str],
    container: str = "native",
    support: str = "unproven",
    role_order: list[str] | None = None,
) -> dict[str, object]:
    policy: dict[str, object] = {
        "enabled": True,
        "descriptor": "m3u",
        "media": media,
        "filenamePatterns": patterns,
        "requiresContinuousSequence": True,
        "adapterPlaylistSupport": support,
        "archiveMemberPolicy": {
            "allowedFormats": media,
            "letterLabelsAreOrdinal": "label" in patterns,
        },
    }
    if role_order is not None:
        policy["roleOrder"] = role_order
        policy["orderingModel"] = "ordinal-and-role"
    return {"media": {"containerPolicy": container, "multiDisc": policy}}


def _zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)


def test_archive_index_hashes_members_without_extracting(tmp_path: Path) -> None:
    archive = tmp_path / "Game (Disk 1 of 4).zip"
    _zip(archive, {"Game (Disk 1 of 4).adf": b"adf"})

    inspected = inspect_archive(archive, allowed_formats=["adf"])

    assert inspected.state == "ready"
    assert inspected.archive_hash
    assert inspected.members[0].member_path == "Game (Disk 1 of 4).adf"
    assert inspected.members[0].member_hash
    assert not (tmp_path / "Game (Disk 1 of 4).adf").exists()


def test_amiga_zip_set_requires_extraction_before_playlist(tmp_path: Path) -> None:
    archives = []
    for number in range(1, 5):
        archive = tmp_path / f"Street Fighter (Disk {number} of 4).zip"
        _zip(archive, {f"Street Fighter (Disk {number} of 4).adf": bytes([number])})
        archives.append(archive)

    result = ArchiveAwareMultiDiscResolver(
        _manifest(media=["adf"], patterns=["disc", "disk"], container="extract")
    ).resolve("amiga", "amiga600", archives)

    assert len(result) == 1
    assert result[0].state == "needs-extraction"
    assert [part.number for part in result[0].parts] == [1, 2, 3, 4]
    assert all(part.member_hash and part.archive_hash for part in result[0].parts)


def test_x68000_archive_can_contain_three_logical_games(tmp_path: Path) -> None:
    archive = tmp_path / "Garou I II Special.zip"
    members: dict[str, bytes] = {}
    for title, total, end in (
        ("Garou Densetsu", 4, "D"),
        ("Garou Densetsu 2", 6, "F"),
        ("Garou Densetsu Special", 9, "I"),
    ):
        for number in range(1, ord(end) - ord("A") + 2):
            label = chr(ord("A") + number - 1)
            members[
                f"{title} (1993)(Magical Company)(Disk {number} of {total})(Disk {label}).dim"
            ] = bytes([number])
    _zip(archive, members)

    result = ArchiveAwareMultiDiscResolver(
        _manifest(
            media=["dim", "xdf"],
            patterns=["disc", "disk", "label", "role"],
            role_order=["system", "program", "data", "user", "opening", "ending"],
        )
    ).resolve("x68000", "x68000", [archive])

    assert len(result) == 3
    assert {resolution.disc_total for resolution in result} == {4, 6, 9}
    assert {resolution.normalized_title for resolution in result} == {
        "garou densetsu (1993)(magical company)",
        "garou densetsu 2 (1993)(magical company)",
        "garou densetsu special (1993)(magical company)",
    }
    assert all(resolution.state == "needs-platform-contract" for resolution in result)
    assert all(part.disc_label for resolution in result for part in resolution.parts)


def test_duplicate_disk_number_is_conflict_not_first_match(tmp_path: Path) -> None:
    first = tmp_path / "Game (Disk 1 of 2).zip"
    second = tmp_path / "Game (Disk 1 of 2) (1).zip"
    _zip(first, {"Game (Disk 1 of 2).adf": b"one"})
    _zip(second, {"Game (Disk 1 of 2).adf": b"different"})

    result = ArchiveAwareMultiDiscResolver(
        _manifest(media=["adf"], patterns=["disc", "disk"])
    ).resolve("amiga", "amiga1200", [first, second])

    assert result[0].state == "conflict"


def test_x68000_role_without_ordinal_is_review(tmp_path: Path) -> None:
    archive = tmp_path / "Bahnwelt.zip"
    _zip(
        archive,
        {
            "Bahnwelt (System Disk).xdf": b"system",
            "Bahnwelt (Data Disk A).xdf": b"data-a",
            "Bahnwelt (Data Disk B).xdf": b"data-b",
        },
    )

    result = ArchiveAwareMultiDiscResolver(
        _manifest(
            media=["dim", "xdf"],
            patterns=["label", "role"],
            role_order=["system", "program", "data"],
        )
    ).resolve("x68000", "x68000", [archive])

    assert len(result) == 1
    assert result[0].state == "needs-review"
    assert [part.number for part in result[0].parts] == [None, None, None]
    assert {part.disc_role for part in result[0].parts} == {"system", "data"}


def test_archive_single_label_is_not_multidisc_without_total(tmp_path: Path) -> None:
    archive = tmp_path / "Single Disk A.zip"
    _zip(archive, {"Single Disk A.dim": b"dim"})

    result = ArchiveAwareMultiDiscResolver(_manifest(media=["dim"], patterns=["label"])).resolve(
        "x68000", "x68000", [archive]
    )

    assert result == ()
