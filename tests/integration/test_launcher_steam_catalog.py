# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""O acervo Steam do usuário existe no Launcher, e é lançado pela rota do Steam.

O defeito: a central somava Steam + emulação ("1134 títulos publicados") e o
Launcher contava só emulação ("1119 jogo(s)"). Medido no host em 2026-09-04:
16 `appmanifest_*.acf`, menos o LSFG (993090, excluído de propósito), dão
exatamente os 15 de diferença.

O número era o sintoma. O defeito é que, em Game Mode — onde o Launcher vive e
onde não existe mouse nem desktop —, os jogos Steam do usuário simplesmente
**não existiam**. Não é divergência de contador; é acervo inalcançável.

Corrigir o rótulo faria os números concordarem e deixaria o acervo fora. Aqui os
jogos entram na home, e a convergência das contagens é consequência.
"""

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


@pytest.fixture
def steam_root(tmp_path: Path) -> Path:
    steamapps = tmp_path / "Steam" / "steamapps"
    steamapps.mkdir(parents=True)
    _write_manifest(steamapps, "620", "Portal 2")
    _write_manifest(steamapps, "1145360", "Hades")
    # O LSFG não é um jogo do usuário: é a ferramenta que o próprio projeto
    # instala. Contá-lo aqui reintroduziria a diferença que este teste fecha.
    _write_manifest(steamapps, _LSFG_APP_ID, "Lossless Scaling")
    return tmp_path / "Steam"


def test_the_steam_library_reaches_the_launcher_catalog(steam_root: Path) -> None:
    games = steam_catalog_games(roots=(steam_root,))

    identifiers = {game.id for game in games}
    assert identifiers == {"620", "1145360"}, (
        "os jogos Steam instalados precisam chegar ao acervo do Launcher; sem "
        "isso eles ficam inalcançáveis em Game Mode, onde não há desktop"
    )
    assert _LSFG_APP_ID not in identifiers, (
        "o LSFG é ferramenta do projeto, não jogo do usuário: contá-lo aqui "
        "recria a divergência de 15 títulos entre a central e o Launcher"
    )
    assert {game.kind for game in games} == {"steam"}, (
        "o registro precisa dizer que é Steam: o lançamento é roteado por kind, "
        "e chamar `emulation launch --game-id 620` passaria um AppID a um "
        "contrato que espera id canônico de emulação"
    )
    assert {game.title for game in games} == {"Portal 2", "Hades"}


def test_the_home_gets_a_steam_section(steam_root: Path) -> None:
    emulation = (CatalogGame(id="celeste", title="Celeste", platform="nes-famicom"),)
    catalog = (*emulation, *steam_catalog_games(roots=(steam_root,)))

    sections = _sections_from_catalog(catalog)
    by_id = {section.id: section for section in sections}

    assert "steam" in by_id, (
        "a home agrupa por sistema; sem uma seção Steam os jogos entrariam em "
        "`outros` ou sumiriam da navegação por controle"
    )
    assert set(by_id["steam"].items) == {"620", "1145360"}


def test_the_published_count_stops_diverging_from_the_central(steam_root: Path) -> None:
    emulation = tuple(
        CatalogGame(id=f"g{index}", title=f"Jogo {index}", platform="nes-famicom")
        for index in range(3)
    )
    steam = steam_catalog_games(roots=(steam_root,))
    catalog = (*emulation, *steam)

    summary = catalog_summary(None, catalog, [])

    assert summary["games"] == len(emulation) + len(steam) == 5, (
        "o rodapé do Launcher precisa contar o mesmo acervo que a central "
        "publica; enquanto contar só emulação, os dois números discordam sem "
        "dizer de que escopo cada um fala"
    )


def test_a_steam_game_is_launched_through_steam_not_through_emulation(
    tmp_path: Path,
) -> None:
    spawned: list[tuple[str, ...]] = []
    router = LaunchRouter(
        on_spawn=lambda argv: (spawned.append(tuple(argv)), 4242)[1],
        context_path=tmp_path / "return.json",
        executable=lambda: "/usr/local/bin/steamzero",
        kinds={"620": "steam"},
        steam_executable=lambda: "/usr/bin/steam",
    )

    router.launch("620", "steam:620")

    assert len(spawned) == 1
    argv = spawned[0]
    assert "emulation" not in argv, (
        "rotear um AppID Steam pela rota de emulação repete o defeito já "
        "registrado em SZ-AURA-LAUNCHER: passar um id a um comando cujo "
        "contrato é outro"
    )
    assert argv == ("/usr/bin/steam", "steam://rungameid/620")


def test_without_the_steam_client_the_launch_fails_loudly(tmp_path: Path) -> None:
    """Falha degrada com causa, nunca sucesso vazio (AGENTS.md §8)."""
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

    assert not spawned, "sem cliente Steam nada pode ser lançado"
    assert "steam" in str(excinfo.value).lower()
