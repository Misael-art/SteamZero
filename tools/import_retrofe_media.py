#!/usr/bin/env python3
"""Plan/apply a local RetroFE artwork import for the canonical library."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from steamzero.domain.retrofe_media_import import apply_import, plan_import


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--media-root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="publish accepted masters")
    parser.add_argument("--replace", action="store_true", help="replace existing roles")
    return parser


def main() -> int:
    args = _parser().parse_args()
    payload = json.loads(args.library.read_text(encoding="utf-8"))
    records = payload.get("games", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise SystemExit("library must contain a games list")
    plan = plan_import(args.source_root, records)
    report: dict[str, object] = {"plan": plan.to_dict(), "applied": False}
    if args.apply:
        games_by_id = {
            str(game.get("id")): game
            for game in records
            if isinstance(game, dict) and game.get("id")
        }
        result = apply_import(plan, args.media_root, games_by_id, replace=args.replace)
        apply_result = {
            "imported": list(result.imported),
            "skippedExisting": list(result.skipped_existing),
            "failed": list(result.failed),
        }
        report["applyResult"] = apply_result
        report["applied"] = True
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not args.apply or not result.failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
