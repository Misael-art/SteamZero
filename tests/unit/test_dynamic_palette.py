# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato executável de extração assíncrona e cacheada de paleta."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from steamzero.adapters.theme_catalog import ThemeCatalog
from steamzero.domain.dynamic_palette import (
    DIAG_PALETTE_SOURCE,
    PaletteCache,
    PaletteRecipe,
    extract_dynamic_palette,
    palette_contrast_ratio,
)
from steamzero.domain.theme_editor import ThemeEditorManager

SCHEMA = json.loads(
    Path("src/steamzero/schemas/dynamic-palette-v1.schema.json").read_text(encoding="utf-8")
)
REQUIRED = {
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
}


def _recipe() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "sourceSlot": "logo",
        "algorithm": "medianCut",
        "fallback": {
            "dominant": "#132833",
            "vibrant": "#22d3ee",
            "lightVibrant": "#7dd3fc",
            "darkVibrant": "#0e7490",
            "muted": "#64748b",
            "lightMuted": "#94a3b8",
            "darkMuted": "#334155",
            "complementary": "#ee3d22",
            "accent": "#22d3ee",
            "background": "#071019",
            "contrastText": "#f2f6fb",
        },
    }


def _cyan_field() -> list[tuple[int, int, int]]:
    return [(34, 211, 238)] * 80 + [(139, 92, 246)] * 30 + [(255, 107, 115)] * 20


def test_schema_and_domain_accept_the_same_closed_recipe() -> None:
    raw = _recipe()
    jsonschema.validate(raw, SCHEMA)
    parsed = PaletteRecipe.from_dict(raw)
    assert parsed.algorithm == "medianCut"
    assert parsed.source_slot == "logo"


def test_pixels_publish_required_swatches_and_readable_contrast() -> None:
    resolved = extract_dynamic_palette(_recipe(), pixels=_cyan_field())
    assert set(resolved.swatches) >= REQUIRED
    assert resolved.swatches["accent"].startswith("#")
    assert (
        palette_contrast_ratio(resolved.swatches["background"], resolved.swatches["contrastText"])
        >= 7.0
    )
    assert resolved.diagnostics == ()


def test_extraction_is_cached_by_source_hash_and_not_repeated() -> None:
    cache = PaletteCache()
    first = cache.resolve(_recipe(), source=b"source-a", pixels=_cyan_field())
    second = cache.resolve(_recipe(), source=b"source-a", pixels=_cyan_field())
    third = cache.resolve(_recipe(), source=b"source-b", pixels=[(255, 0, 0)] * 40)
    assert cache.extract_count == 2
    assert first.cache_key == second.cache_key
    assert first.swatches == second.swatches
    assert third.cache_key != first.cache_key


def test_invalid_source_falls_back_to_theme_palette_with_diagnostic() -> None:
    resolved = extract_dynamic_palette(_recipe(), pixels=[])
    assert resolved.swatches["accent"] == "#22d3ee"
    assert resolved.swatches["contrastText"] == "#f2f6fb"
    assert any(item.code == DIAG_PALETTE_SOURCE for item in resolved.diagnostics)


def test_recipe_refuses_code_unknown_algorithm_and_live_bindings() -> None:
    with pytest.raises(ValueError, match="algorithm"):
        PaletteRecipe.from_dict({**_recipe(), "algorithm": "eval"})
    with pytest.raises(ValueError, match=r"qml|inválid"):
        PaletteRecipe.from_dict({**_recipe(), "qml": "evil.qml"})
    raw = _recipe()
    raw["script"] = "Qt.quit()"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(raw, SCHEMA)


def test_builtin_preview_consumes_resolved_palette_and_keeps_accessibility() -> None:
    preview = ThemeEditorManager().load("org.steamzero.asset-recipes-demo")["preview"]
    assert isinstance(preview, dict)
    palette = preview["dynamicPalette"]
    assert set(palette["swatches"]) >= REQUIRED
    assert preview["reducedMotion"] is False
    accessible = ThemeCatalog().resolve(
        "org.steamzero.asset-recipes-demo",
        high_contrast=True,
        reduced_motion=True,
    )
    assert accessible.dynamic_palette is not None
    assert accessible.high_contrast is True
    assert accessible.reduced_motion is True
    assert accessible.color.background == "#000000"
    assert accessible.motion.durationNormal == 0
