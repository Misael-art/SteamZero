# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""LAUNCH-E2E-02 — PR B (Arcade/Sega): RetroArch como família, Flycast e
validação de core por plataforma.

Matriz por emulador: RetroArch (multi-plataforma, core por plataforma) e
Flycast (Dreamcast primário, fallback RetroArch com core). Nenhum teste
depende de emulador real instalado: spawn/status são injetados, cores usam
caminhos sintéticos e os perfis vêm dos platform manifests do repo.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.adapters import emulation
from steamzero.adapters.emulation import EmulationController
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain.launch_profile import PLATFORM_CORES, parse_launch

#: Plataformas RetroArch 8-bit/16-bit/arcade com o core sancionado esperado.
RETROARCH_CORES: tuple[tuple[str, str], ...] = (
    ("nintendo-handheld", "mgba"),
    ("nes-famicom", "mesen"),
    ("snes", "snes9x"),
    ("mega-drive", "genesis_plus_gx"),
    ("arcade", "fbneo"),
    ("playstation", "swanstation"),
    ("master-system", "genesis_plus_gx"),
    ("game-gear", "genesis_plus_gx"),
    ("pc-engine-turbografx", "mednafen_pce"),
    ("atari-classics", "stella"),
    ("neo-geo-pocket", "mednafen_ngp"),
    ("wonderswan", "mednafen_wswan"),
    ("msx", "bluemsx"),
    ("zx-spectrum", "fuse"),
    ("commodore-64", "vice_x64"),
    ("amiga", "puae"),
    ("colecovision", "bluemsx"),
    ("intellivision", "freeintv"),
    ("virtual-boy", "mednafen_vb"),
    ("three-do", "opera"),
    ("sega-cd-32x", "genesis_plus_gx"),
    ("nintendo-64", "mupen64plus_next"),
    ("playstation-2", "pcsx2"),
    ("playstation-portable", "ppsspp"),
    ("nintendo-ds", "melonds"),
    ("dreamcast", "flycast"),
)


def _controller(monkeypatch, tmp_path: Path) -> EmulationController:  # type: ignore[no-untyped-def]
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return EmulationController(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        which=lambda _command: None,
        spawn=lambda _argv: None,
        secret_store=emulation.SessionSecretStore(),
    )


