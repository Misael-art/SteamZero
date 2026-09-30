"""Resolve, sem escrever nada, cada citação `arquivo:NNN` dos quatro arquivos do corte.

A fatia inseriu linhas em `Main.qml` e `ThemeEditorPanel.qml`, então toda citação
escrita contra a árvore anterior aponta agora para outra linha. O operador pediu
conferência por caminho, símbolo e conteúdo — não pelo número — e preferência por
referência ao símbolo quando ela for mais estável. Isto imprime, para cada
citação, a linha que o número aponta HOJE, para a decisão ser evidência e não
memória.
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
CITACAO = re.compile(r"`?([A-Za-z_0-9./-]+\.(?:qml|py)):(\d{2,5})(?:`?\s*-?\s*(?:`?:)?(\d{2,5}))?`?")

for arq in ARQUIVOS:
    texto = arq.read_text(encoding="utf-8")
    linhas = texto.splitlines()
    print(f"\n######## {arq.relative_to(ROOT)}")
    for numero, conteudo in enumerate(linhas, start=1):
        for casa in CITACAO.finditer(conteudo):
            alvo_nome, inicio, fim = casa.group(1), int(casa.group(2)), casa.group(3)
            alvo = ROOT / "src/steamzero/ui/qml" / alvo_nome
            if not alvo.is_file():
                alvo = ROOT / "src/steamzero" / alvo_nome
            if not alvo.is_file():
                alvo = ROOT / "tests/qml" / alvo_nome
            if not alvo.is_file():
                alvo = ROOT / "tests/integration" / alvo_nome
            if not alvo.is_file():
                print(f"  {numero:>5}  {alvo_nome}:{inicio}  ALVO AUSENTE")
                continue
            alvo_linhas = alvo.read_text(encoding="utf-8").splitlines()
            trecho = []
            for i in range(inicio, min(inicio + (int(fim) - inicio + 1 if fim else 1), len(alvo_linhas) + 1)):
                trecho.append(f"{i}|{alvo_linhas[i - 1].strip()[:96]}")
            print(f"  {numero:>5}  {alvo_nome}:{inicio}-{fim or inicio}")
            for t in trecho:
                print(f"          {t}")
