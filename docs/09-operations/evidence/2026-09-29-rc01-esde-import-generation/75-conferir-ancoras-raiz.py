"""Confere, sem tocar na árvore, se cada âncora da bateria RAIZ ocorre uma única vez.

A bateria aborta no primeiro âncora ambíguo — depois de já ter rodado o gate
contra as anteriores. Conferir antes custa um segundo e preserva a corrida.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ESPEC = importlib.util.spec_from_file_location(
    "bateria_raiz", "/home/misael/steamzero-retrofe-tmp/73-bateria-mutacoes-esde-raiz.py"
)
BAT = importlib.util.module_from_spec(ESPEC)
assert ESPEC and ESPEC.loader
ESPEC.loader.exec_module(BAT)

texto = BAT.ALVO.read_text(encoding="utf-8")
print(f"alvo: {BAT.ALVO.name}")
for rotulo, old, new in BAT.MUTACOES:
    print(f"{texto.count(old)}x  {old!r} -> {new!r}  [{rotulo[:40]}]")
