"""Reproduz, sem Qt, as asserções de substring que as guardas fazem sobre o fonte.

Por que isto existe: o corte de citações escreveu texto novo em COMENTÁRIOS, e as
"guardas de intenção" dos gates conferem o arquivo inteiro por substring
(`assert "inspectEsdeImport(" not in fonte`). Comentário não é linha executável, mas é
fonte lido — então classificar a linha pelo papel dela (script 90) não basta para
declarar o corte puramente documental. Aqui a conferência é pelo critério da própria
guarda: token proibido presente = vermelho, onde quer que esteja escrito.

Extração por AST, por função, sem lista manual. Duas coisas precisam de escopo, e as
duas foram erro de ferramenta na 1ª versão (marcava verde/vivo onde não havia):
  - `fonte` NÃO é sempre o harness: em algumas funções é o próprio `.py`
    (`Path(__file__).read_text()`) ou o `Main.qml` do produto. Só a função cujo
    `fonte` vem de `_harness_source()` descreve o arquivo .qml conferido aqui;
  - a polaridade vem do operador da comparação (`in` exige, `not in` proíbe), tanto
    para literal quanto para o laço `for <var> in (...)`.

Depois varre o harness da árvore de trabalho e marca as ocorrências de token proibido
que não estavam no snapshot de referência. CUIDADO COM A LIXA: `cit-backup-83` foi
tirado às 21:29, DEPOIS do script 80 (21:16) — não é o início do corte de citações. O
que ele separa é "antes dasscripts 84-88", não "antes do corte". A atribuição firme do
que o corte escreveu vem do próprio `80-corrigir-citacoes.py`: suas linhas 33, 59, 63 e
87 trocam citações de número de linha por `applyEsdeImport()`/`inspectEsdeImport()`,
que são exatamente os tokens que a guarda proíbe. Rótulos: NOVO = só na árvore de
hoje; corte = já estava no snapshot de 21:29 (e o log 80 mostra que foi o corte que o
pôs ali); lote = nem uma coisa nem outra.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

ROOT = Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")
HEAD = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                      text=True).stdout.strip()
SNAPSHOT = Path("/home/misael/steamzero-retrofe-tmp/cit-backup-83")

PARES = [
    ("tests/integration/test_ui_shell_esde_import_late_response.py",
     "tests/qml/check_shell_esde_import_late_response.qml"),
    ("tests/integration/test_ui_shell_retrofe_import_late_response.py",
     "tests/qml/check_shell_retrofe_import_late_response.qml"),
    ("tests/integration/test_ui_shell_esde_import_dialog.py",
     "tests/qml/check_shell_esde_import_dialog_journey.qml"),
    ("tests/integration/test_ui_shell_home_first_fold.py",
     "tests/qml/check_home_first_fold_attention.qml"),
]


def _origem_de_fonte(no: ast.AST) -> str | None:
    """O que a função lê em `fonte`: o harness, o próprio .py, outra fonte, ou ambíguo."""
    lida: set[str] = set()
    for s in ast.walk(no):
        if not isinstance(s, ast.Assign):
            continue
        if not any(isinstance(a, ast.Name) and a.id == "fonte" for a in s.targets):
            continue
        ch = s.value
        if isinstance(ch, ast.Call) and isinstance(ch.func, ast.Name) \
                and ch.func.id == "_harness_source":
            lida.add("harness")
        elif isinstance(ch, ast.Call) and isinstance(ch.func, ast.Attribute) \
                and ch.func.attr == "read_text":
            lida.add("arquivo")
        else:
            lida.add("outra")
    return next(iter(lida)) if len(lida) == 1 else None


def _literais(fn: ast.FunctionDef, onde: str) -> tuple[set[str], set[str]]:
    proibidos: set[str] = set()
    exigidos: set[str] = set()
    for no in ast.walk(fn):
        if not isinstance(no, ast.Assert) or no.test is None:
            continue
        for comp in ast.walk(no.test):
            if not isinstance(comp, ast.Compare) or not isinstance(comp.left, ast.Constant):
                continue
            if not isinstance(comp.left.value, str):
                continue
            if not any(isinstance(c, ast.Name) and c.id == onde
                       for c in comp.comparators):
                continue
            if any(isinstance(o, ast.NotIn) for o in comp.ops):
                proibidos.add(comp.left.value)
            elif any(isinstance(o, ast.In) for o in comp.ops):
                exigidos.add(comp.left.value)
    return proibidos, exigidos


def coletar(py: Path) -> tuple[set[str], set[str]]:
    arvore = ast.parse(py.read_text(encoding="utf-8"))
    proibidos: set[str] = set()
    exigidos: set[str] = set()
    for fn in [n for n in ast.walk(arvore) if isinstance(n, ast.FunctionDef)]:
        if _origem_de_fonte(fn) != "harness":
            continue
        p, e = _literais(fn, "fonte")
        for la in [n for n in ast.walk(fn) if isinstance(n, ast.For)]:
            if not isinstance(la.iter, ast.Tuple) or not isinstance(la.target, ast.Name):
                continue
            var = la.target.id
            nomes = {x.value for x in la.iter.elts
                     if isinstance(x, ast.Constant) and isinstance(x.value, str)}
            proibe = exigir = False
            for s in ast.walk(la):
                if (isinstance(s, ast.Compare) and isinstance(s.left, ast.Name)
                        and s.left.id == var
                        and any(isinstance(c, ast.Name) and c.id == "fonte"
                                for c in s.comparators)):
                    if any(isinstance(o, ast.NotIn) for o in s.ops):
                        proibe = True
                    elif any(isinstance(o, ast.In) for o in s.ops):
                        exigir = True
            if proibe:
                nomes and proibidos.update(nomes)
            elif exigir:
                nomes and exigidos.update(nomes)
        proibidos.update(p)
        exigidos.update(e)
    return proibidos, exigidos - proibidos


def main() -> int:
    problemas = 0
    print(f"HEAD {HEAD[:8]} | snapshot pré-corte {SNAPSHOT.name}\n")
    for pyrel, qmlrel in PARES:
        py, qml = ROOT / pyrel, ROOT / qmlrel
        if not qml.is_file() or not py.is_file():
            print(f"AUSENTE  {qmlrel}")
            problemas += 1
            continue
        proibido, exigido = coletar(py)
        hoje = qml.read_text(encoding="utf-8")
        antes_txt = ""
        copia = SNAPSHOT / qmlrel.split("/")[-1]
        if copia.is_file():
            antes_txt = copia.read_text(encoding="utf-8")
        print(f"### {qmlrel}  (proibidos={len(proibido)} exigidos={len(exigido)})")
        for tok in sorted(proibido):
            ns = [i + 1 for i, l in enumerate(hoje.splitlines()) if tok in l]
            if not ns:
                continue
            hs = [i + 1 for i, l in enumerate(antes_txt.splitlines()) if tok in l]
            novos = len(ns) - len(hs)
            print(f"  [{'NOVO ' if novos > 0 else 'lote '}] {tok!r}: hoje={ns} snapshot={hs}")
            problemas += 1
        faltam = sorted(t for t in exigido if t not in hoje)
        for tok in faltam:
            print(f"  [EXIGIDO-AUSENTE] {tok!r}")
            problemas += 1
    print(f"\nPROBLEMAS: {problemas}")
    return 0 if problemas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
