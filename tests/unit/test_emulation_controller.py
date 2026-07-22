# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from steamzero.adapters import emulation
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
    ryubing_config = home / ".config" / "Ryujinx" / "Config.json"
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
        home / ".config" / "Ryujinx" / "system" / "prod.keys",
        home / "Ryujinx" / "system" / "prod.keys",
    ):
        assert target.read_text(encoding="utf-8") == keys.read_text(encoding="utf-8")
    assert controller._key_projection_copies("ryubing") == []  # type: ignore[attr-defined]

    citron_data_key = data_home / "citron" / "keys" / "prod.keys"
    citron_config_key = config_home / "citron" / "keys" / "prod.keys"
    citron_data_key.unlink()
    citron_config_key.unlink()
    assert controller._key_projection_valid("citron") is False  # type: ignore[attr-defined]

    rom = roms / "Example [0100ABCDEF123000][v0].nsp"
    rom.write_bytes(b"owned-game")
    controller.scan_library()
    game_id = controller.snapshot({"context": {}})["platforms"][0]["games"][0]["id"]
    selection = controller.plan_action(
        {"actionId": "game.emulator.set", "gameId": game_id, "emulatorId": "citron"}
    )
    assert str(citron_data_key) in str(selection["preview"])
    _apply(controller, selection)
    assert controller._key_projection_valid("citron") is True  # type: ignore[attr-defined]

    citron_data_key.unlink()
    citron_config_key.unlink()
    repair = controller.plan_action({"actionId": "keys.repair"})
    _apply(controller, repair)
    assert controller._key_projection_valid("citron") is True  # type: ignore[attr-defined]
    assert citron_data_key.read_bytes() == keys.read_bytes()
    assert citron_config_key.read_bytes() == keys.read_bytes()

    firmware = home / "firmware.nca"
    firmware.write_bytes(b"owned-firmware")
    firmware_plan = controller.plan_action(
        {"actionId": "firmware.import", "path": str(firmware), "version": "18.1.0"}
    )
    _apply(controller, firmware_plan)
    assert any((data_home / "citron/nand/system/Contents/registered").glob("*.nca"))
    ryubing_firmware = home / ".config/Ryujinx/bis/system/Contents/registered"
    assert any(path.is_file() for path in ryubing_firmware.glob("*.nca/00"))
    assert not any(path.is_file() for path in ryubing_firmware.glob("*.nca"))
    assert controller._firmware_projection_copies(("ryubing",)) == []  # type: ignore[attr-defined]


def test_legacy_game_setting_survives_rescan_and_keys_gate_is_per_emulator(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    fingerprint = "9b75526e806dd370" + "a" * 48
    current_id = "0fd1b7954e6eaf474f5e8c8c"
    settings_path = controller._game_settings_path  # type: ignore[attr-defined]
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        '{"schemaVersion":1,"games":{"9b75526e806dd370":'
        '{"emulatorId":"eden","steamSelected":true}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        controller,
        "_key_projection_valid",
        lambda emulator_id: emulator_id == "eden",
    )

    enriched = controller._enrich_games(  # type: ignore[attr-defined]
        [{"id": current_id, "fingerprint": fingerprint}],
        [
            {"id": "eden", "installState": "installed"},
            {"id": "citron", "installState": "installed"},
        ],
        {"status": "unverified"},
        {"status": "ok"},
    )

    assert enriched[0]["emulatorId"] == "eden"
    assert enriched[0]["steamSelected"] is True
    assert enriched[0]["playAction"]["enabled"] is True


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