class TestFlycast:
    def test_dreamcast_declares_flycast_profile(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        controller = _controller(monkeypatch, tmp_path)
        profile = controller._launch_profile_for("dreamcast", "flycast")  # type: ignore[attr-defined]
        assert profile is not None
        assert profile.adapter_id == "flycast"
        assert not profile.requires_core

    def test_source_is_pinned_flatpak_ref(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        controller = _controller(monkeypatch, tmp_path)
        source_type, ref, payload = controller._emulator_source("flycast")  # type: ignore[attr-defined]
        assert source_type == "flatpak"
        assert ref == "org.flycast.Flycast"
        assert payload is None

    def test_game_argv_is_atomic_flatpak_run(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        controller = _controller(monkeypatch, tmp_path)
        profile = controller._launch_profile_for("dreamcast", "flycast")  # type: ignore[attr-defined]
        assert profile is not None
        rom = tmp_path / "Sonic Adventure (USA) [Disc 1].gdi"
        argv = controller._build_exec_argv(  # type: ignore[attr-defined]
            profile,
            source_type="flatpak",
            flatpak_ref="org.flycast.Flycast",
            payload=None,
            rom=rom,
        )
        assert argv == ["flatpak", "run", "--user", "org.flycast.Flycast", str(rom)]

    def test_row_carries_dreamcast_platform(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        controller = _controller(monkeypatch, tmp_path)
        rows = controller._emulator_rows()  # workspace do Switch lista só o Switch
        row = next(item for item in rows if item["id"] == "flycast")
        assert row["platform"] == "dreamcast"
        assert "Flatpak" in row["specialty"]
        assert row["action"]["id"] == "emulator.install:flycast"

    def test_retroarch_fallback_declares_flycast_core(self) -> None:
        profile = parse_launch(
            "dreamcast",
            "retroarch",
            {"core": "flycast", "openArgs": [], "gameArgs": ["-L", "{core}", "{rom}"]},
        )
        assert profile is not None
        assert profile.requires_core
        assert profile.core == "flycast"


class TestRetroArchFamily:
    def test_retroarch_has_a_row_in_the_center(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        controller = _controller(monkeypatch, tmp_path)
        rows = controller._emulator_rows()  # workspace do Switch lista só o Switch
        row = next(item for item in rows if item["id"] == "retroarch")
        assert "Flatpak" in row["specialty"]
        assert row["action"]["id"] == "emulator.install:retroarch"

    def test_open_launches_standalone_retroarch(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        controller = _controller(monkeypatch, tmp_path)
        launched: list[tuple[str, ...]] = []
        controller._spawn = lambda argv: launched.append(tuple(argv)) or None  # type: ignore[attr-defined]
        controller._adapter_installed = lambda _adapter_id, _route: True  # type: ignore[attr-defined]

        result = controller.launch_emulator("retroarch")
        assert result["status"] == "started"
        assert launched == [("flatpak", "run", "--user", "org.libretro.RetroArch")]

    @pytest.mark.parametrize(("platform_id", "core"), RETROARCH_CORES)
    def test_platform_declares_sanctioned_core(
        self, monkeypatch, tmp_path: Path, platform_id: str, core: str
    ) -> None:  # type: ignore[no-untyped-def]
        controller = _controller(monkeypatch, tmp_path)
        profile = controller._launch_profile_for(platform_id, "retroarch")  # type: ignore[attr-defined]
        assert profile is not None
        assert profile.requires_core
        assert profile.core == core
        assert core in PLATFORM_CORES[platform_id]

    @pytest.mark.parametrize(("platform_id", "core"), RETROARCH_CORES)
    def test_game_argv_injects_core_and_rom(
        self, monkeypatch, tmp_path: Path, platform_id: str, core: str
    ) -> None:  # type: ignore[no-untyped-def]
        controller = _controller(monkeypatch, tmp_path)
        profile = controller._launch_profile_for(platform_id, "retroarch")  # type: ignore[attr-defined]
        assert profile is not None
        core_path = tmp_path / f"{core}_libretro.so"
        core_path.write_bytes(b"lib")
        rom = tmp_path / "Game [U] [!].rom"
        argv = controller._build_exec_argv(  # type: ignore[attr-defined]
            profile,
            source_type="flatpak",
            flatpak_ref="org.libretro.RetroArch",
            payload=None,
            rom=rom,
            core_path=core_path,
        )
        assert argv == [
            "flatpak",
            "run",
            "--user",
            "org.libretro.RetroArch",
            "-L",
            str(core_path),
            str(rom),
        ]


class TestCoreSanctioning:
    def test_core_from_another_platform_is_rejected(self) -> None:
        with pytest.raises(SteamZeroError, match="não é sancionado"):
            parse_launch(
                "nes-famicom",
                "retroarch",
                {"core": "snes9x", "gameArgs": ["-L", "{core}", "{rom}"]},
            )

    def test_nonexistent_core_is_rejected(self) -> None:
        with pytest.raises(SteamZeroError, match="não é sancionado"):
            parse_launch(
                "snes",
                "retroarch",
                {"core": "totally_fake", "gameArgs": ["-L", "{core}", "{rom}"]},
            )

    def test_platform_without_sanctioned_cores_rejects_any_core(self) -> None:
        with pytest.raises(SteamZeroError, match="sancionados: nenhum"):
            parse_launch(
                "switch",
                "retroarch",
                {"core": "mesen", "gameArgs": ["-L", "{core}", "{rom}"]},
            )

    def test_sanctioned_core_parses(self) -> None:
        profile = parse_launch(
            "arcade", "retroarch", {"core": "fbneo", "gameArgs": ["-L", "{core}", "{rom}"]}
        )
        assert profile is not None
        assert profile.core == "fbneo"

    def test_all_bundled_manifest_cores_are_sanctioned(self) -> None:
        """Varredura do contrato: todo core declarado pertence à plataforma."""
        from steamzero.domain.platforms import PlatformRegistry

        registry = PlatformRegistry.bundled()
        for platform in registry.list():
            for emulator in platform.emulators:
                launch = emulator.get("launch")
                if launch is None:
                    continue
                core = launch.get("core")
                if core is None:
                    continue
                assert core in PLATFORM_CORES.get(platform.id, frozenset()), (
                    f"{platform.id}/{emulator['adapterId']} declara core {core!r} "
                    "fora do registro sancionado"
                )
