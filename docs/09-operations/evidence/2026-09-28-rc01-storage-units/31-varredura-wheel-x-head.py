#!/usr/bin/env python3
"""Varredura wheel-do-CI x blobs do head da branch. Somente leitura.

git roda com --no-optional-locks e GIT_INDEX_FILE apontando para um índice
descartável fora do checkout: nada é escrito no índice/árvore real enquanto a
integral está em voo.
"""
import hashlib
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

# Derivado do próprio arquivo, como o precedente `30-verificacao-wheel-na-cabeca-*.py`:
# nenhum caminho pessoal é fixado no que vai para o repositório.
CHECKOUT = os.environ.get("STEAMZERO_CHECKOUT") or str(
    Path(__file__).resolve().parents[4])  # docs/09-operations/evidence/<lote>/<este arquivo>
TMP = os.environ.get("STEAMZERO_TMP") or tempfile.gettempdir()
WHEEL = os.environ["STEAMZERO_WHEEL"]  # wheel baixado do artefato do CI, fora do checkout
HEAD = sys.argv[1] if len(sys.argv) > 1 else "af6a5c6ed8523c04030d25b1d391e885a3b3b48e"

env = dict(os.environ, GIT_INDEX_FILE=os.path.join(TMP, "idx-read-only.tmp"),
           GIT_OPTIONAL_LOCKS="0")
if os.path.exists(env["GIT_INDEX_FILE"]):
    os.remove(env["GIT_INDEX_FILE"])


def run(*args, stdin=None):
    p = subprocess.run(args, cwd=CHECKOUT, env=env, input=stdin,
                       capture_output=True, check=True)
    return p.stdout


listing = run("git", "ls-tree", "-r", "--format=%(objecttype) %(objectname) %(path)", HEAD)
blobs = {}
for line in listing.splitlines():
    kind, oid, *rest = line.split(b" ", 2)
    if kind != b"blob" or not rest:
        continue
    blobs[rest[0].decode("utf-8", "surrogateescape")] = oid

order = list(blobs)
batch_in = b"".join(blobs[p] + b"\n" for p in order)
out = run("git", "cat-file", "--batch", stdin=batch_in)

# parsing do --batch: "sha1 SP type SP size LF <bytes> LF"
git_entries = {}
i = 0
lines = out
paths = order
pos = 0
for path in paths:
    nl = lines.index(b"\n", pos)
    header = lines[pos:nl]
    _sha1, kind, size = header.split(b" ", 2)
    if kind != b"blob":
        raise SystemExit(f"entrada inesperada para {path}: {header!r}")
    n = int(size)
    payload = lines[nl + 1: nl + 1 + n]
    pos = nl + 2 + n
    git_entries[path] = (hashlib.sha256(payload).hexdigest(), len(payload))

z = zipfile.ZipFile(WHEEL)
wheel_entries = {n: (hashlib.sha256(z.read(n)).hexdigest(), len(z.read(n)))
                 for n in z.namelist()}

META = {"steamzero/_build_info.py"}
gen = {"RECORD"}
matched = ident = 0
diffs, only_wheel, only_head = [], [], []
for name, (sha, size) in sorted(wheel_entries.items()):
    if ".dist-info/" in name:
        continue
    src_path = "src/" + name
    if src_path in git_entries:
        matched += 1
        if git_entries[src_path][0] != sha:
            diffs.append(name)
        else:
            ident += 1
    elif name in META or name.split("/")[-1] in gen:
        only_wheel.append(name + " (gerado no build)")
    else:
        only_wheel.append(name)

wheel_paths = {n for n in wheel_entries if ".dist-info/" not in n}
for path, (sha, size) in sorted(git_entries.items()):
    if path.startswith("src/steamzero/") and path[4:] not in wheel_paths:
        only_head.append(path)

print(f"# varredura wheel x head {HEAD[:12]}")
print(f"head_rev_parse={run('git','rev-parse','HEAD').decode().strip()}")
print(f"wheel_sha256={hashlib.sha256(open(WHEEL,'rb').read()).hexdigest()} "
      f"bytes={os.path.getsize(WHEEL)}")
print(f"entradas_wheel={len(wheel_entries)} arquivos_head={len(git_entries)}")
print(f"pareados={matched} identicos={ident} diferentes={len(diffs)}")
print(f"diferentes={diffs}")
print(f"so_no_wheel={only_wheel}")
print(f"so_no_head={only_head}")
print(f"indice_real_sha256={hashlib.sha256(open(f'{CHECKOUT}/.git/index','rb').read()).hexdigest()}")
