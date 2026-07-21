# SPDX-License-Identifier: GPL-3.0-or-later
"""Dashboard Desktop agrega providers opcionais sem esconder degradação."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from steamzero.adapters.desktop_dashboard import DesktopDashboard, SteamDesktopController
from steamzero.adapters.flatpak import FlatpakState
from steamzero.adapters.steam_gameplay import SteamGameplayController
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore


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


def test_dashboard_snapshot_keeps_eol_component_honest(tmp_path: Path) -> None:
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
    )

    snapshot = dashboard.snapshot(_status())

    components = snapshot["components"]
    assert isinstance(components, list)
    assert [row["id"] for row in components] == ["dolphin", "duckstation", "retroarch"]
    duckstation = components[1]
    assert duckstation["state"] == "unsupported"
    assert duckstation["action"]["enabled"] is False
    assert snapshot["doctor"]["state"] == "healthy"
    assert snapshot["steamGameplay"]["readiness"]["percent"] == 100
    assert snapshot["emulation"]["schemaVersion"] == 1
    platform = snapshot["emulation"]["platforms"][0]
    assert platform["id"] == "switch"
    refresh = platform["areaData"]["overview"]["primaryAction"]
    assert refresh == {
        "id": "emulation.refresh",
        "label": "Verificar ambiente",
        "enabled": True,
        "reason": None,
        "requiresConfirmation": False,
    }
    imports = [
        card["action"]
        for card in platform["areaData"]["keysFirmware"]["cards"]
    ]
    assert all(not action["enabled"] and action["reason"] for action in imports)


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


def test_gameplay_plan_requires_confirmation_and_persists_policy(tmp_path: Path) -> None:
    root = tmp_path / "Steam"
    steamapps = root / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "appmanifest_10.acf").write_text(
        '"AppState"\n{\n  "appid" "10"\n  "name" "Counter-Strike"\n}\n',
        encoding="utf-8",
    )
    available = {"steam", "gamescope", "gamemoderun", "mangohud", "mangoapp"}
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
    )

    plan = controller.plan(payload, status)
    assert plan["blockers"] == []
    with pytest.raises(SteamZeroError, match="plano Steam inválido"):
        controller.apply(str(plan["planId"]), "wrong", status)

    result = controller.apply(str(plan["planId"]), str(plan["confirmToken"]), status)
    assert result["status"] == "saved"
    with StateStore(tmp_path / "state.db") as store:
        saved = store.get_profile("steam-gameplay:game:10")
    assert saved is not None
    assert saved["kind"] == "performance"
    assert "controllerLayout" not in str(saved["payload_json"])
    with StateStore(tmp_path / "state.db") as store:
        controls = store.get_profile("steam-controls:game:10")
    assert controls is not None
    assert controls["kind"] == "controls"
    assert '"layout":"official"' in str(controls["payload_json"])


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
    "field,value", [("frameGeneration", "latest"), ("controllerLayout", "shell")]
)
def test_gameplay_rejects_unknown_lsfg_and_controller_values(
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
