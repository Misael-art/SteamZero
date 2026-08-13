# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import hashlib
import io
import json
import queue
import threading
import time
import zipfile
from collections.abc import Sequence
from pathlib import Path

import jsonschema.exceptions
import pytest

from steamzero.adapters import emulation, input_devices
from steamzero.adapters.converters import NszToolManager, nsz_tool_manifest
from steamzero.adapters.emulation import EmulationController
from steamzero.api.contracts import validate
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.ports import CheatCandidate, CheatIdentity, ModCandidate, ModIdentity


def _controller(monkeypatch, tmp_path: Path, controls=None) -> EmulationController:  # type: ignore[no-untyped-def]
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
        retroarch_controls=controls,
    )


def _apply(controller: EmulationController, plan: dict[str, object]) -> dict[str, object]:
    return controller.apply_action(str(plan["planId"]), str(plan["confirmToken"]))


def _wait_job(controller: EmulationController, job_id: str):  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = controller._jobs.get(job_id)  # type: ignore[attr-defined]
        if job is not None and job.state in {
            "completed",
            "cancelled",
            "rolled-back",
            "rollback-failed",
        }:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} não chegou ao estado terminal")


def test_switch_emulators_publish_managed_ryubing_with_official_icon(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)

    # Contrato alterado em 2026-08-12: o workspace do Switch lista SÓ os
    # emuladores do Switch. Antes esta asserção exigia o inventário inteiro
    # dentro do Switch — Dolphin, PPSSPP, Cemu e companhia — e foi exatamente
    # isso que o operador viu na tela: emuladores de GameCube e de PSP sob
    # Nintendo Switch, com o rótulo "Keys pendentes" que só cabe ao Switch.
    rows = controller.snapshot({"context": {}})["platforms"][0]["emulators"]
    by_id = {row["id"]: row for row in rows}

    assert set(by_id) == {"eden", "citron", "ryubing"}
    assert by_id["ryubing"]["sourceState"] == "verified"
    assert by_id["ryubing"]["targetVersion"] == "1.3.3"
    assert by_id["ryubing"]["iconAsset"] == "../assets/ryubing.png"
    assert by_id["ryubing"]["action"]["id"] == "emulator.install:ryubing"
    assert by_id["ryubing"]["health"] == {
        "state": "unavailable",
        "versionCurrent": False,
        "keysReady": False,
        "firmwareReady": False,
        "reason": "Pendente: instalação, firmware.",
    }
    assert by_id["ryubing"]["running"] is False
    assert by_id["ryubing"]["libraryRootCount"] == 0


def test_snapshot_publishes_global_management_without_a_synthetic_platform(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)

    workspace = controller.snapshot({"context": {}})
    global_management = workspace["globalManagement"]

    assert len(workspace["platforms"]) == 36
    assert global_management["id"] == "emulation-global"
    assert global_management["technicalPlatformCount"] == 36
    assert global_management["editorialDestinationCount"] == 37
    assert global_management["editorialExperienceCount"] == 155
    assert global_management["editorialSource"]["id"] == "steam"
    assert len(global_management["platformCards"]) == 36
    switch = next(card for card in global_management["platformCards"] if card["id"] == "switch")
    assert switch["action"]["id"] == "platform.open"
    assert switch["keysStatus"]["kind"] == "keys"
    # 15, e não 13, desde 2026-08-12: `duckstation` e `pcsx2` passaram a ser
    # apresentáveis. Eles sempre estiveram declarados por PlayStation e
    # PlayStation 2, mas a tupla de ordem da UI também filtrava a membresia e os
    # deixava de fora — as duas plataformas ficavam sem emulador renderizável.
    assert len(global_management["emulators"]) == 15
    assert all("apiKey" not in provider for provider in global_management["mediaProviders"])


def _plant_portable_deployment(
    tmp_path: Path, adapter_id: str, version: str, payload: bytes
) -> None:
    """Monta um deployment portátil (current.json + payload) sem download."""
    from steamzero.adapters.registry import AdapterRegistry
    from steamzero.core import paths as core_paths

    manifest = AdapterRegistry.bundled().get(adapter_id)
    component_root = core_paths.data_home() / "components" / adapter_id
    (component_root / "releases" / version).mkdir(parents=True, exist_ok=True)
    (component_root / "releases" / version / "payload").write_bytes(payload)
    (component_root / "current.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "adapterId": adapter_id,
                "version": version,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "origin": "appimage",
                "manifestHash": manifest.manifest_hash,
            }
        ),
        encoding="utf-8",
    )


def _plant_degraded_deployment(tmp_path: Path, adapter_id: str, version: str) -> None:
    """current.json apontando para payload ausente: degradado real do engine."""
    from steamzero.adapters.registry import AdapterRegistry
    from steamzero.core import paths as core_paths

    manifest = AdapterRegistry.bundled().get(adapter_id)
    component_root = core_paths.data_home() / "components" / adapter_id
    component_root.mkdir(parents=True, exist_ok=True)
    (component_root / "current.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "adapterId": adapter_id,
                "version": version,
                "sha256": "0" * 64,
                "origin": "appimage",
                "manifestHash": manifest.manifest_hash,
            }
        ),
        encoding="utf-8",
    )


def test_degraded_emulator_never_crashes_snapshot(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """G27: payload ausente (degradado) não pode derrubar payload_path()."""
    controller = _controller(monkeypatch, tmp_path)
    _plant_degraded_deployment(tmp_path, "citron", "1.0.0")

    platform = controller.snapshot({"context": {}})["platforms"][0]
    citron = next(row for row in platform["emulators"] if row["id"] == "citron")
    assert citron["installState"] == "degraded"
    assert citron["state"] == "attention"
    assert citron["statusLabel"] == "Reparar"
    assert citron["running"] is False
    assert citron["actions"][0]["id"] == "emulator.repair:citron"
    assert all("emulator.launch" not in action["id"] for action in citron["actions"]), (
        "degradado não pode oferecer launch — payload_path() falha imediatamente"
    )
    assert citron["health"]["state"] == "degraded"
    assert citron["health"]["reason"] == "payload ausente ou checksum divergente"


def test_degraded_emulator_blocks_global_readiness(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """G27: degradado presente nunca produz prontidão global de 100%."""
    controller = _controller(monkeypatch, tmp_path)
    _plant_portable_deployment(tmp_path, "eden", "1.0.0", b"#!/bin/sh\necho ok\n")
    _plant_degraded_deployment(tmp_path, "citron", "1.0.0")

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

    platform = controller.snapshot({"context": {}})["platforms"][0]
    assert platform["state"] == "attention"
    assert platform["readiness"]["percent"] == 45
    assert any("Repare emuladores degradados" in item for item in platform["readiness"]["blockers"])


def test_snapshot_owns_job_store_in_the_calling_thread(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """O dashboard constrói o controller antes de o handler HTTP existir."""
    controller = _controller(monkeypatch, tmp_path)
    result: queue.Queue[dict[str, object] | BaseException] = queue.Queue()

    def read_from_request_thread() -> None:
        try:
            result.put(controller.snapshot({"context": {}}))
        except BaseException as exc:  # pragma: no cover - torna a falha legível
            result.put(exc)
        finally:
            controller.close_request_context()

    thread = threading.Thread(target=read_from_request_thread)
    thread.start()
    thread.join(timeout=5)

    assert not thread.is_alive()
    payload = result.get_nowait()
    if isinstance(payload, BaseException):
        raise payload
    platform = payload["platforms"][0]  # type: ignore[index]
    eden = next(row for row in platform["emulators"] if row["id"] == "eden")
    assert eden["actions"][0]["id"] == "emulator.install:eden"
    assert eden["health"]["state"] == "unavailable"


def test_library_health_plan_runs_bounded_job_and_marks_suspect(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    rom = tmp_path / "Game.nsp"
    rom.write_bytes(b"A" * 2048)
    cache = controller._library_cache_path  # type: ignore[attr-defined]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "games": [
                    {
                        "id": "game-1",
                        "name": "Game",
                        "state": "ready",
                        "path": str(rom),
                        "size": 2048,
                    }
                ],
                "unidentified": 0,
            }
        ),
        encoding="utf-8",
    )

    before = controller.library_health()
    assert before["counts"]["unchecked"] == 1
    plan = controller.plan_library_health()
    assert "somente leitura" in str(plan["preview"]).casefold()
    applied = _apply(controller, plan)
    assert applied["job"]["rawState"] == "completed"
    assert applied["health"]["state"] == "healthy"

    rom.write_bytes(b"B" * 2048)
    second = _apply(controller, controller.plan_library_health())
    assert second["health"]["state"] == "suspect"
    assert second["health"]["counts"]["suspect"] == 1


def test_runtime_profiles_publish_observed_handheld_and_dock_facts(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    monkeypatch.setattr(controller, "_controller_count", lambda: 2)

    profiles = controller.snapshot(
        {
            "context": {
                "physicalDock": True,
                "deviceKind": "deck-oled",
                "displays": [
                    {
                        "connected": True,
                        "internal": False,
                        "width": 2560,
                        "height": 1440,
                    }
                ],
            }
        }
    )["platforms"][0]["runtimeProfiles"]

    assert profiles["activeScope"] == "dock"
    assert profiles["observedScope"] == "dock"
    assert profiles["desiredScope"] is None
    assert profiles["diverged"] is None
    assert profiles["autoTransition"]["supported"] is False
    assert profiles["handheld"]["resolution"] == {
        "width": 1280,
        "height": 720,
        "label": "720p",
    }
    assert profiles["dock"]["resolution"] == {
        "width": 1920,
        "height": 1080,
        "label": "1080p",
    }
    assert profiles["dock"]["controllers"]["activePlayers"] == 2
    assert profiles["dock"]["tdp"] == {
        "value": None,
        "source": "steam-game-profile",
    }


def test_input_profile_plan_apply_snapshot_and_rollback(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)

    before = controller.snapshot({"context": {}})["platforms"][0]["areaData"]["controls"]
    profile_card = next(card for card in before["cards"] if card["id"] == "input-profile")
    assert profile_card["state"] == "unverified"
    assert {action["id"] for action in profile_card["actions"]} == {
        "controls.profile.activate:standard-gamepad",
        "controls.profile.activate:joycon-pair",
    }

    plan = controller.plan_action(
        {
            "actionId": "controls.profile.activate:standard-gamepad",
            "orientation": "portrait-left",
        }
    )
    result = _apply(controller, plan)
    after = controller.snapshot({"context": {}})["platforms"][0]["areaData"]["controls"]
    active_card = next(card for card in after["cards"] if card["id"] == "input-profile")
    assert active_card["state"] == "ready"
    assert "standard-gamepad · revisão 1 · portrait-left" in active_card["detail"]

    rollback = controller.rollback_action(str(result["operationId"]))
    assert rollback["status"] == "rolled-back"
    restored = controller.snapshot({"context": {}})["platforms"][0]["areaData"]["controls"]
    restored_card = next(card for card in restored["cards"] if card["id"] == "input-profile")
    assert restored_card["state"] == "unverified"


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


def test_game_settings_win_over_global_defaults_and_global_fills_gaps(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """Onda 4: precedência jogo→global no launcher — o jogo que opta por
    valor próprio vence; o jogo sem opt-in herda a preferência global."""
    controller = _controller(monkeypatch, tmp_path)
    global_path = controller._global_settings_path  # type: ignore[attr-defined]
    global_path.parent.mkdir(parents=True, exist_ok=True)
    global_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "settings": {
                    "defaultEmulatorId": "citron",
                    "autoPublishSteam": True,
                    "preferNativeNca": True,
                },
            }
        ),
        encoding="utf-8",
    )
    game = {"id": "0fd1b7954e6eaf474f5e8c8c", "fingerprint": "f" * 64}
    settings = {"0fd1b7954e6eaf474f5e8c8c": {"autoPublishSteam": False, "emulatorId": "eden"}}
    merged = controller._settings_for_game_with_global(game, settings)  # type: ignore[attr-defined]
    assert merged["emulatorId"] == "eden"
    assert merged["autoPublishSteam"] is False
    assert merged["preferNativeNca"] is True

    inherited = controller._settings_for_game_with_global(game, {})  # type: ignore[attr-defined]
    assert inherited["emulatorId"] == "citron"
    assert inherited["autoPublishSteam"] is True
    assert inherited["preferNativeNca"] is True


