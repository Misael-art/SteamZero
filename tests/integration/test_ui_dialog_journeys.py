# SPDX-License-Identifier: GPL-3.0-or-later
"""Jornada completa de cada diálogo, não apenas `visible === true`.

A sonda de controles percorre a árvore visual das seções. Diálogos não estão
nela enquanto fechados, então nada do que acontece dentro de um modal era
verificado: nem se o foco entra, nem se cancelar deixa plano sujo, nem se
fechar devolve o foco a quem abriu.

Cada asserção aqui nomeia o evento observado — abertura, fechamento, retorno de
foco — e a espera é por condição com orçamento de frames, nunca por `sleep`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
QML = shutil.which("qml6") or shutil.which("qml")

pytestmark = pytest.mark.skipif(QML is None, reason="qml6 não está instalado neste host")

#: Diálogos que carregam um plano. Fechar sem aplicar precisa deixar o estado
#: limpo — um plano remanescente é uma confirmação pendente sem dono.
PLAN_DIALOGS = {
    "dialog.emulator-plan",
    "dialog.component-plan",
    "dialog.desktop-safe-reset",
    "dialog.conflict",
}


def _run_probe() -> list[dict[str, Any]]:
    env = os.environ.copy()
    env.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "QT_FORCE_STDERR_LOGGING": "1",
            "QT_LOGGING_RULES": "",
        }
    )
    completed = subprocess.run(
        [str(QML), str(ROOT / "tools" / "ui_dialog_probe.qml")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    output = completed.stdout + "\n" + (completed.stderr or "")
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        index = line.find("DIALOG ")
        if index < 0 or line[index:].startswith("DIALOG-DONE"):
            continue
        try:
            rows.append(json.loads(line[index + len("DIALOG ") :]))
        except json.JSONDecodeError:
            continue
    if not rows:
        raise AssertionError(
            f"a sonda de diálogos não produziu jornada (returncode={completed.returncode});"
            f" stderr:\n{(completed.stderr or '')[-2000:]}"
        )
    return rows


@pytest.fixture(scope="module")
def journeys() -> list[dict[str, Any]]:
    return _run_probe()


def test_every_declared_dialog_is_reachable(journeys: list[dict[str, Any]]) -> None:
    """Sem alias, o diálogo não pode ser auditado — e some da matriz calado."""
    unreachable = [row["id"] for row in journeys if row["outcome"] == "sem-alias"]
    assert unreachable == [], "diálogos que o shell não expõe: " + ", ".join(unreachable)

    failed = [row["id"] for row in journeys if row["outcome"] == "nao-abriu"]
    assert failed == [], "diálogos que não abriram: " + ", ".join(failed)
    assert len(journeys) >= 6


def test_opening_a_dialog_moves_focus_into_it(journeys: list[dict[str, Any]]) -> None:
    """Evento observado: `dialog-aberto`.

    Um modal que abre sem levar o foco deixa quem navega por teclado ou controle
    do lado de fora: o Tab continua percorrendo a tela atrás do modal, e não há
    focus trap nenhum porque o foco nunca entrou.
    """
    offenders = [
        f"{row['id']} ({row['focusables']} focáveis dentro)"
        for row in journeys
        if row["outcome"] == "sondado" and not row["focusEnteredDialog"]
    ]
    assert offenders == [], "modais que abrem sem receber o foco:\n" + "\n".join(offenders)


def test_every_dialog_has_something_to_focus(journeys: list[dict[str, Any]]) -> None:
    offenders = [
        row["id"]
        for row in journeys
        if row["outcome"] == "sondado" and not row["hasInitialFocusTarget"]
    ]
    assert offenders == [], "modais sem alvo de foco inicial: " + ", ".join(offenders)


def test_closing_a_dialog_returns_focus_to_the_invoker(
    journeys: list[dict[str, Any]],
) -> None:
    """Evento observado: `foco-restaurado`, esperado por condição após o fechamento."""
    offenders = [
        row["id"]
        for row in journeys
        if row["outcome"] == "sondado" and not row["focusReturnedToInvoker"]
    ]
    assert offenders == [], "modais que não devolvem o foco: " + ", ".join(offenders)


def test_cancelling_a_dialog_leaves_no_pending_plan(
    journeys: list[dict[str, Any]],
) -> None:
    """Evento observado: `dialog-fechado`.

    O botão "Cancelar" limpa o plano, mas fechar por Escape — o caminho do
    teclado e do botão B do controle — não limpava. O plano ficava pendurado
    como uma confirmação sem dono, pronta para ser reaproveitada pela próxima
    abertura.
    """
    offenders = [
        row["id"]
        for row in journeys
        if row["id"] in PLAN_DIALOGS and row.get("planDirtyAfterCancel")
    ]
    assert offenders == [], "planos que sobrevivem ao cancelamento por Escape: " + ", ".join(
        offenders
    )


def test_each_journey_names_the_events_it_observed(
    journeys: list[dict[str, Any]],
) -> None:
    """Guarda contra jornada que passa sem ter esperado por nada."""
    for row in journeys:
        if row["outcome"] != "sondado":
            continue
        assert row["events"] == ["dialog-aberto", "dialog-fechado", "foco-restaurado"]
