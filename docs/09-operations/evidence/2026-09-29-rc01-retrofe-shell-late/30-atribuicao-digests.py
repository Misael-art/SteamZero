"""Atribuição por arquivo do item obsoleto no checkpoint do sétimo elo.

Precedente copiado e adaptado: docs/09-operations/evidence/
2026-09-28-rc01-storage-units/27-atribuicao-digests.py (commit c4839656).

Para cada item acusado pelo `tools/project_status.py check`, mede se algum
arquivo alterado por ESTA frente está em `scopePaths` do item. Sem isso, a
frase "1 item obsoleto" não diz se a frente contaminou outrem ou se é o digest
do próprio item envelhecido por arquivo seu, legitimamente tocado.

Saída incremental: esta frente escreve o log por stdout, então o chamador faz
`python3 ... 30-atribuicao-digests.py > 30-atribuicao-digests.log 2>&1`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()
BASE = "af6a5c6e"  # cabeça do PR #244, base do sétimo elo

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


def contem(scope: list[str]) -> list[str]:
    """Arquivos desta frente que caem dentro do escopo do item.

    `scopePaths` aceita arquivo exato e pasta (o digest desce a pasta), então a
    pertença é por prefixo de caminho — nunca `endswith`, que faria `Main.qml`
    casar com `LaunchMain.qml`.
    """
    hits = []
    for entrada in scope:
        norma = entrada.rstrip("/")
        for caminho in sorted(changed):
            dentro = caminho == norma or caminho.startswith(norma + "/")
            if dentro:
                hits.append(f"{entrada} <- {caminho}")
    return sorted(set(hits))


def main() -> int:
    sys.path.insert(0, str(ROOT / "tools"))
    import project_status  # noqa: E402

    # A acusação do project_status vai para STDERR. Ler o stdout daria "0 itens
    # acusados", que é um falso verde de atribuição.
    processo = subprocess.run(
        [sys.executable, "tools/project_status.py", "check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    saida = processo.stderr or processo.stdout
    acusados = [
        line[2:].split(":")[0].strip()
        for line in saida.splitlines()
        if line.startswith("- SZ-") or line.startswith("- WS-")
    ]
    obsoletos = [
        (line[2:].split(":")[0].strip(), line.split("atual ")[-1].strip())
        for line in saida.splitlines()
        if "evidencia obsoleta" in line
    ]
    catalog = project_status.load_catalog()
    print(f"base desta frente: {BASE}")
    print(f"arquivos desta frente (diff + working tree): {len(changed)}")
    por_tipo: dict[str, int] = {}
    for caminho in changed:
        topo = caminho.split("/")[0]
        if topo == "docs":
            chave = "docs" if not caminho.startswith("docs/status") else "docs/status"
        else:
            chave = topo
        por_tipo[chave] = por_tipo.get(chave, 0) + 1
    print(f"  por área: {por_tipo}")
    print()
    print("acusações do check (todas):")
    for line in saida.splitlines():
        print(f"  {line[:180]}")
    print()
    print(f"itens acusados de qualquer coisa: {len(set(acusados))}")
    print(f"itens com digest obsoleto: {len(obsoletos)}")
    com_culpa = 0
    sem_culpa = []
    for ident, valor in obsoletos:
        item = catalog.items[ident]
        hits = contem(item.get("scopePaths", []))
        print()
        print(f"### {ident}")
        print(f"    scopeDigest na tarjeta: {item.get('scopeDigest')}")
        print(f"    computado pela ferramenta: {valor}")
        recomputed = project_status.scope_digest(ROOT, item["scopePaths"])
        print(f"    recomputado agora neste processo: {recomputed}")
        if recomputed != valor:
            print("    ! divergência entre as duas leituras da mesma função")
        if hits:
            com_culpa += 1
            print(f"    {len(hits)} arquivo(s) desta frente em scopePaths:")
            for h in hits:
                print(f"      - {h}")
        else:
            sem_culpa.append(ident)
            print("    NENHUM arquivo desta frente no escopo")
    print()
    print(f"com ao menos um arquivo desta frente no escopo: {com_culpa}")
    print(f"SEM nenhum arquivo desta frente: {len(sem_culpa)} {sem_culpa}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
