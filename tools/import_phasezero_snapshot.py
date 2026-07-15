#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Converte um snapshot legado offline em bundle nativo; nunca executa o legado.

Esta ferramenta não pertence ao pacote/entrypoint ``steamzero``. Ela recebe um
diretório explicitamente escolhido, lê somente JSON regular e produz um bundle
autocontido que pode ser revisado antes de qualquer importação futura.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

MAX_FILES = 1000
MAX_FILE_BYTES = 2 * 1024 * 1024


def build_bundle(snapshot: Path) -> dict[str, Any]:
    root = snapshot.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("snapshot precisa ser um diretório")
    candidates = sorted(root.rglob("*.json"))
    if len(candidates) > MAX_FILES:
        raise ValueError(f"snapshot excede {MAX_FILES} arquivos JSON")

    records: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    for candidate in candidates:
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError(f"entrada insegura: {candidate.relative_to(root)}")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError(f"entrada fora do snapshot: {candidate}")
        if resolved.stat().st_size > MAX_FILE_BYTES:
            raise ValueError(f"arquivo excede {MAX_FILE_BYTES} bytes: {candidate.name}")
        raw = resolved.read_bytes()
        payload = json.loads(raw)
        relative = resolved.relative_to(root).as_posix()
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(raw)
        records.append({"sourceRelpath": relative, "payload": payload})

    return {
        "schemaVersion": 1,
        "kind": "steamzero.offline-legacy-import",
        "sourceFingerprint": digest.hexdigest(),
        "records": records,
        "runtimeDependency": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args(argv)
    try:
        bundle = build_bundle(args.snapshot)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"snapshot recusado: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(bundle, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
