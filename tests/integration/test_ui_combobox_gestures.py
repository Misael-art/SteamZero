# SPDX-License-Identifier: GPL-3.0-or-later
"""ComboBox pela rota real do usuário, executado pelo QuickTest Qt 6.

A sonda de controles (`tools/ui_control_probe.qml`) só sabe clicar, e clicar num
ComboBox não seleciona nada — por isso `isActivatable` o exclui e todos os
ComboBox da central ficavam `not-probed`. Emitir `activated()` na mão resolveria
o número e não a dúvida: seria a mesma troca que este projeto já rejeitou uma
vez, quando `close()` fazia as vezes de Escape.

Aqui a tecla é real, entregue pelo QuickTest ao controle com foco, e o harness
fecha o denominador: cada ComboBox visível ou é exercitado, ou está bloqueado e
diz por quê.
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
HARNESS = ROOT / "tests" / "qml" / "check_combobox_gestures.qml"


def test_the_harness_uses_real_keys_and_closes_the_denominator() -> None:
    """Guarda de código: roda mesmo sem `qmltestrunner`.

    Existe para impedir que alguém "conserte" um vermelho trocando a tecla real
    por uma emissão de sinal, ou baixando o denominador para só os controles
    fáceis.
    """
    assert HARNESS.is_file(), f"{HARNESS} não existe"
    source = HARNESS.read_text(encoding="utf-8")
    assert "keyClick(" in source, "o harness não envia tecla real"
    assert "activated.connect" in source, (
        "o harness não observa `activated`; mudar de índice sem avisar quem "
        "escuta passaria como sucesso"
    )
    assert "combo.activated(" not in source, (
        "o harness emite `activated` na mão — isso prova o sinal, não a jornada"
    )
    assert "item.visible" in source and "combo.enabled" in source, (
        "o denominador precisa incluir ComboBox desabilitado, não só o fácil"
    )
    assert "Accessible.description" in source, "o harness não cobra motivo de quem está bloqueado"


# `visual` ROTEIA, não dispensa: a prova exige o runtime QML e pertence ao job
# `qml-visual-linux`, que reprova quando o Qt falta.
@pytest.mark.visual
def test_comboboxes_respond_to_real_keys_and_blocked_ones_explain_themselves() -> None:
    assert RUNNER is not None, "qmltestrunner Qt 6 é obrigatório para esta prova"
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
        [str(RUNNER), "-input", str(HARNESS)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    assert completed.returncode == 0, f"harness de ComboBox reprovou:\n{output[-3000:]}"
    assert "FAIL" not in output, f"asserção de tecla real reprovou:\n{output[-3000:]}"
    # O denominador tem de aparecer: um harness que parasse de achar ComboBox
    # ficaria verde sem ter exercitado nada.
    assert output.count("COMBOBOX {") >= 6, (
        f"o harness não publicou o denominador por superfície:\n{output[-2000:]}"
    )
