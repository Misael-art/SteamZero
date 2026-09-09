# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Projeção de ``GameRecord`` para o catálogo da home (frente A1).

O teste central desta suíte é que jogo indisponível **não** entre no catálogo
como jogo normal: a home prometeria o que não abre. O segundo é que ausência de
arte continue ausência, e não um placeholder fingindo capa.
"""

from __future__ import annotations

from typing import Any

import pytest

from steamzero.domain.game_record import GameRecord
from steamzero.domain.library_projection import UNPLAYABLE, project_records


def _record(**overrides: Any) -> GameRecord:
    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "id": "psx-crash",
        "title": "Crash Bandicoot",
        "platformId": "psx",
        "path": "/roms/psx/crash.chd",
        "availability": "available",
        "updatedAt": "2026-09-09T00:00:00Z",
    }
    payload.update(overrides)
    return GameRecord.from_mapping(payload)


def test_projeta_os_campos_que_o_catalogo_le() -> None:
    projection = project_records([_record()])
    (entry,) = projection.entries
    assert entry["id"] == "psx-crash"
    assert entry["title"] == "Crash Bandicoot"
    assert entry["platformId"] == "psx"
    assert entry["contentKind"] == "base"


def test_projecao_alimenta_catalog_games_sem_conversao() -> None:
    """A prova de que o consumidor fecha: o payload entra direto no adapter."""
    from steamzero.adapters.launcher_catalog import catalog_games

    projection = project_records([_record(), _record(id="snes-mario", platformId="snes")])
    games = catalog_games(projection.entries)
    assert {game.id for game in games} == {"psx-crash", "snes-mario"}
    assert {game.platform for game in games} == {"psx", "snes"}


# -- estados indisponíveis ---------------------------------------------------


@pytest.mark.parametrize("state", sorted(UNPLAYABLE))
def test_jogo_indisponivel_nao_entra_como_jogo_normal(state: str) -> None:
    """Listá-lo junto dos jogáveis faria a home prometer o que não abre."""
    projection = project_records([_record(availability=state)])
    assert projection.entries == ()
    assert projection.omitted == (("psx-crash", f"indisponivel-{state}"),)


@pytest.mark.parametrize("state", ["available", "unknown", "degraded", "recovery"])
def test_estado_jogavel_ou_indeterminado_entra_no_catalogo(state: str) -> None:
    """``unknown`` entra: o adapter não leu disco, e esconder por precaução
    apagaria a biblioteca inteira de quem importou metadata."""
    projection = project_records([_record(availability=state)])
    assert len(projection.entries) == 1
    assert projection.omitted == ()


def test_omitido_nunca_desaparece_em_silencio() -> None:
    projection = project_records([_record(), _record(id="x", availability="missing")])
    assert len(projection.entries) == 1
    assert projection.omitted == (("x", "indisponivel-missing"),)


def test_duplicado_e_omitido_com_motivo() -> None:
    projection = project_records([_record(), _record(title="Outro")])
    assert len(projection.entries) == 1
    assert projection.omitted == (("psx-crash", "duplicado-na-projecao"),)


# -- arte --------------------------------------------------------------------


def test_capa_absoluta_vira_url_de_arquivo() -> None:
    projection = project_records(
        [_record(media={"cover": {"path": "/art/crash.png", "format": "png"}})]
    )
    assert projection.entries[0]["coverUrl"] == "file:///art/crash.png"


def test_capa_com_espaco_e_escapada() -> None:
    projection = project_records(
        [_record(media={"cover": {"path": "/art/meu jogo.png", "format": "png"}})]
    )
    assert projection.entries[0]["coverUrl"] == "file:///art/meu%20jogo.png"


def test_sem_arte_a_capa_fica_vazia_e_nao_vira_placeholder() -> None:
    """Placeholder fingindo capa mente sobre o que a biblioteca tem."""
    assert project_records([_record()]).entries[0]["coverUrl"] == ""


def test_capa_relativa_e_ignorada_em_vez_de_ancorada_por_palpite() -> None:
    """Resolvê-la aqui inventaria uma âncora que o registro não declara."""
    projection = project_records(
        [_record(media={"cover": {"path": "media/c.png", "format": "png"}})]
    )
    assert projection.entries[0]["coverUrl"] == ""


def test_fanart_sozinha_nao_vira_capa() -> None:
    projection = project_records(
        [_record(media={"fanart": {"path": "/art/f.jpg", "format": "jpeg"}})]
    )
    assert projection.entries[0]["coverUrl"] == ""


# -- avisos ------------------------------------------------------------------


def test_avisos_do_registro_seguem_para_a_superficie() -> None:
    """Cartão mudo esconde a causa; a superfície precisa dela para degradar."""
    projection = project_records([_record(warnings=["esde-rating-invalido"])])
    assert projection.entries[0]["warnings"] == ["esde-rating-invalido"]


def test_registro_sem_aviso_nao_ganha_chave_vazia() -> None:
    assert "warnings" not in project_records([_record()]).entries[0]


def test_lista_vazia_nao_e_erro() -> None:
    projection = project_records([])
    assert projection.entries == ()
    assert projection.omitted == ()
