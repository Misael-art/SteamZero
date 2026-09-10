# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato de plano de exportação (frente A1).

O plano é o que separa "exportar" de "sobrescrever o arquivo do usuário". Estes
testes fixam as regras que tornam essa diferença real: preview antes de
escrever, backup exigido só quando há o que perder, e recusa que não escreve
nada.
"""

from __future__ import annotations

import pytest

from steamzero.domain.metadata_export import ExportAction, ExportPlan, digest, summarize
from steamzero.domain.metadata_export._plan import decide, refusal

TARGET = "/roms/psx/gamelist.xml"


# -- backup ------------------------------------------------------------------


def test_criar_arquivo_novo_nao_exige_backup() -> None:
    """Não há o que perder num arquivo que ainda não existe."""
    assert ExportPlan(action=ExportAction.CREATE, target=TARGET).requires_backup is False


def test_sobrescrever_exige_backup() -> None:
    assert ExportPlan(action=ExportAction.UPDATE, target=TARGET).requires_backup is True


@pytest.mark.parametrize("action", [ExportAction.UNCHANGED, ExportAction.REFUSED])
def test_plano_que_nao_escreve_nao_exige_backup(action: ExportAction) -> None:
    plan = ExportPlan(action=action, target=TARGET)
    assert plan.writes is False
    assert plan.requires_backup is False


@pytest.mark.parametrize("action", [ExportAction.CREATE, ExportAction.UPDATE])
def test_apenas_create_e_update_tocam_o_disco(action: ExportAction) -> None:
    assert ExportPlan(action=action, target=TARGET).writes is True


# -- decisão -----------------------------------------------------------------


def test_alvo_inexistente_e_create() -> None:
    action, current, proposed = decide(TARGET, None, "conteudo")
    assert action is ExportAction.CREATE
    assert current == ""
    assert proposed == digest("conteudo")


def test_conteudo_identico_e_unchanged() -> None:
    """Idempotência: reexportar o mesmo não pode tocar o disco."""
    action, current, proposed = decide(TARGET, "igual", "igual")
    assert action is ExportAction.UNCHANGED
    assert current == proposed


def test_conteudo_diferente_e_update() -> None:
    action, current, proposed = decide(TARGET, "antes", "depois")
    assert action is ExportAction.UPDATE
    assert current != proposed


def test_diferenca_de_um_byte_ja_e_update() -> None:
    action, _, _ = decide(TARGET, "a", "b")
    assert action is ExportAction.UPDATE


# -- recusa ------------------------------------------------------------------


def test_recusa_nao_carrega_preview_nem_digest_proposto() -> None:
    """Recusar é não ter proposta — preview preenchido convidaria a aplicar."""
    plan = refusal(TARGET, "conteudo atual", "alvo malformado")
    assert plan.action is ExportAction.REFUSED
    assert plan.preview == ""
    assert plan.proposed_digest == ""
    assert plan.writes is False


def test_recusa_preserva_o_digest_do_alvo() -> None:
    plan = refusal(TARGET, "conteudo atual", "motivo")
    assert plan.current_digest == digest("conteudo atual")


def test_recusa_carrega_o_motivo() -> None:
    assert refusal(TARGET, "x", "raiz inesperada").reason == "raiz inesperada"


# -- digest ------------------------------------------------------------------


def test_digest_e_estavel_entre_chamadas() -> None:
    assert digest("mesmo texto") == digest("mesmo texto")


def test_digest_distingue_conteudos() -> None:
    assert digest("a") != digest("b")


def test_digest_distingue_espaco_em_branco() -> None:
    """Diferença invisível ainda é diferença de arquivo."""
    assert digest("a\n") != digest("a")


# -- resumo ------------------------------------------------------------------


def test_resumo_conta_por_acao() -> None:
    plans = [
        ExportPlan(action=ExportAction.CREATE, target="a"),
        ExportPlan(action=ExportAction.UPDATE, target="b"),
        ExportPlan(action=ExportAction.UPDATE, target="c"),
        ExportPlan(action=ExportAction.REFUSED, target="d"),
    ]
    assert summarize(plans) == {"create": 1, "update": 2, "unchanged": 0, "refused": 1}


def test_resumo_de_lista_vazia_traz_todas_as_acoes_em_zero() -> None:
    """Chave ausente forçaria a superfície a adivinhar entre 0 e desconhecido."""
    assert summarize([]) == {"create": 0, "update": 0, "unchanged": 0, "refused": 0}


# -- imutabilidade -----------------------------------------------------------


def test_plano_e_imutavel() -> None:
    """Plano que muda depois de exibido não é plano."""
    plan = ExportPlan(action=ExportAction.CREATE, target=TARGET)
    with pytest.raises(AttributeError):
        plan.action = ExportAction.UPDATE  # type: ignore[misc]
