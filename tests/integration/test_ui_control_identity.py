# SPDX-License-Identifier: GPL-3.0-or-later
"""A identidade de controle só é estável se sobreviver a estas provas.

A matriz funde cenários pela identidade do controle. Se a identidade mudar
entre execuções, o mesmo botão vira dois controles e a cobertura publicada é
ficção — inflada por duplicatas e cega para o que nunca casou.

A identidade atual é ``superfície | tipo | objectName | rótulo | caminho de
índices``. Duas partes dela são frágeis por construção: o rótulo muda com o
estado, e o caminho de índices muda quando um irmão entra ou sai da árvore.
Estes testes existem para dizer exatamente onde ela aguenta e onde não aguenta,
em vez de chamá-la de estável por otimismo.
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

#: Um par barato de cenários: um vazio e um cheio. Rodar os catorze em cada
#: teste de estabilidade custaria minutos sem provar mais nada.
PAIR = ["empty", "ready-small-library"]


def _ids(inventory: dict) -> set[str]:
    return {control["controlId"] for control in inventory["controls"]}


@pytest.fixture(scope="module")
def first_run() -> dict:
    return matrix.build_inventory(only=PAIR)


def test_running_the_same_scenarios_twice_yields_the_same_identities(
    first_run: dict,
) -> None:
    """Não determinismo aqui invalidaria toda comparação entre execuções."""
    second = matrix.build_inventory(only=PAIR)
    assert _ids(second) == _ids(first_run)
    assert second["controlCount"] == first_run["controlCount"]


def test_reversing_scenario_order_changes_nothing(first_run: dict) -> None:
    reversed_run = matrix.build_inventory(only=list(reversed(PAIR)))
    assert _ids(reversed_run) == _ids(first_run)
    assert reversed_run["controlCount"] == first_run["controlCount"]


def test_duplicating_a_scenario_does_not_inflate_the_count(first_run: dict) -> None:
    """Fundir o mesmo cenário duas vezes não pode criar controles."""
    duplicated = matrix.build_inventory(only=[*PAIR, PAIR[0]])
    assert duplicated["controlCount"] == first_run["controlCount"]
    assert _ids(duplicated) == _ids(first_run)


def test_merging_keeps_every_scenario_where_the_control_appeared(
    first_run: dict,
) -> None:
    """Perder a lista de cenários esconderia em qual estado o controle falhou."""
    multi = [
        control for control in first_run["controls"] if len(set(control.get("scenarios", []))) > 1
    ]
    assert multi, "nenhum controle apareceu em mais de um cenário; a fusão não fundiu nada"
    for control in multi:
        assert set(control["scenarios"]) <= set(PAIR)


def test_distinct_delegates_do_not_collide(first_run: dict) -> None:
    """Cards irmãos têm o mesmo tipo e às vezes o mesmo rótulo."""
    assert first_run["identityCollisionCount"] == 0


def test_the_matrix_publishes_how_much_rests_on_the_fallback(first_run: dict) -> None:
    """Sem esta contagem, ninguém sabe qual fatia da matriz é frágil."""
    for key in (
        "explicitIdentityCount",
        "fallbackIdentityCount",
        "identityCollisionCount",
        "controlsSeenInMultipleScenarios",
        "controlsSeenInOneScenario",
        "notProbedCount",
    ):
        assert key in first_run, f"a matriz não publica {key}"
    total = first_run["explicitIdentityCount"] + first_run["fallbackIdentityCount"]
    assert total == first_run["controlCount"]


def test_a_global_control_keeps_its_identity_across_states(first_run: dict) -> None:
    """A sidebar é a mesma em qualquer estado; se o ID muda, a fusão é fictícia.

    Este é o teste que separa "estável" de "determinístico": rodar duas vezes o
    mesmo cenário dando o mesmo resultado é fácil; atravessar estados diferentes
    é o que a matriz realmente precisa.
    """
    across = matrix.build_inventory(only=["empty", "ready-small-library", "stale-profile"])
    sidebar = [c for c in across["controls"] if c["surface"] == "sidebar"]
    assert sidebar, "a sidebar sumiu do inventário"

    shared = [c for c in sidebar if len(set(c.get("scenarios", []))) == 3]
    assert shared, (
        "nenhum controle da sidebar foi reconhecido como o mesmo nos três estados; "
        "a identidade não atravessa cenários"
    )


#: Dois cenários em que o MESMO card de plataforma muda de rótulo: com o
#: emulador instalado o CTA abre a plataforma; sem ele, o CTA instala.
LABEL_SHIFT = ["emulation-ready", "emulation-no-emulator"]


@pytest.fixture(scope="module")
def label_shift() -> dict:
    return matrix.build_inventory(only=LABEL_SHIFT)


def test_explicit_identity_never_carries_label_or_position(label_shift: dict) -> None:
    """Identidade explícita é só o `objectName`, e é isso que a torna estável.

    Se o rótulo ou o caminho de índices vazassem para a chave, ela herdaria a
    fragilidade do fallback sem nenhum aviso.
    """
    explicit = [c for c in label_shift["controls"] if c.get("objectName")]
    assert explicit, "nenhum controle declara identidade explícita"
    for control in explicit:
        assert control["controlId"] == "id:" + control["objectName"]
        assert "/" not in control["controlId"], "caminho de índices vazou para a identidade"


def test_a_label_change_does_not_create_a_second_control(label_shift: dict) -> None:
    """Prova com dado real, não com experimento sintético.

    O CTA do card de plataforma diz "Instalar <emulador>" quando falta emulador
    e "Abrir plataforma" quando não falta. É o mesmo botão: se a identidade o
    partisse em dois, a matriz contaria cobertura em dobro e nunca casaria o
    veredito de um estado com o do outro.
    """
    primaries = [
        control
        for control in label_shift["controls"]
        if str(control.get("objectName", "")).endswith(".primary")
    ]
    assert primaries, "nenhum CTA primário de plataforma no inventário"

    both = [c for c in primaries if len(set(c.get("scenarios", []))) == 2]
    assert both, "nenhum CTA foi reconhecido como o mesmo nos dois cenários"

    labels = {c["label"] for c in both if c.get("label")}
    assert len(labels) >= 1


#: Par em que a quantidade de controles muda de verdade: a Home vazia contra a
#: emulação carregada. É o que dá sentido a falar de irmãos entrando e saindo.
SIBLING_SHIFT = ["empty", "emulation-ready"]


@pytest.fixture(scope="module")
def sibling_shift() -> dict:
    return matrix.build_inventory(only=SIBLING_SHIFT)


def test_explicit_identity_survives_siblings_appearing_and_disappearing(
    sibling_shift: dict,
) -> None:
    """O caminho de índices muda quando irmãos entram ou saem; o `objectName` não.

    Entre os dois cenários a quantidade de controles visíveis muda de verdade —
    é o que dá sentido à comparação. Os controles com identidade explícita
    atravessam essa mudança; os do fallback são justamente os que não têm essa
    garantia, e por isso a matriz publica quantos são.
    """
    per_scenario = {
        scenario: sum(1 for c in sibling_shift["controls"] if scenario in c.get("scenarios", []))
        for scenario in SIBLING_SHIFT
    }
    assert len(set(per_scenario.values())) > 1, (
        f"os cenários têm a mesma contagem {per_scenario}; não provam nada sobre irmãos"
    )

    explicit_in_both = [
        c
        for c in sibling_shift["controls"]
        if c.get("objectName") and len(set(c.get("scenarios", []))) == 2
    ]
    assert explicit_in_both, "nenhuma identidade explícita atravessou os dois cenários"


def test_the_fallback_share_is_published_and_not_pretended_stable(
    label_shift: dict,
) -> None:
    """A matriz precisa dizer de quanto ela não pode garantir estabilidade."""
    explicit = label_shift["explicitIdentityCount"]
    fallback = label_shift["fallbackIdentityCount"]
    assert explicit > 0, "nenhuma identidade explícita: a §4 não foi aplicada"
    assert fallback > 0, (
        "zero fallback significaria identidade explícita em todo controle; "
        "se isso acontecer, remova este teste e afirme a estabilidade geral"
    )
    for control in label_shift["controls"]:
        if not control.get("objectName"):
            assert control["controlId"].startswith("fallback|")
