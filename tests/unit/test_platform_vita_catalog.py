# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Cobertura declarativa do catálogo PlayStation Vita."""

from __future__ import annotations

from pathlib import Path

from steamzero.adapters.scraping.screenscraper import _PLATFORMS_WITHOUT_SYSTEMEID
from steamzero.domain.library import PlatformRomScanner
from steamzero.domain.platforms import PlatformRegistry


def test_vita_manifest_is_visible_but_does_not_promise_an_emulator() -> None:
    manifest = PlatformRegistry.bundled().get("playstation-vita")

    assert manifest.systems == ("psvita", "playstation-vita", "vita")
    assert manifest.requirements == ("keys", "firmware")
    assert manifest.emulators == ()
    assert "playstation-vita" in _PLATFORMS_WITHOUT_SYSTEMEID


def test_psvita_directory_is_classified_by_the_manifest() -> None:
    manifest = PlatformRegistry.bundled().get("playstation-vita")
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
    platform, content_kind, evidence = scanner.classify(
        "demo.vpk",
        {"demo.vpk"},
        root_platform="playstation-vita",
    )

    assert platform == "playstation-vita"
    assert content_kind == "base"
    assert evidence == "root-wins"


def test_psvita_root_name_resolves_to_the_canonical_platform() -> None:
    manifest = PlatformRegistry.bundled().get("playstation-vita")
    scanner = PlatformRomScanner.from_manifests(
        [
            {
                "id": manifest.id,
                "systems": list(manifest.systems),
                "media": {
                    "extensions": list(manifest.media["extensions"]),
                    "formats": manifest.media.get("formats", {}),
                },
            }
        ]
    )

    root = Path("/roms")
    platform, _kind, _evidence = scanner.classify(
        "demo.vpk",
        {"demo.vpk"},
        root_platform=None,
        path=root / "psvita" / "demo.vpk",
    )

    assert platform == "playstation-vita"
