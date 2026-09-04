# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Prova de bootstrap de foco do Launcher: ao abrir, a primeira tecla navega.

Os harnesses irmãos instanciam `LauncherHome`/`LauncherShell` direto e chamam
`forceActiveFocus()` antes de pressionar. Isso prova que a tecla ativa o cartão
FOCADO, mas entrega o foco de mão beijada — que é justamente o que a produção
nunca faz. A cena real é `LauncherMain`, e lá o shell nasce dentro de um
`Loader`.

Medido no host em 2026-09-04, release 2.0.0rc1-a44f52964b3e, com `ydotoold`
ativo e a janela ativa conferida por `kdotool` antes e depois de cada injeção:
setas, Tab e Return moveram ZERO pixel; um clique de mouse e então a mesma seta
moveram o anel de foco em 30.201 pixels. O anel ciano já era desenhado ao abrir,
então a tela parecia focada sem estar.

Causa: um `Loader` não repassa foco ao item carregado a menos que ele próprio
tenha `focus: true`. No Game Mode do Deck não existe mouse, então o Launcher
nascia inoperável por teclado e controle.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests" / "qml" / "launcher" / "check_launcher_focus_bootstrap.qml"


def _qt6_runner() -> str | None:
    for candidate in (
        Path("/usr/lib/qt6/bin/qmltestrunner"),
        Path("/usr/lib64/qt6/bin/qmltestrunner"),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which("qmltestrunner6")


RUNNER = _qt6_runner()


def test_the_harness_never_hands_focus_to_a_control() -> None:
    """Guarda de código: roda mesmo sem `qmltestrunner`.

    Existe para impedir que um vermelho seja "consertado" chamando
    `forceActiveFocus()` — que é exatamente o ponto cego que deixou o defeito
    passar por todos os outros harnesses do Launcher.
    """
    assert HARNESS.is_file(), f"{HARNESS} não existe"
    source = HARNESS.read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("//"))

    assert "forceActiveFocus" not in code, (
        "entregar foco a um controle pula justamente o trecho que estava "
        "quebrado; o bootstrap precisa acontecer sozinho"
    )
    assert "mouseClick(" not in code and "mousePress(" not in code, (
        "um clique destrava o foco e mascara o defeito; no Game Mode do Deck não existe mouse"
    )
    assert "LauncherMain" in code, (
        "o defeito mora no `Loader` da cena raiz; instanciar apenas o shell ou "
        "a home não exercita o caminho quebrado"
    )
    assert "keyClick(Qt.Key_Right)" in code, "o harness não envia tecla real"


@pytest.mark.skipif(RUNNER is None, reason="qmltestrunner do Qt6 não está disponível")
def test_the_first_key_after_opening_navigates_without_a_pointer() -> None:
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
        "o Launcher abriu sem foco de teclado; só um clique de mouse o "
        f"destravaria:\n{completed.stdout}\n{completed.stderr}"
    )
