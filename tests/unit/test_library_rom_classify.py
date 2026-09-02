# SPDX-License-Identifier: GPL-3.0-or-later
"""D1 — classificação pura de ROMs multi-plataforma, sem I/O."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import ClassVar

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


class TestArchivePolicyDecidesInsteadOfABlanketVeto:
    """Contrato alterado em 2026-09-01: quem decide é a plataforma.

    Antes, `.zip`/`.7z` saíam do catálogo por uma lista fixa, antes de qualquer
    pergunta — o veto vencia a declaração dos manifestos. Mas 45 dos 63
    manifestos declaram `zip` entre as extensões e 22 declaram
    `containerPolicy: native`, isto é, o container roda direto no emulador.
    No acervo real do operador isso mantinha ~939 arquivos invisíveis.

    O que NÃO mudou: sem declaração, o arquivo continua fora do catálogo. A
    diferença é que agora o motivo é dito, e um palpite nunca substitui a
    declaração ausente.
    """

    def test_an_undeclared_policy_still_keeps_the_archive_out(
        self, ext_map: dict[str, list[str]]
    ) -> None:
        plat, kind, ev = classify_rom(
            "game.zip", {"game.zip"}, ext_map, root_platform="nes-famicom"
        )
        assert plat is None
        assert kind == "unknown"
        assert ev == "archive-policy-undeclared"

    def test_7z_follows_the_same_contract(self, ext_map: dict[str, list[str]]) -> None:
        plat, kind, ev = classify_rom(
            "game.7z",
            {"game.7z"},
            ext_map,
            root_platform="nes-famicom",
            container_policies={"nes-famicom": "native"},
        )
        assert plat == "nes-famicom"
        assert kind == "base"
        assert ev == "archive-native"

    def test_a_native_container_becomes_a_playable_game(
        self, ext_map: dict[str, list[str]]
    ) -> None:
        plat, kind, ev = classify_rom(
            "game.zip",
            {"game.zip"},
            ext_map,
            root_platform="nes-famicom",
            container_policies={"nes-famicom": "native"},
        )
        assert plat == "nes-famicom"
        assert kind == "base"
        assert ev == "archive-native"

    def test_an_extractable_container_says_so_instead_of_vanishing(
        self, ext_map: dict[str, list[str]]
    ) -> None:
        """`extract` não é canonizável hoje, mas é outro problema que `native`.

        O `archived` genérico misturava "precisa de trabalho" com "precisa de
        declaração"; sem distinguir, não há como saber o que falta implementar.
        """
        plat, kind, ev = classify_rom(
            "game.zip",
            {"game.zip"},
            ext_map,
            root_platform="switch",
            container_policies={"switch": "extract"},
        )
        assert plat is None
        assert kind == "unknown"
        assert ev == "archive-needs-extraction"

    def test_an_ambiguous_extension_is_not_guessed(self, ext_map: dict[str, list[str]]) -> None:
        """Sem raiz declarada, `.zip` pertence a dezenas de plataformas.

        Escolher uma delas repetiria o defeito dos defaults de Switch corrigido
        horas antes: um palpite silencioso que aponta para a plataforma errada.
        """
        plat, _kind, ev = classify_rom(
            "game.zip",
            {"game.zip"},
            ext_map,
            container_policies={"nes-famicom": "native", "snes": "native"},
        )
        assert plat is None
        assert ev == "archive-platform-unknown"


class TestCueBinPairing:
    def test_cue_with_bin_sibling_is_ambiguous_without_declaration(
        self, ext_map: dict[str, list[str]]
    ) -> None:
        siblings = _mksiblings("game.cue", "game.bin", "track02.bin")
        plat, kind, ev = classify_rom("game.cue", siblings, ext_map)
        assert plat is None
        assert kind == "unknown"
        assert ev == "ambiguous-cue"

    def test_declared_unique_cue_pair_identifies_platform(self) -> None:
        ext_map = {".cue": ["test-cd"], ".bin": ["test-cd"]}
        formats = {"test-cd": {"cue-bin": ["cue", "bin"]}}
        siblings = _mksiblings("game.cue", "game.bin")
        plat, kind, ev = classify_rom("game.cue", siblings, ext_map, platform_formats=formats)
        assert (plat, kind, ev) == ("test-cd", "base", "cue-pair")

    def test_cue_without_bin_is_orphan(self, ext_map: dict[str, list[str]]) -> None:
        siblings = _mksiblings("game.cue")
        plat, kind, ev = classify_rom("game.cue", siblings, ext_map)
        assert plat is None
        assert kind == "unknown"
        assert ev == "cue-orphan"

    def test_bin_with_cue_sibling_is_ambiguous_without_declaration(
        self, ext_map: dict[str, list[str]]
    ) -> None:
        siblings = _mksiblings("game.cue", "game.bin")
        plat, kind, ev = classify_rom("game.bin", siblings, ext_map)
        assert plat is None
        assert kind == "unknown"
        assert ev == "ambiguous-cue-bin"

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

    def test_root_platform_alone_does_not_canonize_an_archive(
        self, ext_map: dict[str, list[str]]
    ) -> None:
        """A raiz diz QUAL plataforma, não que o container roda nela.

        Contrato alterado em 2026-09-01: a raiz deixou de ser irrelevante para
        arquivos comprimidos, mas continua não bastando. Sem `containerPolicy`
        declarada, o arquivo fica fora — a raiz não substitui a declaração.
        """
        plat, kind, ev = classify_rom(
            "game.zip", {"game.zip"}, ext_map, root_platform="nintendo-console"
        )
        assert plat is None
        assert kind == "unknown"
        assert ev == "archive-policy-undeclared"

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
        plat, kind, ev = classify_rom("Game.CUE", siblings, ext_map)
        assert plat is None
        assert kind == "unknown"
        assert ev == "ambiguous-cue"


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
        assert results["game.cue"].platform is None
        assert results["game.cue"].evidence == "ambiguous-cue"
        assert results["game.bin"].platform is None
        assert results["game.bin"].evidence == "ambiguous-cue-bin"
        assert results["track02.bin"].platform is None
        assert results["track02.bin"].evidence == "bin-orphan"

    def test_zip_without_a_declared_policy_is_unknown(
        self, tmp_path: Path, ext_map: dict[str, list[str]]
    ) -> None:
        (tmp_path / "rom.zip").write_text("")
        scanner = PlatformRomScanner(ext_map)
        results = list(scanner.inventory(tmp_path))
        assert len(results) == 1
        assert results[0].platform is None
        assert results[0].content_kind == "unknown"
        # Sem raiz declarada a ambiguidade aparece primeiro: `.zip` pertence a
        # 45 plataformas, e nenhuma delas pode ser escolhida por eliminação.
        assert results[0].evidence == "archive-platform-unknown"

    def test_a_native_container_carries_the_container_as_its_format(
        self, tmp_path: Path, ext_map: dict[str, list[str]]
    ) -> None:
        """Só `arcade` lista `zip` em `media.formats`.

        Sem este ajuste o jogo entraria no catálogo com formato `unknown`, e o
        formato é o que o caminho de lançamento entrega ao emulador.
        """
        (tmp_path / "rom.zip").write_text("")
        scanner = PlatformRomScanner(ext_map, None, {"nes-famicom": "native"})
        results = list(scanner.inventory(tmp_path, root_platform="nes-famicom"))
        assert len(results) == 1
        assert results[0].platform == "nes-famicom"
        assert results[0].content_kind == "base"
        assert results[0].format == "zip"

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
    def test_keeps_manifest_declared_auxiliary_content(self, tmp_path: Path) -> None:
        wiiu = tmp_path / "Wii U"
        (wiiu / "updates").mkdir(parents=True)
        (wiiu / "dlc").mkdir()
        (wiiu / "Game.wud").write_bytes(b"")
        (wiiu / "updates" / "Game Update.wud").write_bytes(b"")
        (wiiu / "dlc" / "Game DLC.wud").write_bytes(b"")

        row = PlatformDirectoryInventory.from_registry(PlatformRegistry.bundled()).inventory(
            tmp_path
        )[0]

        assert [item.content_kind for item in row.selected_games] == ["base"]
        assert {item.content_kind for item in row.auxiliary_content} == {"update", "dlc"}

    def test_maps_manifest_aliases_and_selects_every_unique_game(self, tmp_path: Path) -> None:
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
        # Fonte canônica não amostra: os 13 únicos (12 títulos + o grupo
        # multidisco) estão todos selecionados.
        assert len(rows["PSX"].selected_games) == 13
        assert all("not-a-game" not in item.path.name for item in rows["PSX"].selected_games)
        assert rows["bios"].disposition == "excluded"
        assert rows["mystery-console"].disposition == "unmatched"

    def test_maps_esde_names_of_already_supported_platforms(self, tmp_path: Path) -> None:
        """Nomes ES-DE da MESMA plataforma de um manifesto existente casam.

        Variações regionais e de grafia do próprio console — nunca plataforma
        diferente. O que não tem manifesto continua ``unmatched`` para o
        humano decidir, porque extensão não adivinha plataforma.
        """
        esperados = {
            "gc": "nintendo-console",
            "megadrivejp": "mega-drive",
            "megacd": "sega-cd-32x",
            "megacdjp": "sega-cd-32x",
            "sega32xjp": "sega-cd-32x",
            "sega32xna": "sega-cd-32x",
            "msx1": "msx",
        }
        for name in esperados:
            (tmp_path / name).mkdir()
        # Serviços não-jogo ficam excluídos, não matched nem unmatched.
        for name in ("emulators", "generic-applications", "kodi"):
            (tmp_path / name).mkdir()

        inventory = PlatformDirectoryInventory.from_registry(PlatformRegistry.bundled())
        rows = {row.path.name: row for row in inventory.inventory(tmp_path)}

        for name, platform_id in esperados.items():
            assert rows[name].disposition == "matched", name
            assert rows[name].platform_id == platform_id, name
        for name in ("emulators", "generic-applications", "kodi"):
            assert rows[name].disposition == "excluded", name
        # Ainda sem manifesto e sem caminho de emulação declarável: decisão
        # pendente de produto, não casamento. (Saturn se formou no lote 1;
        # amstradcpc segue sem manifesto.)
        (tmp_path / "amstradcpc").mkdir()
        rows = {row.path.name: row for row in inventory.inventory(tmp_path)}
        assert rows["amstradcpc"].disposition == "unmatched"

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


class TestSyntheticRomFixtures:
    """Validates synthetic test ROMs in tests/fixtures/roms/ are scannable."""

    EXCLUSIVE_PLATFORMS: ClassVar[dict[str, str]] = {
        "amiga": ".adf",
        "atari-classics": ".a26",
        "intellivision": ".int",
        "neo-geo-pocket": ".ngc",
        "nes-famicom": ".nes",
        "nintendo-3ds": ".3dsx",
        "nintendo-64": ".n64",
        "nintendo-console": ".gcm",
        "nintendo-ds": ".nds",
        "nintendo-handheld": ".gb",
        "pc-engine-turbografx": ".pce",
        "snes": ".sfc",
        "virtual-boy": ".vb",
        "wonderswan": ".ws",
    }

    def test_exclusive_ext_fixtures_auto_detect(
        self, ext_map: dict[str, list[str]], tmp_path: Path
    ) -> None:
        """Fixtures with exclusive extensions are detected without root_platform."""
        fixtures = Path(__file__).resolve().parent.parent / "fixtures" / "roms"
        scanner = PlatformRomScanner(ext_map)
        for platform_id, ext in self.EXCLUSIVE_PLATFORMS.items():
            rom = fixtures / platform_id / f"test-rom{ext}"
            if not rom.exists():
                continue
            # Use a clean subdirectory for each fixture
            plat_dir = tmp_path / platform_id
            plat_dir.mkdir()
            (plat_dir / f"test-rom{ext}").write_bytes(rom.read_bytes())
            results = scanner.inventory(plat_dir)
            assert len(results) == 1
            assert results[0].platform == platform_id
            assert results[0].evidence == "exclusive-ext"

    def test_root_platform_hint_classifies_non_archived_fixtures(
        self, ext_map: dict[str, list[str]]
    ) -> None:
        """Non-archive fixtures are classified when root_platform is provided."""
        fixtures = Path(__file__).resolve().parent.parent / "fixtures" / "roms"
        scanner = PlatformRomScanner(ext_map)
        for sys_dir in sorted(fixtures.iterdir()):
            if not sys_dir.is_dir():
                continue
            for rom_file in sys_dir.iterdir():
                if not rom_file.is_file():
                    continue
                # Arquivo comprimido segue a política de container da
                # plataforma, coberta em TestArchivePolicyDecidesInsteadOfABlanketVeto;
                # aqui o que se verifica é a dica de raiz.
                if rom_file.suffix.lower() == ".zip":
                    continue
                result = scanner.inventory(sys_dir, root_platform=sys_dir.name)
                assert len(result) == 1
                assert result[0].platform == sys_dir.name
                assert result[0].evidence == "root-wins"


class TestDirectoryInventoryNamesTheFormat:
    """O inventário canônico entrava sem formato.

    `detect_format` era chamado sem o mapa declarado pela plataforma, então
    respondia `unknown` para tudo: 216 dos 231 jogos do acervo real do operador
    estavam no catálogo com `format: "unknown"` (medido em 2026-09-01 na
    release 2.0.0rc1-667789588f23). O formato é o que o caminho de lançamento
    entrega ao emulador, e o scanner já carregava o mapa.
    """

    def _tree(self, root: Path) -> None:
        nes = root / "nes"
        nes.mkdir()
        (nes / "Metroid.nes").write_bytes(b"NES\x1a" + b"0" * 32)
        (nes / "Contra.zip").write_bytes(b"PK\x03\x04" + b"0" * 32)

    def test_a_declared_extension_gets_its_declared_format(self, tmp_path: Path) -> None:
        self._tree(tmp_path)
        inventory = PlatformDirectoryInventory.from_registry(PlatformRegistry.bundled())
        found = {
            game.path.name: game
            for directory in inventory.inventory(tmp_path)
            for game in directory.selected_games
        }
        assert found["Metroid.nes"].format == "nes", (
            "sem o mapa declarado o catálogo inteiro entrava com formato unknown"
        )

    def test_a_native_container_is_its_own_format(self, tmp_path: Path) -> None:
        self._tree(tmp_path)
        inventory = PlatformDirectoryInventory.from_registry(PlatformRegistry.bundled())
        found = {
            game.path.name: game
            for directory in inventory.inventory(tmp_path)
            for game in directory.selected_games
        }
        assert found["Contra.zip"].format == "zip"
        assert found["Contra.zip"].evidence == "archive-native"


class TestSystemIdComesFromTheDisk:
    """O sistema que o usuário já organizou não precisa ser inventado.

    O manifesto agrupa por runtime compartilhado: `nintendo-handheld` cobre gb,
    gbc e gba porque o emulador é o mesmo. Isso vazou para a experiência — 296
    jogos do acervo real apareciam como "nintendo-handheld" enquanto o disco tem
    `roms/gb`, `roms/gbc` e `roms/gba` separados.

    Medido em 2026-09-02 após a correção: 1005 dos 1119 jogos resolvem sistema
    (170 gbc, 147 nes, 111 famicom, 77 gb, 49 gba…); os demais ficam nulos.
    """

    def test_the_directory_decides_the_system(self, tmp_path: Path) -> None:
        from steamzero.domain.library import system_for_path

        rom = tmp_path / "gbc" / "jogo.gbc"
        rom.parent.mkdir(parents=True)
        rom.write_bytes(b"0")
        assert system_for_path(rom, tmp_path, ("gb", "gbc", "gba")) == "gbc"

    def test_the_most_specific_directory_wins(self, tmp_path: Path) -> None:
        from steamzero.domain.library import system_for_path

        rom = tmp_path / "gb" / "gba" / "jogo.gba"
        rom.parent.mkdir(parents=True)
        rom.write_bytes(b"0")
        assert system_for_path(rom, tmp_path, ("gb", "gbc", "gba")) == "gba", (
            "o diretório mais próximo do arquivo é o que declara o sistema"
        )

    def test_no_declaration_stays_null_instead_of_guessing(self, tmp_path: Path) -> None:
        """Adivinhar por extensão erraria: 43 das 213 extensões são disputadas.

        Sem sinal, o jogo fica no grupo e a UI mostra o grupo — mesma regra do
        `containerPolicy` e da plataforma.
        """
        from steamzero.domain.library import system_for_path

        rom = tmp_path / "diversos" / "jogo.gba"
        rom.parent.mkdir(parents=True)
        rom.write_bytes(b"0")
        assert system_for_path(rom, tmp_path, ("gb", "gbc", "gba")) is None

    def test_declared_system_names_are_unique_across_platforms(self) -> None:
        """É esta unicidade que torna o diretório uma evidência confiável.

        Gate de expansão: dois manifestos declarando o mesmo `system` tornariam
        o diretório ambíguo e a derivação, um palpite.
        """
        from collections import Counter

        counts = Counter(
            name for platform in PlatformRegistry.bundled().list() for name in platform.systems
        )
        repetidos = [name for name, total in counts.items() if total > 1]
        assert not repetidos, f"nome de sistema declarado em mais de uma plataforma: {repetidos}"
