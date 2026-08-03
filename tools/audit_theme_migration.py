#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Auditoria executável da migração de temas: relatório de fidelidade por área.

Para cada layout RetroFE informado (default: as duas fixtures do corpus),
produz o relatório de migração: quantas propriedades o autor declarou, quantas
a fatia traduz, por categoria, e a lista nominal do que ficou sem tradutor.

O relatório é o corpo do gate `source_property_count < 388` do P0-03: quando a
fatia migrar o corpus inteiro, o gate reprova e esta ferramenta mostra por quê,
com os nomes e as áreas.

Uso: ``python tools/audit_theme_migration.py [layout.xml ...]``
      ``python tools/audit_theme_migration.py --json [layout.xml ...]``

Leitura pura; não escreve nada em disco.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from steamzero.domain.retrofe_declarations import collect_declarations
from steamzero.domain.theme_migration_audit import audit_migration

_DEFAULT_LAYOUTS = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "retrofe" / "vs04_positive.xml",
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "retrofe" / "vs04_negative.xml",
)


def _render(name: str, payload: dict[str, object]) -> None:
    print(f"== {name} ==")
    declared = payload["sourcePropertyCount"]
    migrated = payload["migratedPropertyCount"]
    print(f"  declaradas: {declared}  migradas: {migrated}  fidelidade: {payload['fidelity']}")
    for item in payload["byCategory"]:
        print(
            f"  {item['category']:<14} {item['declared']:>4} declaradas, "
            f"{item['migrated']:>4} migradas ({item['fidelity']})"
        )
    not_migrated = payload["notMigrated"]
    if not_migrated:
        print(f"  sem tradutor: {', '.join(not_migrated)}")
    else:
        print("  sem tradutor: nenhum")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auditoria de migração de temas RetroFE")
    parser.add_argument("layouts", nargs="*", help="layouts XML (default: fixtures do corpus)")
    parser.add_argument("--json", action="store_true", help="saída JSON em vez de tabela")
    args = parser.parse_args(argv)

    paths = [Path(p) for p in args.layouts] or list(_DEFAULT_LAYOUTS)
    failing = False
    for path in paths:
        if not path.exists():
            print(f"layout inexistente: {path}", file=sys.stderr)
            failing = True
            continue
        declarations = collect_declarations(path.read_text(encoding="utf-8"), file=path.name)
        audit = audit_migration(declarations)
        if args.json:
            print(json.dumps({str(path): audit.to_dict()}, ensure_ascii=False, indent=2))
        else:
            _render(path.name, audit.to_dict())
        if not audit.corpus_gate_ok:
            print(
                f"{path.name}: o gate do corpus reprovou "
                f"({audit.declared} >= {audit.corpus_total})",
                file=sys.stderr,
            )
            failing = True
    if failing:
        return 1
    print("auditoria de migração: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
