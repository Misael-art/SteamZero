"""Confere, por maquina, que o corte de citacoes e documental.

A pergunta do operador e: alguma dessas citacoes participa de uma assercao executavel?
Se sim, o trecho e alteracao de teste e pede revalidacao de comportamento.

Dos conjuntos, um por tipo de arquivo:

  A) arquivos rastreados — TODA linha adicionada por `git diff HEAD -- tests` e
     classificada pela posicao dentro do codigo. Nao se confia nas tabelas dos
     scripts: o diff e a autoridade, e ele pega o que uma tabela nao declarou.
  B) os dois arquivos novos (inexistem em HEAD) — cada texto-novo declarado nas
     tabelas dos scripts do corte (80, 83, 84, 85, 86, 88) e localizado por busca com
     espacos normalizados (as reenvolturas quebram o trecho em duas linhas) e a linha
     portadora e classificada igual.

Papeis: `comentario` (#, //, ///), `docstring` (string que e Expressao sozinha),
`mensagem` (string como argumento de verify/qtest_fail ou msg de assert), `condicao`
(string operando de comparacao — a citacao neste caso e assercao), `codigo` (o resto).
As tabelas sao lidas por AST + literal_eval: importar os scripts reexecitaria edicoes.
(Supera 89, que reconciliava por numero de linha e gerou falso positivo.)
"""

from __future__ import annotations

import ast
import io
import pathlib
import re
import subprocess
import tokenize
from collections import defaultdict

ROOT = pathlib.Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
TMP = pathlib.Path.home() / "steamzero-retrofe-tmp"
HEAD = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                      text=True).stdout.strip()

NOVOS = ("tests/qml/check_shell_esde_import_late_response.qml",
         "tests/integration/test_ui_shell_esde_import_late_response.py")
FONTES = [
    ("80-corrigir-citacoes.py", "TABELA", "arq-linha-old-new"),
    ("83-citacoes-por-simbolo.py", "REPL", "arq-old-new"),
    ("84-citacoes-cruzadas.py", "REPL", "arq-old-new"),
    ("85-reenvolver-linhas-estouradas.py", "TRECHOS", "arq-limite-old-new"),
    ("86-citacoes-cruas-e-afirmacoes-hoje.py", "TRECHOS", "arq-old-new"),
    ("88-reenvolver-retrofe.py", "TRECHOS", "so-old-new"),
]


def tabela(script: str, var: str, forma: str) -> list[tuple[str, str]]:
    arvore = ast.parse((TMP / script).read_text(encoding="utf-8"))
    alvo = arq_default = None
    for casa in arvore.body:
        if isinstance(casa, ast.Assign):
            nomes = [n.id for n in casa.targets if isinstance(n, ast.Name)]
        elif isinstance(casa, ast.AnnAssign) and isinstance(casa.target, ast.Name):
            nomes = [casa.target.id]
        else:
            continue
        for nome in nomes:
            if nome == "ARQ":
                arq_default = ast.literal_eval(casa.value)
            elif nome == var:
                alvo = casa.value
    if alvo is None:
        raise SystemExit(f"{script}: tabela {var} nao encontrada")
    saida: list[tuple[str, str]] = []
    for elemento in alvo.elts:  # type: ignore[attr-defined]
        v = [ast.literal_eval(c) for c in elemento.elts]  # type: ignore[attr-defined]
        if forma in ("arq-linha-old-new", "arq-limite-old-new"):
            saida.append((v[0], v[3]))
        elif forma == "arq-old-new":
            saida.append((v[0], v[2]))
        else:
            assert arq_default
            saida.append((arq_default, v[1]))
    return saida


def papeis_python(caminho: pathlib.Path) -> tuple[set[int], dict[int, str]]:
    """(linhas de comentario, mapa linha -> papel de string)."""
    fonte = caminho.read_text(encoding="utf-8")
    comentarios = {c.start[0] for c in
                   tokenize.generate_tokens(io.StringIO(fonte).readline)
                   if c.type == tokenize.COMMENT}
    papeis: dict[int, str] = {}

    def marcar(no: ast.AST, papel: str) -> None:
        for n in range(getattr(no, "lineno", 0), getattr(no, "end_lineno", 0) + 1):
            papeis.setdefault(n, papel)

    def marcar_comparacoes(sub: ast.AST) -> None:
        for casa in ast.walk(sub):
            if isinstance(casa, ast.Compare):
                for lado in [casa.left, *casa.comparators]:
                    if isinstance(lado, ast.Constant) and isinstance(lado.value, str):
                        marcar(lado, "condicao")

    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, ast.Expr) and isinstance(no.value, ast.Constant) \
                and isinstance(no.value.value, str):
            marcar(no.value, "docstring")
        elif isinstance(no, ast.Assert):
            if no.msg is not None:
                marcar(no.msg, "mensagem")
            marcar_comparacoes(no.test)
        elif isinstance(no, ast.Call):
            for arg in no.args + [k.value for k in no.keywords]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    marcar(arg, "mensagem")
                elif isinstance(arg, ast.JoinedStr):
                    marcar(arg, "mensagem")
                elif isinstance(arg, ast.BinOp):
                    for casa in ast.walk(arg):
                        if isinstance(casa, ast.Constant) and isinstance(casa.value, str):
                            marcar(casa, "mensagem")
            marcar_comparacoes(no)
    return comentarios, papeis


