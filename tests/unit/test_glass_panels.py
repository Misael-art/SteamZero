# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato executável do node de vidro com fallback sem backbuffer."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from steamzero.domain.dynamic_palette import extract_dynamic_palette
from steamzero.domain.glass_panels import (
    DIAG_GLASS_TIER,
    GlassBook,
    resolve_glass_panels,
)
from steamzero.domain.theme_effects import PerformanceTier

SCHEMA = json.loads(
    Path("src/steamzero/schemas/glass-panel-v1.schema.json").read_text(encoding="utf-8")
)


def _book() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "panels": {
            "previewCard": {
                "blur": 24,
                "tint": {"binding": "palette.accent", "fallback": "#132833"},
                "tintOpacity": 0.42,
                "borderColor": "#ffffff",
                "borderOpacity": 0.28,
                "highlightOpacity": 0.16,
                "shadowOpacity": 0.32,
                "sampleScale": 0.5,
                "fallback": "flat",
            }
        },
    }


def _palette() -> dict[str, str]:
    return extract_dynamic_palette(
        {
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
        },
        pixels=[(34, 211, 238)] * 40,
    ).swatches


def test_schema_and_domain_accept_the_same_closed_glass_recipe() -> None:
    raw = _book()
    jsonschema.validate(raw, SCHEMA)
    book = GlassBook.from_dict(raw)
    assert set(book.panels) == {"previewCard"}


def test_glass_binds_extracted_accent_and_keeps_static_chrome() -> None:
    resolved = resolve_glass_panels(_book(), palette=_palette(), tier=PerformanceTier.CINEMATIC)
    panel = resolved.panels["previewCard"]
    assert panel.tint == "#22d3ee"
    assert panel.blur == 24.0
    assert panel.sample_scale == 0.5
    assert panel.blur_enabled is True
    assert panel.border_opacity == 0.28
    assert panel.fallback == "none"


def test_economy_and_missing_capability_flatten_blur_with_diagnostic() -> None:
    economy = resolve_glass_panels(_book(), palette=_palette(), tier=PerformanceTier.ECONOMY)
    assert economy.panels["previewCard"].blur_enabled is False
    assert economy.panels["previewCard"].tint == "#22d3ee"
    assert any(item.code == DIAG_GLASS_TIER for item in economy.diagnostics)
    missing = resolve_glass_panels(
        _book(),
        palette=_palette(),
        capabilities=frozenset(),
    )
    assert missing.panels["previewCard"].blur_enabled is False
    assert missing.panels["previewCard"].fallback == "flat"


def test_recipe_refuses_shader_code_and_excessive_cost() -> None:
    with pytest.raises(ValueError, match="blur"):
        GlassBook.from_dict(
            {
                "schemaVersion": 1,
                "panels": {"bad": {"blur": 96, "tint": "#132833"}},
            }
        )
    with pytest.raises(ValueError, match=r"binding|inválid"):
        GlassBook.from_dict(
            {
                "schemaVersion": 1,
                "panels": {
                    "bad": {
                        "blur": 8,
                        "tint": {"binding": "game.__class__", "fallback": "#000000"},
                    }
                },
            }
        )
    raw = _book()
    raw["panels"]["previewCard"]["shader"] = "evil.frag"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(raw, SCHEMA)
