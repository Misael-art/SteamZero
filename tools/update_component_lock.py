#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Deriva o component-lock.json dos manifestos empacotados.

O lockfile é a barreira de supply chain: ``validate_registry_lock`` recusa
qualquer divergência entre o manifesto e o hash promovido. Até agora ele era
mantido à mão — e um arquivo que só existe para detectar adulteração, editado
manualmente a cada mudança de manifesto, convida ao erro que ele deveria pegar.
Uma capability nova em onze adapters significava onze hashes recalculados e
colados um a um.

Gerar não enfraquece a barreira: o hash continua vindo do mesmo ``load_manifest``
que o validador usa, e o ``--check`` reprova quando o commit não regravou. O que
muda é que a regravação deixa de ser digitação.

Uso:
    python tools/update_component_lock.py --write   # regrava
    python tools/update_component_lock.py --check   # reprova se divergiu
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from steamzero.adapters.registry import AdapterManifest, load_manifest  # noqa: E402

MANIFESTS = ROOT / "src" / "steamzero" / "adapters" / "manifests"
LOCKFILE = ROOT / "src" / "steamzero" / "adapters" / "component-lock.json"


def _source_entry(manifest: AdapterManifest) -> dict[str, Any]:
    """Campos exatos que ``validate_registry_lock`` compara, e só eles."""
    source = manifest.preferred_source(allow_eol=True)
    entry: dict[str, Any] = {
        "type": source.type,
        "version": source.version,
        "priority": source.priority,
    }
    for key, value in (
        ("ref", source.ref),
        ("remote", source.remote),
        ("url", source.url),
        ("sha256", source.sha256),
    ):
        if value is not None:
            entry[key] = value
    if source.end_of_life:
        entry["endOfLife"] = True
    return entry


def render() -> dict[str, Any]:
    components = []
    for path in sorted(MANIFESTS.glob("*.adapter.json")):
        manifest = load_manifest(json.loads(path.read_text(encoding="utf-8")))
        components.append(
            {
                "id": manifest.id,
                "manifestHash": manifest.manifest_hash,
                "source": _source_entry(manifest),
            }
        )
    return {"schemaVersion": 1, "components": components}


def _serialize(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="regrava o lockfile")
    group.add_argument("--check", action="store_true", help="reprova se divergir")
    args = parser.parse_args(argv)

    rendered = _serialize(render())
    if args.write:
        LOCKFILE.write_text(rendered, encoding="utf-8")
        print(f"component-lock regravado: {LOCKFILE.relative_to(ROOT)}")
        return 0
    if not LOCKFILE.is_file():
        print(f"lockfile ausente: {LOCKFILE.relative_to(ROOT)}", file=sys.stderr)
        return 1
    if LOCKFILE.read_text(encoding="utf-8") != rendered:
        print(
            f"component-lock desatualizado: {LOCKFILE.relative_to(ROOT)}\n"
            "os manifestos mudaram e o lockfile não; rode --write e revise o diff",
            file=sys.stderr,
        )
        return 1
    print("component-lock: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
