# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from steamzero.adapters.converters import NszToolManager, nsz_tool_manifest
from steamzero.adapters.emulation import EmulationController
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore


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
    )


def _apply(controller: EmulationController, plan: dict[str, object]) -> dict[str, object]:
    return controller.apply_action(str(plan["planId"]), str(plan["confirmToken"]))


def test_switch_emulators_publish_managed_ryubing_with_official_icon(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)

    rows = controller.snapshot({"context": {}})["platforms"][0]["emulators"]
    by_id = {row["id"]: row for row in rows}

    assert set(by_id) == {"eden", "citron", "ryubing"}
    assert by_id["ryubing"]["sourceState"] == "verified"
    assert by_id["ryubing"]["targetVersion"] == "1.3.3"
    assert by_id["ryubing"]["iconAsset"] == "../assets/ryubing.png"
    assert by_id["ryubing"]["action"]["id"] == "emulator.install:ryubing"


def test_imports_project_to_switch_consumers_and_save_game_directories(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    home = tmp_path / "home"
    config_home = home / ".config"
    data_home = home / ".local" / "share"
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    controller = EmulationController(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        which=lambda _command: None,
        spawn=lambda _argv: None,
    )

    citron_config = config_home / "citron" / "qt-config.ini"
    citron_config.parent.mkdir(parents=True)
    citron_config.write_text(
        "[UI]\nPaths\\gamedirs\\size=1\nPaths\\gamedirs\\1\\path=/existing\n",
        encoding="utf-8",
    )
    ryubing_config = home / "Ryujinx" / "Config.json"
    ryubing_config.parent.mkdir(parents=True)
    ryubing_config.write_text('{"version":70,"game_dirs":[]}\n', encoding="utf-8")
    roms = home / "Games" / "Switch"
    roms.mkdir(parents=True)

    root_plan = controller.plan_action({"actionId": "library.root.add", "path": str(roms)})
    _apply(controller, root_plan)
    assert str(roms) in ryubing_config.read_text(encoding="utf-8")
    assert "Paths\\gamedirs\\1\\path=/existing" in citron_config.read_text(encoding="utf-8")
    assert f"path={roms}" in citron_config.read_text(encoding="utf-8")

    keys = home / "prod.keys"
    keys.write_text(
        "master_key_00 = " + "01" * 16 + "\n"
        "master_key_01 = " + "02" * 16 + "\n"
        "header_key = " + "03" * 16 + "\n"
        "titlekek_00 = " + "04" * 16 + "\n",
        encoding="utf-8",
    )
    key_plan = controller.plan_action({"actionId": "keys.import", "path": str(keys)})
    _apply(controller, key_plan)
    for target in (
        home / ".switch" / "prod.keys",
        data_home / "citron" / "keys" / "prod.keys",
        home / "Ryujinx" / "system" / "prod.keys",
    ):
        assert target.read_text(encoding="utf-8") == keys.read_text(encoding="utf-8")

    firmware = home / "firmware.nca"
    firmware.write_bytes(b"owned-firmware")
    firmware_plan = controller.plan_action(
        {"actionId": "firmware.import", "path": str(firmware), "version": "18.1.0"}
    )
    _apply(controller, firmware_plan)
    assert any((data_home / "citron/nand/system/Contents/registered").glob("*.nca"))
    assert any((home / "Ryujinx/bis/system/Contents/registered").glob("*.nca"))


def test_nsz_manifest_is_valid_and_failed_install_leaves_no_partial_tool(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert nsz_tool_manifest().expected_version == "4.6.1"

    def fail_runner(_argv: Sequence[str]) -> None:
        raise RuntimeError("sem rede")

    manager = NszToolManager(runner=fail_runner)
    with pytest.raises(SteamZeroError, match="instalação NSZ falhou"):
        manager.install()
    assert not manager.root.exists()


def test_nsz_private_install_is_idempotent_after_verified_publication(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    commands: list[tuple[str, ...]] = []
    manager = NszToolManager()

    def runner(argv: Sequence[str]) -> None:
        commands.append(tuple(argv))
        if tuple(argv[1:3]) == ("-m", "venv"):
            executable = manager.executable
            executable.parent.mkdir(parents=True)
            executable.write_text("#!/bin/sh\n", encoding="utf-8")
            executable.chmod(0o700)

    manager._runner = runner  # type: ignore[attr-defined]
    installed = manager.install()
    assert installed["status"] == "installed"
    assert manager.status()["available"] is True
    assert any(command[1:3] == ("-m", "pip") for command in commands)
    assert manager.install()["status"] == "already-installed"


def test_library_roots_scan_and_local_requirements(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    roms = tmp_path / "owned-roms"
    roms.mkdir()
    (roms / "Example [0100ABCDEF123456].nsp").write_bytes(b"owned-game")

    root_plan = controller.plan_action({"actionId": "library.root.add", "path": str(roms)})
    applied = _apply(controller, root_plan)
    scanned = applied["library"]

    assert isinstance(scanned, dict)
    assert scanned["games"] == 1
    workspace = controller.snapshot({"context": {"physicalDock": False}})
    platform = workspace["platforms"][0]
    assert platform["games"][0]["titleId"] == "0100ABCDEF123456"
    assert str(roms.resolve()) in platform["areaData"]["media"]["cards"][0]["detail"]

    keys = tmp_path / "prod.keys"
    keys.write_text(
        "master_key_00 = " + "01" * 16 + "\n"
        "master_key_01 = " + "02" * 16 + "\n"
        "header_key = " + "03" * 16 + "\n"
        "titlekek_00 = " + "04" * 16 + "\n",
        encoding="utf-8",
    )
    key_plan = controller.plan_action({"actionId": "keys.import", "path": str(keys)})
    _apply(controller, key_plan)

    firmware = tmp_path / "firmware.nca"
    firmware.write_bytes(b"owned-firmware")
    firmware_plan = controller.plan_action(
        {"actionId": "firmware.import", "path": str(firmware), "version": "18.1.0"}
    )
    _apply(controller, firmware_plan)

    requirements = controller.snapshot({"context": {}})["platforms"][0]["requirements"]
    assert requirements["keys"]["status"] == "ok"
    assert requirements["keys"]["installed"] == "rev1"
    assert requirements["firmware"]["installed"] == "18.1.0"


def test_library_keeps_games_without_title_id_as_unverified(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    roms = tmp_path / "owned-roms"
    nested = roms / "My Games"
    nested.mkdir(parents=True)
    game = nested / "Example Game.xcz"
    game.write_bytes(b"owned-game")

    root_plan = controller.plan_action({"actionId": "library.root.add", "path": str(roms)})
    applied = _apply(controller, root_plan)
    scanned = applied["library"]

    assert isinstance(scanned, dict)
    assert scanned["games"] == 1
    assert scanned["unidentified"] == 1
    published = controller.snapshot({"context": {}})["platforms"][0]["games"]
    assert published == [
        {
            "id": published[0]["id"],
            "titleId": None,
            "name": "Example Game",
            "state": "unverified",
            "statusLabel": "XCZ · Title ID não identificado",
            "emulatorId": None,
            "path": str(game),
            "fingerprint": published[0]["fingerprint"],
            "size": len(b"owned-game"),
            "format": "xcz",
            "identityVerified": False,
        }
    ]


def test_library_discovers_existing_lowercase_emulation_root(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    home = tmp_path / "home"
    root = home / "emulation" / "roms"
    root.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
    controller = _controller(monkeypatch, tmp_path)

    assert str(root.resolve()) in controller.library_roots()


def test_update_and_dlc_import_can_be_activated(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    title_id = "0100ABCDEF123456"
    update = tmp_path / "update.nsp"
    update.write_bytes(b"owned-update")
    plan = controller.plan_action(
        {
            "actionId": "content.update.import",
            "path": str(update),
            "titleId": title_id,
            "version": "1.2.0",
        }
    )
    _apply(controller, plan)

    platform = controller.snapshot({"context": {}})["platforms"][0]
    cards = platform["areaData"]["updatesDlc"]["cards"]
    record_card = next(card for card in cards if str(card["id"]).startswith("content-"))
    assert record_card["statusLabel"] == "Inativo"

    active_plan = controller.plan_action({"actionId": record_card["action"]["id"]})
    _apply(controller, active_plan)
    cards = controller.snapshot({"context": {}})["platforms"][0]["areaData"]["updatesDlc"]["cards"]
    active_card = next(card for card in cards if str(card["id"]).startswith("content-"))
    assert active_card["statusLabel"] == "Ativo"
    assert active_card["action"]["label"] == "Desativar"
