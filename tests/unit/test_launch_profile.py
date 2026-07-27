# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato declarativo de lançamento.

Fechado de propósito: sem comando livre, sem template textual, sem shell. O que
estes testes protegem é a propriedade que torna isso seguro — a ROM entra como
argumento atômico, montado por substituição posicional, então nome hostil é
apenas um nome, nunca um comando.

E o RetroArch traz a segunda propriedade: uma instalação atende dezenas de
plataformas, cada uma com seu core. Core ausente precisa RECUSAR Jogar, não
oferecer um botão que falha depois.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.launch_profile import (
    LaunchProfile,
    build_argv,
    find_core,
    parse_launch,
)

_MANIFESTS = Path(__file__).resolve().parents[2] / "src" / "steamzero" / "platform_manifests"


def _profile(**overrides: object) -> LaunchProfile:
    base: dict[str, object] = {
        "platform_id": "snes",
        "adapter_id": "retroarch",
        "game_args": ("-L", "{core}", "{rom}"),
        "core": "snes9x",
    }
    base.update(overrides)
    return LaunchProfile(**base)  # type: ignore[arg-type]


class TestRomIsAtomic:
    """A propriedade que substitui escaping: a ROM nunca é concatenada."""

    @pytest.mark.parametrize(
        "name",
        [
            "Jogo com espaço.sfc",
            "Jogo; rm -rf tudo.sfc",
            'Jogo "com aspas".sfc',
            "Jogo $(whoami).sfc",
            "Jogo`id`.sfc",
            "Jogo | tee saida.sfc",
            "Jogo\\barra.sfc",
            "Jogo'apóstrofo.sfc",
        ],
    )
    def test_hostile_names_stay_single_arguments(self, name: str) -> None:
        rom = Path("/roms") / name
        argv = build_argv(_profile(), "/usr/bin/retroarch", rom=rom, core_path=Path("/c.so"))
        assert argv[-1] == str(rom)
        assert len(argv) == 4, "cada placeholder ocupa exatamente um argumento"

    def test_core_path_is_also_atomic(self) -> None:
        core = Path("/lib/com espaço/snes9x_libretro.so")
        argv = build_argv(_profile(), "/usr/bin/retroarch", rom=Path("/r.sfc"), core_path=core)
        assert str(core) in argv

    def test_executable_leads_the_argv(self) -> None:
        argv = build_argv(
            _profile(), "/usr/bin/retroarch", rom=Path("/r.sfc"), core_path=Path("/c")
        )
        assert argv[0] == "/usr/bin/retroarch"


class TestContractIsClosed:
    def test_unknown_placeholder_is_refused(self) -> None:
        with pytest.raises(SteamZeroError, match="placeholder não permitido"):
            parse_launch("snes", "retroarch", {"gameArgs": ["{rom}", "{home}"]})

    def test_rom_must_be_its_own_argument(self) -> None:
        """ "--rom={rom}" passaria numa checagem de substring e deixaria o caminho
        colado à flag."""
        with pytest.raises(SteamZeroError, match="argumento próprio"):
            parse_launch("snes", "retroarch", {"gameArgs": ["--rom={rom}"]})

    def test_core_placeholder_without_core_is_refused(self) -> None:
        with pytest.raises(SteamZeroError, match="sem declarar core"):
            parse_launch("snes", "retroarch", {"gameArgs": ["-L", "{core}", "{rom}"]})

    def test_missing_game_args_is_refused(self) -> None:
        with pytest.raises(SteamZeroError, match="gameArgs"):
            parse_launch("snes", "retroarch", {"openArgs": []})

    def test_non_string_args_are_refused(self) -> None:
        with pytest.raises(SteamZeroError, match="lista de strings"):
            parse_launch("snes", "retroarch", {"gameArgs": ["{rom}", 42]})

    def test_nul_byte_is_refused(self) -> None:
        with pytest.raises(SteamZeroError, match="NUL"):
            parse_launch("snes", "retroarch", {"gameArgs": ["{rom}", "a\x00b"]})

    def test_invalid_core_name_is_refused(self) -> None:
        with pytest.raises(SteamZeroError, match="core inválido"):
            parse_launch("snes", "retroarch", {"gameArgs": ["{rom}"], "core": "../escape"})

    def test_absent_launch_means_not_launchable(self) -> None:
        """Ausência é estado legítimo e precisa ser visível, não um erro."""
        assert parse_launch("x", "y", None) is None


