# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""O ciclo completo: selecionar → jogar → sair → voltar ao mesmo cartão.

Os testes existentes cobrem o domínio do retorno com payload em memória. Este
teste passa pelos artefatos reais: biblioteca em arquivo, contexto gravado pelo
lançamento e catálogo remontado como numa nova sessão do Launcher.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero.adapters.launcher_catalog import catalog_games
from steamzero.adapters.launcher_steam import steam_catalog_games
from steamzero.launcher.app import (
    LaunchRouter,
    _read_library_payload,
    _sections_from_catalog,
)
from steamzero.launcher.launch import consume_context
from steamzero.launcher.navigation import resolve_home_focus
from steamzero.launcher.session import restore_context

_TYPES = {"250760": "Game", "1493710": "Tool"}


def _library(path: Path, games: list[dict[str, str]]) -> Path:
    path.write_text(json.dumps({"games": games}), encoding="utf-8")
    return path


def _steam_root(tmp_path: Path) -> Path:
    steamapps = tmp_path / "Steam" / "steamapps"
    steamapps.mkdir(parents=True)
    for app_id, name in (
        ("250760", "Shovel Knight"),
        ("1493710", "Proton Experimental"),
    ):
        (steamapps / f"appmanifest_{app_id}.acf").write_text(
            f'"AppState"\n{{\n\t"appid"\t\t"{app_id}"\n\t"name"\t\t"{name}"\n}}\n',
            encoding="utf-8",
        )
    return tmp_path / "Steam"


def _catalog(library: Path, steam_root: Path):
    records, payload = _read_library_payload(library)
    return (
        *catalog_games(records),
        *steam_catalog_games(roots=(steam_root,), types=_TYPES),
    ), payload


def _focus_after_restart(context_path: Path, catalog):
    """Reproduz a nova sessão: consome o contexto e resolve o foco."""
    restored = consume_context(context_path)
    focus = resolve_home_focus(_sections_from_catalog(catalog))
    return restore_context(restored, focus)


@pytest.fixture
def scenario(tmp_path: Path):
    library = _library(
        tmp_path / "library.json",
        [
            # A primeira seção é outra para impedir que um fallback genérico
            # passe por acaso no teste de retorno.
            {"id": "sonic", "name": "Sonic", "platform": "master-system"},
            {"id": "celeste", "name": "Celeste", "platform": "nes-famicom"},
            {
                "id": "hollow",
                "name": "Hollow Knight",
                "platform": "nes-famicom",
            },
        ],
    )
    steam_root = _steam_root(tmp_path)
    catalog, _ = _catalog(library, steam_root)
    return library, steam_root, catalog, tmp_path / "return.json"


def test_the_cycle_returns_to_the_same_emulation_card(scenario) -> None:
    _library_path, _steam_root_path, catalog, context_path = scenario
    spawned: list[tuple[str, ...]] = []
    router = LaunchRouter(
        on_spawn=lambda argv: (spawned.append(tuple(argv)), 4242)[1],
        context_path=context_path,
        executable=lambda: "/usr/local/bin/steamzero",
        kinds={game.id: game.kind for game in catalog},
    )

    router.launch("hollow", "nes-famicom:hollow")
    assert spawned
    assert context_path.is_file(), "o contexto precisa existir antes do spawn"

    restored, diagnostics = _focus_after_restart(context_path, catalog)

    assert restored == "nes-famicom:hollow"
    assert not diagnostics


def test_the_cycle_returns_to_the_same_steam_card(scenario) -> None:
    _library_path, _steam_root_path, catalog, context_path = scenario
    router = LaunchRouter(
        on_spawn=lambda argv: 4242,
        context_path=context_path,
        executable=lambda: "/usr/local/bin/steamzero",
        kinds={game.id: game.kind for game in catalog},
        steam_executable=lambda: "/usr/bin/steam",
    )

    router.launch("250760", "steam:250760")

    restored, diagnostics = _focus_after_restart(context_path, catalog)
    assert restored == "steam:250760"
    assert not diagnostics


def test_the_context_is_consumed_so_an_old_return_does_not_hijack_a_new_session(
    scenario,
) -> None:
    _library_path, _steam_root_path, catalog, context_path = scenario
    router = LaunchRouter(
        on_spawn=lambda argv: 4242,
        context_path=context_path,
        executable=lambda: "/usr/local/bin/steamzero",
        kinds={game.id: game.kind for game in catalog},
    )
    router.launch("hollow", "nes-famicom:hollow")

    first, _ = _focus_after_restart(context_path, catalog)
    assert first == "nes-famicom:hollow"

    second, diagnostics = _focus_after_restart(context_path, catalog)
    focus = resolve_home_focus(_sections_from_catalog(catalog))
    assert second == focus.initial
    assert diagnostics


def test_a_game_removed_while_playing_lands_in_the_same_section(scenario) -> None:
    library, steam_root, catalog, context_path = scenario
    router = LaunchRouter(
        on_spawn=lambda argv: 4242,
        context_path=context_path,
        executable=lambda: "/usr/local/bin/steamzero",
        kinds={game.id: game.kind for game in catalog},
    )
    router.launch("hollow", "nes-famicom:hollow")

    _library(
        library,
        [
            {"id": "sonic", "name": "Sonic", "platform": "master-system"},
            {"id": "celeste", "name": "Celeste", "platform": "nes-famicom"},
        ],
    )
    shrunk, _ = _catalog(library, steam_root)

    restored, diagnostics = _focus_after_restart(context_path, shrunk)

    focus = resolve_home_focus(_sections_from_catalog(shrunk))
    assert restored in focus.nodes
    assert focus.nodes[restored].section == "nes-famicom"
    assert diagnostics
