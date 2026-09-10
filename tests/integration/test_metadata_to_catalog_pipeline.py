# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Caminho completo: arquivo de metadados externo até item da home.

Esta suíte existe para provar que ``GameRecord`` tem consumidor. Antes dela o
projeto tinha tradutores de formatos externos e nenhum leitor, e modelo que
ninguém lê não move nada para o usuário.

O percurso exercitado é o real, sem atalho:

    arquivo externo -> adapter -> GameRecord -> projeção -> catalog_games -> home

Nenhuma etapa é substituída por dublê. Se qualquer elo divergir do contrato, o
teste reprova aqui e não numa tela em produção.
"""

from __future__ import annotations

import pathlib

import pytest

from steamzero.adapters.launcher_catalog import catalog_games
from steamzero.domain.library_projection import project_records
from steamzero.domain.metadata_import import (
    import_esde_gamelist,
    import_launchbox_xml,
    import_pegasus_metadata,
    import_retroarch_playlist,
    import_steam_appmanifest,
)

WHEN = "2026-09-09T00:00:00Z"
ROOT = "/roms/psx"

_REAL = pathlib.Path(__file__).resolve().parents[2] / "reference" / "EmuDeck" / "android" / "roms"


def _home(records) -> tuple:
    """Roda a projeção e o adapter da home, como o Launcher faria."""
    return catalog_games(project_records(records).entries)


# -- um adapter de cada formato chega à home ---------------------------------


def test_esde_chega_a_home() -> None:
    result = import_esde_gamelist(
        "<gameList><game><path>./crash.chd</path><name>Crash Bandicoot</name>"
        "<image>./media/crash.png</image></game></gameList>",
        platform_id="psx",
        system_root=ROOT,
        retrieved_at=WHEN,
    )
    (game,) = _home(result.records)
    assert game.title == "Crash Bandicoot"
    assert game.platform == "psx"
    assert game.cover_url == "file:///roms/psx/media/crash.png"


def test_retroarch_chega_a_home() -> None:
    result = import_retroarch_playlist(
        '{"items":[{"path":"/roms/psx/x.chd","label":"Jogo"}]}',
        platform_id="psx",
        system_root=ROOT,
        retrieved_at=WHEN,
    )
    (game,) = _home(result.records)
    assert game.title == "Jogo"
    # Playlist não tem arte; o cartão usa o fallback honesto.
    assert game.cover_url == ""


def test_pegasus_chega_a_home() -> None:
    result = import_pegasus_metadata(
        "game: Final Fantasy IX\nfile: ff9.chd\n",
        platform_id="psx",
        system_root=ROOT,
        retrieved_at=WHEN,
    )
    (game,) = _home(result.records)
    assert game.title == "Final Fantasy IX"


def test_launchbox_chega_a_home() -> None:
    result = import_launchbox_xml(
        "<LaunchBox><Game><Title>Crash</Title>"
        "<ApplicationPath>Games\\crash.chd</ApplicationPath></Game></LaunchBox>",
        platform_id="psx",
        system_root=ROOT,
        retrieved_at=WHEN,
    )
    (game,) = _home(result.records)
    assert game.title == "Crash"


def test_steam_chega_a_home() -> None:
    result = import_steam_appmanifest(
        '"AppState"\n{\n\t"appid"\t\t"220"\n\t"name"\t\t"Half-Life 2"\n'
        '\t"installdir"\t\t"hl2"\n}\n',
        library_root="/steam/steamapps",
        retrieved_at=WHEN,
    )
    (game,) = _home(result.records)
    assert game.id == "steam-220"
    assert game.title == "Half-Life 2"


# -- o que o caminho precisa preservar ---------------------------------------


def test_jogo_marcado_como_quebrado_na_origem_nao_aparece_na_home() -> None:
    """LaunchBox marca ``Broken``; a home não pode oferecer o que não abre."""
    result = import_launchbox_xml(
        "<LaunchBox><Game><Title>Quebrado</Title>"
        "<ApplicationPath>x.chd</ApplicationPath><Broken>true</Broken></Game></LaunchBox>",
        platform_id="psx",
        system_root=ROOT,
        retrieved_at=WHEN,
    )
    assert result.records, "o adapter deve importar o registro, marcando o estado"
    assert _home(result.records) == ()


def test_fusao_de_duas_fontes_chega_a_home_com_o_titulo_mais_rico() -> None:
    """O ganho real de ter modelo canônico: playlist pobre + gamelist rico."""
    (rico,) = import_esde_gamelist(
        "<gameList><game><path>./x.chd</path><name>Crash Bandicoot</name></game></gameList>",
        platform_id="psx",
        system_root=ROOT,
        retrieved_at=WHEN,
    ).records
    (pobre,) = import_retroarch_playlist(
        '{"items":[{"path":"/roms/psx/x.chd","label":"x"}]}',
        platform_id="psx",
        system_root=ROOT,
        retrieved_at=WHEN,
    ).records
    (game,) = _home([rico.merge(pobre).record])
    assert game.title == "Crash Bandicoot"


def test_biblioteca_de_varias_plataformas_agrupa_por_sistema() -> None:
    psx = import_pegasus_metadata(
        "game: A\nfile: a.chd\n", platform_id="psx", system_root=ROOT, retrieved_at=WHEN
    ).records
    snes = import_pegasus_metadata(
        "game: B\nfile: b.sfc\n",
        platform_id="snes",
        system_root="/roms/snes",
        retrieved_at=WHEN,
    ).records
    games = _home([*psx, *snes])
    assert {game.platform for game in games} == {"psx", "snes"}


def test_registro_corrompido_nao_esvazia_a_home() -> None:
    """Um item ruim não pode derrubar a biblioteca inteira."""
    good = import_pegasus_metadata(
        "game: Bom\nfile: bom.chd\n", platform_id="psx", system_root=ROOT, retrieved_at=WHEN
    ).records
    entries = [*project_records(good).entries, {"id": "", "title": ""}]
    assert len(catalog_games(entries)) == 1


# -- prova com dados reais ---------------------------------------------------

# ``reference/`` não é versionado (.gitignore:36), então isto pula na CI. Existe
# porque fixture sintética prova apenas consistência com as suposições de quem a
# escreveu; só arquivo real prova que o caminho inteiro funciona.


@pytest.mark.skipif(not _REAL.is_dir(), reason="reference/ não versionado; checkout sem pesquisa")
def test_biblioteca_real_percorre_o_caminho_inteiro() -> None:
    path = _REAL / "mame" / "metadata.pegasus.txt"
    if not path.is_file():
        pytest.skip("coleção mame ausente na referência")

    result = import_pegasus_metadata(
        path.read_text(encoding="utf-8"),
        platform_id="mame",
        system_root="/roms/mame",
        retrieved_at=WHEN,
    )
    projection = project_records(result.records)
    games = catalog_games(projection.entries)

    assert len(result.records) > 1000, "biblioteca real deveria trazer milhares de jogos"
    assert len(games) == len(result.records), "nenhum jogo pode se perder no caminho"
    assert projection.omitted == ()
    titles = {game.title for game in games}
    assert "Aqua Jack (World)" in titles
    assert all(game.platform == "mame" for game in games)
