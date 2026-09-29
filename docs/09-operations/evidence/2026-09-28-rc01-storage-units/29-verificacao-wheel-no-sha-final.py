# SPDX-License-Identifier: GPL-3.0-or-later
"""Confere o wheel publicado no SHA FINAL do PR contra os blobs daquele SHA.

Complementa `28-verificacao-wheel.py`. Lá a prova foi lida na cabeça funcional
`37f0add4`, sobre a lista de arquivos que o PR mudou. Aqui a leitura é feita na
cabeça final `2d04ac96` — depois de dois commits documentais — e a comparação é
**a árvore `src/steamzero` inteira**, arquivo por arquivo. É a forma honesta da
alegação "a árvore testada só recebeu documento depois do verde": não basta que
os oito arquivos tocados pelo PR estejam certos, tem de estar todo byte do
pacote.

Três blocos, cada um com a própria alegação:

* **A** — proveniência lida do próprio artefato: merge ref, ref, run, SHA-256 do
  sujeito e o estado da árvore no build. Nada é copiado de argumento: a revisão
  comparada é a que o CI usou para construir.
* **B** — varredura total: cada entrada do `steamzero/` dentro do wheel contra o
  blob correspondente da cabeça local. Compara o hash de blob Git (SHA-1 de
  `blob <len>\0` + conteúdo), que é exatamente a identidade que o repositório
  usa; uma divergência de um byte muda o hash.
* **C** — os arquivos deste PR, contra a cabeça local **e** contra o merge ref,
  com SHA-256 por arquivo para conferência independente.

O merge ref é lido de `build/provenance.json`; ele precisa existir no repositório
local (`git fetch --no-tags origin refs/pull/244/merge`) — o fetch não toca a
árvore de trabalho.

Uso: python3 29-verificacao-wheel-no-sha-final.py <dir-do-artefato> <lista>
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

WHEEL_RELATIVO = Path("dist") / "steamzero-2.0.0rc1-py3-none-any.whl"
PROVENANCIA = Path("build") / "provenance.json"
SUBTREE = "src/steamzero"
CHECKOUT = Path("/home/misael/Projects/Steam Zero/Canonical/2026-09-21")

#: Único arquivo esperado dentro do wheel sem par na árvore: gerado em build por
#: `hatch_build.py` e auto-declarado ("NÃO EDITE À MÃO"). Ele carrega o SHA da
#: revisão que o CI construiu, então é conferido por conteúdo, não tolerado.
GERADO_EM_BUILD = "steamzero/_build_info.py"


def git(*args: str) -> str:
    processo = subprocess.run(
        ["git", "-C", str(CHECKOUT), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return processo.stdout


def blob_de(rev: str, path: str) -> bytes:
    processo = subprocess.run(
        ["git", "-C", str(CHECKOUT), "show", f"{rev}:{path}"],
        capture_output=True,
        check=True,
    )
    return processo.stdout


def sha256(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def git_blob(dados: bytes) -> str:
    # SHA-1 é a identidade que o Git usa para blobs; não é primitivo de segurança aqui.
    return hashlib.sha1(b"blob %d\0" % len(dados) + dados, usedforsecurity=False).hexdigest()


def arvore(rev: str) -> dict[str, str]:
    """`{caminho-como-no-wheel: hash-do-blob}` para `src/steamzero`.

    O wheel desprefixa `src/`, então as chaves nascem no espaço de nomes do
    artefato: com o prefixo, o conjunto pareado fica vazio e a varredura passaria
    a afirmar "0 diferentes" sobre 0 comparações.
    """
    saida = git("ls-tree", "-r", "--format=%(objectname) %(path)", rev, "--", SUBTREE)
    pares = {}
    for linha in saida.splitlines():
        hash_blob, caminho = linha.split(" ", 1)
        pares[caminho[len("src/") :]] = hash_blob
    return pares


def bloco_a(artefato: Path) -> tuple[str, str, bool]:
    dados = json.loads((artefato / PROVENANCIA).read_text(encoding="utf-8"))
    merge_ref = str(dados["source"]["commit"])
    sujeito = str(dados["subject"]["sha256"])
    wheel = artefato / WHEEL_RELATIVO
    no_disco = sha256(wheel.read_bytes())
    print("=== A. proveniência lida do próprio artefato ===")
    print(f"repository={dados['source']['repository']}")
    print(f"ref={dados['source']['ref']}")
    print(f"merge_ref={merge_ref}")
    print(f"run={dados['build']['runId']} builder={dados['build']['builder']}")
    print(f"sourceTreeState={dados['build']['sourceTreeState']}")
    print(f"sujeito_arquivo={wheel.name} bytes={wheel.stat().st_size}")
    print(f"sujeito_sha256_publicado={sujeito}")
    print(f"sujeito_sha256_no_disco={no_disco}")
    print(f"sujeito_coincide={no_disco == sujeito}")
    return merge_ref, sujeito, no_disco == sujeito


def bloco_b(artefato: Path, cabeca: str, merge_ref: str) -> bool:
    wheel = artefato / WHEEL_RELATIVO
    zip_ = zipfile.ZipFile(wheel)
    entradas = [n for n in zip_.namelist() if n.startswith("steamzero/") and not n.endswith("/")]
    no_head = arvore(cabeca)
    no_merge = arvore(merge_ref)
    conjunto = set(entradas)
    print("\n=== B. varredura total do pacote (wheel x árvore) ===")
    print(f"entradas_no_wheel={len(entradas)} arquivos_no_HEAD={len(no_head)}")
    print(f"arquivos_no_merge_ref={len(no_merge)}")
    sobrando = sorted(conjunto - set(no_head))
    faltando = sorted(set(no_head) - conjunto)
    print(f"sem_par_no_wheel={sobrando[:20]} (total={len(sobrando)})")
    print(f"sem_par_no_HEAD={faltando[:20]} (total={len(faltando)})")

    # O gerado-em-build é o único sobrajeto admitido, e só é admitido porque se
    # confere o que ele declara: o SHA da revisão construída e a árvore limpa.
    so_gerado = sobrando == [GERADO_EM_BUILD]
    if so_gerado:
        texto = zip_.read(GERADO_EM_BUILD).decode("utf-8")
        commit_declarado = next(
            linha.split('"')[1] for linha in texto.splitlines() if linha.startswith("SOURCE_COMMIT")
        )
        sujo = "SOURCE_DIRTY = True" in texto
        declarado = f"SOURCE_COMMIT={commit_declarado} SOURCE_DIRTY={sujo}"
        print(f"{GERADO_EM_BUILD}: {declarado}")
        so_gerado = commit_declarado == merge_ref and not sujo
    print(f"gerado_em_build_conferido={so_gerado}")

    pareados = sorted(conjunto & set(no_head))
    diferentes = [c for c in pareados if git_blob(zip_.read(c)) != no_head[c]]
    print(
        f"pareados={len(pareados)} identicos_HEAD={len(pareados) - len(diferentes)} "
        f"diferentes_HEAD={len(diferentes)}"
    )
    for caminho in diferentes[:20]:
        print(
            f"  DIF x HEAD {caminho} wheel={git_blob(zip_.read(caminho))} head={no_head[caminho]}"
        )
    pareados_m = sorted(conjunto & set(no_merge))
    dif_m = [c for c in pareados_m if git_blob(zip_.read(c)) != no_merge[c]]
    print(
        f"pareados_merge={len(pareados_m)} identicos_merge={len(pareados_m) - len(dif_m)} "
        f"diferentes_merge={len(dif_m)}"
    )
    for caminho in dif_m[:20]:
        print(f"  DIF x MERGE {caminho}")
    return not diferentes and not dif_m and not faltando and so_gerado


def bloco_c(artefato: Path, cabeca: str, merge_ref: str, lista: Path) -> bool:
    arquivos = [
        linha
        for linha in lista.read_text(encoding="utf-8").splitlines()
        if linha.startswith("src/")
    ]
    zip_ = zipfile.ZipFile(artefato / WHEEL_RELATIVO)
    print(f"\n=== C. os {len(arquivos)} arquivos deste PR, por SHA-256 ===")
    iguais_head = 0
    iguais_merge = 0
    for caminho in arquivos:
        # o wheel desprefixa src/
        dentro = zip_.read(caminho.split("/", 1)[1])
        no_head = blob_de(cabeca, caminho)
        no_merge = blob_de(merge_ref, caminho)
        iguais_head += dentro == no_head
        iguais_merge += dentro == no_merge
        marca = "OK" if dentro == no_head and dentro == no_merge else "DIFERENTE"
        print(f"{caminho}\t{len(dentro)}\t{marca}\tsha256={sha256(dentro)}")
    print(f"total={len(arquivos)} identicos_head={iguais_head} identicos_merge={iguais_merge}")
    return iguais_head == len(arquivos) and iguais_merge == len(arquivos)


def main() -> int:
    artefato = Path(sys.argv[1]).resolve()
    lista = Path(sys.argv[2]).resolve()
    cabeca = git("rev-parse", "HEAD").strip()
    print(f"head_local={cabeca}")
    merge_ref, _, sujeito_ok = bloco_a(artefato)
    ok_b = bloco_b(artefato, cabeca, merge_ref)
    ok_c = bloco_c(artefato, cabeca, merge_ref, lista)
    veredito = sujeito_ok and ok_b and ok_c
    print(
        f"\nveredito=sujeito={sujeito_ok} varredura_total={ok_b} arquivos_do_pr={ok_c} "
        f"{'APROVADO' if veredito else 'REPROVADO'}"
    )
    return 0 if veredito else 1


if __name__ == "__main__":
    raise SystemExit(main())
