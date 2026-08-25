# SPDX-License-Identifier: GPL-3.0-or-later
"""Escape e Tab reais nos modais, executados pelo QuickTest Qt 6.

`dialog.close()` continua sendo apenas limpeza controlada do recovery — nunca
prova Escape. A prova funcional usa `QtTest.keyClick` depois de ativar a janela,
abrir o Popup e observar foco interno.
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
    found = shutil.which("qmltestrunner6")
    return found


RUNNER = _qt6_runner()
HARNESS = ROOT / "tests" / "qml" / "check_dialog_keys.qml"


def _run() -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "QT_FORCE_STDERR_LOGGING": "1",
            "QT_LOGGING_RULES": "",
        }
    )
    return subprocess.run(
        [str(RUNNER), "-input", str(HARNESS)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )


def test_the_real_key_harness_has_a_qquickview_root_and_real_keys() -> None:
    """O harness precisa existir e usar `keyClick`, não `close()`, para Escape.

    Roda sempre, inclusive sem `qmltestrunner`: é a guarda contra alguém
    "consertar" o bloqueio trocando o evento real por uma chamada de volta.
    """
    assert HARNESS.is_file(), f"{HARNESS} não existe"
    source = HARNESS.read_text(encoding="utf-8")
    assert "Item {" in source, "QuickTest precisa de raiz Item para hospedar Main"
    assert "Main {" in source, "o harness precisa carregar a janela real do produto"
    assert "keyClick(Qt.Key_Escape)" in source, "o harness não envia Escape real"
    assert "keyClick(Qt.Key_Tab)" in source, "o harness não exercita o focus trap"
    assert "keyClick(Qt.Key_Backtab)" in source, "o harness não exercita Shift+Tab"
    assert "Popup.NoAutoClose" in source or "recoveryDialogControl" in source, (
        "o harness não distingue o modal que NÃO deve fechar por Escape"
    )
    assert "wait(" not in source, "a jornada deve esperar eventos, não atrasos arbitrários"


# `visual` ROTEIA, não dispensa: esta prova exige o runtime QML e pertence ao
# job `qml-visual-linux`, que reprova quando o Qt falta. Deixá-la no job de
# testes e cobertura, que não provisiona Qt, faria a suíte reprovar por ambiente
# em vez de por código. A guarda de código acima continua sem marcador, porque
# ela existe justamente para rodar onde o runtime NÃO está.
@pytest.mark.visual
def test_real_escape_and_focus_trap() -> None:
    """Prova de Escape/Tab reais pelo executor Qt 6 disponível no ambiente."""
    assert RUNNER is not None, "qmltestrunner Qt 6 é obrigatório para esta prova"
    completed = _run()
    output = (completed.stdout or "") + (completed.stderr or "")
    assert completed.returncode == 0, f"harness de teclas reprovou:\n{output[-3000:]}"
    assert "FAIL" not in output, f"asserção de tecla real reprovou:\n{output[-3000:]}"
