# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Nomes canônicos para apresentação e busca tolerante de mídia."""

from __future__ import annotations

import re
from collections.abc import Sequence

TITLE_VARIANT_MODES = ("full", "extensionless", "clean")

# Evita interpretar um ponto legítimo no nome (por exemplo, ``Version 1.0``)
# como extensão.
_MEDIA_EXTENSIONS = frozenset(
    {
        ".7z",
        ".bin",
        ".cbz",
        ".chd",
        ".cue",
        ".fds",
        ".gb",
        ".gba",
        ".gbc",
        ".gcz",
        ".gen",
        ".iso",
        ".md",
        ".mds",
        ".nds",
        ".nes",
        ".nsp",
        ".nsz",
        ".pbp",
        ".rar",
        ".rom",
        ".rvz",
        ".sfc",
        ".smc",
        ".sms",
        ".tar",
        ".wbfs",
        ".wud",
        ".xci",
        ".zip",
    }
)
_TRAILING_TAG = re.compile(r"\s*(?:\([^()]*\)|\[[^\[\]]*\])$")


def _without_media_extension(value: str) -> str:
    text = value.rstrip()
    dot = text.rfind(".")
    if dot <= 0 or text[dot:].casefold() not in _MEDIA_EXTENSIONS:
        return text
    return text[:dot].rstrip()


def title_variants(value: str) -> tuple[str, ...]:
    """Retorna o nome original e formas progressivamente tratadas."""
    original = str(value)
    if not original.strip():
        return ()

    variants: list[str] = [original]
    extensionless = _without_media_extension(original)
    if extensionless not in variants:
        variants.append(extensionless)

    current = extensionless
    while True:
        match = _TRAILING_TAG.search(current)
        if match is None:
            break
        current = current[: match.start()].rstrip()
        if not current or current in variants:
            break
        variants.append(current)
    return tuple(variants)


def select_title_variant(value: str, mode: str = "full") -> str:
    """Seleciona o rótulo da UI sem modificar o nome armazenado."""
    if mode not in TITLE_VARIANT_MODES:
        raise ValueError(f"modo de título desconhecido: {mode}")
    variants = title_variants(value)
    if not variants:
        return ""
    if mode == "extensionless":
        return variants[1] if len(variants) > 1 else variants[0]
    if mode == "clean":
        return variants[-1]
    return variants[0]


def normalize_title_variants(values: Sequence[str]) -> tuple[str, ...]:
    """Normaliza variantes fornecidas por uma fonte externa sem duplicatas."""
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in result:
            result.append(text)
    return tuple(result)
