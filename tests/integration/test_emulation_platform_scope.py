"""Isolamento do workspace operacional e dos jobs de mídia por plataforma."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from steamzero.adapters.emulation import EmulationController
from steamzero.core.state import StateStore
from steamzero.jobs.manager import JobManager


def _raw_game(game_id: str, platform_id: str, title: str) -> dict[str, Any]:
    return {
        "id": game_id,
        "titleId": "0100ABCDEF123000" if platform_id == "switch" else f"title-{game_id}",
        "name": title,
        "state": "ready",
        "statusLabel": "Pronto",
        "path": f"/owned/{game_id}.rom",
        "platform": platform_id,
        "platformId": platform_id,
    }


def _switch_enrichment(games: list[dict[str, Any]], *_args: object) -> list[dict[str, Any]]:
    return [
        dict(
            game,
            fallbackArtworkUrl="",
            emulatorId=None,
            mediaSource="fallback",
            mediaKind="icon",
            mediaCandidateCount=0,
            mediaCandidates=[],
            mediaErrors={},
            masterState="none",
            optimizedState="none",
            steamViewState="unpublished",
            steamAppId=None,
            steamArtworkKinds=[],
        )
        for game in games
    ]


def test_switch_area_excludes_other_platform_games(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    controller = EmulationController(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        which=lambda _command: None,
        spawn=lambda _argv: None,
    )
    mixed = [
        _raw_game("switch-1", "switch", "Jogo Switch"),
        _raw_game("nes-1", "nes-famicom", "Jogo NES"),
    ]
    monkeypatch.setattr(controller, "_load_library_cache", lambda: (mixed, 0))
    monkeypatch.setattr(controller, "_enrich_games", _switch_enrichment)
    monkeypatch.setattr(controller, "_enrich_preservation", lambda games: games)
    monkeypatch.setattr(controller, "_enrich_controls", lambda games: games)

    workspace = controller.snapshot({"context": {}})
    platforms = workspace["platforms"]
    switch = next(platform for platform in platforms if platform["id"] == "switch")

    assert [game["id"] for game in switch["games"]] == ["switch-1"]
    saves = switch["areaData"]["saves"]["cards"]
    media = switch["areaData"]["media"]
    assert [card["id"] for card in saves] == ["preservation-save-switch-1"]
    assert media["mediaPipeline"]["totalGames"] == 1
    assert all("nes-1" not in str(card) for card in saves + media["cards"])

    nes_platform = next(
        platform
        for platform in platforms
        if any(game["id"] == "nes-1" for game in platform["games"])
    )
    assert nes_platform["games"] == [mixed[1]]


def test_global_media_job_processes_only_switch_games(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    store = StateStore(tmp_path / "state.db")
    store.migrate()
    manager = JobManager(store)
    controller = EmulationController(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        which=lambda _command: None,
        spawn=lambda _argv: None,
        job_manager=manager,
    )
    monkeypatch.setattr(
        controller,
        "_load_library_cache",
        lambda: (
            [
                _raw_game("switch-1", "switch", "Jogo Switch"),
                _raw_game("nes-1", "nes", "Jogo NES"),
            ],
            0,
        ),
    )

    job = manager.create(
        "media.global",
        params={"mode": "optimize", "overwrite": False, "platform_id": "switch"},
        priority="maintenance",
    )
    completed = manager.run(job.id)

    assert completed.state == "completed"
    assert completed.result == {
        "mode": "optimize",
        "platformId": "switch",
        "overwrite": False,
        "outcome": "success",
        "total": 1,
        "processed": 0,
        "skipped": 1,
        "updated": 0,
        "failures": 0,
        "no_candidates": 0,
        "provider_errors": {},
        "provider_details": {},
        "interrupted_providers": [],
    }
