# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero.adapters.console_runtime_readiness import XboxRuntimeReadiness
from steamzero.adapters.emulation import EmulationController
from steamzero.core import paths
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore


def _controller(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> EmulationController:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return EmulationController(store_factory=lambda: StateStore(tmp_path / "state.db"))


def test_reconciled_archive_multidisc_survives_launch_cache_filter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    controller = _controller(monkeypatch, tmp_path)
    root = tmp_path / "roms"
    root.mkdir()
    archive = root / "x68000" / "Garou.zip"
    archive.parent.mkdir()
    archive.write_bytes(b"archive")
    controller.library_roots = lambda: [str(root)]  # type: ignore[method-assign]
    cache = {
        "schemaVersion": 1,
        "unidentified": 0,
        "games": [
            {
                "id": "game-x68000",
                "name": "Garou",
                "state": "unverified",
                "path": str(archive),
                "fingerprint": "not-needed-for-cache",
                "format": "zip",
                "platform": "x68000",
                "contentKind": "base",
                "evidence": "archive-multidisc-needs-extraction",
            }
        ],
    }
    paths.data_home().mkdir(parents=True, exist_ok=True)
    (paths.data_home() / "emulation-library-cache-v1.json").write_text(
        json.dumps(cache), encoding="utf-8"
    )

    games, unidentified = controller._load_library_cache()  # type: ignore[attr-defined]

    assert unidentified == 0
    assert [game["id"] for game in games] == ["game-x68000"]
    assert games[0]["platformId"] == "x68000"


def test_ps3_firmware_import_is_local_and_satisfies_preflight(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    controller = _controller(monkeypatch, tmp_path)
    source = tmp_path / "PS3UPDAT.PUP"
    source.write_bytes(b"local-user-owned-firmware")

    plan = controller.plan_action(
        {"actionId": "firmware.import", "path": str(source), "version": "4.92"}
    )
    controller.apply_action(str(plan["planId"]), str(plan["confirmToken"]))

    assert controller._platform_firmware_version("playstation-3") == "4.92"  # type: ignore[attr-defined]
    projected = paths.firmware_dir() / "playstation-3" / "4.92" / "PS3UPDAT.PUP"
    assert projected.read_bytes() == source.read_bytes()


def test_ps3_missing_firmware_is_actionable_before_spawn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    controller = _controller(monkeypatch, tmp_path)

    with pytest.raises(SteamZeroError, match=r"PS3UPDAT\.PUP") as error:
        controller._require_platform_firmware("playstation-3")  # type: ignore[attr-defined]

    assert error.value.code == "E-CONTENT-FW-MISSING"
    assert "playstation.com" in error.value.detail


def test_xbox_machine_configuration_blocks_before_spawn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    controller = _controller(monkeypatch, tmp_path)
    rom = tmp_path / "roms" / "xbox" / "Outrun.iso"
    rom.parent.mkdir(parents=True)
    rom.write_bytes(b"iso")
    game = {
        "id": "xbox-game",
        "name": "OutRun",
        "path": str(rom),
        "platformId": "xbox",
        "format": "iso",
        "contentKind": "base",
    }
    monkeypatch.setattr(controller, "_current_game", lambda _game_id: game)
    monkeypatch.setattr(controller, "_load_game_settings", lambda strict=False: {})
    monkeypatch.setattr(
        controller,
        "_settings_for_game_with_global",
        lambda _game, _settings: {"emulatorId": "xemu"},
    )
    monkeypatch.setattr(controller, "_require_launchable_emulator", lambda _id: None)
    monkeypatch.setattr(
        controller,
        "_emulator_source",
        lambda _id: ("flatpak", "app.xemu.xemu", None),
    )
    monkeypatch.setattr(
        controller,
        "_xemu_runtime_probe",
        lambda: XboxRuntimeReadiness(
            False,
            True,
            ("flash", "mcpx", "hdd"),
            "xbox-machine-files-missing",
        ),
    )

    with pytest.raises(SteamZeroError, match="xbox-machine-files-missing") as error:
        controller._launch_preflight("xbox-game")  # type: ignore[attr-defined]

    assert error.value.code == "E-COMPONENT-DEGRADED"
    assert "flash, mcpx, hdd" in error.value.detail


def test_archive_without_materialization_is_refused_before_emulator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    controller = _controller(monkeypatch, tmp_path)
    archive = tmp_path / "roms" / "ps4" / "Game.rar"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"rar")
    game = {
        "id": "ps4-archive",
        "name": "Jogo PS4",
        "path": str(archive),
        "platformId": "playstation-4",
        "format": "rar",
        "contentKind": "base",
        "evidence": "archive-needs-extraction",
    }
    monkeypatch.setattr(controller, "_current_game", lambda _game_id: game)
    monkeypatch.setattr(controller, "_load_game_settings", lambda strict=False: {})
    monkeypatch.setattr(
        controller,
        "_settings_for_game_with_global",
        lambda _game, _settings: {"emulatorId": "shadps4"},
    )
    monkeypatch.setattr(controller, "_require_launchable_emulator", lambda _id: None)

    with pytest.raises(SteamZeroError, match="materializado") as error:
        controller._launch_preflight("ps4-archive")  # type: ignore[attr-defined]

    assert error.value.code == "E-CONTENT-INCOMPLETE"


def test_pcsx2_runtime_flag_is_normalized_only_at_spawn_boundary() -> None:
    argv = ["flatpak", "run", "--user", "net.pcsx2.PCSX2", "--fullscreen", "game.iso"]

    assert EmulationController._runtime_compat_argv("pcsx2", argv) == [
        "flatpak",
        "run",
        "--user",
        "net.pcsx2.PCSX2",
        "-fullscreen",
        "game.iso",
    ]
    assert EmulationController._runtime_compat_argv("dolphin", argv) == argv
