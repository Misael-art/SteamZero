# SPDX-License-Identifier: GPL-3.0-or-later
"""A matriz de controles da árvore QML viva, como gate.

``test_ui_action_inventory`` cobre os ``action`` que os read models publicam.
Ele não vê Button estático, aba, disclosure nem botão de diálogo, porque nenhum
deles nasce de um payload — e foi exatamente aí que estava o "Configurações
avançadas" da tela Steam: habilitado, largura total, com chevron e
``Accessible.name``, e sem nenhum ``onClicked``.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import ui_control_inventory as matrix  # noqa: E402

pytestmark = pytest.mark.skipif(
    shutil.which("qml6") is None and shutil.which("qml") is None,
    reason="qml6 não está instalado neste host",
)


@pytest.fixture(scope="module")
def inventory() -> dict:
    return matrix.build_inventory()


def _describe(control: dict) -> str:
    label = control.get("label") or control.get("accessibleName") or "(sem rótulo)"
    return f"{control['surface']} → {label!r} ({control['kind']})"


def test_no_enabled_control_is_a_silent_no_op(inventory: dict) -> None:
    """Um controle habilitado que não produz efeito nem erro é uma promessa falsa."""
    offenders = [
        _describe(control)
        for control in inventory["failures"]
        if control["verdict"] == "silent-no-op"
    ]
    assert offenders == [], "controles habilitados sem efeito observável:\n" + "\n".join(offenders)


def test_no_enabled_control_is_left_without_a_route(inventory: dict) -> None:
    offenders = [
        _describe(control) for control in inventory["failures"] if control["verdict"] == "unrouted"
    ]
    assert offenders == [], "controles habilitados que o shell não despacha:\n" + "\n".join(
        offenders
    )


def test_every_disabled_control_explains_itself(inventory: dict) -> None:
    offenders = [
        _describe(control)
        for control in inventory["failures"]
        if control["verdict"] == "blocked-silent"
    ]
    assert offenders == [], "controles desabilitados sem motivo:\n" + "\n".join(offenders)


def test_the_matrix_runs_every_declared_scenario(inventory: dict) -> None:
    """Um cenário só conta quando roda; fixture no disco não é evidência."""
    declared = sorted(path.stem for path in matrix.scenario_paths())
    assert declared, "nenhum cenário declarado em tests/fixtures/ui-scenarios"
    assert sorted(inventory["scenarios"]) == declared


def test_scenarios_reach_more_controls_than_offline_alone(inventory: dict) -> None:
    """O motivo de existirem cenários: sem eles a maioria fica invisível.

    Offline sozinho acionava 73 de 288. Se um refactor desligar o carregamento
    da fixture, este gate percebe antes de a matriz voltar a medir quase nada.
    """
    probed = sum(
        count for verdict, count in inventory["verdictCounts"].items() if verdict != "not-probed"
    )
    assert probed > 150, f"apenas {probed} controles exercitados; os cenários não carregaram"


def test_the_probe_reached_every_declared_surface(inventory: dict) -> None:
    """Guarda contra matriz vazia passando por engano.

    Se a sonda parar de andar pelas seções, os testes acima ficariam verdes sem
    ter acionado nada — foi assim que a regressão de ícones da a37 atravessou os
    gates.
    """
    assert inventory["controlCount"] > 100, "inventário pequeno demais para ser a central"
    assert inventory["surfaceCount"] >= 12
    assert inventory["verdictCounts"].get("routed", 0) > 0
    assert inventory["verdictCounts"].get("handled-locally", 0) > 0


def test_probe_context_is_recorded(inventory: dict) -> None:
    """Sem contexto, dois inventários de temas diferentes são incomparáveis."""
    context = inventory["context"]
    assert context.get("viewport")
    assert context.get("themeId")
    assert context.get("dataOrigin") in {"bridge-live", "fallback-qml"}


def test_every_control_has_a_stable_identity(inventory: dict) -> None:
    """Casar o mesmo botão entre cenários exige identidade, não rótulo.

    Nenhum dos 288 controles tem `objectName`, e coordenada visual muda com
    viewport, escala e tema. A identidade é estrutural: superfície, tipo QML,
    objectName quando existe, rótulo ou nome acessível, e a cadeia de índices
    até a raiz da superfície.
    """
    identities = [control["controlId"] for control in inventory["controls"]]
    assert all(identities), "controle sem identidade calculada"

    duplicates = sorted({item for item in identities if identities.count(item) > 1})
    assert duplicates == [], "identidades colidindo entre controles:\n" + "\n".join(duplicates)


def test_identity_does_not_carry_engine_revision_numbers(inventory: dict) -> None:
    """`EditorialButton_QML_148` traz um contador do engine que muda entre execuções.

    Deixá-lo na identidade faria a matriz de dois cenários nunca casar.
    """
    leaked = sorted(
        {control["type"] for control in inventory["controls"] if "_QML_" in control["type"]}
    )
    assert leaked == [], "tipo com revisão do engine na identidade: " + ", ".join(leaked)


def _actionable(inventory: dict) -> list[dict]:
    """Controles que se apresentam ao usuário como acionáveis agora.

    Invisível não é promessa, e ToolButton sem rótulo nem nome acessível é
    ícone decorativo — o produto usa esse padrão de propósito.
    """
    return [
        control
        for control in inventory["controls"]
        if control.get("visible")
        and control.get("enabled")
        and (control.get("label") or control.get("accessibleName"))
    ]


def test_every_actionable_control_announces_a_name(inventory: dict) -> None:
    """Sem `Accessible.name`, um leitor de tela anuncia o botão como nada.

    Rótulo visível não substitui: ele não é exposto à árvore de acessibilidade
    quando o controle desenha o próprio contentItem, que é o caso do shell.
    """
    offenders = [
        f"{control['surface']} → {control['label']!r} ({control['type']})"
        for control in _actionable(inventory)
        if not control.get("accessibleName")
    ]
    assert offenders == [], "controles acionáveis sem Accessible.name:\n" + "\n".join(offenders)


def test_every_actionable_target_is_at_least_48px(inventory: dict) -> None:
    """48x48 é o alvo mínimo do produto — o Deck é operado com o polegar."""
    offenders = [
        f"{control['surface']} → {control['label'] or control['accessibleName']!r} "
        f"({control['width']}x{control['height']})"
        for control in _actionable(inventory)
        if control["width"] < 48 or control["height"] < 48
    ]
    assert offenders == [], "alvos acionáveis abaixo de 48x48:\n" + "\n".join(offenders)


def test_decorative_icons_are_not_announced_as_actionable(inventory: dict) -> None:
    """O inverso do gate acima: ícone decorativo não pode virar botão anunciado.

    Um `ToolButton` desabilitado, sem rótulo e sem nome acessível é decoração
    legítima. Se ganhar `Accessible.name` sem ficar acionável, passa a mentir
    para o leitor de tela.
    """
    offenders = [
        f"{control['surface']} → {control['accessibleName']!r} ({control['type']})"
        for control in inventory["controls"]
        if control.get("visible")
        and not control.get("enabled")
        and control.get("accessibleName")
        and not control.get("label")
        and not control.get("accessibleDescription")
    ]
    assert offenders == [], (
        "controles apagados anunciados por nome mas sem dizer o porquê:\n" + "\n".join(offenders)
    )
