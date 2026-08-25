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


def _diagnose(control: dict) -> str:
    return (
        f"{_describe(control)} id={control.get('objectName')!r} "
        f"path={control.get('path')!r} visible={control.get('visible')} "
        f"enabled={control.get('enabled')} note={control.get('probeNote')!r}"
    )


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


@pytest.mark.parametrize("surface", ["handheld-drawer", "task-drawer"])
def test_drawer_controls_are_exercised_while_the_drawer_is_open(
    inventory: dict, surface: str
) -> None:
    """Contar controles de um Drawer fechado não é sondar sua jornada.

    O inventário anterior publicava todos os dez controles do drawer portátil
    e os dois do drawer de tarefas como ``not-probed`` porque percorria os
    Popups fechados. A sonda precisa abrir a superfície, esperar sua animação e
    só então ativar cada controle.
    """
    verdicts = inventory["bySurface"].get(surface, {})
    unprobed = [
        _diagnose(control)
        for control in inventory["controls"]
        if control.get("surface") == surface and control.get("verdict") == "not-probed"
    ]
    assert sum(verdicts.values()) > 0, f"{surface} não entrou no inventário"
    assert verdicts.get("not-probed", 0) == 0, (
        f"{surface} ainda tem controles não exercitados: {verdicts}\n" + "\n".join(unprobed)
    )


def _scenario_run(verdict: str) -> dict:
    return {
        "context": {"scenario": verdict},
        "controls": [{"controlId": "id:shared", "verdict": verdict}],
    }


def test_a_probe_in_one_scenario_outweighs_invisibility_in_another() -> None:
    """Um controle oculto em `ready` continua coberto se foi exercitado em `error`."""
    controls = matrix.merge_scenarios(
        [_scenario_run("handled-locally"), _scenario_run("not-probed")]
    )
    assert controls[0]["verdict"] == "handled-locally"


@pytest.mark.parametrize("failure", matrix.FAILING_VERDICTS)
def test_a_real_failure_still_outweighs_a_successful_scenario(failure: str) -> None:
    controls = matrix.merge_scenarios(
        [_scenario_run("routed"), _scenario_run(failure), _scenario_run("not-probed")]
    )
    assert controls[0]["verdict"] == failure


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


def test_no_control_acts_without_announcing_itself(inventory: dict) -> None:
    """Enfeite é provado, não presumido.

    A sonda classificava como "ícone decorativo" todo item sem rótulo, sem nome
    acessível e desabilitado. Isso é hipótese sobre a FORMA, e classificar ação
    por forma já produziu falso positivo neste projeto. Agora o candidato é
    ATIVADO: se nada muda, nada é despachado e nenhum contrato é tentado, o
    veredito é ``decorative`` — inércia medida. Se qualquer coisa acontece, o
    veredito é ``unnamed-actionable``, e isso reprova: o controle produz efeito
    e não tem rótulo nem nome acessível, então existe para quem enxerga e não
    existe para quem usa leitor de tela ou controle.
    """
    offenders = [
        _diagnose(control)
        for control in inventory["failures"]
        if control["verdict"] == "unnamed-actionable"
    ]
    assert offenders == [], "controles que agem sem se anunciar:\n" + "\n".join(offenders)


def test_decoration_is_measured_and_not_assumed(inventory: dict) -> None:
    """Guarda contra a volta da classificação por forma.

    Se alguém reintroduzir o atalho — rotular de enfeite sem ativar —, o
    veredito ``decorative`` sumiria do inventário e os mesmos itens voltariam a
    inflar ``not-probed`` sem que ninguém tivesse medido nada.
    """
    counts = inventory["verdictCounts"]
    assert counts.get("decorative", 0) > 0, (
        "nenhum controle foi provado inerte; a sonda voltou a presumir pela forma?"
    )
    for control in inventory["controls"]:
        if control.get("verdict") != "decorative":
            continue
        assert not control.get("label"), f"enfeite com rótulo: {_diagnose(control)}"
        assert not control.get("accessibleName"), (
            f"enfeite com nome acessível: {_diagnose(control)}"
        )
