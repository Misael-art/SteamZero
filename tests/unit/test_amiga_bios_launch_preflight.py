# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from steamzero.adapters.emulation import EmulationController
from steamzero.core.errors import SteamZeroError


def _preflight_controller(
    monkeypatch, tmp_path: Path, *, bios_present: bool
) -> EmulationController:  # type: ignore[no-untyped-def]
    controller = EmulationController.__new__(EmulationController)
    rom = tmp_path / "game.adf"
    rom.write_bytes(b"fixture")
    monkeypatch.setattr(
        controller,
        "_current_game",
        lambda _game_id: {
            "platformId": "amiga",
            "path": str(rom),
            "evidence": "rom",
            "format": "adf",
            "contentKind": "base",
        },
    )
    monkeypatch.setattr(
        controller, "_load_game_settings", lambda *, strict: {"emulatorId": "retroarch"}
    )
    monkeypatch.setattr(
        controller, "_settings_for_game_with_global", lambda _game, settings: settings
    )
    monkeypatch.setattr(controller, "_require_launchable_emulator", lambda _emulator: None)
    monkeypatch.setattr(
        controller,
        "_launch_profile_for",
        lambda _platform, _emulator: SimpleNamespace(requires_bios=("kick34005.A500",)),
    )
    monkeypatch.setattr(
        controller, "_bios_present_for", lambda _platform, _emulator, _name: bios_present
    )
    monkeypatch.setattr(controller, "_bios_projection_copies", lambda _platform, _emulator: [])
    monkeypatch.setattr(
        controller,
        "_emulator_source",
        lambda _emulator: pytest.fail(
            "o preflight de BIOS deveria encerrar antes do source lookup"
        ),
    )
    return controller


def test_launch_preflight_blocks_when_declared_bios_is_missing(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _preflight_controller(monkeypatch, tmp_path, bios_present=False)

    with pytest.raises(SteamZeroError) as excinfo:
        controller._launch_preflight("game")

    assert excinfo.value.code == "E-CONTENT-BIOS-MISSING"
    assert "kick34005.A500" in str(excinfo.value.detail)


def test_launch_preflight_blocks_bios_imported_but_not_projected(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _preflight_controller(monkeypatch, tmp_path, bios_present=True)
    target = tmp_path / "retroarch" / "system" / "kick34005.A500"
    monkeypatch.setattr(
        controller,
        "_bios_projection_copies",
        lambda _platform, _emulator: [(tmp_path / "bios" / "kick34005.A500", target)],
    )

    with pytest.raises(SteamZeroError) as excinfo:
        controller._launch_preflight("game")

    assert excinfo.value.code == "E-CONTENT-BIOS-MISSING"
    assert str(target) in str(excinfo.value.detail)
