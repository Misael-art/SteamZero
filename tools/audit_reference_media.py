#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Audita um acervo visual externo sem copiar, mover ou alterar seus arquivos.

O relatório é deliberadamente conservador: sem uma licença e proveniência
publicadas pelo fornecedor, uma imagem só pode ser classificada como referência
(``C_REFERENCE_UNVERIFIED``), nunca como ativo importável. Duplicatas exatas e
perceptuais são destacadas como ``D_DUPLICATE_OR_INVALID``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import warnings
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

_IMAGE_SUFFIXES = frozenset({".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"})


@dataclass(frozen=True)
class MediaRecord:
    relative_path: str
    category: str
    format: str | None
    width: int | None
    height: int | None
    has_alpha: bool | None
    bytes: int
    sha256: str | None
    perceptual_hash: str | None
    classification: str
    error: str | None = None


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _perceptual_hash(image: Image.Image) -> str:
    """Average hash 8x8, suficiente para apontar candidatos à revisão humana."""
    sample = image.convert("L").resize((8, 8), Image.Resampling.LANCZOS)
    pixels = list(sample.get_flattened_data())
    average = sum(pixels) / len(pixels)
    bits = "".join("1" if pixel >= average else "0" for pixel in pixels)
    return f"{int(bits, 2):016x}"


def _iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if path.is_symlink() or not path.is_file():
            continue
        yield path


def inspect_media(root: Path, *, max_files: int | None = None) -> list[MediaRecord]:
    """Lê metadados e hashes; não cria nenhum arquivo sob ``root``."""
    records: list[MediaRecord] = []
    for path in _iter_files(root):
        if max_files is not None and len(records) >= max_files:
            break
        relative = path.relative_to(root).as_posix()
        category = relative.split("/", 1)[0]
        try:
            size = path.stat().st_size
        except OSError as exc:
            records.append(
                MediaRecord(
                    relative, category, None, None, None, None, 0, None, None,
                    "D_DUPLICATE_OR_INVALID", type(exc).__name__
                )
            )
            continue
        if path.suffix.casefold() not in _IMAGE_SUFFIXES:
            records.append(
                MediaRecord(
                    relative, category, None, None, None, None, size, None, None,
                    "D_DUPLICATE_OR_INVALID", "unsupported-format"
                )
            )
            continue
        try:
            with Image.open(path) as image:
                # Pillow avisa sobre uma conversão interna de transparência de
                # paleta. Ela é esperada e ``image.info`` preserva o fato de
                # haver alpha para o relatório.
                with warnings.catch_warnings():
                    warnings.filterwarnings(
                        "ignore",
                        message="Palette images with Transparency expressed in bytes.*",
                        category=UserWarning,
                    )
                    image.load()
                    perceptual_hash = _perceptual_hash(image)
                records.append(
                    MediaRecord(
                        relative_path=relative,
                        category=category,
                        format=image.format,
                        width=image.width,
                        height=image.height,
                        has_alpha="A" in image.getbands() or "transparency" in image.info,
                        bytes=size,
                        sha256=_hash_file(path),
                        perceptual_hash=perceptual_hash,
                        classification="C_REFERENCE_UNVERIFIED",
                    )
                )
        except (OSError, UnidentifiedImageError, ValueError) as exc:
            records.append(
                MediaRecord(
                    relative, category, None, None, None, None, size, None, None,
                    "D_DUPLICATE_OR_INVALID", type(exc).__name__
                )
            )
    return _mark_duplicates(records)


def _mark_duplicates(records: list[MediaRecord]) -> list[MediaRecord]:
    exact = Counter(record.sha256 for record in records if record.sha256 is not None)
    perceptual = Counter(
        record.perceptual_hash for record in records if record.perceptual_hash is not None
    )
    marked: list[MediaRecord] = []
    for record in records:
        duplicate = (
            record.sha256 is not None and exact[record.sha256] > 1
        ) or (
            record.perceptual_hash is not None and perceptual[record.perceptual_hash] > 1
        )
        marked.append(
            MediaRecord(
                **{
                    **asdict(record),
                    "classification": "D_DUPLICATE_OR_INVALID"
                    if duplicate
                    else record.classification,
                }
            )
        )
    return marked


def build_report(records: list[MediaRecord]) -> dict[str, Any]:
    """Consolida uma matriz A/B/C/D sem alegar permissões não verificadas."""
    by_category = Counter(record.category for record in records)
    by_format = Counter(record.format or "unknown" for record in records)
    by_classification = Counter(record.classification for record in records)
    exact_groups: dict[str, list[str]] = defaultdict(list)
    perceptual_groups: dict[str, list[str]] = defaultdict(list)
    for record in records:
        if record.sha256:
            exact_groups[record.sha256].append(record.relative_path)
        if record.perceptual_hash:
            perceptual_groups[record.perceptual_hash].append(record.relative_path)
    return {
        "schemaVersion": 1,
        "summary": {
            "files": len(records),
            "categories": dict(sorted(by_category.items())),
            "formats": dict(sorted(by_format.items())),
            "withAlpha": sum(record.has_alpha is True for record in records),
            "matrix": {
                "A_IMPORTABLE": 0,
                "B_RUNTIME_RECIPE": 0,
                "C_REFERENCE_UNVERIFIED": by_classification["C_REFERENCE_UNVERIFIED"],
                "D_DUPLICATE_OR_INVALID": by_classification["D_DUPLICATE_OR_INVALID"],
            },
            "exactDuplicateGroups": sum(len(items) > 1 for items in exact_groups.values()),
            "perceptualDuplicateGroups": sum(
                len(items) > 1 for items in perceptual_groups.values()
            ),
        },
        "records": [asdict(record) for record in records],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="raiz externa somente leitura")
    parser.add_argument("--output", type=Path, help="arquivo JSON de relatório (opcional)")
    parser.add_argument(
        "--max-files", type=int, help="limita a amostra; omita para auditar tudo"
    )
    parser.add_argument(
        "--summary-only", action="store_true", help="não inclui registros individuais no stdout"
    )
    args = parser.parse_args()
    if not args.root.is_dir() or args.root.is_symlink():
        parser.error("root precisa ser um diretório real, não um link simbólico")
    if args.max_files is not None and args.max_files < 1:
        parser.error("--max-files precisa ser positivo")
    report = build_report(inspect_media(args.root, max_files=args.max_files))
    if args.output is not None:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    payload = report["summary"] if args.summary_only else report
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