def test_keys_import_projects_optional_title_keys(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local/share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    controller = EmulationController(store_factory=lambda: StateStore(tmp_path / "state.db"))
    source = home / "owned-keys"
    source.mkdir(parents=True)
    (source / "prod.keys").write_text(
        "master_key_00 = " + "01" * 16 + "\n"
        "master_key_01 = " + "02" * 16 + "\n"
        "header_key = " + "03" * 16 + "\n"
        "titlekek_00 = " + "04" * 16 + "\n",
        encoding="utf-8",
    )
    title_content = "a" * 32 + " = " + "b" * 32 + "\n"
    (source / "title.keys").write_text(title_content, encoding="utf-8")

    _apply(controller, controller.plan_action({"actionId": "keys.import", "path": str(source)}))

    for target in (
        home / ".switch/title.keys",
        home / ".local/share/eden/keys/title.keys",
        home / ".local/share/citron/keys/title.keys",
        home / ".config/citron/keys/title.keys",
        home / ".config/Ryujinx/system/title.keys",
        home / "Ryujinx/system/title.keys",
    ):
        assert target.read_text(encoding="utf-8") == title_content


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
    (roms / "Example [0100ABCDEF123000].nsp").write_bytes(b"owned-game")

    root_plan = controller.plan_action({"actionId": "library.root.add", "path": str(roms)})
    applied = _apply(controller, root_plan)
    scanned = applied["library"]

    assert isinstance(scanned, dict)
    assert scanned["games"] == 1
    workspace = controller.snapshot({"context": {"physicalDock": False}})
    platform = workspace["platforms"][0]
    assert platform["games"][0]["titleId"] == "0100ABCDEF123000"
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
            "contentKind": "base",
            "metadataSource": "format",
            "version": None,
            "updateCount": 0,
            "updateVersion": None,
            "dlcCount": 0,
            "bannerAsset": "",
            "steamSelected": False,
            "steamPublished": False,
            "playAction": {
                "id": f"game.launch:{published[0]['id']}",
                "label": "Jogar",
                "enabled": False,
                "reason": "Selecione um emulador instalado para este jogo.",
                "requiresConfirmation": False,
            },
            "deleteAction": {
                "id": f"game.delete:{published[0]['id']}",
                "label": "Excluir ROM",
                "enabled": True,
                "reason": None,
                "requiresConfirmation": True,
            },
            "modsCount": 0,
            "cheatsCount": 0,
            "coverUrl": "",
            "mediaSource": "fallback",
            "mediaKind": "icon",
            "mediaCandidateCount": 0,
            "mediaCandidateIdx": -1,
            "masterState": "none",
            "optimizedState": "none",
            "steamViewState": "unpublished",
            "steamAppId": None,
            "steamArtworkKinds": [],
            "mods": [],
            "cheats": [],
        }
    ]


