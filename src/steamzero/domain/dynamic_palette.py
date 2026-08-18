# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Extração declarativa de paleta a partir de um asset-fonte.

A análise roda fora do frame, é cacheada pelo hash da fonte e nunca executa
código do pacote. Falha devolve a paleta determinística do tema com diagnóstico.
"""

from __future__ import annotations

import colorsys
import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from steamzero.domain.asset_recipes import validate_asset_source

DIAG_PALETTE_SOURCE = "THEME-PALETTE-SOURCE-001"
SWATCH_NAMES = (
    "dominant",
    "vibrant",
    "lightVibrant",
    "darkVibrant",
    "muted",
    "lightMuted",
    "darkMuted",
    "complementary",
    "accent",
    "background",
    "contrastText",
)
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_SLOT = re.compile(r"^[a-z][a-zA-Z0-9]{0,31}$")
_SVG_COLOR = re.compile(rb"(?:stop-color|fill)=['\"](#(?:[0-9a-fA-F]{6}))['\"]")


def _hex(value: Any, *, name: str) -> str:
    if not isinstance(value, str) or not _COLOR.fullmatch(value):
        raise ValueError(f"{name} inválida")
    return value.lower()


def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _to_hex(rgb: tuple[float, float, float]) -> str:
    red, green, blue = (max(0, min(255, round(channel))) for channel in rgb)
    return f"#{red:02x}{green:02x}{blue:02x}"


def _relative_luminance(color: str) -> float:
    def _channel(value: int) -> float:
        normalized = value / 255.0
        return (
            normalized / 12.92 if normalized <= 0.03928 else ((normalized + 0.055) / 1.055) ** 2.4
        )

    red, green, blue = _rgb(color)
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def palette_contrast_ratio(left: str, right: str) -> float:
    first, second = _relative_luminance(left), _relative_luminance(right)
    lighter, darker = (first, second) if first >= second else (second, first)
    return (lighter + 0.05) / (darker + 0.05)


def _promote_contrast(background: str, text: str, *, minimum: float = 7.0) -> str:
    if palette_contrast_ratio(background, text) >= minimum:
        return text
    white = palette_contrast_ratio(background, "#ffffff")
    black = palette_contrast_ratio(background, "#000000")
    return "#ffffff" if white >= black else "#000000"


def _hsl(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    return colorsys.rgb_to_hls(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)


def _complementary(color: str) -> str:
    hue, lightness, saturation = _hsl(_rgb(color))
    red, green, blue = colorsys.hls_to_rgb((hue + 0.5) % 1.0, lightness, saturation)
    return _to_hex((red * 255.0, green * 255.0, blue * 255.0))


@dataclass(frozen=True)
class PaletteRecipe:
    source_slot: str
    algorithm: str
    fallback: Mapping[str, str]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("schemaVersion de dynamicPalette inválido")
        if not _SLOT.fullmatch(self.source_slot):
            raise ValueError("sourceSlot inválido")
        if self.algorithm not in {"medianCut", "kmeans", "families"}:
            raise ValueError("algorithm inválido")
        if set(self.fallback) != set(SWATCH_NAMES):
            raise ValueError("fallback de paleta incompleto")
        for name, value in self.fallback.items():
            _hex(value, name=f"fallback.{name}")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> PaletteRecipe:
        unknown = set(raw) - {"schemaVersion", "sourceSlot", "algorithm", "fallback"}
        if unknown:
            raise ValueError(f"dynamicPalette inválido: {sorted(unknown)}")
        required = {"sourceSlot", "algorithm", "fallback"}
        if not required <= set(raw):
            raise ValueError("dynamicPalette inválido")
        fallback = raw["fallback"]
        if not isinstance(fallback, Mapping):
            raise ValueError("fallback exige objeto")
        return cls(
            source_slot=str(raw["sourceSlot"]),
            algorithm=str(raw["algorithm"]),
            fallback={
                name: _hex(fallback.get(name), name=f"fallback.{name}") for name in SWATCH_NAMES
            },
            schema_version=raw.get("schemaVersion", 1),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "sourceSlot": self.source_slot,
            "algorithm": self.algorithm,
            "fallback": dict(self.fallback),
        }


@dataclass(frozen=True)
class PaletteDiagnostic:
    code: str
    reason: str
    fallback: str = "theme"

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "reason": self.reason, "fallback": self.fallback}


@dataclass(frozen=True)
class ExtractedPalette:
    swatches: Mapping[str, str]
    cache_key: str
    algorithm: str
    diagnostics: tuple[PaletteDiagnostic, ...] = ()

    def to_qml_object(self) -> dict[str, Any]:
        return {
            "swatches": dict(self.swatches),
            "cacheKey": self.cache_key,
            "algorithm": self.algorithm,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


def _mean(bucket: Sequence[tuple[int, int, int]]) -> tuple[float, float, float]:
    count = len(bucket) or 1
    return (
        sum(item[0] for item in bucket) / count,
        sum(item[1] for item in bucket) / count,
        sum(item[2] for item in bucket) / count,
    )


def _split(
    bucket: Sequence[tuple[int, int, int]], *, depth: int
) -> list[list[tuple[int, int, int]]]:
    if not bucket or depth <= 0 or len(bucket) < 2:
        return [list(bucket)] if bucket else []
    ranges = (
        max(item[0] for item in bucket) - min(item[0] for item in bucket),
        max(item[1] for item in bucket) - min(item[1] for item in bucket),
        max(item[2] for item in bucket) - min(item[2] for item in bucket),
    )
    axis = ranges.index(max(ranges))
    ordered = sorted(bucket, key=lambda item: item[axis])
    mid = len(ordered) // 2
    return [*_split(ordered[:mid], depth=depth - 1), *_split(ordered[mid:], depth=depth - 1)]


def _score(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    hue, lightness, saturation = colorsys.rgb_to_hls(rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)
    return saturation, lightness, hue


def _pick(
    buckets: Sequence[tuple[tuple[float, float, float], int]],
    *,
    sat: tuple[float, float],
    light: tuple[float, float],
    fallback: tuple[float, float, float],
) -> tuple[float, float, float]:
    ranked = [
        (count * (1.0 + saturation), color)
        for color, count in buckets
        for saturation, lightness, _hue in (_score(color),)
        if sat[0] <= saturation <= sat[1] and light[0] <= lightness <= light[1]
    ]
    if not ranked:
        return fallback
    return max(ranked, key=lambda item: item[0])[1]


def _quantize(
    pixels: Sequence[tuple[int, int, int]], *, algorithm: str
) -> list[tuple[tuple[float, float, float], int]]:
    if algorithm == "kmeans":
        depth = 3
    elif algorithm == "families":
        depth = 2
    else:
        depth = 3
    buckets = [bucket for bucket in _split(pixels, depth=depth) if bucket]
    return [(_mean(bucket), len(bucket)) for bucket in buckets]


def _pixels_from_source(source: bytes | None) -> list[tuple[int, int, int]]:
    if not source:
        return []
    validate_asset_source(source)
    colors = [_rgb(match.group(1).decode("ascii")) for match in _SVG_COLOR.finditer(source)]
    expanded: list[tuple[int, int, int]] = []
    for index, color in enumerate(colors):
        expanded.extend([color] * (80 - index * 20))
    return expanded


def extract_dynamic_palette(
    raw_recipe: Mapping[str, Any] | PaletteRecipe,
    *,
    pixels: Sequence[tuple[int, int, int]] | None = None,
    source: bytes | None = None,
) -> ExtractedPalette:
    recipe = (
        raw_recipe if isinstance(raw_recipe, PaletteRecipe) else PaletteRecipe.from_dict(raw_recipe)
    )
    population = list(pixels or ())
    if not population:
        population = _pixels_from_source(source)
    cache_key = hashlib.sha256(
        b"\0".join(
            (
                recipe.algorithm.encode(),
                recipe.source_slot.encode(),
                source or repr(population[:32]).encode(),
            )
        )
    ).hexdigest()
    if not population:
        swatches = dict(recipe.fallback)
        swatches["contrastText"] = _promote_contrast(
            swatches["background"], swatches["contrastText"]
        )
        return ExtractedPalette(
            swatches=swatches,
            cache_key=cache_key,
            algorithm=recipe.algorithm,
            diagnostics=(
                PaletteDiagnostic(
                    code=DIAG_PALETTE_SOURCE,
                    reason=f"source '{recipe.source_slot}' ausente ou sem amostras",
                ),
            ),
        )
    buckets = _quantize(population, algorithm=recipe.algorithm)
    dominant = max(buckets, key=lambda item: item[1])[0]
    vibrant = _pick(buckets, sat=(0.45, 1.0), light=(0.35, 0.75), fallback=dominant)
    light_vibrant = _pick(buckets, sat=(0.35, 1.0), light=(0.65, 0.95), fallback=vibrant)
    dark_vibrant = _pick(buckets, sat=(0.35, 1.0), light=(0.08, 0.4), fallback=vibrant)
    muted = _pick(buckets, sat=(0.05, 0.45), light=(0.3, 0.7), fallback=dominant)
    light_muted = _pick(buckets, sat=(0.05, 0.4), light=(0.6, 0.92), fallback=muted)
    dark_muted = _pick(buckets, sat=(0.05, 0.4), light=(0.08, 0.4), fallback=muted)
    background = dark_muted
    accent = vibrant
    swatches = {
        "dominant": _to_hex(dominant),
        "vibrant": _to_hex(vibrant),
        "lightVibrant": _to_hex(light_vibrant),
        "darkVibrant": _to_hex(dark_vibrant),
        "muted": _to_hex(muted),
        "lightMuted": _to_hex(light_muted),
        "darkMuted": _to_hex(dark_muted),
        "complementary": _complementary(_to_hex(dominant)),
        "accent": _to_hex(accent),
        "background": _to_hex(background),
        "contrastText": "#f2f6fb",
    }
    swatches["contrastText"] = _promote_contrast(swatches["background"], swatches["contrastText"])
    return ExtractedPalette(swatches=swatches, cache_key=cache_key, algorithm=recipe.algorithm)


class PaletteCache:
    def __init__(self) -> None:
        self._entries: dict[str, ExtractedPalette] = {}
        self.extract_count = 0

    def resolve(
        self,
        raw_recipe: Mapping[str, Any] | PaletteRecipe,
        *,
        source: bytes,
        pixels: Sequence[tuple[int, int, int]] | None = None,
    ) -> ExtractedPalette:
        recipe = (
            raw_recipe
            if isinstance(raw_recipe, PaletteRecipe)
            else PaletteRecipe.from_dict(raw_recipe)
        )
        key = hashlib.sha256(source + b"\0" + recipe.algorithm.encode()).hexdigest()
        cached = self._entries.get(key)
        if cached is not None:
            return cached
        self.extract_count += 1
        resolved = extract_dynamic_palette(recipe, pixels=pixels, source=source)
        self._entries[key] = resolved
        return resolved


def preview_palette_from_theme(
    recipe: PaletteRecipe,
    *,
    source: bytes | None = None,
) -> ExtractedPalette:
    return extract_dynamic_palette(recipe, source=source)
