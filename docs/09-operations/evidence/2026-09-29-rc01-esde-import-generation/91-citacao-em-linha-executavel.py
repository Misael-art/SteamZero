"""Prova estatica de que nenhuma citacao mora em linha executavel dos arquivos NOVOS.

90 respondeu isso para os cinco arquivos rastreados pelo diff (93 linhas somadas, todas
comentario/docstring/mensagem). Para os dois arquivos que só existem nesta arvore nao ha
diff com HEAD, e localizar o texto-novo de cada tabela se provou o caminho errado: um
treco reenvolvido por 85/88 deixa de ser contiguo, e o localizador passa a errar — erro
de ferramenta, nao da arvore.

O teste direto e outro, e nao depende das tabelas:

  * uma linha e EXECUTAVEL se nao e comentario e nao esta dentro de uma string cujo
    papel seja docstring ou mensagem. Em QML isso e `//` no inicio (o arquivo usa `//`
    e `///` para toda prosa) ou string argumento de `verify(...)`; em Python, `tokenize`
    da linha de comentario e a AST da o papel de cada string (docstring / msg de assert
    / argumento de chamada / operando de comparacao);
  * sobre essas linhas executaveis, procura-se o padrao de citacao: `arquivo.qml:NNN`,
    `arquivo.py:NNN` ou `:NNN` entre backticks, e tambem qualquer string que sirva de
    condicao a uma guarda de intencao (o `assert exiga in fonte` da proprio arquivo).

Citacao em linha executavel = alteracao de teste, e ai a revalidacao e de comportamento,
nao de gate verde.
"""

from __future__ import annotations

import ast
import io
import pathlib
import re
import subprocess
import tokenize

ROOT = pathlib.Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
NOVOS = ("tests/qml/check_shell_esde_import_late_response.qml",
         "tests/integration/test_ui_shell_esde_import_late_response.py")
HEAD = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                      text=True).stdout.strip()
CITACAO = re.compile(r"[\w./-]+\.(?:qml|py|js):\d|`:\d")


def linhas_executaveis_py(caminho: pathlib.Path) -> tuple[set[int], dict[int, str]]:
    fonte = caminho.read_text(encoding="utf-8")
    comentarios = {c.start[0] for c in
                   tokenize.generate_tokens(io.StringIO(fonte).readline)
                   if c.type == tokenize.COMMENT}
    papel: dict[int, str] = {}

    def marcar(no: ast.AST, nome: str) -> None:
        for n in range(no.lineno, (no.end_lineno or no.lineno) + 1):
            papel.setdefault(n, nome)

    def comparar(sub: ast.AST) -> None:
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
            comparar(no.test)
        elif isinstance(no, ast.Call):
            for arg in no.args + [k.value for k in no.keywords]:
                if isinstance(arg, (ast.Constant, ast.JoinedStr)):
                    marcar(arg, "mensagem")
                elif isinstance(arg, ast.BinOp):
                    for casa in ast.walk(arg):
                        if isinstance(casa, ast.Constant) and isinstance(casa.value, str):
                            marcar(casa, "mensagem")
            comparar(no)
        elif isinstance(no, ast.Assign):
            # dicionario de documento de falha (RECUSAS_DOC): string que so vira texto
            # de mensagem adiante, nunca condicao.
            for casa in ast.walk(no.value):
                if isinstance(casa, (ast.Constant, ast.JoinedStr)) \
                        and isinstance(getattr(casa, "value", None), str):
                    marcar(casa, "literal-de-dado")
                elif isinstance(casa, ast.JoinedStr):
                    marcar(casa, "literal-de-dado")
    return comentarios, papel


print(f"== arquivos novos deste corte (HEAD {HEAD[:8]}) ==")
suspeitas: list[str] = []
for rel in NOVOS:
    arq = ROOT / rel
    corpo = arq.read_text(encoding="utf-8").splitlines()
    if rel.endswith(".py"):
        comentarios, papel = linhas_executaveis_py(arq)
        documental = {"docstring", "mensagem", "condicao", "literal-de-dado"}
        for n, linha in enumerate(corpo, start=1):
            if n in comentarios or linha.lstrip().startswith("#"):
                continue
            if papel.get(n) in {"docstring", "mensagem", "literal-de-dado"}:
                continue
            if CITACAO.search(linha):
                tipo = papel.get(n, "codigo")
                suspeitas.append(f"{rel}:{n} [{tipo}] {linha.strip()[:96]}")
        cond = [f"{rel}:{n} {linha.strip()[:96]}" for n, linha in enumerate(corpo, start=1)
                if papel.get(n) == "condicao" and CITACAO.search(linha)]
        print(f"  {rel}: linhas={len(corpo)} "
              f"comentario={len(comentarios)} "
              f"docstring={sum(1 for v in papel.values() if v == 'docstring')} "
              f"mensagem={sum(1 for v in papel.values() if v == 'mensagem')} "
              f"condicao={sum(1 for v in papel.values() if v == 'condicao')}")
        for c in cond:
            suspeitas.append("CONDICAO " + c)
    else:
        prosa = sum(1 for l in corpo if l.lstrip().startswith("//"))
        em_string = [f"{rel}:{n} {l.strip()[:96]}" for n, l in enumerate(corpo, start=1)
                     if not l.lstrip().startswith("//") and '"' in l
                     and CITACAO.search(l) and "verify" not in l]
        fora = [f"{rel}:{n} {l.strip()[:96]}" for n, l in enumerate(corpo, start=1)
                if not l.lstrip().startswith("//") and '"' not in l and CITACAO.search(l)]
        print(f"  {rel}: linhas={len(corpo)} prosa(//)={prosa} "
              f"citacao-fora-de-prosa={len(em_string) + len(fora)}")
        suspeitas.extend(fora)
        suspeitas.extend(f"STRING-NAO-VERIFY {s}" for s in em_string)

print(f"\n== CITACAO EM LINHA EXECUTAVEL: {len(suspeitas)} ==")
for s in suspeitas:
    print("  " + s)