class TestCoreIsRequiredBeforePlaying:
    def test_missing_core_refuses_launch(self) -> None:
        with pytest.raises(SteamZeroError, match="exige o core"):
            build_argv(_profile(), "/usr/bin/retroarch", rom=Path("/r.sfc"), core_path=None)

    def test_platform_without_core_launches_directly(self) -> None:
        """Standalone não precisa de core: o contrato não pode exigir um."""
        profile = _profile(core=None, game_args=("{rom}",))
        assert build_argv(profile, "/usr/bin/ppsspp", rom=Path("/j.iso")) == [
            "/usr/bin/ppsspp",
            "/j.iso",
        ]

    def test_absent_core_is_reported_not_raised(self, tmp_path: Path) -> None:
        """find_core devolve None para a UI dizer "instale o core"."""
        assert find_core("snes9x", search_paths=[tmp_path]) is None

    def test_present_core_is_found(self, tmp_path: Path) -> None:
        (tmp_path / "snes9x_libretro.so").write_bytes(b"\x7fELF")
        assert find_core("snes9x", search_paths=[tmp_path]) == tmp_path / "snes9x_libretro.so"

    def test_core_name_is_validated_before_touching_disk(self) -> None:
        with pytest.raises(SteamZeroError, match="nome de core inválido"):
            find_core("../../etc/passwd")

    def test_first_matching_path_wins(self, tmp_path: Path) -> None:
        first, second = tmp_path / "a", tmp_path / "b"
        first.mkdir()
        second.mkdir()
        (first / "mgba_libretro.so").write_bytes(b"1")
        (second / "mgba_libretro.so").write_bytes(b"2")
        assert find_core("mgba", search_paths=[first, second]) == first / "mgba_libretro.so"


class TestDeclaredPlatformsAreCoherent:
    """Os perfis reais dos manifests precisam sobreviver ao parser."""

    def _platforms(self):  # type: ignore[no-untyped-def]
        for path in sorted(_MANIFESTS.glob("*.platform.json")):
            yield json.loads(path.read_text(encoding="utf-8"))

    def test_every_declared_launch_parses(self) -> None:
        parsed = 0
        for platform in self._platforms():
            for emulator in platform.get("emulators", []):
                profile = parse_launch(
                    platform["id"], emulator["adapterId"], emulator.get("launch")
                )
                if profile is not None:
                    parsed += 1
        assert parsed >= 23, f"esperava perfis declarados, encontrei {parsed}"

    def test_retroarch_platforms_declare_a_core(self) -> None:
        """RetroArch sem core não sabe o que carregar."""
        for platform in self._platforms():
            for emulator in platform.get("emulators", []):
                if emulator["adapterId"] != "retroarch":
                    continue
                profile = parse_launch(platform["id"], "retroarch", emulator.get("launch"))
                if profile is None:
                    continue
                assert profile.core, f"{platform['id']} usa RetroArch sem core declarado"

    def test_one_install_serves_many_platforms(self) -> None:
        """A propriedade central do RetroArch: um adapter, muitos cores."""
        cores: dict[str, str] = {}
        for platform in self._platforms():
            for emulator in platform.get("emulators", []):
                if emulator["adapterId"] != "retroarch":
                    continue
                profile = parse_launch(platform["id"], "retroarch", emulator.get("launch"))
                if profile is not None and profile.core:
                    cores[platform["id"]] = profile.core
        assert len(cores) >= 23
        assert len(set(cores.values())) > 1, "cores diferentes por plataforma"

    def test_standalone_platforms_keep_precedence_over_retroarch(self) -> None:
        """Onde existe standalone dedicado, RetroArch é alternativa, não padrão."""
        for platform in self._platforms():
            rows = {e["adapterId"]: e["precedence"] for e in platform.get("emulators", [])}
            if len(rows) > 1 and "retroarch" in rows:
                best = min(rows, key=lambda a: rows[a])
                assert best != "retroarch", (
                    f"{platform['id']} deveria preferir o standalone dedicado"
                )
