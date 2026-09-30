"""Re-auditoria objetiva das citacoes numericas depois da conversao por simbolo.

Invariantemente: uma citacao `arquivo:NNN` está viva se o trecho que o numero aponta
HOJE na arvore de trabalho for IGUAL ao trecho que apontava em HEAD. Em HEAD a
veracidade de cada uma ja foi conferida contra a prosa (77/78/79), entao "igual"
significa "continua correta", e "diferente" significa "deslocou — corrigir".

Imprime tambem a contagem de citacoes que sobraram por arquivo, para a diff
documental ser mensuravel: o que este corte fez foi trocar numero por simbolo, e o
denominador tem de cair.
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


def trecho(src: list[str] | None, inicio: int, fim: int | None) -> str | None:
    if src is None:
        return None
    fim_i = min(inicio + (int(fim) - inicio if fim else 0), len(src))
    return " / ".join(src[i - 1].strip() for i in range(inicio, fim_i + 1) if i <= len(src))


fora_do_repositorio = 0
vivas = 0
deriva = 0
total_citacoes = 0
por_arquivo: dict[str, int] = {}
for rel in ARQUIVOS:
    arq = ROOT / rel
    if not arq.is_file():
        print(f"AUSENTE: {rel}")
        continue
    corpo = arq.read_text(encoding="utf-8").splitlines()
    contagem = 0
    for numero, conteudo in enumerate(corpo, start=1):
        for casa in CITACAO.finditer(conteudo):
            alvo_nome, inicio, fim = casa.group(1), int(casa.group(2)), casa.group(3)
            contagem += 1
            total_citacoes += 1
            hoje = trecho(linhas_de("HOJE", alvo_nome), inicio, fim)
            antes = trecho(linhas_de(HEAD, alvo_nome), inicio, fim)
            if hoje is None and antes is None:
                fora_do_repositorio += 1
                continue
            if hoje is not None and hoje == antes:
                vivas += 1
            else:
                deriva += 1
                print(f"\nDERIVA  {rel}:{numero}  cita {alvo_nome}:{inicio}-{fim or inicio}")
                print(f"  HEAD | {(antes or '<alvo ausente>')[:200]}")
                print(f"  HOJE | {(hoje or '<alvo ausente>')[:200]}")
                print(f"  PROB | {conteudo.strip()[:160]}")
    por_arquivo[rel] = contagem

print("\n== citacoes numericas por arquivo (HOJE) ==")
for rel, n in por_arquivo.items():
    print(f"  {n:>4}  {rel}")
print(f"\nFORA DO REPOSITORIO (caminho qrc/Qt): {fora_do_repositorio}")
print(f"\nTOTAL: {total_citacoes} citacoes | {vivas} apontam o mesmo conteudo de HEAD | "
      f"{deriva} deslocaram")
print(f"HEAD = {HEAD}")
raise SystemExit(0 if deriva == 0 else 1)
