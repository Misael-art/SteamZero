# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Painel do catálogo de temas pela rota real do usuário, via QuickTest Qt 6.

O harness clica de verdade e observa a CHAMADA que sai do painel. Conferir que
um botão existe provaria que alguém o desenhou, não que ele age — e controle
declarado que não age é o defeito que este projeto vem removendo da UI.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _qt6_runner() -> str | None:
    for candidate in (
        Path("/usr/lib/qt6/bin/qmltestrunner"),
        Path("/usr/lib64/qt6/bin/qmltestrunner"),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which("qmltestrunner6")


RUNNER = _qt6_runner()
HARNESS = ROOT / "tests" / "qml" / "check_theme_catalog_panel.qml"
PANEL = ROOT / "src" / "steamzero" / "ui" / "qml" / "ThemeCatalogPanel.qml"


def test_the_harness_clicks_instead_of_calling_the_handler() -> None:
    """Guarda de código: roda mesmo sem `qmltestrunner`.

    Existe para impedir que um vermelho seja "consertado" trocando o clique real
    por uma chamada direta ao handler — que provaria a função, não a jornada.
    """
    assert HARNESS.is_file(), f"{HARNESS} não existe"
    source = HARNESS.read_text(encoding="utf-8")

    assert "mouseClick(" in source, "o harness não clica de verdade"
    for shortcut in ("panel.installTheme(", "panel.uninstallTheme(", "panel.applyGarbage("):
        assert shortcut not in source, (
            f"o harness chama {shortcut} diretamente; isso prova a função, não o botão"
        )
    assert "findChild" in source, (
        "Dialog é um Popup e não aparece em `children`; uma busca por `children` "
        "deixaria o modal aberto bloqueando os cliques seguintes"
    )


def test_the_panel_never_reaches_the_network_or_the_filesystem_directly() -> None:
    """A tela consome rotas do contrato; política mora no backend.

    Uma tela que monta URL ou caminho por conta própria contorna a curadoria do
    catálogo e a fronteira de confiança da AGENTS §10.
    """
    source = PANEL.read_text(encoding="utf-8")

    assert "requestAction(" in source
    for forbidden in ("XMLHttpRequest", "http://", "https://", "Qt.openUrlExternally"):
        assert forbidden not in source, f"o painel alcança {forbidden!r} por conta própria"


def test_destructive_actions_are_behind_a_dialog_in_the_panel() -> None:
    """Remover tema e apagar blob não podem disparar direto do clique."""
    source = PANEL.read_text(encoding="utf-8")

    assert "uninstallDialog.ask(" in source, "remover dispara sem confirmação"
    assert "gcDialog.open()" in source, "recuperar espaço dispara sem confirmação"
    # A prévia é o padrão do GC; `apply` só sai do diálogo.
    assert '"apply": true' in source


# `visual` ROTEIA, não dispensa: a prova exige o runtime QML e pertence ao job
# `qml-visual-linux`, que reprova quando o Qt falta.
@pytest.mark.visual
def test_catalog_panel_buttons_call_the_declared_routes() -> None:
    assert RUNNER is not None, "qmltestrunner Qt 6 é obrigatório para esta prova"
    env = os.environ.copy()
    env.update({"QT_QPA_PLATFORM": "offscreen"})
    completed = subprocess.run(
        [RUNNER, "-input", str(HARNESS)],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, output
    assert "Totals:" in output and ", 0 failed" in output, output
