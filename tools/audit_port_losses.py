"""Compara simbolos entre a origem do porte (#82) e a arvore atual.

Nao mescla nada: le os dois blobs e compara conjuntos de simbolos por AST.
Perder um `raise X` ou uma funcao no auto-merge e silencioso; isto torna visivel.
"""

import ast
import subprocess

SRC = "23b120b"
FILES = [
    "tools/release_host.py",
    "tools/install_host.py",
    "src/steamzero/core/transaction.py",
    "src/steamzero/core/journal.py",
    "src/steamzero/core/net.py",
    "src/steamzero/core/fs.py",
    "src/steamzero/adapters/release_convergence.py",
    "src/steamzero/adapters/lifecycle.py",
    "src/steamzero/adapters/component_jobs.py",
    "src/steamzero/jobs/manager.py",
    "src/steamzero/jobs/models.py",
]


def blob(ref, path):
    r = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def symbols(source):
    tree = ast.parse(source)
    funcs, classes, raises, imports, codes = set(), set(), set(), set(), set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.add(node.name)
        elif isinstance(node, ast.ClassDef):
            classes.add(node.name)
        elif isinstance(node, ast.Raise) and node.exc is not None:
            call = node.exc
            name = call.func if isinstance(call, ast.Call) else call
            if isinstance(name, ast.Name):
                raises.add(name.id)
            elif isinstance(name, ast.Attribute):
                raises.add(name.attr)
            if isinstance(call, ast.Call):
                for a in call.args:
                    if (
                        isinstance(a, ast.Constant)
                        and isinstance(a.value, str)
                        and a.value.startswith("E-")
                    ):
                        codes.add(a.value)
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                imports.add(f"{node.module}.{a.name}")
        elif isinstance(node, ast.Import):
            for a in node.names:
                imports.add(a.name)
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.startswith("E-")
        ):
            codes.add(node.value)
    return {
        "funcoes": funcs,
        "classes": classes,
        "excecoes": raises,
        "imports": imports,
        "codigos": codes,
    }


total = 0
for path in FILES:
    old, new = blob(SRC, path), blob("HEAD", path)
    if old is None:
        print(f"— {path}: nao existe na origem")
        continue
    if new is None:
        print(f"!! {path}: EXISTE na origem e NAO na arvore atual")
        total += 1
        continue
    try:
        so, sn = symbols(old), symbols(new)
    except SyntaxError as e:
        print(f"?? {path}: nao parseou ({e})")
        continue
    perdidos = {k: sorted(so[k] - sn[k]) for k in so if so[k] - sn[k]}
    if perdidos:
        print(f"\n!! {path}")
        for k, v in perdidos.items():
            print(f"   perdido {k}: {v}")
            total += len(v)
print(f"\nTOTAL de simbolos presentes na origem e ausentes aqui: {total}")
