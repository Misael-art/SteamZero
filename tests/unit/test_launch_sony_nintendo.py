# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""LAUNCH-E2E-02 — launch contratado para Dolphin, PPSSPP, melonDS e Azahar.

Matriz por emulador (PR A — Sony/Nintendo):
Fonte Flatpak do flathub, instalação/atualização via FlatpakExecutor, perfil de
launch declarado no platform manifest, argv ``flatpak run --user <ref>``, stop
pela sessão registrada. Nenhum teste instala nada no host.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from steamzero.adapters import emulation
from steamzero.adapters.emulation import EmulationController
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore

#: (plataforma, emulador, ref flatpak fixada no adapter manifest)
_SONY_NINTENDO: tuple[tuple[str, str, str], ...] = (
    ("nintendo-console", "dolphin", "org.DolphinEmu.dolphin-emu"),
    ("playstation-portable", "ppsspp", "org.ppsspp.PPSSPP"),
    ("nintendo-ds", "melonds", "net.kuribo64.melonDS"),
    ("nintendo-3ds", "azahar", "org.azahar_emu.Azahar"),
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


def _apply(controller: EmulationController, plan: dict[str, object]) -> dict[str, object]:
    return controller.apply_action(str(plan["planId"]), str(plan["confirmToken"]))


@pytest.mark.parametrize(
    ("platform_id", "emulator_id", "flatpak_ref"),
    _SONY_NINTENDO,
)
def test_platform_declares_launch_profile_for_emulator(
    monkeypatch, tmp_path: Path, platform_id: str, emulator_id: str, flatpak_ref: str
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    profile = controller._launch_profile_for(platform_id, emulator_id)  # type: ignore[attr-defined]
    assert profile is not None
    assert profile.adapter_id == emulator_id
    assert not profile.requires_core


@pytest.mark.parametrize(
    ("platform_id", "emulator_id", "flatpak_ref"),
    _SONY_NINTENDO,
)
def test_emulator_source_is_pinned_flatpak_ref(
    monkeypatch, tmp_path: Path, platform_id: str, emulator_id: str, flatpak_ref: str
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    source_type, ref, payload = controller._emulator_source(emulator_id)  # type: ignore[attr-defined]
    assert source_type == "flatpak"
    assert ref == flatpak_ref
    assert payload is None


@pytest.mark.parametrize(
    ("platform_id", "emulator_id", "flatpak_ref"),
    _SONY_NINTENDO,
)
def test_game_argv_is_atomic_flatpak_run(
    monkeypatch, tmp_path: Path, platform_id: str, emulator_id: str, flatpak_ref: str
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    profile = controller._launch_profile_for(platform_id, emulator_id)  # type: ignore[attr-defined]
    assert profile is not None
    rom = tmp_path / "Game With Spaces [U].iso"
    argv = controller._build_exec_argv(  # type: ignore[attr-defined]
        profile,
        source_type="flatpak",
        flatpak_ref=flatpak_ref,
        payload=None,
        rom=rom,
    )
    assert argv == ["flatpak", "run", "--user", flatpak_ref, str(rom)]


@pytest.mark.parametrize(
    ("platform_id", "emulator_id", "flatpak_ref"),
    _SONY_NINTENDO,
)
def test_open_argv_launches_standalone_app(
    monkeypatch, tmp_path: Path, platform_id: str, emulator_id: str, flatpak_ref: str
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    profile = controller._launch_profile_for(platform_id, emulator_id)  # type: ignore[attr-defined]
    assert profile is not None
    argv = controller._build_exec_argv(  # type: ignore[attr-defined]
        profile,
        source_type="flatpak",
        flatpak_ref=flatpak_ref,
        payload=None,
    )
    assert argv == ["flatpak", "run", "--user", flatpak_ref]


def test_retroarch_fallback_declares_cores(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    expected = {
        ("nintendo-console", "retroarch"): "dolphin",
        ("playstation-portable", "retroarch"): "ppsspp",
        ("nintendo-ds", "retroarch"): "melonds",
    }
    for (platform_id, adapter_id), core in expected.items():
        profile = controller._launch_profile_for(platform_id, adapter_id)  # type: ignore[attr-defined]
        assert profile is not None
        assert profile.requires_core
        assert profile.core == core


def test_key_projection_is_vacuous_for_non_switch(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    for _platform_id, emulator_id, _ref in _SONY_NINTENDO:
        assert controller._key_projection_valid(emulator_id)  # type: ignore[attr-defined]


def test_game_emulator_set_accepts_sony_nintendo(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    roms = tmp_path / "owned-roms"
    roms.mkdir()
    (roms / "Example [0100ABCDEF123000].nsp").write_bytes(b"owned-game")
    _apply(
        controller,
        controller.plan_action({"actionId": "library.root.add", "path": str(roms)}),
    )
    game_id = controller.snapshot({"context": {}})["platforms"][0]["games"][0]["id"]

    for _platform_id, emulator_id, _ref in _SONY_NINTENDO:
        plan = controller.plan_action(
            {"actionId": "game.emulator.set", "gameId": game_id, "emulatorId": emulator_id}
        )
        assert plan["planId"]

    applied = _apply(
        controller,
        controller.plan_action(
            {"actionId": "game.emulator.set", "gameId": game_id, "emulatorId": "dolphin"}
        ),
    )
    assert applied["status"] == "ok"

    plan = controller.plan_action({"actionId": "game.emulator.default", "emulatorId": "ppsspp"})
    assert plan["planId"]


def test_unknown_emulator_is_still_rejected(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    with pytest.raises(SteamZeroError, match="emulador não declarado"):
        controller.plan_action({"actionId": "game.emulator.default", "emulatorId": "lolicon"})


def test_emulator_rows_carry_real_platform_and_flatpak_specialty(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    rows = controller.snapshot({"context": {}})["platforms"][0]["emulators"]
    by_id = {row["id"]: row for row in rows}
    expected_platform = {
        "dolphin": "nintendo-console",
        "ppsspp": "playstation-portable",
        "melonds": "nintendo-ds",
        "azahar": "nintendo-3ds",
    }
    for emulator_id, platform_id in expected_platform.items():
        row = by_id[emulator_id]
        assert row["platform"] == platform_id
        assert "Flatpak" in row["specialty"]
        assert row["action"]["id"] == f"emulator.install:{emulator_id}"


def test_launch_emulator_starts_pinned_flatpak(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    launched: list[tuple[str, ...]] = []
    controller._spawn = lambda argv: launched.append(tuple(argv)) or None  # type: ignore[attr-defined]
    controller._adapter_installed = lambda _adapter_id, _route: True  # type: ignore[attr-defined]

    result = controller.launch_emulator("dolphin")
    assert result["status"] == "started"
    assert result["emulatorId"] == "dolphin"
    assert launched == [("flatpak", "run", "--user", "org.DolphinEmu.dolphin-emu")]

    stopped = controller.stop_emulator("dolphin")
    assert stopped["status"] == "not-running"


def test_stop_flatpak_emulator_terminates_registered_session(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    process = subprocess.Popen(
        ["sleep", "30"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        assert process.pid > 1
        controller._running_pids["melonds"] = process.pid  # type: ignore[attr-defined]

        stopped = controller.stop_emulator("melonds")
        assert stopped["status"] == "stopping"
        assert stopped["processGroups"] == 1

        # SIGTERM cria zombie até o pai (este teste) reaper o processo.
        process.wait(timeout=3)
        assert not emulation._process_alive(process.pid)
    finally:
        if emulation._process_alive(process.pid):
            process.kill()
            process.wait()
