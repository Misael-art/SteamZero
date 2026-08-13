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

import re
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


def test_a_partial_audit_never_publishes_contracts_as_orphans(matrix: dict) -> None:
    """Orfandade é afirmação sobre o produto inteiro, não sobre o que foi visitado.

    A passagem anterior publicou 117 `orphanContracts` tendo inventariado só a
    Emulação. Quase todos eram contratos de telas que a auditoria nem abriu:
    o número parecia um achado e não era nada.
    """
    coverage = matrix["coverage"]
    assert coverage["covered"], "uma auditoria sem superfície coberta não prova nada"

    if coverage["complete"]:
        assert "orphanContracts" in matrix
        assert "notCoveredContracts" not in matrix
        return

    assert "orphanContracts" not in matrix, (
        "auditoria parcial não pode chamar de órfão o que não visitou; faltam: "
        + ", ".join(coverage["missing"])
    )
    assert "notCoveredContracts" in matrix


def test_coverage_is_measured_against_the_sections_the_shell_publishes() -> None:
    """A régua de cobertura vem do produto, não de uma lista inventada aqui.

    Toda seção de ``navigationSections`` em Main.qml precisa estar declarada,
    senão a auditoria poderia declarar-se completa ignorando uma tela inteira.
    """
    main_qml = (ROOT / "src" / "steamzero" / "ui" / "qml" / "Main.qml").read_text(encoding="utf-8")
    block = main_qml.split("readonly property var navigationSections:", 1)[1].split("]", 1)[0]
    sections = re.findall(r'\{"id":\s*"([a-z-]+)"', block)

    assert sections, "não foi possível ler navigationSections de Main.qml"
    missing = [item for item in sections if item not in inventory.DECLARED_SURFACES]
    assert missing == [], "seções do shell ausentes de DECLARED_SURFACES: " + ", ".join(missing)


def test_claiming_an_undeclared_surface_is_refused() -> None:
    """Cobrir "tudo" declarando um nome que não existe seria verde barato."""
    with pytest.raises(SystemExit) as excinfo:
        inventory.coverage_report(["emulators", "tela-que-nao-existe"])
    assert "tela-que-nao-existe" in str(excinfo.value)


def test_coverage_report_only_claims_completeness_when_nothing_is_missing() -> None:
    partial = inventory.coverage_report(["emulators"])
    assert partial["complete"] is False
    assert "overview" in partial["missing"]

    whole = inventory.coverage_report(inventory.DECLARED_SURFACES)
    assert whole["complete"] is True
    assert whole["missing"] == []
