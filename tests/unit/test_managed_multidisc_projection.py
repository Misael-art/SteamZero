# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import zipfile
from dataclasses import replace
from pathlib import Path

from steamzero.adapters import emulation
from steamzero.adapters.emulation import EmulationController
from steamzero.adapters.managed_multidisc_projection import discover_managed_projection
from steamzero.core.state import StateStore
from steamzero.domain.multidisc import ArchiveAwareMultiDiscResolver, MultiDiscResolution
from steamzero.domain.multidisc_artifacts import OWNERSHIP_MARKER


def _manifest() -> dict[str, object]:
    return {
        "media": {
            "containerPolicy": "extract",
            "multiDisc": {
                "enabled": True,
                "descriptor": "m3u",
                "media": ["adf"],
                "filenamePatterns": ["disk"],
                "requiresContinuousSequence": True,
                "adapterPlaylistSupport": "proven",
                "archiveMemberPolicy": {"allowedFormats": ["adf"]},
            },
        }
    }


def _archives(root: Path) -> tuple[Path, ...]:
    result = []
    for number in (1, 2):
        path = root / f"Game (Disk {number} of 2).zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(f"Game (Disk {number} of 2).adf", f"disk-{number}".encode())
        result.append(path)
    return tuple(result)


def _prepare_projection(root: Path, archives: tuple[Path, ...]) -> tuple[Path, MultiDiscResolution]:
    logical_set = ArchiveAwareMultiDiscResolver(_manifest()).resolve("amiga", "amiga", archives)[0]
    destination = root / ".steamzero" / "derived" / "amiga" / "game"
    destination.mkdir(parents=True)
    lines = [OWNERSHIP_MARKER, f"# SteamZero-MultiDisc-Set: {logical_set.set_id}"]
    for index, _part in enumerate(logical_set.parts, start=1):
        payload = f"disk-{index}".encode()
        (destination / f"disk-{index:02d}.adf").write_bytes(payload)
        lines.extend(
            [
                f"# SteamZero-MultiDisc-Disc: {logical_set.set_id}:disc-{index}",
                f"disk-{index:02d}.adf",
            ]
        )
    descriptor = destination / "game.m3u"
    descriptor.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return descriptor, logical_set


def test_publishes_only_current_owned_projection_bound_to_reconciled_archives(
    tmp_path: Path,
) -> None:
    archives = _archives(tmp_path)
    descriptor, logical_set = _prepare_projection(tmp_path, archives)

    projection = discover_managed_projection(tmp_path, logical_set)

    assert projection is not None
    assert projection.descriptor_path == descriptor
    assert [path.name for path in projection.entries] == ["disk-01.adf", "disk-02.adf"]
    assert (
        discover_managed_projection(tmp_path, replace(logical_set, state="needs-platform-contract"))
        is None
    )


def test_rejects_changed_member_bytes_and_wrong_set_identity(tmp_path: Path) -> None:
    archives = _archives(tmp_path)
    descriptor, logical_set = _prepare_projection(tmp_path, archives)
    (descriptor.parent / "disk-02.adf").write_bytes(b"tampered")
    assert discover_managed_projection(tmp_path, logical_set) is None

    (descriptor.parent / "disk-02.adf").write_bytes(b"disk-2")
    descriptor.write_text(
        descriptor.read_text(encoding="utf-8").replace(logical_set.set_id, "wrong:set"),
        encoding="utf-8",
    )
    assert discover_managed_projection(tmp_path, logical_set) is None


def test_rejects_symlinked_or_missing_members_and_user_owned_playlists(tmp_path: Path) -> None:
    archives = _archives(tmp_path)
    descriptor, logical_set = _prepare_projection(tmp_path, archives)
    second = descriptor.parent / "disk-02.adf"
    second.unlink()
    second.symlink_to(descriptor.parent / "disk-01.adf")
    assert discover_managed_projection(tmp_path, logical_set) is None

    second.unlink()
    assert discover_managed_projection(tmp_path, logical_set) is None

    descriptor.write_text("# user playlist\ndisk-01.adf\n", encoding="utf-8")
    assert discover_managed_projection(tmp_path, logical_set) is None


def test_library_scan_publishes_projection_and_suppresses_its_archives(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    library_root = tmp_path / "roms"
    platform_root = library_root / "amiga"
    platform_root.mkdir(parents=True)
    archives = _archives(platform_root)
    descriptor, logical_set = _prepare_projection(library_root, archives)
    projection = discover_managed_projection(library_root, logical_set)
    assert projection is not None

    # The bundled Amiga manifest still says M3U support is unproven. This test
    # isolates catalogue wiring after the projection validator accepts a set.
    monkeypatch.setattr(
        emulation,
        "discover_managed_projection",
        lambda _root, _logical_set: projection,
    )
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    controller = EmulationController(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        which=lambda _command: None,
        spawn=lambda _argv: None,
    )
    monkeypatch.setattr(controller, "library_roots", lambda: [str(library_root)])

    result = controller._scan_library_now()  # type: ignore[attr-defined]
    games, _unidentified = controller._load_library_cache()  # type: ignore[attr-defined]

    assert result["games"] == 1
    assert len(games) == 1
    assert games[0]["path"] == str(descriptor)
    assert games[0]["state"] == "ready"
    assert games[0]["evidence"] == "archive-multidisc-ready"
    assert all(str(path) != games[0]["path"] for path in archives)