def test_global_emulator_and_media_preferences_are_persisted(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)

    _apply(
        controller,
        controller.plan_action({"actionId": "game.emulator.default", "emulatorId": "citron"}),
    )
    _apply(
        controller,
        controller.plan_action(
            {"actionId": "emulation.global.set-auto-publish-steam", "value": True}
        ),
    )
    _apply(
        controller,
        controller.plan_action(
            {"actionId": "emulation.global.set-prefer-native-nca", "value": False}
        ),
    )

    platform = controller.snapshot({"context": {}})["platforms"][0]
    assert platform["defaultEmulatorId"] == "citron"
    assert platform["configuredDefaultEmulatorId"] == "citron"
    assert platform["primaryEmulator"] == {
        "id": "citron",
        "name": "Citron",
        "state": "unavailable",
        "statusLabel": "Não instalado",
        "source": "configured-unavailable",
    }
    assert platform["fallbackArtworkAsset"] == "../assets/switch.svg"
    assert next(row for row in platform["emulators"] if row["id"] == "citron")["isDefault"] is True
    assert (
        next(row for row in platform["emulators"] if row["id"] == "eden")["actions"][0]["id"]
        == "emulator.install:eden"
    )
    assert platform["globalSettings"] == {
        "defaultEmulatorId": "citron",
        "autoPublishSteam": True,
        "preferNativeNca": False,
    }


def test_primary_emulator_falls_back_to_installed_precedence() -> None:
    rows = [
        {"id": "eden", "installState": "not-installed"},
        {"id": "citron", "installState": "installed"},
        {"id": "ryubing", "installState": "installed"},
    ]
    assert emulation._resolve_primary_emulator(rows, None) == ("citron", "precedence")
    assert emulation._resolve_primary_emulator(rows, "ryubing") == (
        "ryubing",
        "configured",
    )
    assert emulation._resolve_primary_emulator(rows, "eden") == (
        "eden",
        "configured-unavailable",
    )
    assert emulation._resolve_primary_emulator([], "eden") == (None, "none")


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


