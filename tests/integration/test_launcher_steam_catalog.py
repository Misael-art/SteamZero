# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato do acervo Steam do Launcher e sua rota de lançamento."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.adapters.launcher_catalog import CatalogGame, catalog_summary
from steamzero.adapters.launcher_steam import steam_catalog_games
from steamzero.launcher.app import LaunchRouter, _sections_from_catalog

_LSFG_APP_ID = "993090"


def _write_manifest(steamapps: Path, app_id: str, name: str) -> None:
    (steamapps / f"appmanifest_{app_id}.acf").write_text(
        f'"AppState"\n{{\n\t"appid"\t\t"{app_id}"\n\t"name"\t\t"{name}"\n}}\n',
        encoding="utf-8",
    )


_TYPES = {
    "620": "Game",
    "1145360": "game",
    "3311720": "Demo",
    "1493710": "Tool",
    "431960": "Application",
    _LSFG_APP_ID: "Application",
}


@pytest.fixture
def steam_root(tmp_path: Path) -> Path:
    steamapps = tmp_path / "Steam" / "steamapps"
    steamapps.mkdir(parents=True)
    _write_manifest(steamapps, "620", "Portal 2")
    _write_manifest(steamapps, "1145360", "Hades")
    _write_manifest(steamapps, "3311720", "Gimmick! 2 Demo")
    _write_manifest(steamapps, "1493710", "Proton Experimental")
    _write_manifest(steamapps, "431960", "Wallpaper Engine")
    _write_manifest(steamapps, _LSFG_APP_ID, "Lossless Scaling")
    return tmp_path / "Steam"


def test_the_steam_library_reaches_the_launcher_catalog(steam_root: Path) -> None:
    games = steam_catalog_games(roots=(steam_root,), types=_TYPES)
    identifiers = {game.id for game in games}
    assert identifiers == {"620", "1145360", "3311720"}
    assert _LSFG_APP_ID not in identifiers
    assert {game.kind for game in games} == {"steam"}
    assert {game.title for game in games} == {
        "Portal 2",
        "Hades",
        "Gimmick! 2 Demo",
    }


def test_tools_and_runtimes_never_reach_the_game_grid(steam_root: Path) -> None:
    identifiers = {game.id for game in steam_catalog_games(roots=(steam_root,), types=_TYPES)}
    assert "1493710" not in identifiers
    assert "431960" not in identifiers


def test_without_the_classifier_the_library_still_shows_up(steam_root: Path) -> None:
    identifiers = {game.id for game in steam_catalog_games(roots=(steam_root,), types={})}
    assert {"620", "1145360", "3311720"} <= identifiers
    assert "1493710" in identifiers


def test_the_home_gets_a_steam_section(steam_root: Path) -> None:
    emulation = (CatalogGame(id="celeste", title="Celeste", platform="nes-famicom"),)
    catalog = (*emulation, *steam_catalog_games(roots=(steam_root,), types=_TYPES))
    sections = _sections_from_catalog(catalog)
    by_id = {section.id: section for section in sections}
    assert "steam" in by_id
    assert set(by_id["steam"].items) == {"620", "1145360", "3311720"}


def test_the_published_count_stops_diverging_from_the_central(steam_root: Path) -> None:
    emulation = tuple(
        CatalogGame(id=f"g{index}", title=f"Jogo {index}", platform="nes-famicom")
        for index in range(3)
    )
    steam = steam_catalog_games(roots=(steam_root,), types=_TYPES)
    summary = catalog_summary(None, (*emulation, *steam), [])
    assert summary["games"] == len(emulation) + len(steam) == 6


def test_a_steam_game_is_launched_through_steam_not_emulation(tmp_path: Path) -> None:
    spawned: list[tuple[str, ...]] = []
    router = LaunchRouter(
        on_spawn=lambda argv: (spawned.append(tuple(argv)), 4242)[1],
        context_path=tmp_path / "return.json",
        executable=lambda: "/usr/local/bin/steamzero",
        kinds={"620": "steam"},
        steam_executable=lambda: "/usr/bin/steam",
    )
    router.launch("620", "steam:620")
    assert spawned == [("/usr/bin/steam", "steam://rungameid/620")]


def test_without_the_steam_client_the_launch_fails_loudly(tmp_path: Path) -> None:
    spawned: list[tuple[str, ...]] = []
    router = LaunchRouter(
        on_spawn=lambda argv: (spawned.append(tuple(argv)), 1)[1],
        context_path=tmp_path / "return.json",
        executable=lambda: "/usr/local/bin/steamzero",
        kinds={"620": "steam"},
        steam_executable=lambda: None,
    )
    with pytest.raises(Exception) as excinfo:
        router.launch("620", "steam:620")
    assert not spawned
    assert "steam" in str(excinfo.value).lower()
