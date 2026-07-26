# SPDX-License-Identifier: GPL-3.0-or-later
"""D1 — classificação pura de ROMs multi-plataforma, sem I/O."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.domain.library import (
    PlatformRomScanner,
    RomCandidate,
    build_ext_map,
    classify_rom,
)
from steamzero.domain.platforms import PlatformRegistry


@pytest.fixture(scope="session")
def ext_map() -> dict[str, list[str]]:
    reg = PlatformRegistry.bundled()
    manifests = [{"id": m.id, "media": dict(m.media)} for m in reg.list()]
    return build_ext_map(manifests)


def _mksiblings(*names: str) -> set[str]:
    return set(names)


# ── classify_rom: regras individuais ────────────────────────────────────────


class TestZip7zAlwaysUnknown:
    def test_zip_is_unknown(self, ext_map: dict[str, list[str]]) -> None:
        plat, kind, ev = classify_rom("game.zip", {"game.zip"}, ext_map)
        assert plat is None
        assert kind == "unknown"
        assert ev == "archived"

    def test_7z_is_unknown(self, ext_map: dict[str, list[str]]) -> None:
        plat, kind, ev = classify_rom("game.7z", {"game.7z"}, ext_map)
        assert plat is None
        assert kind == "unknown"
        assert ev == "archived"


class TestCueBinPairing:
    def test_cue_with_bin_sibling_is_playstation(self, ext_map: dict[str, list[str]]) -> None:
        siblings = _mksiblings("game.cue", "game.bin", "track02.bin")
        plat, kind, ev = classify_rom("game.cue", siblings, ext_map)
        assert plat == "playstation"
        assert kind == "base"
        assert ev == "cue-pair"

    def test_cue_without_bin_is_orphan(self, ext_map: dict[str, list[str]]) -> None:
        siblings = _mksiblings("game.cue")
        plat, kind, ev = classify_rom("game.cue", siblings, ext_map)
        assert plat is None
        assert kind == "unknown"
        assert ev == "cue-orphan"

    def test_bin_with_cue_sibling_is_playstation(self, ext_map: dict[str, list[str]]) -> None:
        siblings = _mksiblings("game.cue", "game.bin")
        plat, kind, ev = classify_rom("game.bin", siblings, ext_map)
        assert plat == "playstation"
        assert kind == "base"
        assert ev == "cue-pair"

    def test_bin_without_cue_is_orphan(self, ext_map: dict[str, list[str]]) -> None:
        siblings = _mksiblings("game.bin", "other.txt")
        plat, kind, ev = classify_rom("game.bin", siblings, ext_map)
        assert plat is None
        assert kind == "unknown"
        assert ev == "bin-orphan"


class TestExclusiveExtension:
    def test_gcm_is_nintendo_console(self, ext_map: dict[str, list[str]]) -> None:
        plat, kind, ev = classify_rom("game.gcm", {"game.gcm"}, ext_map)
        assert plat == "nintendo-console"
        assert kind == "base"
        assert ev == "exclusive-ext"

    def test_wbfs_is_nintendo_console(self, ext_map: dict[str, list[str]]) -> None:
        plat, kind, ev = classify_rom("game.wbfs", {"game.wbfs"}, ext_map)
        assert plat == "nintendo-console"
        assert kind == "base"
        assert ev == "exclusive-ext"

    def test_nes_is_nes_famicom(self, ext_map: dict[str, list[str]]) -> None:
        plat, kind, ev = classify_rom("game.nes", {"game.nes"}, ext_map)
        assert plat == "nes-famicom"
        assert kind == "base"
        assert ev == "exclusive-ext"

    def test_sfc_is_snes(self, ext_map: dict[str, list[str]]) -> None:
        plat, kind, ev = classify_rom("game.sfc", {"game.sfc"}, ext_map)
        assert plat == "snes"
        assert kind == "base"
        assert ev == "exclusive-ext"

    def test_pbp_is_playstation(self, ext_map: dict[str, list[str]]) -> None:
        plat, kind, ev = classify_rom("game.pbp", {"game.pbp"}, ext_map)
        assert plat == "playstation"
        assert kind == "base"
        assert ev == "exclusive-ext"


class TestAmbiguousExtensions:
    def test_iso_shared_by_disc_platforms_is_unknown(self, ext_map: dict[str, list[str]]) -> None:
        plat, kind, ev = classify_rom("game.iso", {"game.iso"}, ext_map)
        assert plat is None
        assert kind == "unknown"
        assert ev == "ambiguous-ext"

    def test_rvz_now_exclusive_to_nintendo_console(self, ext_map: dict[str, list[str]]) -> None:
        plat, kind, ev = classify_rom("game.rvz", {"game.rvz"}, ext_map)
        assert plat == "nintendo-console"
        assert kind == "base"
        assert ev == "exclusive-ext"

    def test_chd_shared_arcade_psx_is_unknown(self, ext_map: dict[str, list[str]]) -> None:
        plat, kind, ev = classify_rom("game.chd", {"game.chd"}, ext_map)
        assert plat is None
        assert kind == "unknown"
        assert ev == "ambiguous-ext"

    def test_bin_without_cue_is_not_playstation(self, ext_map: dict[str, list[str]]) -> None:
        siblings = _mksiblings("rom.bin", "rom.txt")
        plat, _kind, ev = classify_rom("rom.bin", siblings, ext_map)
        assert plat is None
        assert ev == "bin-orphan"


class TestUnknownExtensions:
    def test_unknown_ext_is_no_match(self, ext_map: dict[str, list[str]]) -> None:
        plat, kind, ev = classify_rom("game.xyz", {"game.xyz"}, ext_map)
        assert plat is None
        assert kind == "unknown"
        assert ev == "no-ext-match"


class TestRootWins:
    def test_root_platform_resolves_ambiguous_iso(self, ext_map: dict[str, list[str]]) -> None:
        plat, kind, ev = classify_rom(
            "game.iso", {"game.iso"}, ext_map, root_platform="nintendo-console"
        )
        assert plat == "nintendo-console"
        assert kind == "base"
        assert ev == "root-wins"

    def test_root_platform_resolves_single_platform(self, ext_map: dict[str, list[str]]) -> None:
        plat, _kind, _ev = classify_rom(
            "game.nes", {"game.nes"}, ext_map, root_platform="nes-famicom"
        )
        assert plat == "nes-famicom"

    def test_root_platform_does_not_override_archive(self, ext_map: dict[str, list[str]]) -> None:
        plat, kind, ev = classify_rom(
            "game.zip", {"game.zip"}, ext_map, root_platform="nintendo-console"
        )
        assert plat is None
        assert kind == "unknown"
        assert ev == "archived"

    def test_root_platform_does_not_override_orphan_cue(
        self, ext_map: dict[str, list[str]]
    ) -> None:
        plat, _kind, _ev = classify_rom(
            "game.cue", {"game.cue"}, ext_map, root_platform="playstation"
        )
        assert plat is None
        assert _ev == "cue-orphan"

    def test_root_platform_resolves_orphan_bin(self, ext_map: dict[str, list[str]]) -> None:
        plat, _kind, _ev = classify_rom(
            "game.bin", {"game.bin"}, ext_map, root_platform="mega-drive"
        )
        assert plat == "mega-drive"
        assert _ev == "root-wins"


class TestCaseInsensitivity:
    def test_uppercase_extension(self, ext_map: dict[str, list[str]]) -> None:
        plat, _kind, _ev = classify_rom("GAME.Z64", {"GAME.Z64"}, ext_map)
        assert plat == "nintendo-64"

    def test_mixed_case_cue_bin(self, ext_map: dict[str, list[str]]) -> None:
        siblings = _mksiblings("Game.CUE", "Game.BIN")
        plat, _kind, ev = classify_rom("Game.CUE", siblings, ext_map)
        assert plat == "playstation"
        assert ev == "cue-pair"


# ── build_ext_map ───────────────────────────────────────────────────────────


class TestBuildExtMap:
    def test_builds_ext_map(self) -> None:
        manifests = [
            {"id": "test-a", "media": {"extensions": ["iso", "rvz"]}},
            {"id": "test-b", "media": {"extensions": ["rvz", "wbfs"]}},
        ]
        em = build_ext_map(manifests)
        assert em[".iso"] == ["test-a"]
        assert sorted(em[".rvz"]) == ["test-a", "test-b"]
        assert em[".wbfs"] == ["test-b"]

    def test_empty_extensions(self) -> None:
        manifests = [{"id": "cloud", "media": {"extensions": []}}]
        em = build_ext_map(manifests)
        assert em == {}


# ── PlatformRomScanner.inventory ────────────────────────────────────────────


class TestPlatformRomScanner:
    def test_empty_root(self, tmp_path: Path) -> None:
        scanner = PlatformRomScanner.from_manifests([])
        assert scanner.inventory(tmp_path) == []

    def test_classifies_by_extension(self, tmp_path: Path, ext_map: dict[str, list[str]]) -> None:
        (tmp_path / "game.nes").write_text("data")
        (tmp_path / "readme.txt").write_text("notes")
        scanner = PlatformRomScanner(ext_map)
        results = scanner.inventory(tmp_path)
        results.sort(key=lambda r: r.path.name)
        assert len(results) == 2
        assert results[0].path.name == "game.nes"
        assert results[0].platform == "nes-famicom"
        assert results[0].content_kind == "base"
        assert results[0].evidence == "exclusive-ext"
        assert results[1].path.name == "readme.txt"
        assert results[1].platform is None
        assert results[1].content_kind == "unknown"
        assert results[1].evidence == "no-ext-match"

    def test_bin_cue_pair_in_directory(self, tmp_path: Path, ext_map: dict[str, list[str]]) -> None:
        (tmp_path / "game.cue").write_text("")
        (tmp_path / "game.bin").write_text("")
        (tmp_path / "track02.bin").write_text("")
        scanner = PlatformRomScanner(ext_map)
        results = {r.path.name: r for r in scanner.inventory(tmp_path)}
        assert results["game.cue"].platform == "playstation"
        assert results["game.bin"].platform == "playstation"
        assert results["track02.bin"].platform is None
        assert results["track02.bin"].evidence == "bin-orphan"

    def test_zip_is_unknown(self, tmp_path: Path, ext_map: dict[str, list[str]]) -> None:
        (tmp_path / "rom.zip").write_text("")
        scanner = PlatformRomScanner(ext_map)
        results = list(scanner.inventory(tmp_path))
        assert len(results) == 1
        assert results[0].platform is None
        assert results[0].content_kind == "unknown"
        assert results[0].evidence == "archived"

    def test_romcandidate_dataclass(self) -> None:
        c = RomCandidate(
            path=Path("/fake/game.iso"),
            format="iso",
            platform="nintendo-console",
            content_kind="base",
            evidence="root-wins",
        )
        assert c.format == "iso"
        assert c.platform == "nintendo-console"

    def test_inventory_with_root_platform(
        self, tmp_path: Path, ext_map: dict[str, list[str]]
    ) -> None:
        (tmp_path / "game.iso").write_text("")
        (tmp_path / "readme.txt").write_text("")
        scanner = PlatformRomScanner(ext_map)
        results = scanner.inventory(tmp_path, root_platform="nintendo-console")
        by_name = {r.path.name: r for r in results}
        assert by_name["game.iso"].platform == "nintendo-console"
        assert by_name["game.iso"].evidence == "root-wins"
        assert by_name["readme.txt"].platform is None
        assert by_name["readme.txt"].evidence == "no-ext-match"
