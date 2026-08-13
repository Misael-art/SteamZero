# SPDX-License-Identifier: GPL-3.0-or-later
"""A matriz de controles como gate, não como relatório.

A auditoria de 2026-08-11 achou um botão "Instalar" habilitado que não chamava
nada (P0-4). Nenhum gate pegou porque nenhum gate sabia quais botões existiam.
Estes testes perguntam ao próprio shell o que cada ação publicada faz e reprovam
as três formas de botão desonesto:

* habilitado e silencioso — clicar não produz efeito nem erro;
* habilitado sem rota — o shell não sabe despachar, então sempre erra;
* desabilitado sem motivo — some da jornada sem dizer por quê.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import ui_action_inventory as inventory  # noqa: E402

pytestmark = pytest.mark.skipif(
    shutil.which("qml6") is None and shutil.which("qml") is None,
    reason="qml6 não está instalado neste host",
)


@pytest.fixture(scope="module")
def matrix() -> dict:
    return inventory.build_inventory()


def test_no_enabled_action_is_a_silent_no_op(matrix: dict) -> None:
    """Regressão do P0-4: botão habilitado que não produz efeito nem erro."""
    offenders = [f"{row['surface']} → {row['id'] or row['kind']}" for row in matrix["silentNoOps"]]
    assert offenders == [], "ações habilitadas sem efeito e sem erro:\n" + "\n".join(offenders)


def test_every_disabled_action_explains_itself(matrix: dict) -> None:
    offenders = [
        f"{row['surface']} → {row['id'] or row['kind']} ({row['label']})"
        for row in matrix["unexplainedBlocked"]
    ]
    assert offenders == [], "ações desabilitadas sem motivo:\n" + "\n".join(offenders)


def test_the_probe_actually_exercised_the_dispatcher(matrix: dict) -> None:
    """Guarda contra matriz vazia passando por engano.

    Se a sonda deixar de rodar, os dois testes acima ficariam verdes sem ter
    verificado nada — foi assim que a regressão da a37 atravessou os gates.
    """
    assert matrix["publishedActionCount"] > 0
    assert matrix["verdictCounts"].get("routed", 0) > 0
    assert "not-probed" not in matrix["verdictCounts"]


def test_platform_cards_offer_an_action_the_shell_can_dispatch(matrix: dict) -> None:
    """O CTA do card de plataforma precisa existir para o despachante.

    Hoje o botão do card chama ``openPlatformFromGlobal`` direto e ignora o
    ``action.id`` publicado. O payload continua anunciando ``platform.open``,
    que nenhum despachante entende — qualquer superfície nova que roteie esse
    payload herda um botão que só sabe errar.
    """
    unrouted = sorted({row["id"] for row in matrix["unrouted"]})
    assert unrouted == [], "ações habilitadas que o shell não sabe despachar: " + ", ".join(
        unrouted
    )
