# SPDX-License-Identifier: GPL-3.0-or-later
"""Dashboard Desktop agrega providers opcionais sem esconder degradação."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from steamzero.adapters.cast_orchestrator import CastOrchestrator
from steamzero.adapters.desktop_dashboard import DesktopDashboard, SteamDesktopController
from steamzero.adapters.flatpak import FlatpakState
from steamzero.adapters.steam_gameplay import SteamGameplayController
from steamzero.core import ids
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain.saves import SavesStore
from steamzero.ports import CaptureConsent


class FakeFlatpak:
    def __init__(self, states: dict[str, FlatpakState] | None = None) -> None:
        self.states = states or {}

    def status(self, ref: str) -> FlatpakState:
        return self.states.get(ref, FlatpakState(False, ref))

    def resolve(self, remote: str, ref: str, commit: str) -> str:
        return commit

    def install(self, remote: str, ref: str) -> None:
        self.states[ref] = FlatpakState(True, ref, remote, "0" * 64)

    def deploy(self, ref: str, commit: str) -> None:
        origin = self.states.get(ref, FlatpakState(True, ref, "flathub")).origin or "flathub"
        self.states[ref] = FlatpakState(True, ref, origin, commit)

    def uninstall(self, ref: str) -> None:
        self.states[ref] = FlatpakState(False, ref)

    def smoke(self, ref: str, arguments: Sequence[str]) -> None:
        return


class FakeGameplay:
    def snapshot(self, _status: dict[str, object]) -> dict[str, object]:
        return {"readiness": {"percent": 100}, "games": []}

    def plan(self, payload: dict[str, object], _status: dict[str, object]) -> dict[str, object]:
        return {"planId": "gameplay-plan", "profile": payload}

    def apply(
        self,
        plan_id: str,
        confirm_token: str,
        _status: dict[str, object],
    ) -> dict[str, object]:
        return {"status": "saved", "planId": plan_id, "token": confirm_token}


class BrokenGameplay(FakeGameplay):
    def snapshot(self, _status: dict[str, object]) -> dict[str, object]:
        raise OSError("biblioteca Steam temporariamente ilegível")


class InterruptedGameplay(FakeGameplay):
    def session_status(self, game_id: str) -> dict[str, object]:
        return {"gameId": game_id, "recoveryRequired": True}


def _status(*, conflict: bool = False) -> dict[str, object]:
    return {
        "context": {
            "capabilities": ["steam-keyboard"],
            "conflicts": ["watcher.service"] if conflict else [],
        }
    }


def test_steam_rows_are_optional_and_conflict_aware() -> None:
    controller = SteamDesktopController(
        which=lambda command: "/usr/bin/steam" if command == "steam" else None,
        running_probe=lambda: False,
        spawn=lambda _argv: None,
    )

    rows = controller.rows(_status(conflict=True))

    assert rows[0]["statusLabel"] == "Instalado"
    assert rows[0]["versionLabel"] == "Cliente do sistema"
    assert rows[2]["state"] == "blocked"
    assert rows[3]["action"]["kind"] == "keyboard"


def test_steam_rows_do_not_claim_a_specific_distribution() -> None:
    controller = SteamDesktopController(
        which=lambda _command: None,
        running_probe=lambda: False,
        spawn=lambda _argv: None,
    )

    rows = controller.rows(_status())

    assert "sua distribuição" in rows[0]["detail"]
    assert "BigLinux" not in str(rows)


def test_steam_open_uses_only_allowlisted_uri() -> None:
    calls: list[tuple[str, ...]] = []
    controller = SteamDesktopController(
        which=lambda _command: "/usr/bin/steam",
        running_probe=lambda: False,
        spawn=lambda argv: calls.append(tuple(argv)),
    )

    assert controller.open("library")["uri"] == "steam://open/games"
    assert calls == [("/usr/bin/steam", "steam://open/games")]
    with pytest.raises(SteamZeroError, match="não permitido"):
        controller.open("arbitrary-uri")


def test_steam_input_opens_only_numeric_game_configuration() -> None:
    calls: list[tuple[str, ...]] = []
    controller = SteamDesktopController(
        which=lambda _command: "/usr/bin/steam",
        running_probe=lambda: False,
        spawn=lambda argv: calls.append(tuple(argv)),
    )

    result = controller.open_controller_config("1091500")

    assert result["uri"] == "steam://controllerconfig/1091500"
    assert calls == [("/usr/bin/steam", "steam://controllerconfig/1091500")]
    with pytest.raises(SteamZeroError, match="gameId inválido"):
        controller.open_controller_config("1091500;shutdown")


def test_steam_continue_uses_only_numeric_rungameid_uri() -> None:
    calls: list[tuple[str, ...]] = []
    controller = SteamDesktopController(
        which=lambda _command: "/usr/bin/steam",
        running_probe=lambda: False,
        spawn=lambda argv: calls.append(tuple(argv)),
    )

    result = controller.open_game("1091500")

    assert result["uri"] == "steam://rungameid/1091500"
    assert calls == [("/usr/bin/steam", "steam://rungameid/1091500")]
    with pytest.raises(SteamZeroError, match="gameId Steam inválido"):
        controller.open_game("../../evil")


def test_playtime_enrichment_turns_dead_active_steam_session_into_recovery() -> None:
    dashboard = DesktopDashboard(gameplay=InterruptedGameplay())  # type: ignore[arg-type]
    payload: dict[str, object] = {
        "games": [
            {
                "gameId": "10",
                "title": "Jogo 10",
                "coverUrl": "",
                "source": "steam",
                "continueState": "in-progress",
                "action": {"kind": "detail", "enabled": False},
            }
        ]
    }

    dashboard._enrich_playtime(  # type: ignore[attr-defined]
        payload,
        steam_games=[{"id": "10", "name": "Portal", "coverUrl": "file:///cover.jpg"}],
        emulation={},
    )

    game = payload["games"][0]  # type: ignore[index]
    assert game["title"] == "Portal"
    assert game["continueState"] == "interrupted"
    assert game["action"]["kind"] == "steam-recover"


def test_collection_catalog_unifies_sources_and_enriches_recent_games() -> None:
    catalog = DesktopDashboard._collection_games(  # type: ignore[attr-defined]
        steam_games=[{"id": "10", "name": "Steam Game"}],
        emulation={"platforms": [{"id": "switch", "games": [{"id": "abc", "name": "Emulated"}]}]},
    )
    assert [item["gameRef"] for item in catalog] == ["steam:10", "emulation:abc"]
    playtime = {
        "games": [
            {"gameId": "10", "source": "steam"},
            {"gameId": "abc", "source": "emulation"},
        ]
    }
    DesktopDashboard._enrich_collection_state(  # type: ignore[attr-defined]
        playtime,
        {
            "favorites": ["steam:10"],
            "assignments": [{"gameRef": "emulation:abc", "tagIds": ["retro"]}],
        },
    )
    assert playtime["games"] == [
        {
            "gameId": "10",
            "source": "steam",
            "gameRef": "steam:10",
            "favorite": True,
            "tagIds": [],
        },
        {
            "gameId": "abc",
            "source": "emulation",
            "gameRef": "emulation:abc",
            "favorite": False,
            "tagIds": ["retro"],
        },
    ]


def test_dashboard_snapshot_keeps_eol_component_honest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    flatpak = FakeFlatpak()
    steam = SteamDesktopController(
        which=lambda _command: None,
        running_probe=lambda: False,
        spawn=lambda _argv: None,
    )
    dashboard = DesktopDashboard(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        flatpak_factory=lambda: flatpak,  # type: ignore[arg-type]
        doctor_runner=lambda: ({"version": "test"}, []),
        steam=steam,
        gameplay=FakeGameplay(),  # type: ignore[arg-type]
        which=lambda command: "/usr/bin/flatpak" if command == "flatpak" else None,
        spawn=lambda _argv: None,
        reduced_motion_probe=lambda: True,
        high_contrast_probe=lambda: True,
    )

    snapshot = dashboard.snapshot(_status())

    components = snapshot["components"]
    assert isinstance(components, list)
    assert [row["id"] for row in components] == ["dolphin", "duckstation", "retroarch"]
    duckstation = components[1]
    assert duckstation["state"] == "unsupported"
    assert duckstation["action"]["enabled"] is False
    assert snapshot["doctor"]["state"] == "healthy"
    assert snapshot["accessibility"] == {"reducedMotion": True, "highContrast": True}
    assert snapshot["steamGameplay"]["readiness"]["percent"] == 100
    assert snapshot["playtime"]["schemaVersion"] == 1
    assert snapshot["playtime"]["games"] == []
    assert snapshot["libraryHealth"]["state"] == "unchecked"
    assert snapshot["libraryHealth"]["counts"]["unchecked"] == 0
    assert snapshot["emulation"]["schemaVersion"] == 1
    assert snapshot["sync"]["mode"] == "read-only"
    assert snapshot["sync"]["provider"]["configured"] is False
    assert snapshot["sync"]["capabilities"] == {
        "retry": False,
        "cancel": False,
        "resolveConflict": False,
    }
    platform = snapshot["emulation"]["platforms"][0]
    assert platform["id"] == "switch"
    refresh = platform["areaData"]["overview"]["primaryAction"]
    assert refresh == {
        "id": "library.scan",
        "label": "Varrer biblioteca",
        "enabled": True,
        "reason": None,
        "requiresConfirmation": False,
    }
    imports = [card["action"] for card in platform["areaData"]["keysFirmware"]["cards"]]
    assert {action["id"] for action in imports} == {"keys.import", "firmware.import"}
    assert all(action["enabled"] and action["requiresConfirmation"] for action in imports)
    eden = platform["emulators"][0]
    assert eden["sourceState"] == "verified"
    assert eden["action"]["id"] == "emulator.install:eden"


def test_sync_snapshot_lists_real_queue_without_inventing_mutations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    database = tmp_path / "state.db"
    with StateStore(database) as store:
        store.migrate()
        store.save_platform({"id": "switch", "name": "Switch"})
        game_id = ids.new_ulid()
        store.save_game(
            {"id": game_id, "platform_id": "switch", "title": "Example", "state": "ready"}
        )
        save = SavesStore(store).record_save(game_id, b"save")
        store.save_sync_entry(
            {
                "id": "sync-1",
                "save_entry_id": save.id,
                "direction": "upload",
                "state": "conflicted",
            }
        )
    dashboard = DesktopDashboard(
        store_factory=lambda: StateStore(database),
        flatpak_factory=FakeFlatpak,  # type: ignore[arg-type]
        doctor_runner=lambda: ({"version": "test"}, []),
        steam=SteamDesktopController(
            which=lambda _command: None,
            running_probe=lambda: False,
            spawn=lambda _argv: None,
        ),
        gameplay=FakeGameplay(),  # type: ignore[arg-type]
        which=lambda _command: None,
        spawn=lambda _argv: None,
    )

    sync = dashboard.snapshot(_status())["sync"]
    assert sync["state"] == "attention"
    assert sync["items"] == [
        {
            "id": "sync-1",
            "saveEntryId": save.id,
            "gameId": game_id,
            "direction": "upload",
            "state": "conflicted",
            "lastAttempt": None,
            "error": None,
            "conflict": {"preserved": True, "group": None},
        }
    ]
    assert all(value is False for value in sync["capabilities"].values())


def test_gameplay_snapshot_reads_real_manifest_and_capabilities(tmp_path: Path) -> None:
    root = tmp_path / "Steam"
    steamapps = root / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "appmanifest_1091500.acf").write_text(
        '"AppState"\n{\n  "appid" "1091500"\n  "name" "Cyberpunk 2077"\n}\n',
        encoding="utf-8",
    )
    (steamapps / "appmanifest_993090.acf").write_text(
        '"AppState"\n{\n  "appid" "993090"\n  "name" "Lossless Scaling"\n'
        '  "installdir" "Lossless Scaling"\n}\n',
        encoding="utf-8",
    )
    lossless_dir = steamapps / "common" / "Lossless Scaling"
    lossless_dir.mkdir(parents=True)
    (lossless_dir / "Lossless.dll").write_bytes(b"owned fixture")
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemAvailable:       11744000 kB\n", encoding="utf-8")
    available = {"steam", "gamescope", "gamemoderun"}
    controller = SteamGameplayController(
        roots=(root,),
        which=lambda command: f"/usr/bin/{command}" if command in available else None,
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        meminfo=meminfo,
    )

    snapshot = controller.snapshot(
        {
            "context": {
                "deviceKind": "deck-lcd",
                "displays": [
                    {
                        "name": "eDP-1",
                        "connected": True,
                        "internal": True,
                        "width": 800,
                        "height": 1280,
                        "refreshHz": 60.0,
                    }
                ],
            }
        }
    )

    assert snapshot["games"] == [
        {"id": "1091500", "name": "Cyberpunk 2077", "coverUrl": "", "state": "installed"}
    ]
    assert snapshot["hardware"]["tdpMax"] == 15
    assert snapshot["hardware"]["memoryGb"] == 11.2
    assert snapshot["impact"]["resolution"] == "800x1280"
    assert snapshot["readiness"]["percent"] == 100
    assert snapshot["lsfgInstaller"]["losslessScalingInstalled"] is True


def test_gameplay_failure_degrades_only_steam_section(tmp_path: Path) -> None:
    dashboard = DesktopDashboard(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        flatpak_factory=FakeFlatpak,  # type: ignore[arg-type]
        doctor_runner=lambda: ({"version": "test"}, []),
        steam=SteamDesktopController(
            which=lambda _command: None,
            running_probe=lambda: False,
            spawn=lambda _argv: None,
        ),
        gameplay=BrokenGameplay(),  # type: ignore[arg-type]
        which=lambda _command: None,
        spawn=lambda _argv: None,
    )

    snapshot = dashboard.snapshot(_status())

    assert snapshot["steamGameplay"]["truthState"] == "degraded"
    assert snapshot["doctor"]["state"] == "healthy"
    assert len(snapshot["components"]) == 3


def test_emulation_builder_failure_degrades_only_emulation_section(tmp_path: Path) -> None:
    def broken_builder(**_kwargs: object) -> dict[str, object]:
        raise OSError("provider de emulação indisponível")

    dashboard = DesktopDashboard(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        flatpak_factory=FakeFlatpak,  # type: ignore[arg-type]
        doctor_runner=lambda: ({"version": "test"}, []),
        steam=SteamDesktopController(
            which=lambda _command: None,
            running_probe=lambda: False,
            spawn=lambda _argv: None,
        ),
        gameplay=FakeGameplay(),  # type: ignore[arg-type]
        emulation_builder=broken_builder,
        which=lambda _command: None,
        spawn=lambda _argv: None,
    )

    snapshot = dashboard.snapshot(_status())

    assert snapshot["emulation"]["truthState"] == "unverified"
    assert snapshot["doctor"]["state"] == "healthy"


def test_gameplay_plan_requires_confirmation_and_persists_policy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    root = tmp_path / "Steam"
    steamapps = root / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "appmanifest_10.acf").write_text(
        '"AppState"\n{\n  "appid" "10"\n  "name" "Counter-Strike"\n}\n',
        encoding="utf-8",
    )
    available = {"steam", "gamescope", "gamemoderun", "mangohud", "mangoapp", "vkbasalt"}
    status = {"context": {"deviceKind": "deck-lcd", "displays": []}}
    payload = {
        "gameId": "10",
        "scope": "game",
        "profile": "balanced",
        "fps": 40,
        "tdp": 10,
        "gpuMode": "auto",
        "gpuClock": None,
        "gamescope": True,
        "gameMode": True,
        "mangoHud": "basic",
        "vkBasalt": "cas",
        "upscaling": "fsr2-quality",
        "frameGeneration": "lsfg-2x",
        "controllerLayout": "official",
    }

    lsfg_manifest = tmp_path / "VkLayer_LS_frame_generation.json"
    lsfg_manifest.write_text("{}", encoding="utf-8")
    controller = SteamGameplayController(
        roots=(root,),
        which=lambda command: f"/usr/bin/{command}" if command in available else None,
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        lsfg_manifests=(lsfg_manifest,),
        vkbasalt_config_root=tmp_path / "vkbasalt",
    )

    plan = controller.plan(payload, status)
    assert plan["blockers"] == []
    with pytest.raises(SteamZeroError, match="plano Steam inválido"):
        controller.apply(str(plan["planId"]), "wrong", status)

    result = controller.apply(str(plan["planId"]), str(plan["confirmToken"]), status)
    assert result["status"] == "saved"
    assert ids.is_ulid(str(result["operationId"]))
    with StateStore(tmp_path / "state.db") as store:
        saved = store.get_profile("steam-gameplay:game:10")
    assert saved is not None
    assert saved["kind"] == "performance"
    assert "controllerLayout" not in str(saved["payload_json"])
    vkbasalt_config = tmp_path / "vkbasalt/10.conf"
    assert "effects = cas" in vkbasalt_config.read_text(encoding="utf-8")
    with StateStore(tmp_path / "state.db") as store:
        controls = store.get_profile("steam-controls:game:10")
    assert controls is not None
    assert controls["kind"] == "controls"
    assert '"layout":"official"' in str(controls["payload_json"])

    changed = dict(payload)
    changed["mangoHud"] = "detailed"
    changed["vkBasalt"] = "off"
    changed_plan = controller.plan(changed, status)
    assert "MangoHud: basic → detailed" in changed_plan["changes"]
    assert "vkBasalt: cas → off" in changed_plan["changes"]
    changed_result = controller.apply(
        str(changed_plan["planId"]), str(changed_plan["confirmToken"]), status
    )
    assert not vkbasalt_config.exists()
    rolled_back = controller.rollback_profile(str(changed_result["operationId"]))
    assert rolled_back["status"] == "rolled-back"
    with StateStore(tmp_path / "state.db") as store:
        restored = store.get_profile("steam-gameplay:game:10")
    assert restored is not None
    assert '"mangoHud":"basic"' in str(restored["payload_json"])
    assert '"vkBasalt":"cas"' in str(restored["payload_json"])
    assert "effects = cas" in vkbasalt_config.read_text(encoding="utf-8")
    with pytest.raises(SteamZeroError, match="indisponível"):
        controller.rollback_profile(str(changed_result["operationId"]))


def test_gameplay_plan_blocks_lsfg_when_vulkan_layer_is_missing(tmp_path: Path) -> None:
    root = tmp_path / "Steam"
    steamapps = root / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "appmanifest_10.acf").write_text(
        '"AppState"\n{\n  "appid" "10"\n  "name" "Counter-Strike"\n}\n',
        encoding="utf-8",
    )
    available = {"steam", "gamescope", "gamemoderun"}
    controller = SteamGameplayController(
        roots=(root,),
        which=lambda command: f"/usr/bin/{command}" if command in available else None,
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        lsfg_manifests=(tmp_path / "missing.json",),
    )

    payload = SteamGameplayController.safe_profile("10")
    payload["frameGeneration"] = "lsfg-3x"
    plan = controller.plan(
        payload,
        {"context": {"deviceKind": "deck-lcd", "displays": []}},
    )

    assert any("LSFG-VK" in blocker for blocker in plan["blockers"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("frameGeneration", "latest"),
        ("controllerLayout", "shell"),
        ("vkBasalt", "custom-shader"),
    ],
)
def test_gameplay_rejects_unknown_rendering_and_controller_values(
    tmp_path: Path, field: str, value: str
) -> None:
    root = tmp_path / "Steam"
    (root / "steamapps").mkdir(parents=True)
    controller = SteamGameplayController(
        roots=(root,),
        which=lambda command: "/usr/bin/steam" if command == "steam" else None,
        store_factory=lambda: StateStore(tmp_path / "state.db"),
    )
    payload = SteamGameplayController.safe_profile("")
    payload[field] = value

    with pytest.raises(SteamZeroError) as error:
        controller.plan(payload, {"context": {"deviceKind": "deck-lcd", "displays": []}})
    assert error.value.code == "E-API-SCHEMA"


def test_gameplay_vkbasalt_requires_per_game_scope_and_capability(tmp_path: Path) -> None:
    root = tmp_path / "Steam"
    steamapps = root / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "appmanifest_10.acf").write_text(
        '"AppState"\n{\n  "appid" "10"\n  "name" "Game"\n}\n',
        encoding="utf-8",
    )
    controller = SteamGameplayController(
        roots=(root,),
        which=lambda command: "/usr/bin/steam" if command == "steam" else None,
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        vkbasalt_config_root=tmp_path / "vkbasalt",
        vkbasalt_manifests=(tmp_path / "missing-vkBasalt.json",),
    )
    payload = SteamGameplayController.safe_profile("10")
    payload["scope"] = "global"
    payload["vkBasalt"] = "smaa"

    plan = controller.plan(payload, {"context": {"deviceKind": "deck-lcd", "displays": []}})

    assert any("exclusivamente" in blocker for blocker in plan["blockers"])
    assert any("não está disponível" in blocker for blocker in plan["blockers"])


def test_gameplay_plan_blocks_missing_runtime_instead_of_simulating_apply(
    tmp_path: Path,
) -> None:
    root = tmp_path / "Steam"
    (root / "steamapps").mkdir(parents=True)
    controller = SteamGameplayController(
        roots=(root,),
        which=lambda command: "/usr/bin/steam" if command == "steam" else None,
        store_factory=lambda: StateStore(tmp_path / "state.db"),
    )
    plan = controller.plan(
        {
            "gameId": "",
            "scope": "global",
            "profile": "performance",
            "fps": 60,
            "tdp": 15,
            "gpuMode": "auto",
            "gpuClock": None,
            "gamescope": True,
            "gameMode": True,
            "mangoHud": "detailed",
            "upscaling": "native",
        },
        {"context": {"deviceKind": "deck-lcd", "displays": []}},
    )

    assert len(plan["blockers"]) == 3
    assert "Gamescope" in plan["blockers"][0]


def test_gameplay_apply_refuses_plan_after_library_changes(tmp_path: Path) -> None:
    root = tmp_path / "Steam"
    steamapps = root / "steamapps"
    steamapps.mkdir(parents=True)
    manifest = steamapps / "appmanifest_10.acf"
    manifest.write_text(
        '"AppState"\n{\n  "appid" "10"\n  "name" "Counter-Strike"\n}\n',
        encoding="utf-8",
    )
    available = {"steam", "gamescope", "gamemoderun"}
    controller = SteamGameplayController(
        roots=(root,),
        which=lambda command: f"/usr/bin/{command}" if command in available else None,
        store_factory=lambda: StateStore(tmp_path / "state.db"),
    )
    status = {"context": {"deviceKind": "deck-lcd", "displays": []}}
    plan = controller.plan(
        {
            "gameId": "10",
            "scope": "game",
            "profile": "economy",
            "fps": 30,
            "tdp": 7,
            "gpuMode": "auto",
            "gpuClock": None,
            "gamescope": True,
            "gameMode": True,
            "mangoHud": "off",
            "upscaling": "native",
        },
        status,
    )
    manifest.unlink()

    with pytest.raises(SteamZeroError) as error:
        controller.apply(str(plan["planId"]), str(plan["confirmToken"]), status)
    assert error.value.code == "E-TX-STALE-PLAN"


class TestCastDashboardIntegration:
    """Testes de integração entre DesktopDashboard e CastOrchestrator."""

    @pytest.fixture
    def mock_cast(self) -> MagicMock:
        cast = MagicMock(spec=CastOrchestrator)
        cast.discover_receivers.return_value = [{"receiverId": "tv-sala", "name": "TV Sala"}]
        cast.pair_receiver.return_value = True
        cast.start_stream.return_value = {"started": True, "receiverId": "tv-sala"}
        cast.session_status.return_value = {"state": "streaming", "receiverId": "tv-sala"}
        cast.active_sessions.return_value = [
            {"sessionId": "sess-1", "receiverId": "tv-sala", "state": "streaming"}
        ]
        return cast

    def test_cast_section_is_unavailable_when_orchestrator_not_configured(
        self, tmp_path: Path
    ) -> None:
        dashboard = DesktopDashboard(
            store_factory=lambda: StateStore(tmp_path / "state.db"),
            flatpak_factory=lambda: MagicMock(),
            doctor_runner=lambda: ({"version": "test"}, []),
            which=lambda _: None,
            spawn=lambda _argv: None,
        )
        snapshot = dashboard.snapshot({"context": {"deviceKind": "deck-lcd"}})
        cast = snapshot.get("cast", {})
        assert cast.get("state") == "unavailable"
        assert cast.get("detail") is not None

    def test_cast_section_is_available_when_orchestrator_configured(
        self, tmp_path: Path, mock_cast: MagicMock
    ) -> None:
        dashboard = DesktopDashboard(
            cast_orchestrator=mock_cast,
            store_factory=lambda: StateStore(tmp_path / "state.db"),
            flatpak_factory=lambda: MagicMock(),
            doctor_runner=lambda: ({"version": "test"}, []),
            which=lambda _: None,
            spawn=lambda _argv: None,
        )
        snapshot = dashboard.snapshot({"context": {"deviceKind": "deck-lcd"}})
        cast = snapshot.get("cast", {})
        assert cast.get("state") == "available"
        assert cast.get("status") == {"state": "streaming", "receiverId": "tv-sala"}
        assert len(cast.get("activeSessions", [])) == 1

    def test_cast_section_degrades_on_orchestrator_error(
        self, tmp_path: Path, mock_cast: MagicMock
    ) -> None:
        mock_cast.session_status.side_effect = RuntimeError("connection lost")
        dashboard = DesktopDashboard(
            cast_orchestrator=mock_cast,
            store_factory=lambda: StateStore(tmp_path / "state.db"),
            flatpak_factory=lambda: MagicMock(),
            doctor_runner=lambda: ({"version": "test"}, []),
            which=lambda _: None,
            spawn=lambda _argv: None,
        )
        snapshot = dashboard.snapshot({"context": {"deviceKind": "deck-lcd"}})
        cast = snapshot.get("cast", {})
        assert cast.get("state") == "degraded"
        assert "connection lost" in cast.get("detail", "")

    def test_cast_discover_delegates_to_orchestrator(
        self, tmp_path: Path, mock_cast: MagicMock
    ) -> None:
        dashboard = DesktopDashboard(
            cast_orchestrator=mock_cast,
            store_factory=lambda: StateStore(tmp_path / "state.db"),
            flatpak_factory=lambda: MagicMock(),
            doctor_runner=lambda: ({"version": "test"}, []),
            which=lambda _: None,
            spawn=lambda _argv: None,
        )
        receivers = dashboard.cast_discover(timeout_ms=3000)
        mock_cast.discover_receivers.assert_called_once_with(timeout_ms=3000)
        assert receivers == [{"receiverId": "tv-sala", "name": "TV Sala"}]

    def test_cast_pair_delegates_to_orchestrator(
        self, tmp_path: Path, mock_cast: MagicMock
    ) -> None:
        dashboard = DesktopDashboard(
            cast_orchestrator=mock_cast,
            store_factory=lambda: StateStore(tmp_path / "state.db"),
            flatpak_factory=lambda: MagicMock(),
            doctor_runner=lambda: ({"version": "test"}, []),
            which=lambda _: None,
            spawn=lambda _argv: None,
        )
        result = dashboard.cast_pair("tv-sala", pin="1234")
        mock_cast.pair_receiver.assert_called_once()
        args, kwargs = mock_cast.pair_receiver.call_args
        assert args == ("tv-sala",)
        assert "pin" in kwargs
        secret = kwargs["pin"]
        assert secret is not None
        assert secret.reveal() == "1234"
        assert result == {"paired": True, "receiverId": "tv-sala"}

    def test_cast_start_delegates_to_orchestrator(
        self, tmp_path: Path, mock_cast: MagicMock
    ) -> None:
        dashboard = DesktopDashboard(
            cast_orchestrator=mock_cast,
            store_factory=lambda: StateStore(tmp_path / "state.db"),
            flatpak_factory=lambda: MagicMock(),
            doctor_runner=lambda: ({"version": "test"}, []),
            which=lambda _: None,
            spawn=lambda _argv: None,
        )
        consent = CaptureConsent(granted=True, scope="window", audio=False)
        result = dashboard.cast_start(
            "tv-sala",
            profile_id="game",
            mode="mirror",
            consent=consent,
        )
        mock_cast.start_stream.assert_called_once_with(
            "tv-sala",
            profile_id="game",
            mode="mirror",
            consent=consent,
        )
        assert result == {"started": True, "receiverId": "tv-sala"}

    def test_cast_stop_delegates_to_orchestrator(
        self, tmp_path: Path, mock_cast: MagicMock
    ) -> None:
        dashboard = DesktopDashboard(
            cast_orchestrator=mock_cast,
            store_factory=lambda: StateStore(tmp_path / "state.db"),
            flatpak_factory=lambda: MagicMock(),
            doctor_runner=lambda: ({"version": "test"}, []),
            which=lambda _: None,
            spawn=lambda _argv: None,
        )
        result = dashboard.cast_stop()
        mock_cast.stop_stream.assert_called_once_with()
        assert result == {"stopped": True}

    def test_cast_status_delegates_to_orchestrator(
        self, tmp_path: Path, mock_cast: MagicMock
    ) -> None:
        dashboard = DesktopDashboard(
            cast_orchestrator=mock_cast,
            store_factory=lambda: StateStore(tmp_path / "state.db"),
            flatpak_factory=lambda: MagicMock(),
            doctor_runner=lambda: ({"version": "test"}, []),
            which=lambda _: None,
            spawn=lambda _argv: None,
        )
        result = dashboard.cast_status()
        mock_cast.session_status.assert_called_once_with()
        assert result == {"state": "streaming", "receiverId": "tv-sala"}

    def test_cast_sessions_delegates_to_orchestrator(
        self, tmp_path: Path, mock_cast: MagicMock
    ) -> None:
        dashboard = DesktopDashboard(
            cast_orchestrator=mock_cast,
            store_factory=lambda: StateStore(tmp_path / "state.db"),
            flatpak_factory=lambda: MagicMock(),
            doctor_runner=lambda: ({"version": "test"}, []),
            which=lambda _: None,
            spawn=lambda _argv: None,
        )
        result = dashboard.cast_sessions()
        mock_cast.active_sessions.assert_called_once_with()
        assert len(result) == 1

    def test_cast_methods_raise_when_orchestrator_not_configured(self, tmp_path: Path) -> None:
        dashboard = DesktopDashboard(
            store_factory=lambda: StateStore(tmp_path / "state.db"),
            flatpak_factory=lambda: MagicMock(),
            doctor_runner=lambda: ({"version": "test"}, []),
            which=lambda _: None,
            spawn=lambda _argv: None,
        )
        with pytest.raises(SteamZeroError) as exc:
            dashboard.cast_pair("tv-sala")
        assert exc.value.code == "E-CAST-UNAVAILABLE"

        with pytest.raises(SteamZeroError) as exc:
            dashboard.cast_start("tv-sala")
        assert exc.value.code == "E-CAST-UNAVAILABLE"

        with pytest.raises(SteamZeroError) as exc:
            dashboard.cast_stop()
        assert exc.value.code == "E-CAST-UNAVAILABLE"

    def test_cast_discover_returns_empty_when_not_configured(self, tmp_path: Path) -> None:
        dashboard = DesktopDashboard(
            store_factory=lambda: StateStore(tmp_path / "state.db"),
            flatpak_factory=lambda: MagicMock(),
            doctor_runner=lambda: ({"version": "test"}, []),
            which=lambda _: None,
            spawn=lambda _argv: None,
        )
        assert dashboard.cast_discover() == []

    def test_cast_sessions_returns_empty_when_not_configured(self, tmp_path: Path) -> None:
        dashboard = DesktopDashboard(
            store_factory=lambda: StateStore(tmp_path / "state.db"),
            flatpak_factory=lambda: MagicMock(),
            doctor_runner=lambda: ({"version": "test"}, []),
            which=lambda _: None,
            spawn=lambda _argv: None,
        )
        assert dashboard.cast_sessions() == []

    def test_cast_status_returns_unavailable_when_not_configured(self, tmp_path: Path) -> None:
        dashboard = DesktopDashboard(
            store_factory=lambda: StateStore(tmp_path / "state.db"),
            flatpak_factory=lambda: MagicMock(),
            doctor_runner=lambda: ({"version": "test"}, []),
            which=lambda _: None,
            spawn=lambda _argv: None,
        )
        result = dashboard.cast_status()
        assert result.get("state") == "unavailable"
