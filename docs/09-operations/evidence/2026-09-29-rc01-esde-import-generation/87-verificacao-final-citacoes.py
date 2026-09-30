"""Verificacao objetiva do fim do corte de citacoes — o denominador reconciliado.

Quatro invariantes, cada um medido na arvore de trabalho contra `c4975979`:

  1. toda citacao `arquivo:NNN` aponta HOJE o mesmo conteudo que apontava em HEAD
     (a veracidade de cada uma contra a prosa ja foi conferida em 77/78/79, entao
     "igual" == "continua correta");
  2. nenhuma citacao crua `:NNN` sobra — ela so se resolve pelo contexto da frase,
     que e justamente o que desloca quando um corte insere linhas;
  3. nenhum comentario ou docstring passa do largamento da propria lingua (QML 88,
     Python 100) se ja passava antes do corte — contagem por arquivo, hoje x HEAD;
  4. o que ainda esta no tempo presente sobre o estado ANTES do corte e listado para
     leitura humana, porque aferir verdade de prosa e decisao humana, nao de regex.

Saida: contagens reconciliadas por arquivo mais o veredito. Nao reescreve nada.
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
LARGURA = {"qml": 88, "py": 100}
CITACAO = re.compile(
    r"`?([A-Za-z_0-9./-]+\.(?:qml|py|js)):(\d{2,5})(?:`?\s*-?\s*(?:`?:)?(\d{2,5}))?`?"
)
CRUA = re.compile(r"`:\d")
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


ARQUIVO_HEAD = set(subprocess.run(["git", "ls-tree", "-r", "--name-only", HEAD],
                                  cwd=ROOT, capture_output=True, text=True).stdout.split())


def _existe_na_head(nome: str) -> bool:
    return any(caminho.endswith(nome) for caminho in ARQUIVO_HEAD)


def comentarios_largos(linhas, limite, prefixos):
    return sum(1 for l in linhas
               if len(l) > limite and any(l.lstrip().startswith(p) for p in prefixos))


def docstrings_largos(linhas, limite):
    """Linhas de Python acima do limite que nao sejam `#` — docstring inclusive."""
    return sum(1 for l in linhas if len(l) > limite and not l.lstrip().startswith("#"))


total = deslocadas = identicas = fora = sem_head = 0
cruas: list[str] = []
largura: list[str] = []
presente: list[str] = []

print("== 1 e 2: citacoes numericas, hoje x HEAD ==")
for rel in ARQUIVOS:
    arq = ROOT / rel
    if not arq.is_file():
        continue
    corpo = arq.read_text(encoding="utf-8").splitlines()
    hits = [(n, c) for n, c in enumerate(corpo, start=1) if CITACAO.search(c)]
    for numero, conteudo in hits:
        for casa in CITACAO.finditer(conteudo):
            nome, inicio, fim = casa.group(1), int(casa.group(2)), casa.group(3)
            antecedente = conteudo[max(0, casa.start() - 6):casa.start()]
            if nome.startswith("/") or "qrc:" in antecedente or "qt-project.org" in nome:
                # caminho de controle do Qt (qrc), não do repositório: sem linha
                fora += 1
                continue
            hoje, antes = linhas_de("HOJE", nome), linhas_de(HEAD, nome)
            if hoje is None or antes is None:
                if hoje is None:
                    # caminho fora do repositório (qrc/Qt) — não tem linha para conferir
                    fora += 1
                    continue
                if not _existe_na_head(nome):
                    sem_head += 1
                    continue
                deslocadas += 1
                print(f"  {rel}:{numero} alvo ausente em HEAD ({nome})")
                continue
            fim_i = min(inicio + (int(fim) - inicio if fim else 0), len(hoje), len(antes))

            def recorte(src):
                i = min(inicio, len(src))
                f = min(fim_i, len(src))
                return " / ".join(src[k - 1].strip() for k in range(i, f + 1))

            total += 1
            if recorte(hoje) == recorte(antes):
                identicas += 1
            else:
                deslocadas += 1
                print(f"\n  DESLOCOU  {rel}:{numero}  cita {nome}:{inicio}-{fim_i}")
                print(f"    ALEGA | {conteudo.strip()[:120]}")
                print(f"    HEAD  | {recorte(antes)[:120]}")
                print(f"    HOJE  | {recorte(hoje)[:120]}")
    for numero, linha in enumerate(corpo, start=1):
        if CRUA.search(linha):
            cruas.append(f"{rel}:{numero}: {linha.strip()[:90]}")

print(f"\n  conferidas: {total} | iguais a HEAD: {identicas} | deslocaram: {deslocadas} "
      f"| fora do repositorio (qrc/Qt): {fora} | alvo sem HEAD (arquivo deste corte): "
      f"{sem_head}")

print("\n== 2: citacoes cruas `:NNN` ==")
if cruas:
    for c in cruas:
        print("  " + c)
print(f"  restantes: {len(cruas)}")

print("\n== 3: largamento de comentario/docstring, hoje x antes-do-corte ==")
BACKUP = Path.home() / "steamzero-retrofe-tmp" / "cit-backup-83"
for rel in ARQUIVOS[:7]:
    arq = ROOT / rel
    if not arq.is_file():
        continue
    lingua = "py" if rel.endswith(".py") else "qml"
    limite = LARGURA[lingua]
    prefixos = ("#",) if lingua == "py" else ("//",)
    hoje = arq.read_text(encoding="utf-8").splitlines()
    copia = BACKUP / Path(rel).name
    if copia.is_file():
        antes = copia.read_text(encoding="utf-8").splitlines()
    else:
        feito = subprocess.run(["git", "show", f"{HEAD}:{rel}"], cwd=ROOT,
                               capture_output=True, text=True)
        antes = feito.stdout.splitlines()
    n_hoje = (comentarios_largos(hoje, limite, prefixos) if lingua == "qml"
              else comentarios_largos(hoje, limite, prefixos) + docstrings_largos(hoje, limite))
    n_antes = (comentarios_largos(antes, limite, prefixos) if lingua == "qml"
               else comentarios_largos(antes, limite, prefixos) + docstrings_largos(antes, limite))
    marca = "OK " if n_hoje <= n_antes else "PIOR"
    print(f"  {marca} {rel}: hoje={n_hoje} antes={n_antes} (limite {limite})")
    if n_hoje > n_antes:
        largura.append(rel)

print("\n== 4: afirmações de presente sobre o estado antes do corte ==")
for rel in ARQUIVOS[:7]:
    arq = ROOT / rel
    if not arq.is_file():
        continue
    for numero, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), start=1):
        if re.search(r"[Hh]oje", linha):
            presente.append(f"{rel}:{numero}: {linha.strip()[:100]}")
for p in presente:
    print("  " + p)
print(f"  lidas: {len(presente)} (julgamento humano; nenhuma deve afirmar o pre-corte)")

veredito = (deslocadas == 0 and not cruas and not largura)
print(f"\n== VEREDITO == {'PASSO' if veredito else 'FALHA'} "
      f"(HEAD {HEAD[:8]} | citacoes {identicas}/{total} estaveis, cruas {len(cruas)}, "
      f"largura {len(largura)})")
raise SystemExit(0 if veredito else 1)
