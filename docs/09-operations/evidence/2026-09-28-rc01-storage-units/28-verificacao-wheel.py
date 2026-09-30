# SPDX-License-Identifier: GPL-3.0-or-later
"""Compara o wheel publicado pelo CI com os blobs do HEAD e do merge ref.

Lê o artefato `steamzero-wheel-<merge-sha>` baixado pelo `gh run download` e
confere, arquivo por arquivo, se o bytes dentro do `.whl` são idênticos aos
dos dois commits que importam: a cabeça enviada ao PR e o merge ref sobre o
qual o próprio run construiu o artefato. Sem isso, "a configuração empacota"
não passa de prova de configuração.

Uso: python 28-verificacao-wheel.py <diretório-do-artefato> <lista-de-arquivos>

A lista é saída de `git diff --name-only <base>..<head>`; só entradas `src/`
são conferidas, porque só elas entram no wheel.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

WHEEL_RELATIVO = Path("dist") / "steamzero-2.0.0rc1-py3-none-any.whl"
MERGE_REF = "a555999c856a18a711a251f23708c0270355ad27"
CHECKOUT = Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")


def blob(rev: str, path: str) -> bytes:
    processo = subprocess.run(
        ["git", "-C", str(CHECKOUT), "show", f"{rev}:{path}"],
        capture_output=True,
        check=True,
    )
    return processo.stdout


def sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def main() -> int:
    artefato = Path(sys.argv[1]).resolve()
    lista = Path(sys.argv[2]).resolve()
    wheel = artefato / WHEEL_RELATIVO
    arquivos = [
        linha
        for linha in lista.read_text(encoding="utf-8").splitlines()
        if linha.startswith("src/")
    ]
    conteudo = zipfile.ZipFile(wheel)

    iguais_head = 0
    iguais_merge = 0
    for caminho in arquivos:
        # o wheel desprefixa src/, e o zip não conhece o layout do repositório
        dentro = conteudo.read(caminho.split("/", 1)[1])
        no_head = blob("HEAD", caminho)
        no_merge = blob(MERGE_REF, caminho)
        iguais_head += dentro == no_head
        iguais_merge += dentro == no_merge
        marca = "OK" if dentro == no_head and dentro == no_merge else "DIFERENTE"
        print(f"{caminho}\t{len(dentro)}\t{marca}\tsha256={sha256(dentro)}")

    print(f"\ntotal={len(arquivos)} identicos_head={iguais_head} identicos_merge={iguais_merge}")
    return 0 if iguais_head == len(arquivos) and iguais_merge == len(arquivos) else 1


if __name__ == "__main__":
    raise SystemExit(main())
