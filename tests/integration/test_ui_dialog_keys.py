# SPDX-License-Identifier: GPL-3.0-or-later
"""Escape e Tab reais nos modais — e o registro de que ainda não foi provado.

A passagem de 2026-08-14 chamou `dialog.close()` de "Escape". Não é. `close()`
é uma chamada programática que ignora `closePolicy` inteiro: um modal com
`Popup.NoAutoClose` fecha por `close()` e **não deve** fechar por Escape. O
harness antigo daria o mesmo verde nos dois casos, então ele nunca provou o
que dizia provar.

`tests/qml/check_dialog_keys.qml` faz a prova certa via `QtTest.keyClick`, que
entrega a tecla ao item com foco pelo mesmo caminho de um teclado real. O que
falta é o executor: neste host `qmltestrunner` termina com exit 1 e **zero
bytes** de saída ao carregar um harness que instancia a janela do produto.

Enquanto isso durar, o estado honesto é "Escape não provado" — não um verde
comprado com `close()`. Este teste tenta rodar o harness a cada execução: no
dia em que o ambiente suportar, ele passa a valer sozinho.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


#: O `qmltestrunner` do PATH neste host pertence ao qt5-declarative 5.15 e
#: rejeita os imports versionless do produto, que e Qt 6.11. O binario correto
#: existe, so nao esta no PATH — procura-lo pelo prefixo do Qt6 e o que separa
#: "o ambiente nao suporta" de "eu chamei o binario errado".
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

#: Diagnóstico citável no relatório e no item de status.
DIAG_NO_KEY_INJECTION = "QML-KEY-INJECTION-001"


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


def test_the_real_key_harness_exists_and_is_not_a_programmatic_close() -> None:
    """O harness precisa existir e usar `keyClick`, não `close()`, para Escape.

    Roda sempre, inclusive sem `qmltestrunner`: é a guarda contra alguém
    "consertar" o bloqueio trocando o evento real por uma chamada de volta.
    """
    assert HARNESS.is_file(), f"{HARNESS} não existe"
    source = HARNESS.read_text(encoding="utf-8")
    assert "keyClick(Qt.Key_Escape)" in source, "o harness não envia Escape real"
    assert "keyClick(Qt.Key_Tab)" in source, "o harness não exercita o focus trap"
    assert "keyClick(Qt.Key_Backtab)" in source, "o harness não exercita Shift+Tab"
    assert "Popup.NoAutoClose" in source or "recoveryDialogControl" in source, (
        "o harness não distingue o modal que NÃO deve fechar por Escape"
    )


@pytest.mark.skipif(RUNNER is None, reason="qmltestrunner ausente neste host")
def test_real_escape_and_focus_trap() -> None:
    """Prova de Escape/Tab reais. Pula com motivo medido enquanto for bloqueada."""
    completed = _run()
    output = (completed.stdout or "") + (completed.stderr or "")

    if not output.strip() or "invalid root object" in output:
        pytest.skip(
            f"{DIAG_NO_KEY_INJECTION}: o QuickTest do Qt6 carrega o harness numa "
            "QQuickView, que exige raiz do tipo Item. `Main` é uma Window e por "
            "isso não pode ser o objeto raiz "
            f"(exit {completed.returncode}). O `qmltestrunner` do PATH é pior: "
            "pertence ao qt5-declarative 5.15 e rejeita os imports versionless "
            "do produto. Escape real permanece NÃO PROVADO — o fechamento "
            "programático de test_ui_dialog_journeys.py NÃO substitui esta prova. "
            "Saída: um harness com raiz Item que hospede os diálogos, ou teste "
            "de teclado pelo lado C++."
        )

    assert completed.returncode == 0, f"harness de teclas reprovou:\n{output[-3000:]}"
    assert "FAIL" not in output, f"asserção de tecla real reprovou:\n{output[-3000:]}"
