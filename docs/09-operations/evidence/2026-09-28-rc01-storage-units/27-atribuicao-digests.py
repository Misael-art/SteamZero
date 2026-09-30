"""Atribuição por arquivo dos itens obsoletos no checkpoint 27 (UX-04).

Para cada item acusado pelo `tools/project_status.py check`, mede se algum
arquivo alterado por ESTA frente está em `scopePaths` do item. Sem isso, a
frase "31 itens obsoletos" não diz se a frente contaminou outrem ou se é o
digest de cada item envelhecido por arquivo seu, legitimamente tocado.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
BASE = "c0de54c9"

# Arquivos que esta frente escreve: diff da branch contra a base + o que está
# no working tree (docs ainda não commitados).
changed: set[str] = set()
diff = subprocess.run(
    ["git", "diff", "--name-only", f"{BASE}..HEAD"],
    capture_output=True,
    text=True,
    check=True,
).stdout.splitlines()
changed.update(diff)
porcelain = subprocess.run(
    ["git", "status", "--porcelain"],
    capture_output=True,
    text=True,
    check=True,
).stdout.splitlines()
for line in porcelain:
    changed.add(line[3:].strip())

# Pastas de evidência: um item que lista a pasta own-a; aqui só interessa a
# pasta deste lote, que é exclusiva desta frente.
front_evidence = "docs/09-operations/evidence/2026-09-28-rc01-storage-units"


def contem(scope: list[str]) -> list[str]:
    """Arquivos desta frente que caem dentro do escopo do item.

    `scopePaths` aceita arquivo exato e pasta (o digest desce a pasta), então a
    pertença é por prefixo de caminho — nunca `endswith`, que faria `Main.qml`
    casar com `LaunchMain.qml`.
    """
    hits = []
    for entrada in scope:
        norma = entrada.rstrip("/")
        for caminho in changed:
            dentro = caminho == norma or caminho.startswith(norma + "/")
            eh_pasta_do_lote = norma == front_evidence and caminho.startswith(
                front_evidence
            )
            if dentro or eh_pasta_do_lote:
                hits.append(f"{entrada} <- {caminho}")
    return sorted(set(hits))


def main() -> int:
    sys.path.insert(0, str(ROOT / "tools"))
    import project_status  # noqa: E402

    # A acusação do project_status vai para STDERR (medido: `check` com stdout
    # redirectado para arquivo imprime zero linhas e 35 linhas no stderr). Ler
    # o stdout daria "0 itens acusados", que é um falso verde de atribuição.
    processo = subprocess.run(
        [sys.executable, "tools/project_status.py", "check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    saida = processo.stderr
    acusados = [
        line[2:].split(":")[0].strip()
        for line in saida.splitlines()
        if line.startswith("- SZ-")
    ]
    catalog = project_status.load_catalog()
    print(f"arquivos desta frente: {len(changed)}")
    com_culpa = 0
    sem_culpa = []
    for ident in acusados:
        item = catalog.items[ident]
        hits = contem(item.get("scopePaths", []))
        if hits:
            com_culpa += 1
            print(f"{ident}: {len(hits)} arquivo(s) desta frente em scopePaths")
            for h in hits:
                print(f"    - {h}")
        else:
            sem_culpa.append(ident)
    print()
    print(f"itens acusados: {len(acusados)}")
    print(f"com ao menos um arquivo desta frente no escopo: {com_culpa}")
    print(f"SEM nenhum arquivo desta frente: {len(sem_culpa)}")
    for ident in sem_culpa:
        print(f"    ! {ident}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
