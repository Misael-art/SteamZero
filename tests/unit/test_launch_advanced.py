# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""LAUNCH-E2E-02 — PR C (Advanced): Cemu, RPCS3, xemu e Xenia Canary.

Matriz por emulador: fontes reais pinadas (Cemu/RPCS3/xemu Flatpak do flathub,
Xenia Canary AppImage fixado), perfil de launch declarado no platform manifest,
argv atômico e estados honestos (não instalado → motivo explícito). Nenhum
teste depende de emulador real instalado.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.adapters import emulation
from steamzero.adapters.emulation import EmulationController
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore

#: (platforma, emulador, fonte, flags de jogo declaradas antes da ROM)
_ADVANCED: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("wii-u", "cemu", "flatpak", ("-g",)),
    ("playstation-3", "rpcs3", "flatpak", ()),
    ("xbox", "xemu", "flatpak", ("-dvd_path",)),
    ("xbox-360", "xenia-canary", "appimage", ()),
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


@pytest.mark.parametrize(("platform_id", "emulator_id", "_src", "_flags"), _ADVANCED)
def test_platform_declares_launch_profile(
    monkeypatch,
    tmp_path: Path,
    platform_id: str,
    emulator_id: str,
    _src: str,
    _flags: tuple[str, ...],
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    profile = controller._launch_profile_for(platform_id, emulator_id)  # type: ignore[attr-defined]
    assert profile is not None
    assert profile.adapter_id == emulator_id
    assert not profile.requires_core


def test_flatpak_game_argv_is_atomic(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    cases = {
        "wii-u": ("cemu", "info.cemu.Cemu", ("-g",)),
        "playstation-3": ("rpcs3", "net.rpcs3.RPCS3", ()),
        "xbox": ("xemu", "app.xemu.xemu", ("-dvd_path",)),
    }
    controller = _controller(monkeypatch, tmp_path)
    rom = tmp_path / "Game [U] [X] !.iso"
    for platform_id, (emulator_id, ref, flags) in cases.items():
        profile = controller._launch_profile_for(platform_id, emulator_id)  # type: ignore[attr-defined]
        assert profile is not None
        argv = controller._build_exec_argv(  # type: ignore[attr-defined]
            profile,
            source_type="flatpak",
            flatpak_ref=ref,
            payload=None,
            rom=rom,
        )
        assert argv == ["flatpak", "run", "--user", ref, *flags, str(rom)]


def test_xenia_is_portable_and_launches_payload_with_rom(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    rom = tmp_path / "Game [U].xbe"
    payload = tmp_path / "xenia_canary_linux.AppImage"
    monkeypatch.setattr(
        emulation.AdapterEngine,
        "payload_path",
        lambda _self, _emulator_id: payload,
    )
    source_type, flatpak_ref, payload_path = controller._emulator_source("xenia-canary")  # type: ignore[attr-defined]
    assert source_type == "appimage"
    assert flatpak_ref is None

    profile = controller._launch_profile_for("xbox-360", "xenia-canary")  # type: ignore[attr-defined]
    assert profile is not None
    argv = controller._build_exec_argv(  # type: ignore[attr-defined]
        profile,
        source_type="appimage",
        flatpak_ref=None,
        payload=payload_path,
        rom=rom,
    )
    assert argv == [str(payload), str(rom)]


def test_rows_carry_real_platforms_and_specialties(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    rows = controller.snapshot({"context": {}})["platforms"][0]["emulators"]
    by_id = {row["id"]: row for row in rows}

    expected = {
        "cemu": "wii-u",
        "rpcs3": "playstation-3",
        "xemu": "xbox",
        "xenia-canary": "xbox-360",
    }
    for emulator_id, platform_id in expected.items():
        assert by_id[emulator_id]["platform"] == platform_id
        assert by_id[emulator_id]["action"]["id"] == f"emulator.install:{emulator_id}"

    assert by_id["cemu"]["specialty"].startswith("Flatpak")
    assert by_id["xenia-canary"]["specialty"].startswith("AppImage")


def test_open_launches_standalone_rpcs3(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    launched: list[tuple[str, ...]] = []
    controller._spawn = lambda argv: launched.append(tuple(argv)) or None  # type: ignore[attr-defined]
    controller._adapter_installed = lambda _adapter_id, _route: True  # type: ignore[attr-defined]

    result = controller.launch_emulator("rpcs3")
    assert result["status"] == "started"
    assert launched == [("flatpak", "run", "--user", "net.rpcs3.RPCS3")]


def test_not_installed_emulator_is_not_launchable(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """Estado honesto: emulador sem fonte instalada nunca abre."""
    controller = _controller(monkeypatch, tmp_path)
    controller._adapter_installed = lambda _adapter_id, _route: False  # type: ignore[attr-defined]
    with pytest.raises(SteamZeroError, match="não está instalado"):
        controller.launch_emulator("cemu")