def test_library_groups_updates_and_dlcs_under_unique_base(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    roms = tmp_path / "owned-roms"
    roms.mkdir()
    (roms / "Example [0100ABCDEF123000][v0].nsp").write_bytes(b"base")
    (roms / "Example [0100ABCDEF123800][v131072].nsp").write_bytes(b"update")
    (roms / "Example [DLC Pack] [0100ABCDEF124001][v0].nsp").write_bytes(b"dlc")

    applied = _apply(
        controller,
        controller.plan_action({"actionId": "library.root.add", "path": str(roms)}),
    )

    assert applied["library"]["games"] == 1
    assert applied["library"]["ignoredAuxiliary"] == 2
    game = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    assert game["name"] == "Example"
    assert game["updateCount"] == 1
    assert game["updateVersion"] == "v131072"
    assert game["dlcCount"] == 1


def test_game_preference_launch_delete_and_rollback(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    launched: list[tuple[str, ...]] = []
    controller = _controller(monkeypatch, tmp_path)
    controller._spawn = lambda argv: launched.append(tuple(argv))  # type: ignore[attr-defined]
    roms = tmp_path / "owned-roms"
    roms.mkdir()
    rom = roms / "Example [0100ABCDEF123000].nsp"
    rom.write_bytes(b"owned-game")
    _apply(
        controller,
        controller.plan_action({"actionId": "library.root.add", "path": str(roms)}),
    )
    game_id = controller.snapshot({"context": {}})["platforms"][0]["games"][0]["id"]
    _apply(
        controller,
        controller.plan_action(
            {"actionId": "game.emulator.set", "gameId": game_id, "emulatorId": "ryubing"}
        ),
    )

    monkeypatch.setattr(
        "steamzero.adapters.emulation.AdapterEngine.payload_path",
        lambda _self, emulator_id: tmp_path / f"{emulator_id}.AppImage",
    )
    monkeypatch.setattr(controller, "_require_key_projection", lambda _emulator_id: None)
    result = controller.launch_game(game_id)
    assert result["emulatorId"] == "ryubing"
    assert launched == [
        (
            str(tmp_path / "ryubing.AppImage"),
            "-f",
            "--hide-updates",
            str(rom),
        )
    ]

    delete_plan = controller.plan_action({"actionId": "game.delete", "gameId": game_id})
    deleted = _apply(controller, delete_plan)
    assert not rom.exists()
    assert deleted["library"]["games"] == 0
    restored = controller.rollback_action(str(deleted["operationId"]))
    assert restored["status"] == "rolled-back"
    assert rom.read_bytes() == b"owned-game"
    assert restored["library"]["games"] == 1

    restored_game_id = controller.snapshot({"context": {}})["platforms"][0]["games"][0]["id"]
    assert restored_game_id == game_id
    foreign = controller.plan_action(
        {"actionId": "game.emulator.set", "gameId": restored_game_id, "emulatorId": "eden"}
    )
    applied_foreign = _apply(controller, foreign)
    with pytest.raises(SteamZeroError, match="não pertence à exclusão"):
        controller.rollback_action(str(applied_foreign["operationId"]))


def test_detached_spawn_disables_appimage_launcher_and_preserves_argv(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    observed: dict[str, object] = {}

    class FakeProcess:
        pid = 1234

    def fake_popen(argv, **kwargs):  # type: ignore[no-untyped-def]
        observed["argv"] = argv
        observed["env"] = kwargs["env"]
        return FakeProcess()

    monkeypatch.setattr(emulation.subprocess, "Popen", fake_popen)
    emulation._spawn_detached(
        ("/home/test/Emulator.AppImage", "-g", "/home/test/Game With Spaces.nsp")
    )

    assert observed["argv"] == [
        "/home/test/Emulator.AppImage",
        "-g",
        "/home/test/Game With Spaces.nsp",
    ]
    assert observed["env"]["APPIMAGELAUNCHER_DISABLE"] == "true"  # type: ignore[index]


def test_stop_emulator_signals_only_managed_process_group(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    payload = tmp_path / "ryubing.AppImage"
    signaled: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "steamzero.adapters.emulation.AdapterEngine.payload_path",
        lambda _self, _emulator_id: payload,
    )
    monkeypatch.setattr(controller, "_managed_process_groups", lambda _payload: {4321})
    monkeypatch.setattr(
        emulation.os,
        "killpg",
        lambda process_group, requested_signal: signaled.append((process_group, requested_signal)),
    )

    result = controller.stop_emulator("ryubing")

    assert result["status"] == "stopping"
    assert result["processGroups"] == 1
    assert signaled == [(4321, emulation.signal.SIGTERM)]


def test_launch_argv_uses_explicit_appimage_bypass(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    bypass = tmp_path / "appimagelauncher-binfmt-bypass"
    bypass.write_bytes(b"executable")
    bypass.chmod(0o700)
    controller = EmulationController(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        which=lambda command: str(bypass) if command == "appimagelauncher-binfmt-bypass" else None,
    )
    payload = tmp_path / "Eden.AppImage"
    rom = tmp_path / "Game With Spaces.nsp"

    assert controller._launch_argv("eden", payload, rom) == (  # type: ignore[attr-defined]
        str(bypass),
        str(payload),
        "-f",
        "-g",
        str(rom),
    )


def test_runtime_prepare_mutes_interactive_update_checks(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local/share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    controller = EmulationController(store_factory=lambda: StateStore(tmp_path / "state.db"))
    for name in ("eden", "citron"):
        config = home / ".config" / name / "qt-config.ini"
        config.parent.mkdir(parents=True)
        config.write_text(
            "[UI]\ncheck_for_updates_on_start\\default=true\n"
            "check_for_updates_on_start=true\n"
            "enable_auto_update_check\\default=true\n"
            "enable_auto_update_check=true\n",
            encoding="utf-8",
        )
    ryubing = home / ".config" / "Ryujinx" / "Config.json"
    ryubing.parent.mkdir(parents=True)
    ryubing.write_text('{"check_updates_on_start":true}\n', encoding="utf-8")

    plan = controller.plan_action({"actionId": "runtime.prepare"})
    _apply(controller, plan)

    assert "check_for_updates_on_start=false" in (home / ".config/eden/qt-config.ini").read_text(
        encoding="utf-8"
    )
    assert "enable_auto_update_check=false" in (home / ".config/citron/qt-config.ini").read_text(
        encoding="utf-8"
    )
    assert "enable_auto_update_check\\default=false" in (
        home / ".config/citron/qt-config.ini"
    ).read_text(encoding="utf-8")
    assert '"check_updates_on_start": false' in ryubing.read_text(encoding="utf-8")


def test_library_discovers_existing_lowercase_emulation_root(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    home = tmp_path / "home"
    root = home / "emulation" / "roms"
    root.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
    controller = _controller(monkeypatch, tmp_path)

    assert str(root.resolve()) in controller.library_roots()


def test_firmware_folder_is_not_registered_as_game_directory(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    home = tmp_path / "home"
    default_root = home / "emulation" / "roms"
    firmware = default_root / "switch" / "Firmware"
    firmware.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local/share"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    controller = EmulationController(store_factory=lambda: StateStore(tmp_path / "state.db"))
    eden = home / ".config/eden/qt-config.ini"
    eden.parent.mkdir(parents=True)
    eden.write_text(
        "[UI]\nPaths\\gamedirs\\size=2\n"
        f"Paths\\gamedirs\\1\\path={firmware}\n"
        f"Paths\\gamedirs\\2\\path={default_root / 'keys'}\n",
        encoding="utf-8",
    )
    ryubing = home / ".config/Ryujinx/Config.json"
    ryubing.parent.mkdir(parents=True)
    ryubing.write_text(
        json.dumps({"game_dirs": [str(firmware), str(default_root / "keys")]}) + "\n",
        encoding="utf-8",
    )

    _apply(
        controller,
        controller.plan_action({"actionId": "library.root.add", "path": str(firmware)}),
    )

    assert str(default_root) in eden.read_text(encoding="utf-8")
    assert str(firmware) not in eden.read_text(encoding="utf-8")
    configured = json.loads(ryubing.read_text(encoding="utf-8"))["game_dirs"]
    assert str(default_root) in configured
    assert str(firmware) not in configured


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


def _configured_game(controller: EmulationController, tmp_path: Path) -> tuple[str, str]:
    roms = tmp_path / "owned-roms"
    roms.mkdir()
    title_id = "0100ABCDEF123000"
    (roms / f"Example [{title_id}][v0].nsp").write_bytes(b"owned-game")
    _apply(
        controller,
        controller.plan_action({"actionId": "library.root.add", "path": str(roms)}),
    )
    game_id = controller.snapshot({"context": {}})["platforms"][0]["games"][0]["id"]
    _apply(
        controller,
        controller.plan_action(
            {"actionId": "game.emulator.set", "gameId": game_id, "emulatorId": "eden"}
        ),
    )
    return game_id, title_id


def test_mod_import_toggle_and_remove_are_transactional(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    game_id, _title_id = _configured_game(controller, tmp_path)
    mod_source = tmp_path / "60 FPS"
    (mod_source / "exefs").mkdir(parents=True)
    (mod_source / "exefs" / "main.pchtxt").write_text("@nsobid-test", encoding="utf-8")

    _apply(
        controller,
        controller.plan_action(
            {
                "actionId": "mod.import",
                "gameId": game_id,
                "emulatorId": "eden",
                "path": str(mod_source),
            }
        ),
    )
    game = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    assert game["modsCount"] == 1
    mod = game["mods"][0]
    assert mod["state"] == "active"

    _apply(controller, controller.plan_action({"actionId": mod["stateAction"]["id"]}))
    mod = controller.snapshot({"context": {}})["platforms"][0]["games"][0]["mods"][0]
    assert mod["state"] == "inactive"

    _apply(controller, controller.plan_action({"actionId": mod["stateAction"]["id"]}))
    mod = controller.snapshot({"context": {}})["platforms"][0]["games"][0]["mods"][0]
    assert mod["state"] == "active"
    _apply(controller, controller.plan_action({"actionId": mod["removeAction"]["id"]}))
    assert controller.snapshot({"context": {}})["platforms"][0]["games"][0]["mods"] == []


def test_cheat_import_toggle_and_remove_use_build_id(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    game_id, _title_id = _configured_game(controller, tmp_path)
    cheat_source = tmp_path / "0123456789ABCDEF.txt"
    cheat_source.write_text("[Infinite health]\n04000000 12345678 00000001\n", encoding="utf-8")

    _apply(
        controller,
        controller.plan_action(
            {
                "actionId": "cheat.import",
                "gameId": game_id,
                "emulatorId": "eden",
                "path": str(cheat_source),
            }
        ),
    )
    cheat = controller.snapshot({"context": {}})["platforms"][0]["games"][0]["cheats"][0]
    assert cheat["buildId"] == "0123456789ABCDEF"
    assert cheat["enabled"] is True

    _apply(controller, controller.plan_action({"actionId": cheat["stateAction"]["id"]}))
    cheat = controller.snapshot({"context": {}})["platforms"][0]["games"][0]["cheats"][0]
    assert cheat["enabled"] is False
    _apply(controller, controller.plan_action({"actionId": cheat["removeAction"]["id"]}))
    assert controller.snapshot({"context": {}})["platforms"][0]["games"][0]["cheats"] == []


def test_media_search_job_created_in_plan(
    monkeypatch, tmp_path: Path
) -> None:
    from steamzero.jobs.manager import JobManager
    store = StateStore(tmp_path / "test_media_job.db")
    store.migrate()
    jobs = JobManager(store)
    jobs.register("media.search", lambda j, c: {"candidate_count": 0})
    job = jobs.create("media.search", params={"game_id": "g1"})
    assert job.type == "media.search"
    assert job.state == "queued"
    stored = jobs.get(job.id)
    assert stored is not None
    assert stored.state == "queued"


def test_get_job_status_returns_none_for_missing(
    monkeypatch, tmp_path: Path
) -> None:
    from steamzero.jobs.manager import JobManager
    store = StateStore(tmp_path / "test_missing_job.db")
    store.migrate()
    controller = _controller(monkeypatch, tmp_path)
    controller._jobs = JobManager(store)
    assert controller.get_job_status("nonexistent") is None


def test_validate_mime_jpeg(tmp_path: Path) -> None:
    from steamzero.adapters.emulation import _validate_mime
    f = tmp_path / "test.jpg"
    f.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 60)
    _validate_mime(f)


def test_validate_mime_png(tmp_path: Path) -> None:
    from steamzero.adapters.emulation import _validate_mime
    f = tmp_path / "test.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 60)
    _validate_mime(f)


def test_validate_mime_webp(tmp_path: Path) -> None:
    from steamzero.adapters.emulation import _validate_mime
    f = tmp_path / "test.webp"
    f.write_bytes(b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 60)
    _validate_mime(f)


def test_validate_mime_rejects_unknown(tmp_path: Path) -> None:
    from steamzero.adapters.emulation import _guess_mime, _validate_mime
    from steamzero.core.errors import SteamZeroError
    f = tmp_path / "test.bin"
    f.write_bytes(b"\x00" * 100)
    with pytest.raises(SteamZeroError) as info:
        _guess_mime(b"\x00" * 100)
    assert info.value.code == "E-CONTENT-UNSUPPORTED"
    with pytest.raises(SteamZeroError) as info:
        _validate_mime(f)
    assert info.value.code == "E-CONTENT-UNSUPPORTED"


def test_validate_mime_rejects_large(tmp_path: Path) -> None:
    from steamzero.adapters.emulation import _validate_mime
    from steamzero.core.errors import SteamZeroError
    f = tmp_path / "big.jpg"
    size = 33 * 1024 * 1024 + 1000
    data = b"\xff\xd8\xff\xe0" + b"\x00" * (size - 4)
    f.write_bytes(data)
    with pytest.raises(SteamZeroError) as info:
        _validate_mime(f)
    assert info.value.code == "E-CONTENT-LIMIT"


def test_rom_scan_job_created_in_plan(
    monkeypatch, tmp_path: Path
) -> None:
    from steamzero.jobs.manager import JobManager
    store = StateStore(tmp_path / "test_rom_job.db")
    store.migrate()
    jobs = JobManager(store)
    jobs.register("rom.scan", lambda j, c: {"roots_scanned": 0, "total_files": 0})
    controller = _controller(monkeypatch, tmp_path)
    controller._jobs = jobs
    rom_dir = tmp_path / "roms"
    rom_dir.mkdir()
    (rom_dir / "game.nsp").write_text("dummy")
    monkeypatch.setattr(
        "steamzero.adapters.emulation.EmulationController.library_roots",
        lambda self: [str(rom_dir)],
    )
    result = controller.plan_action({"actionId": "rom.scan"})
    assert "jobId" in result
    job = controller.get_job_status(result["jobId"])
    assert job is not None
    assert job["type"] == "rom.scan"
