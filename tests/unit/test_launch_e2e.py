# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""LAUNCH-E2E-01 — provas da primeira vertical funcional de launch.

Nenhum destes testes depende de emulador real instalado: spawn/status/payload
são injetados e os perfis de launch vêm dos platform manifests do repo.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero.adapters.emulation import EmulationController
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain.launch_profile import LaunchProfile, parse_launch


def _launch(platform_id: str, adapter_id: str) -> dict:
    from steamzero.domain.platforms import PlatformRegistry

    registry = PlatformRegistry.bundled()
    platform = registry.get(platform_id)
    for emulator in platform.emulators:
        if emulator["adapterId"] == adapter_id:
            return emulator.get("launch") or {}
    return {}


def _new(tmp_path: Path) -> EmulationController:
    return EmulationController(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        spawn=lambda _a: 4242,
    )


class TestContractClosed:
    def test_switch_emulators_declare_launch_profile(self) -> None:
        assert _launch("switch", "eden")["gameArgs"] == ["-f", "-g", "{rom}"]
        assert _launch("switch", "citron")["gameArgs"] == ["-f", "-g", "{rom}"]
        assert _launch("switch", "ryubing")["gameArgs"] == ["-f", "--hide-updates", "{rom}"]

    def test_standalone_flatpak_declares_launch_profile(self) -> None:
        assert _launch("playstation-2", "pcsx2")["gameArgs"] == ["--fullscreen", "{rom}"]

    def test_retroarch_platform_declares_core(self) -> None:
        assert _launch("nes-famicom", "retroarch")["core"] == "mesen"

    def test_unknown_placeholder_is_rejected(self) -> None:
        with pytest.raises(SteamZeroError, match=r"placeholder n([aã])o permitido"):
            parse_launch("nes-famicom", "retroarch", {"gameArgs": ["-L", "{shell}", "{rom}"]})

    def test_shell_is_rejected(self, tmp_path: Path) -> None:
        # O contrato não tem shell: o argv final é o executor + argumentos
        # atômicos, nunca `sh -c`/`bash -c`.
        controller = _new(tmp_path)
        profile = LaunchProfile("playstation-2", "pcsx2", game_args=("--fullscreen", "{rom}"))
        argv = controller._build_exec_argv(  # type: ignore[attr-defined]
            profile,
            source_type="flatpak",
            flatpak_ref="net.pcsx2.PCSX2",
            payload=None,
            rom=tmp_path / "game.iso",
        )
        assert "sh" not in argv
        assert "bash" not in argv
        assert "-c" not in argv

    def test_rom_must_be_own_argument(self) -> None:
        with pytest.raises(SteamZeroError, match="argumento próprio"):
            parse_launch("playstation-2", "pcsx2", {"gameArgs": ["--rom={rom}"]})

    def test_core_placeholder_without_declared_core_rejected(self) -> None:
        with pytest.raises(SteamZeroError, match=r"\{core\}"):
            parse_launch("nes-famicom", "retroarch", {"gameArgs": ["-L", "{core}", "{rom}"]})

    def test_eol_source_still_declares_launch(self) -> None:
        assert _launch("playstation", "duckstation")["gameArgs"] == ["{rom}"]


class TestArgvAtomicity:
    def test_rom_with_spaces_is_a_single_argument(self, tmp_path: Path) -> None:
        controller = _new(tmp_path)
        profile = LaunchProfile("playstation-2", "pcsx2", game_args=("--fullscreen", "{rom}"))
        rom = tmp_path / "Rugby Reign [USA] (Disc 1).iso"
        argv = controller._build_exec_argv(  # type: ignore[attr-defined]
            profile,
            source_type="flatpak",
            flatpak_ref="net.pcsx2.PCSX2",
            payload=None,
            rom=rom,
        )
        assert argv[-1] == str(rom)
        assert sum(1 for item in argv if " " in item) == 1


class TestCoreRequirement:
    def test_core_missing_never_enables_jogar(self, tmp_path: Path) -> None:
        controller = _new(tmp_path)
        profile = LaunchProfile(
            "nes-famicom",
            "retroarch",
            game_args=("-L", "{core}", "{rom}"),
            core="mesen",
        )
        with pytest.raises(SteamZeroError, match="exige o core"):
            controller._build_exec_argv(  # type: ignore[attr-defined]
                profile,
                source_type="flatpak",
                flatpak_ref="org.libretro.RetroArch",
                payload=None,
                rom=tmp_path / "game.nes",
                core_path=None,
            )

    def test_core_present_is_injected(self, tmp_path: Path) -> None:
        controller = _new(tmp_path)
        profile = LaunchProfile(
            "nes-famicom", "retroarch", game_args=("-L", "{core}", "{rom}"), core="mesen"
        )
        core = tmp_path / "mesen_libretro.so"
        core.write_bytes(b"lib")
        rom = tmp_path / "game.nes"
        rom.write_text("nes")
        argv = controller._build_exec_argv(  # type: ignore[attr-defined]
            profile,
            source_type="flatpak",
            flatpak_ref="org.libretro.RetroArch",
            payload=None,
            rom=rom,
            core_path=core,
        )
        assert argv == [
            "flatpak",
            "run",
            "--user",
            "org.libretro.RetroArch",
            "-L",
            str(core),
            str(rom),
        ]


class TestNonSwitchNoKeys:
    def test_profile_parse_does_not_mention_keys(self) -> None:
        text = json.dumps(_launch("playstation-2", "pcsx2"))
        assert "keys" not in text.casefold()
