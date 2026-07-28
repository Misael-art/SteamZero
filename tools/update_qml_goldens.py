#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Atualiza as baselines visuais — só quando alguém pede.

Nunca roda no CI, e nunca é chamado por um teste. A razão é que uma baseline
regravada automaticamente deixa de ser uma baseline: o primeiro resultado, certo
ou errado, viraria a definição do correto, e ninguém revisaria a imagem que
passou a definir o que é aprovado.

O comando lista o que mudou, gera a diferença antes de sobrescrever e deixa as
imagens no commit, onde alguém precisa olhá-las. Escrever por cima em silêncio é
o que transforma golden image em carimbo.

Uso:
    .venv/bin/python tools/update_qml_goldens.py --check     # só relata
    .venv/bin/python tools/update_qml_goldens.py --write     # regrava
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from qml_capture_fixtures import FIXTURES  # noqa: E402
from qml_capture_runner import (  # noqa: E402
    CaptureError,
    assert_not_empty,
    capture,
    compare_with_golden,
)

GOLDEN_DIR = ROOT / "tests" / "qml" / "golden"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="relata diferenças, não escreve")
    group.add_argument("--write", action="store_true", help="regrava as baselines alteradas")
    parser.add_argument("--work", type=Path, default=ROOT / "build" / "qml-goldens")
    args = parser.parse_args(argv)

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    args.work.mkdir(parents=True, exist_ok=True)

    changed: list[str] = []
    created: list[str] = []
    failed: list[str] = []

    for fixture in FIXTURES:
        run = args.work / fixture.name
        golden = GOLDEN_DIR / f"{fixture.name}.png"
        try:
            result = capture(
                fixture.model().to_dict(),
                output=run,
                canvas=fixture.canvas,
                background=fixture.background,
            )
            assert_not_empty(result.image, background=fixture.background)
        except CaptureError as exc:
            # Captura quebrada não regrava baseline. Congelar uma imagem que o
            # harness nem conseguiu produzir direito é pior que não ter baseline.
            failed.append(f"{fixture.name}: {exc}")
            continue

        if not golden.exists():
            created.append(fixture.name)
            if args.write:
                shutil.copyfile(result.image, golden)
            continue

        try:
            metrics = compare_with_golden(result.image, golden, run)
        except CaptureError as exc:
            failed.append(f"{fixture.name}: {exc}")
            continue

        if metrics.changed_pixel_count == 0:
            continue

        changed.append(
            f"{fixture.name}: {metrics.changed_pixel_count} pixels "
            f"({metrics.changed_pixel_ratio:.4%}), delta máximo "
            f"{metrics.maximum_channel_delta}, região {metrics.bounding_box_of_changes}"
        )
        if args.write:
            shutil.copyfile(result.image, golden)

    for label, entries in (("NOVAS", created), ("ALTERADAS", changed), ("FALHAS", failed)):
        if entries:
            print(f"\n{label}:")
            for entry in entries:
                print(f"  {entry}")

    if failed:
        return 2
    if not created and not changed:
        print("nenhuma baseline mudou")
        return 0
    if args.write:
        print(f"\nbaselines regravadas em {GOLDEN_DIR}")
        print("Revise as imagens no diff antes de commitar: uma baseline aprovada")
        print("sem alguém olhar é um carimbo, não uma verificação.")
        return 0
    print(f"\ndiferenças em {args.work} (diff.png, overlay.png, metrics.json)")
    print("Use --write para aceitar, depois de olhar.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