def test_rollback_action_rejects_non_ulid_without_operation_id(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """operationId malformado é pré-condição: E-API-SCHEMA e sem operationId agregável."""
    controller = _controller(monkeypatch, tmp_path)
    with pytest.raises(SteamZeroError) as exc:
        controller.rollback_action("invalido")
    assert exc.value.code == "E-API-SCHEMA"
    assert exc.value.operation_id is None


def test_post_commit_side_effect_error_inherits_operation_id(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """Falha no efeito colateral pós-commit herda o operationId da transação comitada.

    A transação já foi aplicada quando ``_persist_import`` roda; sem herdar o id
    o ErrorCard não consegue agregar a falha à operação que o usuário disparou.
    """
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

    def _persist_failing(_pending) -> None:  # type: ignore[no-untyped-def]
        raise SteamZeroError("E-STATE-INTEGRITY", detail="falha simulada pós-commit")

    monkeypatch.setattr(controller, "_persist_import", _persist_failing)
    plan = controller.plan_action({"actionId": "keys.import", "path": str(source)})
    with pytest.raises(SteamZeroError) as exc:
        _apply(controller, plan)
    assert exc.value.code == "E-STATE-INTEGRITY"
    assert exc.value.operation_id
    # As chaves foram gravadas: a transação comitou, só o efeito colateral falhou.
    assert (home / ".switch/prod.keys").exists()


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


def test_nsz_ready_state_publishes_the_existing_conversion_journey(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    controller._nsz.status = lambda: {  # type: ignore[method-assign]
        "available": True,
        "version": "4.6.1",
    }
    controller._requirements = lambda _emulators: (  # type: ignore[method-assign]
        {
            "kind": "keys",
            "status": "ok",
            "required": None,
            "installed": "rev1",
            "detail": "Keys validadas.",
            "blocksPlay": False,
        },
        {
            "kind": "firmware",
            "status": "missing",
            "required": None,
            "installed": None,
            "detail": "Firmware ausente.",
            "blocksPlay": True,
        },
    )

    advanced = controller.snapshot({"context": {}})["platforms"][0]["areaData"]["advanced"]
    card = next(card for card in advanced["cards"] if card["id"] == "nsz")

    assert card["statusLabel"] == "Pronto"
    assert card["action"] == {
        "id": "nsz.convert",
        "label": "Selecionar arquivo",
        "enabled": True,
        "reason": None,
        "requiresConfirmation": True,
    }


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
            "platformId": "switch",
            "fallbackArtworkUrl": "../assets/switch.svg",
            "steamSelected": False,
            "steamPublished": False,
            "playAction": {
                "id": f"game.launch:{published[0]['id']}",
                "label": "Jogar",
                "enabled": False,
                "reason": "Selecione um emulador para este jogo.",
                "requiresConfirmation": False,
            },
            "launchReadiness": {
                "state": "blocked",
                "emulator": "unconfigured",
                "reason": "Selecione um emulador para este jogo.",
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
            "mediaCandidates": [],
            "mediaErrors": {},
            "mediaErrorCategories": {},
            "masterState": "none",
            "optimizedState": "none",
            "steamViewState": "unpublished",
            "steamAppId": None,
            "steamArtworkKinds": [],
            "mods": [],
            "cheats": [],
            "modCandidates": [],
            "cheatCandidates": [],
            "catalogSearchAction": {
                "id": f"extras.catalog.search:{published[0]['id']}",
                "label": "Buscar mods e cheats",
                "enabled": False,
                "reason": "Title ID não identificado para consultar catálogos.",
                "requiresConfirmation": True,
                "gameId": published[0]["id"],
            },
            "modPriorityCapability": {
                "supported": False,
                "reason": (
                    "Eden, Citron e Ryubing não publicam uma ordem de sobreposição "
                    "estável que o backend possa verificar; controles de prioridade "
                    "permanecem ocultos."
                ),
            },
            "saveTarget": {
                "confirmed": False,
                "ambiguous": False,
                "reason": "defina um emulador e confirme o Title ID",
            },
            "shaderTarget": {
                "confirmed": False,
                "ambiguous": False,
                "reason": "defina um emulador e confirme o Title ID",
            },
            "saveBackups": [],
            "stateTarget": {
                "confirmed": False,
                "ambiguous": False,
                "reason": "defina um emulador e confirme o Title ID",
            },
            "stateBackups": [],
            "shaderBackups": [],
            "saveState": "Destino não confirmado",
            "stateCount": 0,
            "shaderCount": 0,
            # CONTROLS-E2E: o game row agora publica o perfil de input por jogo
            # (herdado da plataforma quando não há override) e a prontidão de
            # controles, que informa sem bloquear o launch.
            "controlsProfile": {
                "state": "unverified",
                "statusLabel": "Perfil não selecionado",
                "source": "platform",
                "scope": "platform",
                "active": None,
                "available": [
                    {"id": "standard-gamepad", "revision": 1, "label": "Controle padrão"},
                    {"id": "joycon-pair", "revision": 1, "label": "Par de Joy-Con"},
                ],
                "activateActions": [
                    {
                        "id": "controls.profile.activate:standard-gamepad",
                        "label": "Controle padrão",
                        "enabled": True,
                        "reason": None,
                        "requiresConfirmation": True,
                        "gameId": published[0]["id"],
                        "scope": "game",
                        "scopeId": published[0]["id"],
                    },
                    {
                        "id": "controls.profile.activate:joycon-pair",
                        "label": "Par de Joy-Con",
                        "enabled": True,
                        "reason": None,
                        "requiresConfirmation": True,
                        "gameId": published[0]["id"],
                        "scope": "game",
                        "scopeId": published[0]["id"],
                    },
                ],
                "clearAction": None,
                # Sem perfil ativo não há binding para resolver contra pad
                # nenhum, então o autoconfig é ausência honesta e não um objeto
                # com estado inventado (G45).
                "autoconfig": None,
                # E sem nada resolvido não se oferece a confirmação de gravar:
                # ela não poderia resultar em perfil valendo.
                "applyAutoconfigAction": None,
            },
            "controlsReadiness": {
                "state": "attention",
                "reason": (
                    "Nenhum perfil de input ativo; o jogo usará os padrões do emulador."
                    if published[0]["controlsReadiness"]["controllers"] > 0
                    else "Nenhum perfil de input ativo; o jogo usará os padrões do emulador. "
                    "Nenhum controle detectado no host."
                ),
                "profileConfigured": False,
                "controllers": published[0]["controlsReadiness"]["controllers"],
                # A prontidão passou a publicar o estado do EFEITO, não só o da
                # intenção: perfil salvo não é perfil valendo.
                "autoconfigState": "not-configured",
            },
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


def test_game_launch_tracks_detached_session_and_playtime(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    ticks = iter((10.0, 75.8))
    controller._spawn = lambda _argv: 4242  # type: ignore[attr-defined]
    controller._process_waiter = lambda _pid: 0  # type: ignore[attr-defined]
    controller._monotonic = lambda: next(ticks)  # type: ignore[attr-defined]
    roms = tmp_path / "owned-roms"
    roms.mkdir()
    rom = roms / "Example [0100ABCDEF123000].nsp"
    rom.write_bytes(b"owned-game")
    _apply(
        controller,
        controller.plan_action({"actionId": "library.root.add", "path": str(roms)}),
    )
    game = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    _apply(
        controller,
        controller.plan_action(
            {
                "actionId": "game.emulator.set",
                "gameId": game["id"],
                "emulatorId": "ryubing",
            }
        ),
    )
    monkeypatch.setattr(
        "steamzero.adapters.emulation.AdapterEngine.payload_path",
        lambda _self, emulator_id: tmp_path / f"{emulator_id}.AppImage",
    )
    monkeypatch.setattr(controller, "_require_key_projection", lambda _emulator_id: None)

    result = controller.launch_game(game["id"])
    deadline = time.monotonic() + 2
    session = None
    while time.monotonic() < deadline:
        with StateStore(tmp_path / "state.db") as store:
            store.migrate()
            session = store.latest_game_session(game["id"])
        if session is not None and session["state"] == "closed":
            break
        time.sleep(0.01)

    assert result["sessionId"]
    assert session is not None
    assert session["state"] == "closed"
    assert session["played_seconds"] == 65
    assert session["duration_source"] == "observed-monotonic"
    metadata = json.loads(session["metadata_json"])
    assert metadata["source"] == "emulation"
    assert metadata["title"] == "Example"


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
    assert observed["env"]["STEAMZERO_CLASS"] == "emulator"  # type: ignore[index]


def test_launch_game_persists_ephemeral_start_ticks_identity(
    monkeypatch,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    ticks = iter((10.0, 11.0))
    controller._spawn = lambda _argv: 4242  # type: ignore[attr-defined]
    controller._process_waiter = lambda _pid: 0  # type: ignore[attr-defined]
    controller._monotonic = lambda: next(ticks)  # type: ignore[attr-defined]
    controller._read_start_ticks = lambda _pid: 777  # type: ignore[attr-defined]
    roms = tmp_path / "owned-roms"
    roms.mkdir()
    rom = roms / "Example [0100ABCDEF123000].nsp"
    rom.write_bytes(b"owned-game")
    _apply(
        controller,
        controller.plan_action({"actionId": "library.root.add", "path": str(roms)}),
    )
    game = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    _apply(
        controller,
        controller.plan_action(
            {
                "actionId": "game.emulator.set",
                "gameId": game["id"],
                "emulatorId": "ryubing",
            }
        ),
    )
    monkeypatch.setattr(
        "steamzero.adapters.emulation.AdapterEngine.payload_path",
        lambda _self, _emulator_id: tmp_path / f"{_emulator_id}.AppImage",
    )
    monkeypatch.setattr(controller, "_require_key_projection", lambda _emulator_id: None)

    controller.launch_game(game["id"])

    with StateStore(tmp_path / "state.db") as store:
        store.migrate()
        running = store.active_game_sessions("steamzero-game-session")
    assert [(row["pid"], row["start_ticks"]) for row in running] == [(4242, 777)]


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

    # O argv do Switch agora vem do perfil de launch declarado no platform
    # manifest ("-f -g {rom}") — deve reproduzir exatamente o que o código
    # hardcoded antigo produzia, via _build_exec_argv.
    profile = controller._launch_profile_for("switch", "eden")  # type: ignore[attr-defined]
    assert profile is not None
    assert controller._build_exec_argv(  # type: ignore[attr-defined]
        profile,
        source_type="appimage",
        flatpak_ref=None,
        payload=payload,
        rom=rom,
    ) == [str(bypass), str(payload), "-f", "-g", str(rom)]


def test_launch_argv_flatpak_standalone_from_platform_profile(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = EmulationController(store_factory=lambda: StateStore(tmp_path / "state.db"))
    rom = tmp_path / "Rugby Reigns [Disc 1].iso"
    profile = controller._launch_profile_for("playstation-2", "pcsx2")  # type: ignore[attr-defined]
    assert profile is not None
    argv = controller._build_exec_argv(  # type: ignore[attr-defined]
        profile,
        source_type="flatpak",
        flatpak_ref="net.pcsx2.PCSX2",
        payload=None,
        rom=rom,
    )
    assert argv == ["flatpak", "run", "--user", "net.pcsx2.PCSX2", "--fullscreen", str(rom)]


def test_launch_core_missing_refuses_jogar_before_spawn(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = EmulationController(store_factory=lambda: StateStore(tmp_path / "state.db"))
    from steamzero.domain.launch_profile import LaunchProfile

    profile = LaunchProfile(
        platform_id="nes-famicom",
        adapter_id="retroarch",
        game_args=("-L", "{core}", "{rom}"),
        core="mesen",
    )
    with pytest.raises(SteamZeroError, match="core"):
        controller._build_exec_argv(  # type: ignore[attr-defined]
            profile,
            source_type="flatpak",
            flatpak_ref="org.libretro.RetroArch",
            payload=None,
            rom=tmp_path / "Super (U).nes",
            core_path=None,
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

    with pytest.raises(SteamZeroError) as exc:
        controller.plan_action({"actionId": "library.root.add", "path": str(firmware)})
    assert exc.value.code == "E-CONTENT-UNSAFE-PATH"
    assert str(firmware) in eden.read_text(encoding="utf-8")
    assert str(firmware) in json.loads(ryubing.read_text(encoding="utf-8"))["game_dirs"]


def test_library_root_read_model_open_scan_and_unregister_without_deleting_roms(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    opened: list[tuple[str, ...]] = []
    controller = _controller(monkeypatch, tmp_path)
    controller._which = lambda command: "/usr/bin/xdg-open" if command == "xdg-open" else None  # type: ignore[attr-defined]
    controller._spawn = lambda argv: opened.append(tuple(argv)) or None  # type: ignore[attr-defined]
    root = tmp_path / "owned-roms"
    root.mkdir()
    rom = root / "Example [0100ABCDEF123000].nsp"
    rom.write_bytes(b"owned-game")
    (root / "Update [0100ABCDEF123800].nsp").write_bytes(b"owned-update")
    (root / "DLC [0100ABCDEF124001].nsp").write_bytes(b"owned-dlc")
    (root / "archive.zip").write_bytes(b"archive")
    _apply(
        controller,
        controller.plan_action({"actionId": "library.root.add", "path": str(root)}),
    )
    controller.scan_library()

    media = controller.snapshot({"context": {}})["platforms"][0]["areaData"]["media"]
    row = next(item for item in media["libraryRoots"] if item["displayPath"] == str(root))
    assert row["accessible"] is True
    assert row["counts"] == {
        "base": 1,
        "updates": 1,
        "dlcs": 1,
        "incompatible": 1,
        "errors": 0,
    }
    actions = {action["label"]: action for action in row["actions"]}
    opened_result = _apply(
        controller,
        controller.plan_action({"actionId": actions["Abrir pasta"]["id"]}),
    )
    assert opened_result["opened"] is True
    assert opened == [("/usr/bin/xdg-open", str(root))]

    remove_plan = controller.plan_action({"actionId": actions["Remover da biblioteca"]["id"]})
    _apply(controller, remove_plan)
    assert rom.read_bytes() == b"owned-game"
    assert str(root) not in controller.library_roots()


def test_library_scan_indexes_known_platform_directories_without_scanning_bios(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    root = tmp_path / "owned-roms"
    psx = root / "PSX"
    psx.mkdir(parents=True)
    for index in range(12):
        (psx / f"Game {index:02}.chd").write_bytes(b"owned-game")
    bios = root / "bios"
    bios.mkdir()
    (bios / "ignored.chd").write_bytes(b"firmware")
    _apply(
        controller,
        controller.plan_action({"actionId": "library.root.add", "path": str(root)}),
    )

    result = controller.scan_library()
    cached = json.loads(controller._library_cache_path.read_text(encoding="utf-8"))  # type: ignore[attr-defined]

    assert result["games"] == 10
    assert {game["platform"] for game in cached["games"]} == {"playstation"}
    report = {item["root"]: item for item in cached["directoryInventory"]}
    assert report[str(psx)]["gameCount"] == 12
    assert report[str(psx)]["selectedCount"] == 10
    assert report[str(bios)]["disposition"] == "excluded"


def test_library_scan_enriches_platform_games_with_identity_seam(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """Onda 1 parte 3: costura mínima do domínio na varredura de plataforma —
    identity do disco preenche o game dict sem tocar no caminho Switch."""
    controller = _controller(monkeypatch, tmp_path)
    root = tmp_path / "platform-roms"
    psx = root / "PSX"
    psx.mkdir(parents=True)

    pvd = bytearray(2048)
    pvd[0] = 1
    pvd[1:6] = b"CD001"
    pvd[6] = 1
    pvd[0x20:0x2B] = b"SLUS_005.55"
    image = bytearray(0x8000)
    image[0x8000:0x8800] = pvd
    (psx / "Ridge Racer Revolution.iso").write_bytes(bytes(image))

    _apply(
        controller,
        controller.plan_action({"actionId": "library.root.add", "path": str(root)}),
    )
    result = controller.scan_library()
    assert result["games"] == 1
    cached = json.loads(controller._library_cache_path.read_text(encoding="utf-8"))  # type: ignore[attr-defined]
    game = cached["games"][0]
    assert game["platform"] == "playstation"
    assert game["titleId"] == "SLUS_005.55"
    assert game["identityScheme"] == "psx-serial"
    assert game["identityDiagnosis"] == "pvd-serial"
    assert game["identityVerified"] is True
    assert game["state"] == "ready"


def test_missing_registered_root_remains_visible_and_arbitrary_id_is_refused(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    root = tmp_path / "offline-roms"
    root.mkdir()
    _apply(
        controller,
        controller.plan_action({"actionId": "library.root.add", "path": str(root)}),
    )
    root.rmdir()

    rows = controller.snapshot({"context": {}})["platforms"][0]["areaData"]["media"]["libraryRoots"]
    row = next(item for item in rows if item["displayPath"] == str(root))
    assert row["accessible"] is False
    assert (
        next(action for action in row["actions"] if action["label"] == "Abrir pasta")["enabled"]
        is False
    )
    with pytest.raises(SteamZeroError) as exc:
        controller.plan_action({"actionId": "library.root.open:" + "a" * 24})
    assert exc.value.code == "E-CONTENT-UNSAFE-PATH"


def test_library_root_audit_requires_explicit_selection_and_quarantine_rolls_back(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    root = tmp_path / "audit-roms"
    root.mkdir()
    unknown = root / "readme.txt"
    unknown.write_bytes(b"keep-until-approved")
    _apply(
        controller,
        controller.plan_action({"actionId": "library.root.add", "path": str(root)}),
    )
    row = next(
        item
        for item in controller.snapshot({"context": {}})["platforms"][0]["areaData"]["media"][
            "libraryRoots"
        ]
        if item["displayPath"] == str(root)
    )
    audit_action = next(
        action for action in row["actions"] if action["label"] == "Auditar/higienizar"
    )

    preview = controller.plan_action({"actionId": audit_action["id"]})
    assert preview["auditPreview"]["counts"]["unknown"] == 1
    assert unknown.read_bytes() == b"keep-until-approved"
    quarantining = controller.plan_action(
        {"actionId": audit_action["id"], "approvedPaths": ["readme.txt"]}
    )
    result = _apply(controller, quarantining)
    quarantine = root / ".steamzero-quarantine" / str(result["quarantineId"])
    assert not unknown.exists()
    assert (quarantine / "readme.txt").read_bytes() == b"keep-until-approved"

    rolled_back = controller.rollback_action(str(result["operationId"]))
    assert rolled_back["status"] == "rolled-back"
    assert unknown.read_bytes() == b"keep-until-approved"
    assert not (quarantine / "manifest.json").exists()


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

    active_plan = controller.plan_action({"actionId": record_card["actions"][0]["id"]})
    _apply(controller, active_plan)
    cards = controller.snapshot({"context": {}})["platforms"][0]["areaData"]["updatesDlc"]["cards"]
    active_card = next(card for card in cards if str(card["id"]).startswith("content-"))
    assert active_card["statusLabel"] == "Ativo"
    assert active_card["actions"][0]["label"] == "Desativar"
    assert active_card["actions"][1]["label"] == "Remover"

    remove_plan = controller.plan_action({"actionId": active_card["actions"][1]["id"]})
    _apply(controller, remove_plan)
    cards = controller.snapshot({"context": {}})["platforms"][0]["areaData"]["updatesDlc"]["cards"]
    assert not any(str(card["id"]).startswith("content-") for card in cards)


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


def test_global_media_pipeline_publishes_operational_read_model_and_actions(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    game_id, _title_id = _configured_game(controller, tmp_path)
    queued = controller._jobs.create(  # type: ignore[attr-defined]
        "media.global",
        params={"mode": "refresh", "overwrite": False},
        priority="maintenance",
        created_by="qam",
    )

    area = controller.snapshot({"context": {}})["platforms"][0]["areaData"]["media"]
    pipeline = area["mediaPipeline"]
    assert pipeline["totalGames"] == 1
    assert pipeline["overwriteDefault"] is False
    assert pipeline["cacheBytes"] >= 0
    assert pipeline["lastScan"] is not None
    assert pipeline["activeJobs"][0]["jobId"] == queued.id
    assert {kind["id"] for kind in pipeline["mediaKinds"]} >= {
        "boxart",
        "gridPortrait",
        "gridLandscape",
        "hero",
        "logo",
        "icon",
        "screenshot",
    }
    card = next(card for card in area["cards"] if card["id"] == "media-pipeline")
    assert card["title"] == "Pipeline de mídias"
    action_ids = {action["id"] for action in card["actions"]}
    assert action_ids == {
        "media.audit",
        "media.global.search-missing",
        "media.global.refresh",
        "media.global.overwrite",
        "media.global.optimize",
    }
    overwrite = next(
        action for action in card["actions"] if action["id"] == "media.global.overwrite"
    )
    assert overwrite["overwrite"] is True
    assert overwrite["requiresConfirmation"] is True
    assert game_id


def test_remote_extra_catalogs_are_wired_cached_and_install_cheats_transactionally(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    title_id = "0100ABCDEF123000"
    build_id = "A1" * 16
    mod_candidate = ModCandidate(
        title_id=title_id,
        build_id=build_id,
        identity=ModIdentity(
            name="60 FPS",
            mod_type="performance",
            source="github:test",
            source_url="https://example.invalid/mod.zip",
            description="Patch de desempenho",
        ),
    )
    cheat_candidate = CheatCandidate(
        title_id=title_id,
        build_id=build_id,
        identity=CheatIdentity(
            name="Vida infinita",
            cheat_type="infinite",
            source="nsecm:test",
            source_url="https://example.invalid/cheat.txt",
        ),
        codes=("[Vida infinita]", "04000000 00000000 00000001"),
    )

    class ModCatalog:
        def search_by_title_id(self, requested: str) -> list[ModCandidate]:
            return [mod_candidate] if requested == title_id else []

        def search_by_build_id(self, requested: str, requested_build: str) -> list[ModCandidate]:
            return [mod_candidate] if requested == title_id and requested_build == build_id else []

        def refresh_catalog(self) -> int:
            return 1

    class CheatCatalog:
        def search_by_title_id(self, requested: str) -> list[CheatCandidate]:
            return [cheat_candidate] if requested == title_id else []

        def search_by_build_id(self, requested: str, requested_build: str) -> list[CheatCandidate]:
            return (
                [cheat_candidate] if requested == title_id and requested_build == build_id else []
            )

        def refresh_catalog(self) -> int:
            return 1

    controller = _controller(monkeypatch, tmp_path)
    controller._mod_catalog = ModCatalog()  # type: ignore[attr-defined]
    controller._cheat_catalog = CheatCatalog()  # type: ignore[attr-defined]
    game_id, _ = _configured_game(controller, tmp_path)
    game = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    search_action = game["catalogSearchAction"]

    search_response = _apply(
        controller,
        controller.plan_action(
            {
                "actionId": search_action["id"],
                "gameId": game_id,
            }
        ),
    )
    completed = _wait_job(controller, str(search_response["jobId"]))
    assert completed.result["mods_found"] == 1
    assert completed.result["cheats_found"] == 1

    game = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    assert game["modCandidates"][0]["name"] == "60 FPS"
    mod_action = game["modCandidates"][0]["installAction"]
    assert mod_action["enabled"] is True
    assert str(mod_action["id"]).startswith("mod.catalog.prepare:")
    cheat_action = game["cheatCandidates"][0]["installAction"]
    assert cheat_action["enabled"] is True

    class OfflineCatalog:
        def search_by_title_id(self, _requested: str):  # type: ignore[no-untyped-def]
            raise RuntimeError("offline")

        def search_by_build_id(  # type: ignore[no-untyped-def]
            self, _requested: str, _requested_build: str
        ):
            raise RuntimeError("offline")

        def refresh_catalog(self) -> int:
            raise RuntimeError("offline")

    controller._mod_catalog = OfflineCatalog()  # type: ignore[attr-defined]
    controller._cheat_catalog = OfflineCatalog()  # type: ignore[attr-defined]
    offline_response = _apply(
        controller,
        controller.plan_action(
            {
                "actionId": search_action["id"],
                "gameId": game_id,
            }
        ),
    )
    offline = _wait_job(controller, str(offline_response["jobId"]))
    assert set(offline.result["errors"]) == {"mods", "cheats"}
    cached = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    assert len(cached["modCandidates"]) == 1
    assert len(cached["cheatCandidates"]) == 1

    package = io.BytesIO()
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("exefs/main.ips", b"verified-mod")
    monkeypatch.setattr(emulation, "fetch_bytes", lambda *_args, **_kwargs: package.getvalue())
    prepare_response = _apply(
        controller,
        controller.plan_action(
            {
                "actionId": mod_action["id"],
                "gameId": game_id,
                "emulatorId": "eden",
            }
        ),
    )
    prepared = _wait_job(controller, str(prepare_response["jobId"]))
    assert prepared.result["file_count"] == 1
    cached = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    prepared_mod = cached["modCandidates"][0]
    assert prepared_mod["prepared"] is True
    assert str(prepared_mod["installAction"]["id"]).startswith("mod.catalog.install:")
    catalog_id = str(prepared_mod["installAction"]["id"]).split(":", 1)[1]
    prepared_package = controller._prepared_mod_package(catalog_id)  # type: ignore[attr-defined]
    assert prepared_package is not None
    prepared_file = prepared_package[1][0]
    prepared_file.write_bytes(b"tampered-mod")
    with pytest.raises(SteamZeroError, match="E-MOD-CATALOG-STALE"):
        controller.plan_action(
            {
                "actionId": prepared_mod["installAction"]["id"],
                "gameId": game_id,
                "emulatorId": "eden",
            }
        )
    prepared_file.write_bytes(b"verified-mod")
    _apply(
        controller,
        controller.plan_action(
            {
                "actionId": prepared_mod["installAction"]["id"],
                "gameId": game_id,
                "emulatorId": "eden",
            }
        ),
    )

    install = controller.plan_action(
        {
            "actionId": cheat_action["id"],
            "gameId": game_id,
            "emulatorId": "eden",
        }
    )
    _apply(controller, install)

    game = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    assert game["modsCount"] == 1
    assert game["mods"][0]["source"] == "github:test"
    installed_mod = controller._extra_record(  # type: ignore[attr-defined]
        "mod", str(game["mods"][0]["id"])
    )
    assert installed_mod is not None and installed_mod.install_path is not None
    assert (Path(installed_mod.install_path) / "main.ips").read_bytes() == b"verified-mod"
    assert game["cheatsCount"] == 1
    assert game["cheats"][0]["source"] == "nsecm:test"
    installed = controller._extra_record(  # type: ignore[attr-defined]
        "cheat", str(game["cheats"][0]["id"])
    )
    assert installed is not None and installed.install_path is not None
    installed_path = Path(installed.install_path)
    assert installed_path.read_text(encoding="utf-8").startswith("// Vida infinita\n// BuildID:")


def test_remote_mod_catalog_rejects_zip_traversal_without_prepared_cache(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    title_id = "0100ABCDEF123000"
    candidate = ModCandidate(
        title_id=title_id,
        build_id=None,
        identity=ModIdentity(
            name="Pacote suspeito",
            mod_type="other",
            source="github:test",
            source_url="https://example.invalid/traversal.zip",
        ),
    )

    class ModCatalog:
        def search_by_title_id(self, requested: str) -> list[ModCandidate]:
            return [candidate] if requested == title_id else []

        def search_by_build_id(self, _requested: str, _requested_build: str) -> list[ModCandidate]:
            return []

        def refresh_catalog(self) -> int:
            return 1

    class EmptyCheatCatalog:
        def search_by_title_id(self, _requested: str) -> list[CheatCandidate]:
            return []

        def search_by_build_id(
            self, _requested: str, _requested_build: str
        ) -> list[CheatCandidate]:
            return []

        def refresh_catalog(self) -> int:
            return 0

    controller = _controller(monkeypatch, tmp_path)
    controller._mod_catalog = ModCatalog()  # type: ignore[attr-defined]
    controller._cheat_catalog = EmptyCheatCatalog()  # type: ignore[attr-defined]
    game_id, _ = _configured_game(controller, tmp_path)
    game = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    search_response = _apply(
        controller,
        controller.plan_action(
            {
                "actionId": game["catalogSearchAction"]["id"],
                "gameId": game_id,
            }
        ),
    )
    _wait_job(controller, str(search_response["jobId"]))
    game = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    prepare_action = game["modCandidates"][0]["installAction"]

    package = io.BytesIO()
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("../escape.ips", b"unsafe")
    monkeypatch.setattr(emulation, "fetch_bytes", lambda *_args, **_kwargs: package.getvalue())
    response = _apply(
        controller,
        controller.plan_action(
            {
                "actionId": prepare_action["id"],
                "gameId": game_id,
                "emulatorId": "eden",
            }
        ),
    )
    rejected = _wait_job(controller, str(response["jobId"]))

    assert rejected.state == "rolled-back"
    assert rejected.error_code == "E-CONTENT-UNSAFE-PATH"
    assert not (tmp_path / "escape.ips").exists()
    game = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    assert game["modCandidates"][0]["prepared"] is False


def test_global_media_overwrite_requires_explicit_flag_and_returns_job(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    _configured_game(controller, tmp_path)
    with pytest.raises(SteamZeroError, match="overwrite=true"):
        controller.plan_action({"actionId": "media.global.overwrite"})

    response = _apply(
        controller,
        controller.plan_action({"actionId": "media.global.overwrite", "overwrite": True}),
    )

    assert response["job"]["rawState"] in {"queued", "running", "completed"}
    completed = _wait_job(controller, str(response["jobId"]))
    result = completed.result
    assert result["overwrite"] is True
    assert result["total"] == 1
    assert result["provider_errors"] == {}
    assert completed.progress["stage"] == "games"
    assert completed.progress["current"] == 1


def test_global_media_overwrite_collects_and_optimizes_first_candidate(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    import base64

    from steamzero.core import fs
    from steamzero.ports import GameIdentity, MediaCandidate

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
        "AScY42YAAAAASUVORK5CYII="
    )

    class Provider:
        name = "screenscraper"

        @staticmethod
        def supported_kinds() -> frozenset[str]:
            return frozenset({"boxart"})

        @staticmethod
        def supported_platforms() -> frozenset[str]:
            return frozenset({"switch"})

        def search(
            self,
            _identity: GameIdentity,
            _media_kinds: list[str],
            _region_priority: list[str] | None = None,
        ) -> list[MediaCandidate]:
            return [
                MediaCandidate(
                    url="https://provider.invalid/boxart.png",
                    media_kind="boxart",
                    provider=self.name,
                    confidence=1.0,
                )
            ]

    controller = _controller(monkeypatch, tmp_path)
    game_id, _title_id = _configured_game(controller, tmp_path)
    controller._media_providers = (Provider(),)  # type: ignore[attr-defined]
    controller._media_candidate_fetcher = lambda _url: png  # type: ignore[attr-defined]

    def optimize(source: Path, destination: Path, _profile: str) -> bool:
        fs.copy_file_atomic(source, destination)
        return True

    controller._media_optimizer_tool = optimize  # type: ignore[attr-defined]

    response = _apply(
        controller,
        controller.plan_action({"actionId": "media.global.overwrite", "overwrite": True}),
    )

    completed = _wait_job(controller, str(response["jobId"]))
    assert completed.result["updated"] == 1
    game = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    assert game["id"] == game_id
    assert game["mediaSource"] == "scraper"
    assert game["masterState"] == "collected"
    assert game["optimizedState"] == "ready"


def test_global_media_apply_returns_before_background_provider_finishes(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    from steamzero.ports import GameIdentity, MediaCandidate

    started = threading.Event()
    release = threading.Event()

    class SlowProvider:
        name = "screenscraper"

        @staticmethod
        def supported_kinds() -> frozenset[str]:
            return frozenset({"boxart"})

        @staticmethod
        def supported_platforms() -> frozenset[str]:
            return frozenset({"switch"})

        def search(
            self,
            _identity: GameIdentity,
            _media_kinds: list[str],
            _region_priority: list[str] | None = None,
        ) -> list[MediaCandidate]:
            started.set()
            release.wait(timeout=2)
            return []

    controller = _controller(monkeypatch, tmp_path)
    _configured_game(controller, tmp_path)
    (tmp_path / "owned-roms" / "Second [0100ABCDEF124000].nsp").write_bytes(b"second-owned-game")
    controller.scan_library()
    controller._media_providers = (SlowProvider(),)  # type: ignore[attr-defined]

    response = _apply(
        controller,
        controller.plan_action({"actionId": "media.global.refresh"}),
    )

    assert started.wait(timeout=1)
    # O estado prova o retorno antecipado sem medir a carga do runner:
    # o provider continua bloqueado e o job ainda não pôde terminar.
    assert controller._jobs.get(str(response["jobId"])).state == "running"  # type: ignore[attr-defined,union-attr]
    cancellation = controller.cancel_job(str(response["jobId"]))
    assert cancellation["rawState"] == "running"
    release.set()
    assert _wait_job(controller, str(response["jobId"])).state == "cancelled"


def test_media_cache_open_uses_only_managed_real_directory(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from steamzero.core import paths

    controller = _controller(monkeypatch, tmp_path)
    paths.media_dir().mkdir(parents=True)
    calls: list[tuple[str, ...]] = []
    controller._which = (  # type: ignore[attr-defined]
        lambda command: "/usr/bin/xdg-open" if command == "xdg-open" else None
    )
    controller._spawn = lambda argv: calls.append(tuple(argv))  # type: ignore[attr-defined]

    response = _apply(
        controller,
        controller.plan_action({"actionId": "media.cache.open"}),
    )

    assert response["opened"] is True
    assert response["target"] == "media-cache"
    assert calls == [("/usr/bin/xdg-open", str(paths.media_dir().resolve()))]


def test_global_media_job_cancel_and_retry_are_persistent(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    job = controller._jobs.create(  # type: ignore[attr-defined]
        "media.global",
        params={"mode": "audit", "overwrite": False},
        priority="maintenance",
        created_by="qam",
    )

    cancelled = controller.cancel_job(job.id)
    assert cancelled["rawState"] == "cancelled"
    retried = controller.retry_job(job.id)
    assert retried["rawState"] in {"queued", "running", "completed"}
    completed = _wait_job(controller, str(retried["jobId"]))
    assert completed.result["mode"] == "audit"
    assert controller._media_audit_path.is_file()  # type: ignore[attr-defined]
    pipeline = controller.snapshot({"context": {}})["platforms"][0]["areaData"]["media"][
        "mediaPipeline"
    ]
    assert pipeline["lastAudit"] == completed.result["checked_at"]


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


def test_mod_conflicts_are_blocked_and_priority_is_honestly_unsupported(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    game_id, _title_id = _configured_game(controller, tmp_path)
    first = tmp_path / "First mod"
    second = tmp_path / "Second mod"
    (first / "romfs").mkdir(parents=True)
    (second / "romfs").mkdir(parents=True)
    (first / "romfs" / "config.bin").write_bytes(b"one")
    (second / "romfs" / "config.bin").write_bytes(b"two")
    _apply(
        controller,
        controller.plan_action(
            {
                "actionId": "mod.import",
                "gameId": game_id,
                "emulatorId": "eden",
                "path": str(first),
            }
        ),
    )

    with pytest.raises(SteamZeroError) as error:
        controller.plan_action(
            {
                "actionId": "mod.import",
                "gameId": game_id,
                "emulatorId": "eden",
                "path": str(second),
            }
        )
    assert error.value.code == "E-MOD-INSTALL-FAILED"
    assert "First mod" in str(error.value.detail)

    game = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    assert game["modPriorityCapability"]["supported"] is False
    assert "ordem de sobreposição" in game["modPriorityCapability"]["reason"]
    assert game["mods"][0]["priority"] is None
    assert game["mods"][0]["prioritySupported"] is False
    assert "moveUpAction" not in game["mods"][0]
    assert "moveDownAction" not in game["mods"][0]


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


def test_media_search_job_created_in_plan(monkeypatch, tmp_path: Path) -> None:
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
    store.close()


def test_media_search_plan_does_not_require_fixed_remote_provider(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    game_id, _title_id = _configured_game(controller, tmp_path)

    plan = controller.plan_action(
        {"actionId": f"game.media.search:{game_id}", "mediaKinds": ["boxart"]}
    )

    assert isinstance(plan["planId"], str)
    assert isinstance(plan["confirmToken"], str)


def test_media_job_persists_read_model_in_injected_store(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from steamzero.adapters.emulation import SessionSecretStore
    from steamzero.adapters.state_store_media import StateStoreGameMediaAdapter

    controller = _controller(monkeypatch, tmp_path)
    controller._secret_store = SessionSecretStore()  # type: ignore[attr-defined]
    job = controller._jobs.create(  # type: ignore[attr-defined]
        "media.search",
        params={"game_id": "g1", "title_id": "0100ABCDEF123000", "title": "Owned"},
    )

    completed = controller._jobs.run(job.id)  # type: ignore[attr-defined]

    assert completed.state == "completed"
    with StateStore(tmp_path / "state.db") as store:
        store.migrate()
        media = StateStoreGameMediaAdapter(store.adapter_connection()).load("g1")
    assert media is not None
    assert media.metadata_state == "degraded"
    assert "Nenhum provider remoto configurado" in media.reason


def test_get_job_status_returns_none_for_missing(monkeypatch, tmp_path: Path) -> None:
    from steamzero.jobs.manager import JobManager

    store = StateStore(tmp_path / "test_missing_job.db")
    store.migrate()
    controller = _controller(monkeypatch, tmp_path)
    controller._jobs = JobManager(store)
    assert controller.get_job_status("nonexistent") is None
    store.close()


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


def test_rom_scan_job_created_in_plan(monkeypatch, tmp_path: Path) -> None:
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
    plan = controller.plan_action({"actionId": "rom.scan"})
    result = _apply(controller, plan)
    assert "jobId" in result
    job = controller.get_job_status(result["jobId"])
    assert job is not None
    assert job["type"] == "rom.scan"
    store.close()


def test_library_scan_publishes_global_job_progress(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    roms = tmp_path / "roms"
    roms.mkdir()
    (roms / "Game [0100ABCDEF123000].nsp").write_bytes(b"owned")
    monkeypatch.setattr(controller, "library_roots", lambda: [str(roms)])

    result = controller.scan_library()

    assert result["games"] == 1
    assert result["job"]["state"] == "succeeded"
    assert result["job"]["progress"] == {
        "stage": "done",
        "current": 1,
        "total": 1,
        "unit": "roots",
        "currentItem": None,
    }
    listed = controller.list_jobs()
    assert listed[0]["jobId"] == result["jobId"]
    assert "params" not in listed[0]


def _plant_library_cache(tmp_path: Path, games: list[dict]) -> Path:
    cache = tmp_path / "data" / "steamzero" / "emulation-library-cache-v1.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps({"schemaVersion": 1, "games": games}, ensure_ascii=False),
        encoding="utf-8",
    )
    return cache


class TestProjectionRepair:
    """library.projection.repair: plan/apply/verify/rollback do catálogo."""

    def test_removes_ghosts_and_keeps_real_files(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        controller = _controller(monkeypatch, tmp_path)
        rom = tmp_path / "data" / "roms" / "Game.nsp"
        rom.parent.mkdir(parents=True)
        rom.write_bytes(b"owned-game")
        _plant_library_cache(
            tmp_path,
            [
                {"id": "a", "name": "Game", "state": "ready", "path": str(rom)},
                {"id": "b", "name": "Ghost", "state": "ready", "path": str(tmp_path / "sumiu.nsp")},
            ],
        )

        plan = controller.plan_action({"actionId": "library.projection.repair"})
        assert "1 de 2" in str(plan["preview"])
        result = _apply(controller, plan)

        assert result["projectionRepair"]["removed"] == 1  # type: ignore[index]
        assert result["verify"]["ghostsAfterApply"] == 0  # type: ignore[index]
        assert result["verify"]["userFilesUntouched"] is True  # type: ignore[index]
        data = json.loads(controller._library_cache_path.read_text(encoding="utf-8"))  # type: ignore[attr-defined]
        assert [game["id"] for game in data["games"]] == ["a"]
        assert rom.read_bytes() == b"owned-game"

    def test_is_noop_when_projection_is_consistent(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        controller = _controller(monkeypatch, tmp_path)
        rom = tmp_path / "data" / "roms" / "Game.nsp"
        rom.parent.mkdir(parents=True)
        rom.write_bytes(b"owned-game")
        cache = _plant_library_cache(
            tmp_path,
            [{"id": "a", "name": "Game", "state": "ready", "path": str(rom)}],
        )
        before = cache.read_bytes()

        plan = controller.plan_action({"actionId": "library.projection.repair"})
        assert "0 de 1" in str(plan["preview"])
        result = _apply(controller, plan)

        assert result["projectionRepair"]["removed"] == 0  # type: ignore[index]
        assert result["verify"]["ghostsAfterApply"] == 0  # type: ignore[index]
        assert cache.read_bytes() == before

    def test_rollback_restores_cache_with_ghost(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        controller = _controller(monkeypatch, tmp_path)
        rom = tmp_path / "data" / "roms" / "Game.nsp"
        rom.parent.mkdir(parents=True)
        rom.write_bytes(b"owned-game")
        cache = _plant_library_cache(
            tmp_path,
            [
                {"id": "a", "name": "Game", "state": "ready", "path": str(rom)},
                {"id": "b", "name": "Ghost", "state": "ready", "path": str(tmp_path / "sumiu.nsp")},
            ],
        )
        before = cache.read_bytes()

        result = _apply(
            controller, controller.plan_action({"actionId": "library.projection.repair"})
        )
        assert result["verify"]["ghostsAfterApply"] == 0  # type: ignore[index]

        controller.rollback_action(str(result["operationId"]))
        assert cache.read_bytes() == before

    def test_blocks_without_cache(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        controller = _controller(monkeypatch, tmp_path)
        with pytest.raises(SteamZeroError) as excinfo:
            controller.plan_action({"actionId": "library.projection.repair"})
        assert excinfo.value.code == "E-CONTENT-INCOMPLETE"


class TestBiosLink:
    """bios.link: projeção do store central de BIOS para emuladores."""

    def _plant_bios(self, tmp_path: Path, platform: str, names: dict[str, bytes]) -> None:
        root = tmp_path / "data" / "steamzero" / "bios" / platform
        root.mkdir(parents=True)
        for name, content in names.items():
            (root / name).write_bytes(content)

    def test_projects_central_store_to_emulator_dirs(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        controller = _controller(monkeypatch, tmp_path)
        self._plant_bios(
            tmp_path,
            "amiga",
            {"kick34005.A500": b"a500", "kick40068.A1200": b"a1200"},
        )

        plan = controller.plan_action(
            {"actionId": "bios.link", "platformId": "amiga", "adapterId": "retroarch"}
        )
        _apply(controller, plan)

        system = tmp_path / "home" / ".config" / "retroarch" / "system"
        assert (system / "kick34005.A500").read_bytes() == b"a500"
        assert (system / "kick40068.A1200").read_bytes() == b"a1200"
        assert controller._bios_projection_copies("amiga", "retroarch") == []  # type: ignore[attr-defined]

    def test_blocks_when_bios_missing_in_store(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        controller = _controller(monkeypatch, tmp_path)
        with pytest.raises(SteamZeroError) as excinfo:
            controller.plan_action(
                {"actionId": "bios.link", "platformId": "amiga", "adapterId": "retroarch"}
            )
        assert excinfo.value.code == "E-CONTENT-BIOS-MISSING"
        assert "kick34005.A500" in str(excinfo.value.detail)

    def test_blocks_adapter_without_declared_bios(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        controller = _controller(monkeypatch, tmp_path)
        with pytest.raises(SteamZeroError) as excinfo:
            controller.plan_action(
                {"actionId": "bios.link", "platformId": "playstation", "adapterId": "duckstation"}
            )
        assert excinfo.value.code == "E-API-SCHEMA"

    def test_blocks_divergent_existing_target(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        controller = _controller(monkeypatch, tmp_path)
        self._plant_bios(
            tmp_path, "amiga", {"kick34005.A500": b"a500", "kick40068.A1200": b"a1200"}
        )
        system = tmp_path / "home" / ".config" / "retroarch" / "system"
        system.mkdir(parents=True)
        (system / "kick34005.A500").write_bytes(b"divergente")

        with pytest.raises(SteamZeroError) as excinfo:
            controller.plan_action(
                {"actionId": "bios.link", "platformId": "amiga", "adapterId": "retroarch"}
            )
        assert excinfo.value.code == "E-CONTENT-FW-INCOMPAT"

    def test_rollback_removes_projected_copies(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        controller = _controller(monkeypatch, tmp_path)
        self._plant_bios(
            tmp_path, "amiga", {"kick34005.A500": b"a500", "kick40068.A1200": b"a1200"}
        )
        system = tmp_path / "home" / ".config" / "retroarch" / "system"

        result = _apply(
            controller,
            controller.plan_action(
                {"actionId": "bios.link", "platformId": "amiga", "adapterId": "retroarch"}
            ),
        )
        assert (system / "kick34005.A500").is_file()

        controller.rollback_action(str(result["operationId"]))
        assert not (system / "kick34005.A500").exists()


class TestAssociatedContentProjection:
    """update/DLC como conteúdo associado: nunca viram jogos duplicados."""

    def test_game_rows_carry_associated_content_and_validate(
        self, monkeypatch, tmp_path: Path
    ) -> None:  # type: ignore[no-untyped-def]
        controller = _controller(monkeypatch, tmp_path)
        roms = tmp_path / "home" / "Games" / "Switch"
        roms.mkdir(parents=True)
        root_plan = controller.plan_action({"actionId": "library.root.add", "path": str(roms)})
        _apply(controller, root_plan)
        rom = roms / "Game [0100ABCDEF123000][v0].nsp"
        rom.write_bytes(b"owned-game")
        controller.scan_library()
        data = json.loads(controller._library_cache_path.read_text(encoding="utf-8"))  # type: ignore[attr-defined]
        data["games"][0].update({"updateCount": 2, "dlcCount": 1, "updateVersion": "v3"})
        controller._library_cache_path.write_text(  # type: ignore[attr-defined]
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

        workspace = controller.snapshot({"context": {}})
        game = workspace["platforms"][0]["games"][0]  # type: ignore[index]
        assert game["updateCount"] == 2
        assert game["dlcCount"] == 1
        assert game["updateVersion"] == "v3"
        assert game["contentKind"] == "base"

    def test_auxiliary_content_never_becomes_a_game(self, monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        controller = _controller(monkeypatch, tmp_path)
        roms = tmp_path / "home" / "Games" / "Switch"
        roms.mkdir(parents=True)
        root_plan = controller.plan_action({"actionId": "library.root.add", "path": str(roms)})
        _apply(controller, root_plan)
        rom = roms / "Game [0100ABCDEF123000][v0].nsp"
        rom.write_bytes(b"owned-game")
        controller.scan_library()
        data = json.loads(controller._library_cache_path.read_text(encoding="utf-8"))  # type: ignore[attr-defined]
        data["games"][0]["contentKind"] = "update"
        controller._library_cache_path.write_text(  # type: ignore[attr-defined]
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

        workspace = controller.snapshot({"context": {}})
        games = workspace["platforms"][0]["games"]  # type: ignore[index]
        assert games == []


def test_contract_rejects_auxiliary_kind_in_game_row(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """O contrato cimenta: update/DLC nunca podem aparecer como jogo."""
    controller = _controller(monkeypatch, tmp_path)
    roms = tmp_path / "home" / "Games" / "Switch"
    roms.mkdir(parents=True)
    root_plan = controller.plan_action({"actionId": "library.root.add", "path": str(roms)})
    _apply(controller, root_plan)
    (roms / "Game [0100ABCDEF123000][v0].nsp").write_bytes(b"owned-game")
    controller.scan_library()

    workspace = controller.snapshot({"context": {}})
    game = workspace["platforms"][0]["games"][0]  # type: ignore[index]
    game["contentKind"] = "update"
    with pytest.raises(jsonschema.exceptions.ValidationError):
        validate(workspace, "emulation-workspace-v1.schema.json")


def test_bios_import_plans_applies_and_persists(monkeypatch, tmp_path: Path) -> None:
    """REQUIREMENTS-E2E: importar BIOS local copia para o store central e
    registra presença no state — nunca baixa, nunca loga conteúdo."""
    controller = _controller(monkeypatch, tmp_path)
    from steamzero.core import paths as core_paths

    bios_file = tmp_path / "panafz1.bin"
    bios_file.write_bytes(b"owned-bios")
    plan = controller.plan_action(
        {
            "actionId": "bios.import",
            "path": str(bios_file),
            "platformId": "three-do",
            "adapterId": "retroarch",
        }
    )
    _apply(controller, plan)
    target = core_paths.bios_dir() / "three-do" / "panafz1.bin"
    assert target.is_file()
    assert target.read_bytes() == b"owned-bios"
    with controller._store_factory() as store:  # type: ignore[attr-defined]
        store.migrate()
        items = store.list_bios("three-do")
    assert len(items) == 1
    assert items[0]["state"] == "present"
    assert items[0]["relpath"] == "three-do/panafz1.bin"
    assert items[0]["hash"] == hashlib.sha256(b"owned-bios").hexdigest()


def test_bios_import_rejects_undeclared_name(monkeypatch, tmp_path: Path) -> None:
    """Só nomes declarados no perfil de launch da plataforma são aceitos."""
    controller = _controller(monkeypatch, tmp_path)
    foreign = tmp_path / "scph5501.bin"
    foreign.write_bytes(b"foreign-bios")
    with pytest.raises(SteamZeroError) as exc:
        controller.plan_action(
            {
                "actionId": "bios.import",
                "path": str(foreign),
                "platformId": "three-do",
                "adapterId": "retroarch",
            }
        )
    assert exc.value.code == "E-CONTENT-FW-INCOMPAT"


def test_bios_import_rejects_platform_without_bios(monkeypatch, tmp_path: Path) -> None:
    """Plataforma/emulador que não declara BIOS não aceita import."""
    controller = _controller(monkeypatch, tmp_path)
    bios_file = tmp_path / "scph5501.bin"
    bios_file.write_bytes(b"bios")
    with pytest.raises(SteamZeroError) as exc:
        controller.plan_action(
            {
                "actionId": "bios.import",
                "path": str(bios_file),
                "platformId": "playstation",
                "adapterId": "duckstation",
            }
        )
    assert exc.value.code == "E-API-SCHEMA"


def test_bios_import_rejects_oversized_or_missing_source(monkeypatch, tmp_path: Path) -> None:
    controller = _controller(monkeypatch, tmp_path)
    huge = tmp_path / "panafz1.bin"
    huge.write_bytes(b"x" * (64 * 1024**2 + 1))
    with pytest.raises(SteamZeroError) as exc:
        controller.plan_action(
            {
                "actionId": "bios.import",
                "path": str(huge),
                "platformId": "three-do",
                "adapterId": "retroarch",
            }
        )
    assert exc.value.code == "E-CONTENT-UNSAFE-ARCHIVE"
    missing = tmp_path / "nunca-existiu.bin"
    with pytest.raises(SteamZeroError) as exc:
        controller.plan_action(
            {
                "actionId": "bios.import",
                "path": str(missing),
                "platformId": "three-do",
                "adapterId": "retroarch",
            }
        )
    assert exc.value.code == "E-CONTENT-UNSAFE-PATH"


def test_bios_import_reimport_is_idempotent_on_the_file(monkeypatch, tmp_path: Path) -> None:
    """Reimportar a mesma BIOS não sobrescreve nem duplica o arquivo central."""
    controller = _controller(monkeypatch, tmp_path)
    from steamzero.core import paths as core_paths

    bios_file = tmp_path / "panafz1.bin"
    bios_file.write_bytes(b"owned-bios")
    first = controller.plan_action(
        {
            "actionId": "bios.import",
            "path": str(bios_file),
            "platformId": "three-do",
            "adapterId": "retroarch",
        }
    )
    _apply(controller, first)
    second = controller.plan_action(
        {
            "actionId": "bios.import",
            "path": str(bios_file),
            "platformId": "three-do",
            "adapterId": "retroarch",
        }
    )
    _apply(controller, second)
    target = core_paths.bios_dir() / "three-do" / "panafz1.bin"
    assert target.is_file()
    assert target.read_bytes() == b"owned-bios"


def test_bios_import_never_leaks_content_into_logs(
    monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-BI-01/SR-14: conteúdo e hash completo de BIOS nunca vão para log."""
    controller = _controller(monkeypatch, tmp_path)
    bios_file = tmp_path / "panafz1.bin"
    bios_file.write_bytes(b"conteudo-sintetico-de-bios-falsa")
    plan = controller.plan_action(
        {
            "actionId": "bios.import",
            "path": str(bios_file),
            "platformId": "three-do",
            "adapterId": "retroarch",
        }
    )
    _apply(controller, plan)
    captured = capsys.readouterr().out + capsys.readouterr().err
    assert "conteudo-sintetico-de-bios-falsa" not in captured
    assert hashlib.sha256(b"conteudo-sintetico-de-bios-falsa").hexdigest() not in captured


def _preservation_controller(  # type: ignore[no-untyped-def]
    monkeypatch, tmp_path: Path, kind: str, file: str | None
):
    from steamzero.adapters.preservation import PreservationService, PreservationTarget

    controller = _controller(monkeypatch, tmp_path)
    roms = tmp_path / "owned-roms"
    roms.mkdir()
    (roms / "Example [0100ABCDEF123000].nsp").write_bytes(b"owned-game")
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
    root = tmp_path / "emulator" / "saves"
    root.mkdir(parents=True)
    if file is not None:
        (root / file).write_bytes(b"initial")
    target = PreservationTarget(
        kind=kind,
        game_id=game_id,
        title_id="0100ABCDEF123000",
        emulator_id="ryubing",
        root=root,
        emulator_version="1.0",
        file=file,
    )
    service = PreservationService(
        controller._content,  # type: ignore[attr-defined]
        targets=[target],
        emulator_version=lambda _emulator_id: "1.0",
    )
    controller._preservation = service  # type: ignore[attr-defined]
    return controller, game_id, root


def test_preservation_actions_blocked_while_game_session_runs(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    import os

    controller, game_id, root = _preservation_controller(monkeypatch, tmp_path, "save", None)
    (root / "save.bin").write_bytes(b"dado")
    controller._running_pids["ryubing"] = os.getpid()  # type: ignore[attr-defined]
    for action in (
        f"game.save.backup:{game_id}",
        f"game.shader.backup:{game_id}",
        f"game.state.restore:{game_id}:qualquer",
    ):
        with pytest.raises(SteamZeroError) as error:
            controller.plan_action({"actionId": action})
        assert error.value.code == "E-CONTENT-BUSY"
    controller._running_pids.clear()  # type: ignore[attr-defined]
    plan = controller.plan_action({"actionId": f"game.save.backup:{game_id}"})
    assert plan["planId"]


def test_session_save_checkpoint_captures_once_and_trims_to_eight(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller, game_id, root = _preservation_controller(monkeypatch, tmp_path, "save", None)
    save = root / "save.bin"
    save.write_bytes(b"v1")
    controller._session_save_checkpoint(game_id, "0100ABCDEF123000", "ryubing")  # type: ignore[attr-defined]
    assert len(controller._preservation.backups("0100ABCDEF123000", "ryubing", "save")) == 1  # type: ignore[attr-defined]
    controller._session_save_checkpoint(game_id, "0100ABCDEF123000", "ryubing")  # type: ignore[attr-defined]
    assert len(controller._preservation.backups("0100ABCDEF123000", "ryubing", "save")) == 1  # type: ignore[attr-defined]
    for index in range(2, 12):
        save.write_bytes(f"v{index}".encode())
        controller._session_save_checkpoint(game_id, "0100ABCDEF123000", "ryubing")  # type: ignore[attr-defined]
    rows = controller._preservation.backups("0100ABCDEF123000", "ryubing", "save")  # type: ignore[attr-defined]
    assert len(rows) == 8
    assert save.read_bytes() == b"v11"


def test_state_backup_restore_roundtrip_via_controller(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller, game_id, root = _preservation_controller(
        monkeypatch, tmp_path, "state", "Zelda (USA).state"
    )
    (root / "Zelda (USA).state").write_bytes(b"state-one")
    backup = controller.plan_action({"actionId": f"game.state.backup:{game_id}"})
    _apply(controller, backup)
    rows = controller._preservation.backups("0100ABCDEF123000", "ryubing", "state")  # type: ignore[attr-defined]
    assert len(rows) == 1
    (root / "Zelda (USA).state").write_bytes(b"state-two")
    restore = controller.plan_action(
        {"actionId": f"game.state.restore:{game_id}:{rows[0]['recordKey']}"}
    )
    assert "preservado como um novo backup" in restore["preview"]
    applied = _apply(controller, restore)
    assert applied.get("restoreApplied") is True
    assert (root / "Zelda (USA).state").read_bytes() == b"state-one"
    after = controller._preservation.backups("0100ABCDEF123000", "ryubing", "state")  # type: ignore[attr-defined]
    assert len(after) == 2


def test_conflicting_save_restore_preserves_both_versions(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controller, game_id, root = _preservation_controller(monkeypatch, tmp_path, "save", None)
    save = root / "save.bin"
    save.write_bytes(b"v1")
    _apply(controller, controller.plan_action({"actionId": f"game.save.backup:{game_id}"}))
    save.write_bytes(b"v2")
    rows = controller._preservation.backups("0100ABCDEF123000", "ryubing", "save")  # type: ignore[attr-defined]
    assert len(rows) == 1
    restore = controller.plan_action(
        {"actionId": f"game.save.restore:{game_id}:{rows[0]['recordKey']}"}
    )
    applied = _apply(controller, restore)
    assert applied.get("restoreApplied") is True
    assert save.read_bytes() == b"v1"
    after = controller._preservation.backups("0100ABCDEF123000", "ryubing", "save")  # type: ignore[attr-defined]
    assert len(after) == 2


def _controls_game(monkeypatch, tmp_path: Path, controls=None) -> tuple[EmulationController, str]:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path, controls=controls)
    roms = tmp_path / "roms"
    roms.mkdir()
    (roms / "Example [0100ABCDEF123000][v0].nsp").write_bytes(b"owned-game")
    root_plan = controller.plan_action({"actionId": "library.root.add", "path": str(roms)})
    _apply(controller, root_plan)
    controller.scan_library()
    game = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    return controller, str(game["id"])


_AUTOCONFIG_PAD = """
input_driver = "udev"
input_device = "Pad de Teste"
input_vendor_id = "10462"
input_product_id = "1142"
input_b_btn = "0"
input_a_btn = "1"
input_y_btn = "2"
input_x_btn = "3"
input_start_btn = "7"
input_select_btn = "6"
input_l_btn = "4"
input_r_btn = "5"
input_up_btn = "h0up"
input_down_btn = "h0down"
input_left_btn = "h0left"
input_right_btn = "h0right"
"""


class _FakePad:
    def identities(self) -> list[input_devices.DeviceIdentity]:
        return [input_devices.DeviceIdentity("Pad de Teste", 10462, 1142)]


def _controls_with_pad(monkeypatch, tmp_path: Path, *, declared: bool):  # type: ignore[no-untyped-def]
    bundled = tmp_path / "bundled"
    bundled.mkdir()
    (bundled / "pad.cfg").write_text(_AUTOCONFIG_PAD, encoding="utf-8")
    target = tmp_path / "perfis"
    target.mkdir()
    return input_devices.RetroArchControls(
        devices=_FakePad(),
        catalog=input_devices.AutoconfigCatalog([bundled]),
        target=input_devices.AutoconfigTarget(target, declared=declared),
    )


def test_controls_profile_publishes_the_autoconfig_the_screen_needs(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """G45: a tela precisa distinguir perfil SALVO de perfil que vale de fato.

    O perfil ativo aqui esta salvo e traduzido, e o pad e reconhecido — mas
    nada foi gravado, entao o estado publicado e `pending-write`. Dizer
    "configurado" neste ponto seria a promessa vazia que a G45 registra.
    """
    controller, _game_id = _controls_game(
        monkeypatch, tmp_path, controls=_controls_with_pad(monkeypatch, tmp_path, declared=True)
    )
    plan = controller.plan_action({"actionId": "controls.profile.activate:standard-gamepad"})
    _apply(controller, plan)

    autoconfig = controller.snapshot({"context": {}})["platforms"][0]["games"][0][
        "controlsProfile"
    ]["autoconfig"]

    assert autoconfig["state"] == "pending-write"
    assert autoconfig["device"] == {
        "name": "Pad de Teste",
        "vendorId": 10462,
        "productId": 1142,
    }
    assert autoconfig["unresolvedBindings"] == []
    gravados = {row["key"]: row["value"] for row in autoconfig["resolvedBindings"]}
    assert gravados["input_b_btn"] == "0"
    # O direcional deste pad e BOTAO. A traducao abstrata publica
    # `input_up_axis`; quem resolve contra o dispositivo corrige para `_btn`.
    assert gravados["input_up_btn"] == "h0up"
    assert "input_up_axis" not in gravados


def test_the_autoconfig_reaches_disk_through_a_confirmed_action(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """G45: o writer precisa ter rota de PRODUÇÃO, não só de teste.

    Antes desta ação o perfil chegava a `pending-write` e ninguém materializava
    o arquivo: a ativação só gravava a seleção, e o dashboard apenas observava.
    A integração inteira ficava inerte — e `write-failed` era inalcançável.
    """
    controls = _controls_with_pad(monkeypatch, tmp_path, declared=True)
    controller, _game_id = _controls_game(monkeypatch, tmp_path, controls=controls)
    _apply(
        controller,
        controller.plan_action({"actionId": "controls.profile.activate:standard-gamepad"}),
    )

    def _profile() -> dict:
        return controller.snapshot({"context": {}})["platforms"][0]["games"][0]["controlsProfile"]

    antes = _profile()
    assert antes["autoconfig"]["state"] == "pending-write"
    assert antes["applyAutoconfigAction"]["id"] == "controls.autoconfig.apply"
    assert antes["applyAutoconfigAction"]["requiresConfirmation"] is True

    plano = controller.plan_action({"actionId": "controls.autoconfig.apply"})
    _apply(controller, plano)

    depois = _profile()
    assert depois["autoconfig"]["state"] == "applied"
    # A ação some quando não há mais o que gravar: oferecer confirmação que não
    # muda nada seria ruído.
    assert depois["applyAutoconfigAction"] is None
    gravado = Path(depois["autoconfig"]["path"])
    assert gravado.is_file()
    assert gravado.read_text(encoding="utf-8").splitlines()[0] == "# SteamZero-Managed: true"


def test_applying_the_autoconfig_twice_is_idempotent(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    controls = _controls_with_pad(monkeypatch, tmp_path, declared=True)
    controller, _game_id = _controls_game(monkeypatch, tmp_path, controls=controls)
    _apply(
        controller,
        controller.plan_action({"actionId": "controls.profile.activate:standard-gamepad"}),
    )
    _apply(controller, controller.plan_action({"actionId": "controls.autoconfig.apply"}))

    # Já aplicado: planejar de novo é recusado com causa, em vez de oferecer uma
    # confirmação que não mudaria nada.
    with pytest.raises(SteamZeroError, match="não está pronto para gravar"):
        controller.plan_action({"actionId": "controls.autoconfig.apply"})


def test_applying_the_autoconfig_is_refused_without_an_active_profile(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controls = _controls_with_pad(monkeypatch, tmp_path, declared=True)
    controller, _game_id = _controls_game(monkeypatch, tmp_path, controls=controls)

    with pytest.raises(SteamZeroError, match="nenhum perfil de controle ativo"):
        controller.plan_action({"actionId": "controls.autoconfig.apply"})


def test_readiness_is_not_ready_until_the_autoconfig_is_applied(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """Perfil salvo com controle plugado NÃO é perfil valendo.

    A prontidão olhava só "existe perfil" e "existe controle", então dizia
    `ready` enquanto o emulador ainda rodava nos padrões dele — o falso verde
    que a G45 existe para não repetir.
    """
    controls = _controls_with_pad(monkeypatch, tmp_path, declared=True)
    controller, _game_id = _controls_game(monkeypatch, tmp_path, controls=controls)
    _apply(
        controller,
        controller.plan_action({"actionId": "controls.profile.activate:standard-gamepad"}),
    )

    def _readiness() -> dict:
        return controller.snapshot({"context": {}})["platforms"][0]["games"][0]["controlsReadiness"]

    antes = _readiness()
    assert antes["state"] == "attention"
    assert antes["autoconfigState"] == "pending-write"
    assert antes["reason"]

    _apply(controller, controller.plan_action({"actionId": "controls.autoconfig.apply"}))

    depois = _readiness()
    assert depois["autoconfigState"] == "applied"
    # `ready` continua exigindo controle detectado; num host sem joystick o
    # estado permanece honesto.
    assert depois["state"] == ("ready" if depois["controllers"] > 0 else "attention")


def test_a_game_scoped_profile_never_offers_to_write_the_platform_one(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """O autoconfig vale por CONTROLE; o perfil por jogo nao cabe nele.

    O cartao mostra o perfil efetivo do jogo, mas a gravacao usa o perfil de
    PLATAFORMA — sao arquivos por dispositivo, sem nocao de qual jogo roda. Se a
    acao fosse oferecida aqui, confirmar "aplicar" gravaria silenciosamente OUTRO
    perfil. Melhor dizer que o mecanismo nao alcanca esse caso.
    """
    controls = _controls_with_pad(monkeypatch, tmp_path, declared=True)
    controller, game_id = _controls_game(monkeypatch, tmp_path, controls=controls)
    _apply(
        controller,
        controller.plan_action({"actionId": "controls.profile.activate:standard-gamepad"}),
    )
    # Perfil especifico do jogo, diferente do da plataforma.
    _apply(
        controller,
        controller.plan_action(
            {
                "actionId": "controls.profile.activate:joycon-pair",
                "gameId": game_id,
                "scope": "game",
                "scopeId": game_id,
            }
        ),
    )

    profile = controller.snapshot({"context": {}})["platforms"][0]["games"][0]["controlsProfile"]

    assert profile["source"] == "game"
    assert profile["active"]["id"] == "joycon-pair"
    assert profile["autoconfig"]["state"] == "unsupported-scope"
    assert profile["applyAutoconfigAction"] is None
    assert "por jogo" in profile["autoconfig"]["detail"]


def test_controls_profile_never_says_applied_when_retroarch_did_not_declare_a_dir(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """Caso REAL deste host: o RetroArch nunca gravou `retroarch.cfg`."""
    controller, _game_id = _controls_game(
        monkeypatch, tmp_path, controls=_controls_with_pad(monkeypatch, tmp_path, declared=False)
    )
    plan = controller.plan_action({"actionId": "controls.profile.activate:standard-gamepad"})
    _apply(controller, plan)

    autoconfig = controller.snapshot({"context": {}})["platforms"][0]["games"][0][
        "controlsProfile"
    ]["autoconfig"]

    assert autoconfig["state"] == "awaiting-emulator"
    assert autoconfig["directoryDeclared"] is False
    assert autoconfig["statusLabel"]


def test_controls_autoconfig_is_absent_while_no_profile_is_active(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller, _game_id = _controls_game(
        monkeypatch, tmp_path, controls=_controls_with_pad(monkeypatch, tmp_path, declared=True)
    )

    game = controller.snapshot({"context": {}})["platforms"][0]["games"][0]

    assert game["controlsProfile"]["autoconfig"] is None


def test_game_row_exposes_controls_profile_inheritance_and_clear(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller, game_id = _controls_game(monkeypatch, tmp_path)

    def _row() -> dict:
        return controller.snapshot({"context": {}})["platforms"][0]["games"][0]

    game = _row()
    profile = game["controlsProfile"]
    assert profile["source"] == "platform"
    assert profile["state"] == "unverified"
    assert profile["clearAction"] is None
    assert profile["active"] is None
    assert {action["id"] for action in profile["activateActions"]} == {
        "controls.profile.activate:standard-gamepad",
        "controls.profile.activate:joycon-pair",
    }
    assert all(
        action["gameId"] == game_id and action["scope"] == "game" and action["scopeId"] == game_id
        for action in profile["activateActions"]
    )
    readiness = game["controlsReadiness"]
    assert readiness["profileConfigured"] is False
    assert readiness["state"] == "attention"
    assert readiness["controllers"] >= 0
    assert readiness["reason"]

    platform_plan = controller.plan_action({"actionId": "controls.profile.activate:joycon-pair"})
    _apply(controller, platform_plan)
    profile = _row()["controlsProfile"]
    assert profile["source"] == "platform"
    assert profile["state"] == "ready"
    assert profile["active"]["id"] == "joycon-pair"
    assert profile["clearAction"] is None

    plan = controller.plan_action(
        {
            "actionId": "controls.profile.activate:standard-gamepad",
            "gameId": game_id,
            "scope": "game",
        }
    )
    _apply(controller, plan)
    game = _row()
    profile = game["controlsProfile"]
    assert profile["source"] == "game"
    assert profile["state"] == "ready"
    assert profile["active"]["id"] == "standard-gamepad"
    assert profile["active"]["scope"] == "game"
    assert profile["active"]["scopeId"] == game_id
    assert profile["clearAction"]["id"] == f"controls.profile.clear:{game_id}"
    assert game["controlsReadiness"]["profileConfigured"] is True
    assert (game["controlsReadiness"]["state"] == "ready") == (
        game["controlsReadiness"]["controllers"] > 0
    )

    clear = controller.plan_action({"actionId": f"controls.profile.clear:{game_id}"})
    clear_result = _apply(controller, clear)
    profile = _row()["controlsProfile"]
    assert profile["source"] == "platform"
    assert profile["state"] == "ready"
    assert profile["active"]["id"] == "joycon-pair"
    assert profile["clearAction"] is None

    rollback = controller.rollback_action(str(clear_result["operationId"]))
    assert rollback["status"] == "rolled-back"
    profile = _row()["controlsProfile"]
    assert profile["source"] == "game"
    assert profile["state"] == "ready"
    assert profile["active"]["id"] == "standard-gamepad"


def test_game_scope_controls_profile_blocked_while_session_runs(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    import os

    controller, game_id = _controls_game(monkeypatch, tmp_path)
    settings_path = Path(os.environ["XDG_CONFIG_HOME"]) / "steamzero" / "emulation-games-v1.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps({"schemaVersion": 1, "games": {game_id: {"emulatorId": "citron"}}}),
        encoding="utf-8",
    )
    controller._running_pids["citron"] = os.getpid()  # type: ignore[attr-defined]

    with pytest.raises(SteamZeroError) as busy:
        controller.plan_action(
            {
                "actionId": "controls.profile.activate:standard-gamepad",
                "gameId": game_id,
                "scope": "game",
            }
        )
    assert busy.value.code == "E-CONTENT-BUSY"
    with pytest.raises(SteamZeroError) as busy_clear:
        controller.plan_action({"actionId": f"controls.profile.clear:{game_id}"})
    assert busy_clear.value.code == "E-CONTENT-BUSY"

    controller._running_pids.clear()  # type: ignore[attr-defined]
    plan = controller.plan_action(
        {
            "actionId": "controls.profile.activate:standard-gamepad",
            "gameId": game_id,
            "scope": "game",
        }
    )
    assert plan["planId"]


def test_orphaned_session_with_dead_pid_never_blocks_the_next_launch(
    monkeypatch,
    tmp_path: Path,
) -> None:  # type: ignore[no-untyped-def]
    """Jogo morto anormalmente não pode travar a biblioteca inteira.

    Sem a colheita, a linha fica em `running` para sempre e o índice único de
    sessão ativa faz TODO lançamento seguinte falhar com E-TX-LOCKED — sem
    caminho de recuperação no CLI. Defeito observado no host real: `kill` no
    emulador deixou a sessão viva e nenhum jogo lançava mais.
    """
    controller = _controller(monkeypatch, tmp_path)
    controller._spawn = lambda _argv: 4242  # type: ignore[attr-defined]
    controller._process_waiter = lambda _pid: 0  # type: ignore[attr-defined]
    controller._read_start_ticks = lambda _pid: 777  # type: ignore[attr-defined]
    roms = tmp_path / "owned-roms"
    roms.mkdir()
    (roms / "Example [0100ABCDEF123000].nsp").write_bytes(b"owned-game")
    _apply(
        controller,
        controller.plan_action({"actionId": "library.root.add", "path": str(roms)}),
    )
    game = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    _apply(
        controller,
        controller.plan_action(
            {"actionId": "game.emulator.set", "gameId": game["id"], "emulatorId": "ryubing"}
        ),
    )
    monkeypatch.setattr(
        "steamzero.adapters.emulation.AdapterEngine.payload_path",
        lambda _self, _emulator_id: tmp_path / f"{_emulator_id}.AppImage",
    )
    monkeypatch.setattr(controller, "_require_key_projection", lambda _emulator_id: None)

    # Sessão órfã: processo já não existe (PID impossível de estar vivo).
    with StateStore(tmp_path / "state.db") as store:
        store.migrate()
        store.create_game_session(
            {
                "id": "01ORPHANORPHANORPHANORPHAN",
                "game_id": str(game["id"]),
                "state": "launching",
                "owner": "steamzero-game-session",
                "metadata_json": "{}",
            }
        )
        store.transition_game_session("01ORPHANORPHANORPHANORPHAN", "running", pid=2**22)

    result = controller.launch_game(game["id"])
    assert result["status"] == "started"

    with StateStore(tmp_path / "state.db") as store:
        store.migrate()
        rows = {r["id"]: r for r in store.active_game_sessions("steamzero-game-session")}
    assert "01ORPHANORPHANORPHANORPHAN" not in rows, "sessão órfã continuou ativa"
    assert [r["pid"] for r in rows.values()] == [4242]
