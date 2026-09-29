"""Matriz de locales do harness de unidades: prova documental do defeito e do conserto."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
QML = shutil.which("qml6")
HARNESS = "tests/qml/check_storage_units.qml"
MARCADOR = "FAIL:"
VEREDITO = "check_storage_units:"


def ambiente(locale_nome: str | None) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "QT_FORCE_STDERR_LOGGING": "1",
            "QT_LOGGING_RULES": "",
            "QT_QPA_PLATFORM": "offscreen",
            "QML_DISABLE_DISK_CACHE": "1",
        }
    )
    for chave in ("LANG", "LC_ALL", "LANGUAGE"):
        env.pop(chave, None)
    if locale_nome is not None:
        env["LANG"] = locale_nome
        env["LC_ALL"] = locale_nome
    return env


def main() -> int:
    for locale_nome in ("C", "C.UTF-8", None, "en_US.UTF-8", "pt_BR.UTF-8"):
        completed = subprocess.run(
            [QML, HARNESS], cwd=ROOT, env=ambiente(locale_nome),
            capture_output=True, text=True, timeout=120, check=False,
        )
        saida = completed.stdout + completed.stderr
        falhas = [l for l in saida.splitlines() if MARCADOR in l]
        veredito = [l for l in saida.splitlines() if VEREDITO in l]
        print(f"LC_ALL={locale_nome or '(sem)'}: rc={completed.returncode} "
              f"falhas={len(falhas)} veredito={veredito[-1] if veredito else 'AUSENTE'}")
        for linha in falhas[:12]:
            print("   " + linha.strip()[:150])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
