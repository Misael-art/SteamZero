"""Auditoria das citacoes `arquivo:NNN` contra DUAS arvores: HEAD (antes do corte) e hoje.

Distingue, para cada citacao:
  DERIVA     — estava certa em HEAD e o corte deslocou a linha;
  FALSA      — ja estava errada em HEAD (citacao escrita errada, nao deriva);
  OK         — aponta hoje no conteudo que a prosa alega.

O julgamento de conteudo e humano: aqui se imprime o que cada numero aponta nas
duas arvores, mais a linha que alega. A decisao de corrigir vira tabela.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
HEAD = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                      text=True).stdout.strip()
ARQUIVOS = (
    "tests/qml/check_shell_esde_import_late_response.qml",
    "tests/integration/test_ui_shell_esde_import_late_response.py",
    "tests/qml/check_shell_retrofe_import_late_response.qml",
    "tests/integration/test_ui_shell_retrofe_import_late_response.py",
    "tests/qml/check_shell_esde_import_dialog_journey.qml",
    "tests/integration/test_ui_shell_esde_import_dialog.py",
    "tests/integration/test_ui_shell_home_first_fold.py",
    "tests/qml/check_esde_import_dialog_compact_viewport.qml",
    "tests/qml/check_readiness_surface.qml",
    "tests/unit/test_ui_audit_runner.py",
)
CITACAO = re.compile(
    r"`?([A-Za-z_0-9./-]+\.(?:qml|py|js)):(\d{2,5})(?:`?\s*-?\s*(?:`?:)?(\d{2,5}))?`?"
)
CACHE: dict[tuple[str, str], list[str] | None] = {}


def linhas_de(versao: str, nome: str):
    chave = (versao, nome)
    if chave in CACHE:
        return CACHE[chave]
    candidatos = [c for c in ROOT.rglob(Path(nome).name)
                  if ".venv" not in c.parts and "node_modules" not in c.parts]
    if not candidatos:
        CACHE[chave] = None
        return None
    alvo = next((c for c in candidatos if str(c).endswith(nome)), candidatos[0])
    rel = str(alvo.relative_to(ROOT))
    if versao == "HOJE":
        conteudo = alvo.read_text(encoding="utf-8")
    else:
        feito = subprocess.run(["git", "show", f"{versao}:{rel}"], cwd=ROOT,
                               capture_output=True, text=True)
        conteudo = feito.stdout if not feito.returncode else ""
    CACHE[chave] = conteudo.splitlines() or None
    return CACHE[chave]


total = 0
for rel in ARQUIVOS:
    arq = ROOT / rel
    if not arq.is_file():
        continue
    corpo = arq.read_text(encoding="utf-8").splitlines()
    hits = [(n, c) for n, c in enumerate(corpo, start=1) for _ in CITACAO.finditer(c)]
    if not hits:
        continue
    print(f"\n################ {rel}  ({len(hits)} citacoes)")
    for numero, conteudo in hits:
        for casa in CITACAO.finditer(conteudo):
            alvo_nome, inicio, fim = casa.group(1), int(casa.group(2)), casa.group(3)
            hoje, antes = linhas_de("HOJE", alvo_nome), linhas_de(HEAD, alvo_nome)
            print(f"\n  linha {numero}:  cita {alvo_nome}:{inicio}-{fim or inicio}")
            print(f"    ALEGA | {conteudo.strip()[:120]}")
            for rotulo, src in (("HOJE ", hoje), ("HEAD ", antes)):
                if src is None:
                    print(f"    {rotulo} alvo ausente")
                    continue
                fim_i = min(inicio + (int(fim) - inicio if fim else 0), len(src))
                trecho = " / ".join(src[i - 1].strip()[:70]
                                    for i in range(inicio, fim_i + 1) if i <= len(src))
                print(f"    {rotulo} {inicio}-{fim_i} (len {len(src)}): {trecho[:150]}")
            total += 1
print(f"\nTOTAL CITACOES RESOLVIDAS: {total}  (HEAD {HEAD[:8]})")
