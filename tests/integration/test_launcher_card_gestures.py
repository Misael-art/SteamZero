# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Prova de gesto do P0 do Launcher: tecla e clique reais ativam o cartão.

O harness irmão (`check_launcher_activation.qml`) chama `card.activate()` e
`home.activateCurrent()` direto. Isso prova a função, não o caminho — e o
caminho era o que estava quebrado: `LauncherShell.openGame()` já existia na
release auditada e mesmo assim Return e clique não abriam nada, porque nenhum
handler ligava o gesto à função.

Medido em 2026-09-02: removendo os `Keys.onPressed` do cartão e da home,
`check_launcher_activation.qml` continuava passando. O harness deste módulo
reprova nos quatro cenários.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests" / "qml" / "launcher" / "check_launcher_gestures.qml"


def _qt6_runner() -> str | None:
    for candidate in (
        Path("/usr/lib/qt6/bin/qmltestrunner"),
        Path("/usr/lib64/qt6/bin/qmltestrunner"),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which("qmltestrunner6")


RUNNER = _qt6_runner()


def test_the_harness_presses_keys_instead_of_calling_functions() -> None:
    """Guarda de código: roda mesmo sem `qmltestrunner`.

    Existe para impedir que um vermelho seja "consertado" trocando a tecla real
    por uma chamada a `activate()` — que é precisamente o ponto cego que deixou
    o P0 passar sem rede.
    """
    assert HARNESS.is_file(), f"{HARNESS} não existe"
    source = HARNESS.read_text(encoding="utf-8")
    assert "keyClick(Qt.Key_Return)" in source, "o harness não envia Return real"
    assert "keyClick(Qt.Key_Space)" in source, "o harness não envia Space real"
    assert "mouseClick(" in source, "o harness não envia clique real"
    # Só o código conta: o cabeçalho explica o ponto cego citando as próprias
    # chamadas, e casar com o comentário reprovaria a explicação.
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("//"))
    assert ".activate()" not in code and "activateCurrent()" not in code, (
        "chamar a função de ativação pula justamente o trecho que estava "
        "quebrado; o gesto precisa ser o único gatilho"
    )


@pytest.mark.skipif(RUNNER is None, reason="qmltestrunner do Qt6 não está disponível")
def test_real_key_and_pointer_gestures_activate_the_focused_card() -> None:
    environment = dict(os.environ)
    environment["QT_QPA_PLATFORM"] = "offscreen"
    completed = subprocess.run(
        [str(RUNNER), "-input", str(HARNESS)],
        capture_output=True,
        text=True,
        timeout=180,
        env=environment,
        cwd=str(ROOT),
    )
    assert completed.returncode == 0, (
        f"gesto real não chegou à ativação do cartão:\n{completed.stdout}\n{completed.stderr}"
    )
