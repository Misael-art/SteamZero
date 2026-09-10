# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Exportação para ``gamelist.xml`` do ES-DE (frente A1).

Os testes centrais aqui não são os do caminho feliz: são os três que provam que
a exportação **não destrói arquivo do usuário** — não apaga jogo desconhecido,
não apaga campo que não modelamos, e recusa alvo que não entende em vez de
sobrescrever.
"""

from __future__ import annotations

from typing import Any

import pytest

from steamzero.domain.game_record import GameRecord
from steamzero.domain.metadata_export import ExportAction, plan_esde_export

ROOT = "/roms/psx"
TARGET = "/roms/psx/gamelist.xml"


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


def _plan(records, current: str | None = None):
    return plan_esde_export(records, system_root=ROOT, target=TARGET, current_xml=current)


# -- criação -----------------------------------------------------------------


def test_alvo_inexistente_e_criacao_e_nao_exige_backup() -> None:
    plan = _plan([_record()])
    assert plan.action is ExportAction.CREATE
    assert plan.requires_backup is False
    assert plan.writes is True
    assert "<name>Crash Bandicoot</name>" in plan.preview
    assert "<path>./crash.chd</path>" in plan.preview


def test_preview_e_o_conteudo_final_e_nao_um_resumo() -> None:
    """Quem aplica precisa poder comparar com o arquivo atual."""
    preview = _plan([_record()]).preview
    assert preview.startswith('<?xml version="1.0"?>')
    assert preview.rstrip().endswith("</gameList>")


def test_campos_modelados_sao_exportados() -> None:
    plan = _plan(
        [
            _record(
                description="Um marsupial.",
                developer="Naughty Dog",
                publisher="Sony",
                genres=["Plataforma", "Ação"],
                players=2,
                releaseDate="1996-09-09",
                media={"cover": {"path": "/roms/psx/media/c.png", "format": "png"}},
            )
        ]
    )
    for fragment in (
        "<desc>Um marsupial.</desc>",
        "<developer>Naughty Dog</developer>",
        "<publisher>Sony</publisher>",
        "<genre>Plataforma</genre>",
        "<players>2</players>",
        "<releasedate>19960909T000000</releasedate>",
        "<image>./media/c.png</image>",
    ):
        assert fragment in plan.preview


def test_campo_ausente_nao_vira_tag_vazia() -> None:
    preview = _plan([_record()]).preview
    for absent in ("<desc>", "<developer>", "<rating>", "<image>"):
        assert absent not in preview


# -- escala do rating: espelho do bug que passou pelo schema -----------------


@pytest.mark.parametrize(
    ("rating", "expected"),
    [(85.0, "0.85"), (100.0, "1"), (0.0, "0"), (50.0, "0.5"), (87.5, "0.875")],
)
def test_rating_volta_para_a_fracao_do_esde(rating: float, expected: str) -> None:
    """Contrato 0..100 -> fração 0..1. Valores calculados à mão de propósito:
    derivá-los da mesma fórmula do código repetiria o erro que o schema não
    pegou na importação."""
    plan = _plan([_record(rating=rating)])
    assert f"<rating>{expected}</rating>" in plan.preview


def test_exportar_e_reimportar_preserva_o_rating() -> None:
    """Ida e volta é a prova real de que as duas escalas concordam."""
    from steamzero.domain.metadata_import import import_esde_gamelist

    plan = _plan([_record(rating=85.0)])
    (voltou,) = import_esde_gamelist(
        plan.preview, platform_id="psx", system_root=ROOT, retrieved_at="2026-09-09T00:00:00Z"
    ).records
    assert voltou.to_mapping()["rating"] == 85.0


# -- não destruir arquivo do usuário -----------------------------------------


def test_jogo_desconhecido_no_alvo_e_preservado() -> None:
    """Exportar 1 jogo para um arquivo com 2 não pode devolver 1."""
    atual = (
        '<?xml version="1.0"?><gameList>'
        "<game><path>./outro.chd</path><name>Outro Jogo</name></game>"
        "</gameList>"
    )
    plan = _plan([_record()], atual)
    assert "<name>Outro Jogo</name>" in plan.preview
    assert "<name>Crash Bandicoot</name>" in plan.preview


def test_campo_nao_modelado_sobrevive_a_atualizacao() -> None:
    """``<favorite>`` e ``<playcount>`` são curadoria do usuário."""
    atual = (
        '<?xml version="1.0"?><gameList><game>'
        "<path>./crash.chd</path><name>Nome Antigo</name>"
        "<favorite>true</favorite><playcount>42</playcount><kidgame>false</kidgame>"
        "</game></gameList>"
    )
    plan = _plan([_record()], atual)
    assert "<favorite>true</favorite>" in plan.preview
    assert "<playcount>42</playcount>" in plan.preview
    assert "<kidgame>false</kidgame>" in plan.preview
    # O que é nosso é reescrito.
    assert "<name>Crash Bandicoot</name>" in plan.preview
    assert "Nome Antigo" not in plan.preview


def test_campos_preservados_sao_declarados_no_plano() -> None:
    """O usuário precisa ver que não foram perdidos."""
    atual = (
        '<?xml version="1.0"?><gameList><game>'
        "<path>./crash.chd</path><favorite>true</favorite><playcount>1</playcount>"
        "</game></gameList>"
    )
    plan = _plan([_record()], atual)
    assert plan.preserved == ("favorite", "playcount")


# -- recusar em vez de adivinhar ---------------------------------------------


def test_alvo_malformado_e_recusado_e_nada_seria_escrito() -> None:
    """O parser pode estar diante de arquivo válido que não sabe ler."""
    plan = _plan([_record()], "<gameList><game>")
    assert plan.action is ExportAction.REFUSED
    assert plan.writes is False
    assert plan.preview == ""
    assert "malformado" in plan.reason


def test_alvo_com_dtd_e_recusado() -> None:
    plan = _plan([_record()], '<!DOCTYPE gameList [<!ENTITY x "y">]><gameList/>')
    assert plan.action is ExportAction.REFUSED
    assert "DTD" in plan.reason


def test_alvo_com_raiz_inesperada_e_recusado() -> None:
    """Pode ser outro arquivo por engano; sobrescrever destruiria."""
    plan = _plan([_record()], '<?xml version="1.0"?><configuracao><x/></configuracao>')
    assert plan.action is ExportAction.REFUSED
    assert "raiz inesperada" in plan.reason


def test_recusa_preserva_o_digest_do_que_esta_la() -> None:
    plan = _plan([_record()], "<gameList><game>")
    assert plan.current_digest
    assert plan.proposed_digest == ""


# -- idempotência e backup ---------------------------------------------------


def test_reexportar_o_mesmo_conteudo_e_unchanged() -> None:
    primeiro = _plan([_record()])
    segundo = _plan([_record()], primeiro.preview)
    assert segundo.action is ExportAction.UNCHANGED
    assert segundo.writes is False
    assert segundo.requires_backup is False


def test_mudanca_real_e_update_e_exige_backup() -> None:
    primeiro = _plan([_record()])
    segundo = _plan([_record(title="Outro Título")], primeiro.preview)
    assert segundo.action is ExportAction.UPDATE
    assert segundo.requires_backup is True
    assert segundo.current_digest != segundo.proposed_digest


def test_digest_atual_identifica_exatamente_o_arquivo_planejado() -> None:
    """Se o alvo mudar entre planejar e aplicar, quem aplica precisa notar —
    e para isso o digest tem que casar com o conteúdo lido, não ser opaco."""
    from steamzero.domain.metadata_export import digest

    primeiro = _plan([_record()])
    plan = _plan([_record(title="X")], primeiro.preview)
    assert plan.current_digest == digest(primeiro.preview)
    assert plan.proposed_digest == digest(plan.preview)
    assert plan.current_digest != plan.proposed_digest


# -- limites -----------------------------------------------------------------


def test_registro_fora_da_raiz_e_recusado_com_motivo() -> None:
    plan = _plan([_record(path="/outro/lugar/x.chd")])
    assert plan.skipped == (("psx-crash", "caminho fora da raiz do sistema"),)
    assert "<game>" not in plan.preview


def test_lista_vazia_gera_gamelist_vazio_e_nao_erro() -> None:
    plan = _plan([])
    assert plan.action is ExportAction.CREATE
    assert "<gameList" in plan.preview


def test_caractere_especial_e_escapado_uma_vez_so() -> None:
    plan = _plan([_record(title="Tom & Jerry <1>")])
    assert "<name>Tom &amp; Jerry &lt;1&gt;</name>" in plan.preview
    assert "&amp;amp;" not in plan.preview
