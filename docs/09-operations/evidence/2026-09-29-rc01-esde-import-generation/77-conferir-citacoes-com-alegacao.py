"""Conferencia das citacoes `arquivo:NNN` dos quatro arquivos do corte, com a alegacao.

Imprime, para cada citacao: a linha que alega (texto completo) e a linha que o
numero aponta HOJE. A decisao de corrigir e feita contra conteudo e simbolo, nao
contra memoria do numero.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
ARQUIVOS = (
    ROOT / "src/steamzero/ui/qml/Main.qml",
    ROOT / "src/steamzero/ui/qml/ThemeEditorPanel.qml",
    ROOT / "tests/qml/check_shell_esde_import_late_response.qml",
    ROOT / "tests/integration/test_ui_shell_esde_import_late_response.py",
)
CITACAO = re.compile(
    r"`?([A-Za-z_0-9./-]+\.(?:qml|py|js)):(\d{2,5})(?:`?\s*-?\s*(?:`?:)?(\d{2,5}))?`?"
)
CACHE: dict[str, list[str] | None] = {}


def linhas_de(nome: str):
    if nome in CACHE:
        return CACHE[nome]
    candidatos = [c for c in ROOT.rglob(Path(nome).name)
                  if ".venv" not in c.parts and "node_modules" not in c.parts]
    if not candidatos:
        CACHE[nome] = None
        return None
    alvo = next((c for c in candidatos if str(c).endswith(nome)), candidatos[0])
    CACHE[nome] = alvo.read_text(encoding="utf-8").splitlines()
    return CACHE[nome]


for arq in ARQUIVOS:
    linhas = arq.read_text(encoding="utf-8").splitlines()
    print(f"\n######## {arq.relative_to(ROOT)}")
    for numero, conteudo in enumerate(linhas, start=1):
        for casa in CITACAO.finditer(conteudo):
            alvo_nome, inicio, fim = casa.group(1), int(casa.group(2)), casa.group(3)
            alvo_linhas = linhas_de(alvo_nome)
            print(f"\n  -- {arq.name}:{numero}  cita  {alvo_nome}:{inicio}-{fim or inicio}")
            print(f"     ALEGA: {conteudo.strip()}")
            if alvo_linhas is None:
                print("     ALVO AUSENTE no repositorio")
                continue
            ultimo = min(inicio + (int(fim) - inicio if fim else 0), len(alvo_linhas))
            for i in range(inicio, ultimo + 1):
                print(f"     HOJE {i:>5}| {alvo_linhas[i - 1].strip()[:110]}")
