# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato declarativo do catálogo PlayStation 5 via SharpEmu."""

from __future__ import annotations

from pathlib import Path

from steamzero.adapters.registry import AdapterRegistry
from steamzero.domain.input_profiles import InputProfileRegistry
from steamzero.domain.library import PlatformDirectoryInventory, PlatformRomScanner
from steamzero.domain.platforms import PlatformRegistry


def test_ps5_manifest_declares_sharpemu_and_pinned_tarball() -> None:
    manifest = PlatformRegistry.bundled().get("playstation-5")
    assert manifest.systems == ("ps5",)
    assert manifest.requirements == ()
    assert [emulator["adapterId"] for emulator in manifest.emulators] == ["sharpemu"]

    adapter = AdapterRegistry.bundled().get("sharpemu")
    assert adapter.platforms == ("playstation-5",)
    assert adapter.sources[0].archive_format == "tar.gz"
    assert adapter.sources[0].payload_path == "SharpEmu"
    assert adapter.sources[0].sha256 == (
        "8fbbfb1fb2a0e7fca5df683bfb8e6149c0e4b2c3e2272c5324e2dee3f0f5e26d"
    )


def test_ps5_scanner_accepts_only_executable_entries() -> None:
    manifest = PlatformRegistry.bundled().get("playstation-5")
    scanner = PlatformRomScanner.from_manifests(
        [
            {
                "id": manifest.id,
                "media": {
                    "extensions": list(manifest.media["extensions"]),
                    "formats": manifest.media.get("formats", {}),
                    "containerPolicy": manifest.media.get("containerPolicy"),
                },
            }
        ]
    )

    assert scanner.classify("eboot.bin", {"eboot.bin"}, root_platform="playstation-5") == (
        "playstation-5",
        "base",
        "root-wins",
    )
    assert scanner.classify("libfoo.bin", {"libfoo.bin"}, root_platform="playstation-5")[2] == (
        "ps5-auxiliary-bin"
    )
    assert scanner.classify("package.pkg", {"package.pkg"}, root_platform="playstation-5")[2] == (
        "ps5-pkg-unresolved"
    )
    assert scanner.classify("dump.zip", {"dump.zip"}, root_platform="playstation-5") == (
        None,
        "unknown",
        "archive-needs-extraction",
    )
    assert scanner.classify("dump.tar.gz", {"dump.tar.gz"}, root_platform="playstation-5") == (
        None,
        "unknown",
        "archive-needs-extraction",
    )
    assert (
        scanner.classify("module.prx", {"module.prx"}, root_platform="playstation-5")[2]
        == "ps5-unsupported-entry"
    )


def test_dualsense_profile_fits_ps5() -> None:
    platform = PlatformRegistry.bundled().get("playstation-5")
    profile = InputProfileRegistry.bundled().get("dualsense")
    assert profile.platforms == ("playstation-5",)
    assert profile.max_players <= int(platform.controls["maxPlayers"])
    assert "adaptive-triggers" in platform.controls["specialized"]


def test_ps5_directory_inventory_exposes_only_eboot_as_game(tmp_path: Path) -> None:
    game = tmp_path / "roms" / "ps5" / "Demo"
    (game / "sce_sys").mkdir(parents=True)
    (game / "eboot.bin").write_bytes(b"ELF")
    (game / "libfoo.bin").write_bytes(b"module")
    (game / "module.prx").write_bytes(b"module")
    (game / "package.pkg").write_bytes(b"pkg")

    rows = PlatformDirectoryInventory.from_registry(PlatformRegistry.bundled()).inventory(
        tmp_path / "roms"
    )

    assert len(rows) == 1
    assert rows[0].platform_id == "playstation-5"
    assert rows[0].game_count == 1
    assert [item.path.name for item in rows[0].selected_games] == ["eboot.bin"]
