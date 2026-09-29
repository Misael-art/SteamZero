#!/usr/bin/env python3
"""Atribui, arquivo por arquivo, cada digest reprovado pelo `make status-check`.

Por que este script existe: a mudança desta frente toca três arquivos compartilhados
(`Main.qml`, `ErrorCard.qml`, `ThemeEditorPanel.qml`) que entram no escopo de outros
itens além do desta frente. Renovar um digest sem dizer **por qual arquivo** ele envelheceu
é transformar renovação de escopo em verificação nova — exatamente o que a diretiva do
operador (item 10) proíbe. O script não escreve nada no catálogo: só lê, compara e imprime.

Comando refazível, do checkout canônico:
    .venv/bin/python docs/09-operations/evidence/2026-09-29-rc01-home-first-fold/51-atribuicao-digests.py
"""

from __future__ import annotations

import glob
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = "2d6a8957"
HEAD_REF = "HEAD"

# Arquivos que esta frente trouxe para a árvore: os commitados desta base até HEAD mais
# os caminhos ainda não commitados do lote (evidência, cartões, testes novos).
def files_of_front() -> list[str]:
    committed = subprocess.run(
        ["git", "diff", "--name-only", BASE, HEAD_REF],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    untracked = [
        "tests/integration/test_ui_shell_home_first_fold.py",
        "tests/qml/check_home_first_fold_attention.qml",
        "docs/09-operations/evidence/2026-09-29-rc01-home-first-fold",
        "docs/09-operations/evidence/2026-09-29-rc01-retrofe-shell-late"
        "/32-ci-terminal-pr245-2d6a8957.log",
        "docs/status/workstreams/rc01-home-first-fold-2026-09-29.json",
    ]
    return sorted(set(committed + untracked))


def accused() -> list[tuple[str, str, str]]:
    rodado = subprocess.run(
        [str(ROOT / ".venv/bin/python"), "tools/project_status.py", "check"],
        cwd=ROOT, capture_output=True, text=True,
    )
    out = rodado.stdout + rodado.stderr
    rows = []
    for line in out.splitlines():
        if "scopeDigest esperado" in line:
            item = line.split(":", 1)[0].strip("- ")
            esperado = line.split("esperado ", 1)[1].split(",")[0]
            atual = line.split("atual ", 1)[1].strip()
            rows.append((item, esperado, atual))
    return rows


def main() -> int:
    mine = files_of_front()
    print(f"arquivos desta frente (base {BASE} -> {HEAD_REF} + não commitados): {len(mine)}")
    for m in mine:
        print("  -", m)
    print()
    rows = accused()
    print(f"itens acusados pelo check: {len(rows)}")
    sem_causa = 0
    for item, esperado, atual in rows:
        card = None
        for p in glob.glob(str(ROOT / "docs/status/items/*.json")):
            d = json.loads(Path(p).read_text())
            if d.get("id") == item:
                card = d
                break
        assert card is not None, item
        scope = set(card.get("scopePaths", []))

        def inside(x: str) -> bool:
            return x in scope or any(x.startswith(s + "/") or s.startswith(x + "/") for s in scope)

        hits = [x for x in mine if inside(x)]
        if not hits:
            sem_causa += 1
        print(
            f'{item:34} scopePaths={len(scope):3} '
            f'causados por esta frente: {len(hits):2}  {hits}'
        )
        print(f'  esperado {esperado[:16]}…  atual {atual[:16]}…')
    print()
    print(f"itens acusados SEM arquivo desta frente no escopo: {sem_causa}")
    return 0 if sem_causa == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
