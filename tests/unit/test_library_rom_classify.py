# SPDX-License-Identifier: GPL-3.0-or-later
"""D1 — classificação pura de ROMs multi-plataforma, sem I/O."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from steamzero.domain.library import (
    PlatformDirectoryInventory,
    PlatformRomScanner,
    RomCandidate,
    build_ext_map,
    classify_rom,
    platform_from_magic,
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

    def test_pbp_shared_with_psp_requires_more_evidence(
        self, ext_map: dict[str, list[str]]
    ) -> None:
        plat, kind, ev = classify_rom("game.pbp", {"game.pbp"}, ext_map)
        assert plat is None
        assert kind == "unknown"
        assert ev == "ambiguous-ext"


class TestAmbiguousExtensions:
    def test_iso_shared_with_playstation_2_requires_more_evidence(
        self, ext_map: dict[str, list[str]]
    ) -> None:
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
    def test_uppercase_exclusive_extension(self, ext_map: dict[str, list[str]]) -> None:
        plat, _kind, _ev = classify_rom("GAME.Z64", {"GAME.Z64"}, ext_map)
        assert plat == "nintendo-64"

    def test_uppercase_ambiguous_extension(self, ext_map: dict[str, list[str]]) -> None:
        plat, kind, ev = classify_rom("GAME.ISO", {"GAME.ISO"}, ext_map)
        assert plat is None
        assert kind == "unknown"
        assert ev == "ambiguous-ext"

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


class TestPlatformDirectoryInventory:
    def test_maps_manifest_aliases_excludes_auxiliary_and_limits_unique_games(
        self, tmp_path: Path
    ) -> None:
        psx = tmp_path / "PSX"
        psx.mkdir()
        (psx / "Racing (Disc 1).cue").write_bytes(b"")
        (psx / "Racing (Disc 1).bin").write_bytes(b"")
        (psx / "Racing (Disc 2).cue").write_bytes(b"")
        (psx / "Racing (Disc 2).bin").write_bytes(b"")
        for index in range(12):
            (psx / f"Title {index:02}.chd").write_bytes(b"")
        (psx / "updates").mkdir()
        (psx / "updates" / "not-a-game.chd").write_bytes(b"")
        (tmp_path / "bios").mkdir()
        (tmp_path / "mystery-console").mkdir()

        inventory = PlatformDirectoryInventory.from_registry(PlatformRegistry.bundled())
        rows = {row.path.name: row for row in inventory.inventory(tmp_path)}

        assert rows["PSX"].disposition == "matched"
        assert rows["PSX"].platform_id == "playstation"
        assert rows["PSX"].game_count == 13
        assert len(rows["PSX"].selected_games) == 10
        assert all("not-a-game" not in item.path.name for item in rows["PSX"].selected_games)
        assert rows["bios"].disposition == "excluded"
        assert rows["mystery-console"].disposition == "unmatched"

    def test_does_not_follow_symlinked_content(self, tmp_path: Path) -> None:
        platform_root = tmp_path / "n64"
        platform_root.mkdir()
        target = tmp_path / "outside"
        target.mkdir()
        (target / "game.z64").write_bytes(b"")
        (platform_root / "outside").symlink_to(target, target_is_directory=True)

        inventory = PlatformDirectoryInventory.from_registry(PlatformRegistry.bundled())
        row = inventory.inventory(tmp_path)[0]

        assert row.platform_id == "nintendo-64"
        assert row.game_count == 0
        assert row.skipped_symlinks == 1


# ── Desambiguação por assinatura de cabeçalho (D1 passo 2b) ──────────────────


def _fake_reader(blob: bytes) -> Callable[[int, int], bytes]:
    """Leitor injetado: devolve fatias de um buffer sintético, sem tocar disco."""

    def read_at(offset: int, length: int) -> bytes:
        return blob[offset : offset + length]

    return read_at


def _disc_image(offset: int, magic: bytes) -> bytes:
    """Imagem mínima com a assinatura no offset esperado e zeros no resto."""
    blob = bytearray(offset + len(magic))
    blob[offset : offset + len(magic)] = magic
    return bytes(blob)


class TestPlatformFromMagic:
    def test_gamecube_magic(self) -> None:
        blob = _disc_image(0x1C, b"\xc2\x33\x9f\x3d")
        assert platform_from_magic(_fake_reader(blob)) == "nintendo-console"

    def test_wii_magic(self) -> None:
        blob = _disc_image(0x18, b"\x5d\x1c\x9e\xa3")
        assert platform_from_magic(_fake_reader(blob)) == "nintendo-console"

    def test_xbox_magic(self) -> None:
        blob = _disc_image(0x10000, b"MICROSOFT*XBOX*MEDIA")
        assert platform_from_magic(_fake_reader(blob)) == "xbox"

    def test_no_signature_is_none(self) -> None:
        assert platform_from_magic(_fake_reader(bytes(0x20000))) is None

    def test_truncated_file_is_none(self) -> None:
        """Arquivo menor que o offset não pode levantar — só não identifica."""
        assert platform_from_magic(_fake_reader(b"\x00" * 8)) is None

    def test_io_error_degrades_to_none(self) -> None:
        def broken(_offset: int, _length: int) -> bytes:
            raise OSError("disco removido no meio do scan")

        assert platform_from_magic(broken) is None


class TestClassifyWithHeader:
    def test_header_resolves_ambiguous_ext(self) -> None:
        ext_map = {".iso": ["nintendo-console", "ps2"]}
        plat, kind, ev = classify_rom(
            "game.iso", set(), ext_map, header_platform="nintendo-console"
        )
        assert (plat, kind, ev) == ("nintendo-console", "base", "magic-header")

    def test_header_outside_claimants_is_ignored(self) -> None:
        """Header apontando plataforma que não reivindica a extensão não vence."""
        ext_map = {".iso": ["ps2", "psp"]}
        plat, _kind, ev = classify_rom("game.iso", set(), ext_map, header_platform="xbox")
        assert plat is None
        assert ev == "ambiguous-ext"

    def test_header_ignored_when_ext_exclusive(self) -> None:
        ext_map = {".gcm": ["nintendo-console"]}
        _plat, _kind, ev = classify_rom("game.gcm", set(), ext_map, header_platform="xbox")
        assert ev == "exclusive-ext"

    def test_root_still_wins_over_header(self) -> None:
        ext_map = {".iso": ["nintendo-console", "ps2"]}
        plat, _kind, ev = classify_rom(
            "game.iso", set(), ext_map, root_platform="ps2", header_platform="nintendo-console"
        )
        assert (plat, ev) == ("ps2", "root-wins")

    def test_ambiguous_without_header_stays_unknown(self) -> None:
        ext_map = {".iso": ["nintendo-console", "ps2"]}
        plat, kind, ev = classify_rom("game.iso", set(), ext_map)
        assert (plat, kind, ev) == (None, "unknown", "ambiguous-ext")


class TestInventoryReadsHeader:
    def test_inventory_disambiguates_iso_by_header(self, tmp_path: Path) -> None:
        ext_map = {".iso": ["nintendo-console", "ps2"]}
        (tmp_path / "zelda.iso").write_bytes(_disc_image(0x1C, b"\xc2\x33\x9f\x3d"))
        (tmp_path / "sem-assinatura.iso").write_bytes(bytes(0x40))
        results = {r.path.name: r for r in PlatformRomScanner(ext_map).inventory(tmp_path)}
        assert results["zelda.iso"].platform == "nintendo-console"
        assert results["zelda.iso"].evidence == "magic-header"
        assert results["sem-assinatura.iso"].platform is None
        assert results["sem-assinatura.iso"].evidence == "ambiguous-ext"

    def test_exclusive_ext_never_opens_the_file(self, tmp_path: Path) -> None:
        """Extensão com dona única não paga leitura: o arquivo nem precisa abrir."""
        ext_map = {".gcm": ["nintendo-console"]}
        target = tmp_path / "game.gcm"
        target.write_bytes(b"")
        target.chmod(0o000)
        try:
            results = PlatformRomScanner(ext_map).inventory(tmp_path)
        finally:
            target.chmod(0o600)
        assert results[0].platform == "nintendo-console"
        assert results[0].evidence == "exclusive-ext"
