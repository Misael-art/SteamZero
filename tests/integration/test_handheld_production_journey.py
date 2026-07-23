# SPDX-License-Identifier: GPL-3.0-or-later
"""Smoke único da jornada handheld até publicação real na Steam."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from steamzero.adapters.emulation import EmulationController, SessionSecretStore
from steamzero.adapters.steam_shortcuts import (
    SteamShortcutManager,
    decode_shortcuts,
)
from steamzero.core import fs, paths
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.ports import GameIdentity, MediaCandidate

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
    "AScY42YAAAAASUVORK5CYII="
)
_SECRET = "production-smoke-secret-must-never-leak"
_TERMINAL = {"completed", "cancelled", "rolled-back", "rollback-failed"}


class _DeterministicProvider:
    name = "steamgriddb"

    def __init__(self) -> None:
        self.attempts = 0
        self.identities: list[GameIdentity] = []

    @staticmethod
    def supported_kinds() -> frozenset[str]:
        return frozenset({"icon"})

    @staticmethod
    def supported_platforms() -> frozenset[str]:
        return frozenset({"switch"})

    def search(
        self,
        identity: GameIdentity,
        media_kinds: list[str],
        region_priority: list[str] | None = None,
    ) -> list[MediaCandidate]:
        del region_priority
        self.attempts += 1
        self.identities.append(identity)
        if self.attempts == 1:
            raise SteamZeroError(
                "E-SCRAPE-PROVIDER-UNREACHABLE",
                detail="indisponibilidade transitória simulada",
            )
        assert media_kinds == ["icon"]
        return [
            MediaCandidate(
                url="https://provider.invalid/example-icon.png",
                media_kind="icon",
                provider=self.name,
                confidence=1.0,
                width=256,
                height=256,
                license="fixture",
                attribution="provider simulado",
            )
        ]


def _apply(controller: EmulationController, plan: dict[str, object]) -> dict[str, object]:
    return controller.apply_action(str(plan["planId"]), str(plan["confirmToken"]))


def _terminal_job(controller: EmulationController, job_id: str) -> dict[str, object]:
    for _attempt in range(8):
        status = controller.get_job_status(job_id)
        assert status is not None
        if status["rawState"] in _TERMINAL:
            return status
    pytest.fail(f"job {job_id} não alcançou estado terminal")


def _copy_optimizer(source: Path, destination: Path, _profile: str) -> bool:
    fs.copy_file_atomic(source, destination)
    return True


def test_handheld_journey_from_root_to_transactional_steam_publication(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda _class: home))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    steam_root = tmp_path / "Steam"
    steam_config = steam_root / "userdata" / "123" / "config"
    steam_config.mkdir(parents=True)
    (steam_config / "localconfig.vdf").write_bytes(b'"UserLocalConfigStore"\n{\n}\n')
    shortcuts = SteamShortcutManager(roots=[steam_root], running_probe=lambda: False)
    provider = _DeterministicProvider()
    fetched: list[str] = []

    def fetch_candidate(url: str) -> bytes:
        fetched.append(url)
        return _PNG

    state_db = tmp_path / "state.db"
    controller = EmulationController(
        store_factory=lambda: StateStore(state_db),
        which=lambda _command: None,
        spawn=lambda _argv: None,
        shortcuts=shortcuts,
        secret_store=SessionSecretStore(),
        media_providers=[provider],
        media_candidate_fetcher=fetch_candidate,
        media_optimizer_tool=_copy_optimizer,
    )
    controller.save_credential("steamgriddb", _SECRET)

    title_id = "0100ABCDEF123000"
    local_cover = paths.data_home() / "cache" / "covers" / f"{title_id}.png"
    fs.ensure_dir(local_cover.parent)
    fs.write_atomic(local_cover, _PNG)
    roms = tmp_path / "owned-roms"
    roms.mkdir()
    base_rom = roms / f"Example [{title_id}][v0].nsp"
    update_rom = roms / "Example [0100ABCDEF123800][v131072].nsp"
    dlc_rom = roms / "Example [DLC Pack] [0100ABCDEF124001][v0].nsp"
    base_rom.write_bytes(b"base")
    update_rom.write_bytes(b"update")
    dlc_rom.write_bytes(b"dlc")

    root_result = _apply(
        controller,
        controller.plan_action({"actionId": "library.root.add", "path": str(roms)}),
    )
    scan = root_result["library"]
    assert isinstance(scan, dict)
    scan_job = _terminal_job(controller, str(scan["jobId"]))
    assert scan_job["rawState"] == "completed"
    assert scan["games"] == 1
    assert scan["ignoredAuxiliary"] == 2

    snapshot = controller.snapshot({"context": {}})
    games = snapshot["platforms"][0]["games"]
    assert len(games) == 1
    game = games[0]
    game_id = str(game["id"])
    assert game["contentKind"] == "base"
    assert game["updateCount"] == 1
    assert game["dlcCount"] == 1
    assert game["coverUrl"] == local_cover.resolve().as_uri()
    assert game["mediaSource"] == "scraped"

    search_result = _apply(
        controller,
        controller.plan_action(
            {
                "actionId": f"game.media.search:{game_id}",
                "mediaKinds": ["icon"],
            }
        ),
    )
    failed_search = _terminal_job(controller, str(search_result["jobId"]))
    assert failed_search["rawState"] == "rolled-back"
    assert failed_search["errorCode"] == "E-SCRAPE-PROVIDER-UNREACHABLE"
    assert failed_search["canRetry"] is True
    assert isinstance(search_result.get("library"), dict)
    offline_game = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    assert offline_game["coverUrl"] == local_cover.resolve().as_uri()
    assert offline_game["mediaSource"] == "scraped"

    retried = controller.retry_job(str(search_result["jobId"]))
    assert retried["rawState"] == "completed"
    assert retried["result"] == {"candidate_count": 1, "provider_errors": {}}
    refreshed_game = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    assert refreshed_game["mediaCandidateCount"] == 1
    assert refreshed_game["mediaErrors"] == {}
    assert provider.attempts == 2
    assert provider.identities[-1].game_id == game_id

    selected = _apply(
        controller,
        controller.plan_action({"actionId": f"game.media.select:{game_id}:0"}),
    )
    selected_game = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    assert selected_game["mediaCandidateIdx"] == 0
    assert selected_game["mediaSource"] == "scraper"
    assert selected_game["masterState"] == "collected"
    assert selected_game["optimizedState"] == "ready"
    assert fetched == ["https://provider.invalid/example-icon.png"]

    emulator_selection = _apply(
        controller,
        controller.plan_action(
            {
                "actionId": "game.emulator.set",
                "gameId": game_id,
                "emulatorId": "citron",
            }
        ),
    )
    steam_selection = _apply(
        controller,
        controller.plan_action(
            {"actionId": "game.steam.set", "gameId": game_id, "selected": True}
        ),
    )
    settings = controller._load_game_settings(strict=True)  # type: ignore[attr-defined]
    assert settings[game_id] == {"emulatorId": "citron", "steamSelected": True}

    shortcut_result = _apply(
        controller,
        controller.plan_action({"actionId": "steam.shortcuts.sync"}),
    )
    shortcut_target = steam_config / "shortcuts.vdf"
    rows = decode_shortcuts(shortcut_target.read_bytes())
    assert len(rows) == 1
    assert rows[0]["ShortcutPath"] == f"steamzero://switch/{game_id}"
    assert rows[0]["AppName"] == "Example"
    assert "update" not in json.dumps(rows).casefold()
    assert "dlc" not in json.dumps(rows).casefold()
    app_id = shortcuts.resolve_app_id(game_id)
    assert app_id is not None

    publish_plan = controller.plan_action(
        {"actionId": f"game.media.publish-steam:{game_id}", "steamUserId": "123"}
    )
    original_symlink = fs.symlink_atomic

    def fail_publication(_source: Path, _target: Path) -> None:
        raise OSError("falha Steam simulada")

    monkeypatch.setattr(fs, "symlink_atomic", fail_publication)
    with pytest.raises(OSError, match="falha Steam simulada"):
        _apply(controller, publish_plan)
    steam_grid = steam_config / "grid"
    assert not steam_grid.exists() or not any(steam_grid.iterdir())
    monkeypatch.setattr(fs, "symlink_atomic", original_symlink)

    published_media = _apply(
        controller,
        controller.plan_action(
            {"actionId": f"game.media.publish-steam:{game_id}", "steamUserId": "123"}
        ),
    )
    grid_assets = list(steam_grid.iterdir())
    assert len(grid_assets) == 1
    assert grid_assets[0].is_symlink()
    assert grid_assets[0].name == f"{app_id}_icon.png"
    assert grid_assets[0].resolve().is_file()

    republished_media = _apply(
        controller,
        controller.plan_action(
            {"actionId": f"game.media.publish-steam:{game_id}", "steamUserId": "123"}
        ),
    )
    grid_assets = list(steam_grid.iterdir())
    assert len(grid_assets) == 1
    assert grid_assets[0].is_symlink()

    unpublished_media = _apply(
        controller,
        controller.plan_action(
            {"actionId": f"game.media.unpublish-steam:{game_id}", "steamUserId": "123"}
        ),
    )
    assert list(steam_grid.iterdir()) == []
    unpublished_game = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    assert unpublished_game["steamViewState"] == "unpublished"

    published_media = _apply(
        controller,
        controller.plan_action(
            {"actionId": f"game.media.publish-steam:{game_id}", "steamUserId": "123"}
        ),
    )
    grid_assets = list(steam_grid.iterdir())
    assert len(grid_assets) == 1 and grid_assets[0].is_symlink()

    final_snapshot = controller.snapshot({"context": {}})
    final_game = final_snapshot["platforms"][0]["games"][0]
    assert final_game["steamSelected"] is True
    assert final_game["steamPublished"] is True
    assert final_game["steamAppId"] == app_id
    assert final_game["steamViewState"] == "published"
    assert final_game["steamArtworkKinds"] == ["steam-icon"]

    with StateStore(state_db) as store:
        store.migrate()
        exported_state = store.export_json()
    evidence = json.dumps(
        {
            "root": root_result,
            "search": search_result,
            "retry": retried,
            "selected": selected,
            "emulator": emulator_selection,
            "steamSelection": steam_selection,
            "shortcut": shortcut_result,
            "republishedMedia": republished_media,
            "unpublishedMedia": unpublished_media,
            "publishedMedia": published_media,
            "snapshot": final_snapshot,
            "state": exported_state,
        },
        sort_keys=True,
        default=str,
    )
    assert _SECRET not in evidence
    if paths.core_log().is_file():
        assert _SECRET not in paths.core_log().read_text(encoding="utf-8")