def papel_da_linha(arq: str, numero: int, texto: str,
                   cache: dict[str, tuple[set[int], dict[int, str]]]) -> str:
    if not texto.strip():
        return "branco"
    if arq.endswith(".py"):
        if arq not in cache:
            cache[arq] = papeis_python(ROOT / arq)
        comentarios, papeis = cache[arq]
        if numero in comentarios or texto.lstrip().startswith("#"):
            return "comentario"
        return papeis.get(numero, "codigo")
    if texto.lstrip().startswith("//"):
        return "comentario"
    return "mensagem" if '"' in re.sub(r"//.*$", "", texto) else "codigo"


EXECUTAVEL = {"codigo", "condicao"}
cache: dict[str, tuple[set[int], dict[int, str]]] = {}
A: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
B: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))


def despeja(titulo: str, grupo: dict[str, dict[str, list[int]]]) -> None:
    print(f"== {titulo} ==")
    for arq in sorted(grupo):
        resumo = ", ".join(f"{p}={len(v)}" for p, v in sorted(grupo[arq].items()))
        marca = "!!" if EXECUTAVEL & set(grupo[arq]) else "  "
        print(f"  {marca} {arq}: {resumo}")
        for p, v in grupo[arq].items():
            if p in EXECUTAVEL:
                corpo = (ROOT / arq).read_text(encoding="utf-8").splitlines()
                for n in v:
                    print(f"       EXECUTAVEL {arq}:{n}: {corpo[n - 1].strip()[:90]}")


print("== A) linhas adicionadas no diff (arquivos rastreados) ==")
diff = subprocess.run(["git", "diff", "--unified=0", HEAD, "--", "tests"],
                      cwd=ROOT, capture_output=True, text=True).stdout
arquivo_atual = None
contador = 0
proxima = 0
for casa in diff.splitlines():
    if casa.startswith("+++ b/"):
        arquivo_atual = casa[6:]
        continue
    if casa.startswith("@@"):
        m = re.search(r" \+(\d+)", casa)
        proxima = int(m.group(1)) if m else 0
        continue
    if not arquivo_atual or arquivo_atual in NOVOS:
        continue
    if casa.startswith("+"):
        A[arquivo_atual][papel_da_linha(arquivo_atual, proxima, casa[1:], cache)].append(proxima)
        proxima += 1
        contador += 1
    elif casa.startswith("-"):
        continue
    else:
        proxima += 1
despeja("A) linhas somadas no diff, por papel", A)

print("\n== B) textos-novo declarados nos scripts (arquivos novos deste corte) ==")
declaracoes: list[tuple[str, str]] = []
for script, var, forma in FONTES:
    declaracoes.extend(tabela(script, var, forma))
normal = re.compile(r"\s+")
ausentes: list[str] = []
for arq, novo_t in declaracoes:
    if arq not in NOVOS:
        continue
    corpo = (ROOT / arq).read_text(encoding="utf-8").splitlines()
    # normaliza: remove o marcador de comentario do inicio de cada linha e junta com
    # um espaco — o que permite achar um trecho que a reenvoltura quebrou em duas
    # linhas, mapeando de volta para a primeira linha portadora.
    limpas: list[str] = []
    mapa: list[int] = []
    for n, linha in enumerate(corpo, start=1):
        limpas.append(re.sub(r"^\s*(?://+|#+)\s*", "", linha))
        mapa.append(n)
    texto = normal.sub(" ", " ".join(limpas)).strip()
    alvo = normal.sub(" ", re.sub(r"^\s*(?://+|#+)\s*", "", novo_t)).strip()
    pos = texto.find(alvo) if alvo else -1
    if pos < 0:
        ausentes.append(f"{arq}: {novo_t[:60]!r}")
        continue
    acumulo = 0
    numero = 0
    for i, pedaco in enumerate(limpas):
        proximo = acumulo + len(pedaco) + 1
        if pos < proximo or pos == acumulo:
            numero = mapa[i]
            break
        acumulo = proximo
    if not numero:
        ausentes.append(f"{arq}: {novo_t[:60]!r} (sem linha) ")
        continue
    B[arq][papel_da_linha(arq, numero, corpo[numero - 1], cache)].append(numero)
despeja("B) textos-novo dos arquivos novos, por papel", B)
if ausentes:
    print(f"  TRECHO-AUSENTE ({len(ausentes)}):")
    for a in ausentes:
        print("    " + a)

total_b = sum(len(v) for a in B for v in B[a].values())
print(f"\nHEAD {HEAD[:8]} | somadas no diff dos rastreados: {contador} | declaracoes "
      f"localizadas nos novos: {total_b} | ausentes: {len(ausentes)}")
