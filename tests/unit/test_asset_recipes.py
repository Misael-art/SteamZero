# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero.domain.asset_recipes import (
    DEFAULT_ASSET_CAPABILITIES,
    AssetRecipeBook,
    AssetRecipeCache,
    AssetRecipeNode,
    AssetRecipeNodeType,
    CachePressure,
    resolve_asset_recipes,
    validate_asset_source,
)
from steamzero.domain.theme_editor import ThemeEditorManager
from steamzero.domain.theme_effects import PerformanceTier

PACKAGE = Path("src/steamzero/themes/org.steamzero.asset-recipes-demo")
MANIFEST = PACKAGE / "theme.json"
VISUAL_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".avif", ".svg"})


def _raw_book() -> dict[str, object]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    raw = payload["assetRecipes"]
    assert isinstance(raw, dict)
    return raw


def _book() -> AssetRecipeBook:
    return AssetRecipeBook.from_dict(_raw_book())


def test_package_contains_one_visual_source_and_no_derivatives() -> None:
    visuals = sorted(
        path.relative_to(PACKAGE).as_posix()
        for path in PACKAGE.rglob("*")
        if path.is_file() and path.suffix.lower() in VISUAL_SUFFIXES
    )
    assert visuals == ["assets/source.svg"]
    assert not any(
        part in {"cache", "derived", "variants"}
        for path in PACKAGE.rglob("*")
        for part in path.parts
    )


def test_one_source_declares_every_required_variant() -> None:
    book = _book()
    assert book.source_slot == "logo"
    assert {
        "original",
        "colored",
        "grayscale",
        "black",
        "white",
        "invert",
        "hueShift",
        "outlineThin",
        "outlineThick",
        "outlineInner",
        "outlinedGlow",
        "outlinedShadow",
    } <= set(book.recipes)
    assert {recipe.source_slot for recipe in book.recipes.values()} == {"logo"}


def test_outline_uses_alpha_and_thin_and_thick_are_distinct() -> None:
    book = _book()
    thin = book.recipes["outlineThin"].node(AssetRecipeNodeType.OUTLINE)
    thick = book.recipes["outlineThick"].node(AssetRecipeNodeType.OUTLINE)
    assert thin.parameters["mask"] == "alpha"
    assert thick.parameters["mask"] == "alpha"
    assert float(thin.parameters["width"]) < float(thick.parameters["width"])


def test_recipe_nodes_are_allowlisted_and_reject_code() -> None:
    with pytest.raises(ValueError, match="não permitidos"):
        AssetRecipeNode.from_dict({"type": "recolor", "color": "#22d3ee", "qml": "evil.qml"})
    with pytest.raises(ValueError, match="desconhecido"):
        AssetRecipeNode.from_dict({"type": "shader", "source": "evil.frag"})


@pytest.mark.parametrize(
    "active_content",
    [
        b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>',
        b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>',
        b'<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>',
    ],
)
def test_svg_source_rejects_active_content(active_content: bytes) -> None:
    with pytest.raises(ValueError, match=r"conteúdo ativo|event handler"):
        validate_asset_source(active_content)


def test_builtin_preview_consumes_resolved_asset_recipes() -> None:
    loaded = ThemeEditorManager().load("org.steamzero.asset-recipes-demo")
    preview = loaded["preview"]
    assert isinstance(preview, dict)
    recipes = preview["assetRecipes"]
    assert isinstance(recipes, dict)
    assert recipes["colored"]["nodes"][0]["capability"] == "graphics.asset.recolor"
    assert recipes["outlineThin"]["nodes"][0]["parameters"]["mask"] == "alpha"
    assert preview["reducedMotion"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "outline", "width": 0, "color": "#ffffff", "mask": "alpha"},
        {"type": "outline", "width": 65, "color": "#ffffff", "mask": "alpha"},
        {"type": "outline", "width": 2, "color": "white", "mask": "alpha"},
        {"type": "outline", "width": 2, "color": "#ffffff", "opacity": 1.1, "mask": "alpha"},
        {"type": "outline", "width": 2, "color": "#ffffff", "mask": "rgb"},
    ],
)
def test_outline_limits_and_colors_are_validated(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        AssetRecipeNode.from_dict(payload)


def test_node_count_and_cost_are_bounded() -> None:
    nodes = [{"type": "grayscale"}] * 13
    with pytest.raises(ValueError, match="nodes"):
        AssetRecipeBook.from_dict(
            {
                "schemaVersion": 1,
                "sourceSlot": "logo",
                "recipes": {"tooMany": {"source": "logo", "nodes": nodes}},
            }
        )

    costly = AssetRecipeBook.from_dict(
        {
            "schemaVersion": 1,
            "sourceSlot": "logo",
            "recipes": {
                "costly": {
                    "source": "logo",
                    "nodes": [
                        {"type": "outline", "width": 16, "color": "#ffffff", "mask": "alpha"},
                        {"type": "glow", "color": "#ffffff", "strength": 1, "blur": 48},
                    ],
                }
            },
        }
    )
    resolved, diagnostics = resolve_asset_recipes(
        costly,
        capabilities=DEFAULT_ASSET_CAPABILITIES,
        tier=PerformanceTier.ECONOMY,
    )
    assert resolved["costly"].nodes == ()
    assert any("orçamento" in item.reason for item in diagnostics)


def test_missing_capability_has_diagnostic_and_safe_source_fallback() -> None:
    resolved, diagnostics = resolve_asset_recipes(
        _book(), capabilities=frozenset(), tier=PerformanceTier.CINEMATIC
    )
    assert all(recipe.source_slot == "logo" for recipe in resolved.values())
    assert resolved["colored"].nodes == ()
    assert resolved["outlineThick"].nodes == ()
    assert diagnostics
    assert all(item.fallback == "source" for item in diagnostics)


def test_inner_outline_degrades_to_outer_when_only_outer_is_available() -> None:
    capabilities = DEFAULT_ASSET_CAPABILITIES - {"graphics.asset.outline.inner"}
    resolved, diagnostics = resolve_asset_recipes(
        _book(), capabilities=capabilities, tier=PerformanceTier.CINEMATIC
    )
    outline = resolved["outlineInner"].node(AssetRecipeNodeType.OUTLINE)
    assert outline.parameters["position"] == "outer"
    assert any(item.recipe == "outlineInner" and item.fallback == "outer" for item in diagnostics)


def test_reduced_motion_does_not_remove_static_variants() -> None:
    normal, _ = resolve_asset_recipes(
        _book(), capabilities=DEFAULT_ASSET_CAPABILITIES, tier=PerformanceTier.BALANCED
    )
    reduced, _ = resolve_asset_recipes(
        _book(),
        capabilities=DEFAULT_ASSET_CAPABILITIES,
        tier=PerformanceTier.BALANCED,
        reduced_motion=True,
    )
    assert {name: recipe.to_dict() for name, recipe in normal.items()} == {
        name: recipe.to_dict() for name, recipe in reduced.items()
    }


def test_cache_key_covers_source_recipe_size_scale_tier_and_capabilities() -> None:
    source = (PACKAGE / "assets/source.svg").read_bytes()
    resolved, _ = resolve_asset_recipes(
        _book(), capabilities=DEFAULT_ASSET_CAPABILITIES, tier=PerformanceTier.CINEMATIC
    )
    cache = AssetRecipeCache(max_entries=8)

    base = cache.prepare(
        source,
        resolved["colored"],
        size=(320, 180),
        scale=1.0,
        tier=PerformanceTier.CINEMATIC,
        capabilities=DEFAULT_ASSET_CAPABILITIES,
    )
    assert cache.source_decodes == 1
    same_source_new_color = cache.prepare(
        source,
        resolved["black"],
        size=(320, 180),
        scale=1.0,
        tier=PerformanceTier.CINEMATIC,
        capabilities=DEFAULT_ASSET_CAPABILITIES,
    )
    assert cache.source_decodes == 1
    assert same_source_new_color.source_hash == base.source_hash
    assert same_source_new_color.cache_key != base.cache_key

    mutations = (
        {"size": (640, 360)},
        {"scale": 1.25},
        {"tier": PerformanceTier.BALANCED},
        {"capabilities": frozenset({"graphics.asset.recolor"})},
    )
    for mutation in mutations:
        arguments = {
            "size": (320, 180),
            "scale": 1.0,
            "tier": PerformanceTier.CINEMATIC,
            "capabilities": DEFAULT_ASSET_CAPABILITIES,
        }
        arguments.update(mutation)
        changed = cache.prepare(source, resolved["colored"], **arguments)
        assert changed.cache_key != base.cache_key


def test_contract_and_hashes_are_deterministic() -> None:
    source = (PACKAGE / "assets/source.svg").read_bytes()
    resolved, first_diagnostics = resolve_asset_recipes(
        _book(), capabilities=DEFAULT_ASSET_CAPABILITIES, tier=PerformanceTier.BALANCED
    )
    repeated, second_diagnostics = resolve_asset_recipes(
        _book(), capabilities=DEFAULT_ASSET_CAPABILITIES, tier=PerformanceTier.BALANCED
    )
    first = AssetRecipeCache(max_entries=4).prepare(
        source,
        resolved["outlineThin"],
        size=(320, 180),
        scale=1.0,
        tier=PerformanceTier.BALANCED,
        capabilities=DEFAULT_ASSET_CAPABILITIES,
    )
    second = AssetRecipeCache(max_entries=4).prepare(
        source,
        resolved["outlineThin"],
        size=(320, 180),
        scale=1.0,
        tier=PerformanceTier.BALANCED,
        capabilities=DEFAULT_ASSET_CAPABILITIES,
    )
    assert first.cache_key == second.cache_key
    assert first.recipe_hash == second.recipe_hash
    assert {name: recipe.to_dict() for name, recipe in resolved.items()} == {
        name: recipe.to_dict() for name, recipe in repeated.items()
    }
    assert [item.to_dict() for item in first_diagnostics] == [
        item.to_dict() for item in second_diagnostics
    ]


def test_adaptive_cache_has_512_mib_ceiling_without_preallocation() -> None:
    cache = AssetRecipeCache()
    assert cache.configured_max_bytes == 512 * 1024 * 1024
    assert cache.effective_max_bytes == 512 * 1024 * 1024
    assert cache.resident_bytes == 0
    assert len(cache) == 0


def test_adaptive_cache_evicts_lru_by_estimated_rgba_bytes() -> None:
    source = (PACKAGE / "assets/source.svg").read_bytes()
    resolved, _ = resolve_asset_recipes(_book(), tier=PerformanceTier.BALANCED)
    cache = AssetRecipeCache(max_entries=8, max_bytes=80_000)
    first = cache.prepare(
        source,
        resolved["colored"],
        size=(100, 100),
        scale=1,
        tier=PerformanceTier.BALANCED,
        capabilities=DEFAULT_ASSET_CAPABILITIES,
    )
    second = cache.prepare(
        source,
        resolved["black"],
        size=(100, 100),
        scale=1,
        tier=PerformanceTier.BALANCED,
        capabilities=DEFAULT_ASSET_CAPABILITIES,
    )
    cache.prepare(
        source,
        resolved["colored"],
        size=(100, 100),
        scale=1,
        tier=PerformanceTier.BALANCED,
        capabilities=DEFAULT_ASSET_CAPABILITIES,
    )
    third = cache.prepare(
        source,
        resolved["white"],
        size=(100, 100),
        scale=1,
        tier=PerformanceTier.BALANCED,
        capabilities=DEFAULT_ASSET_CAPABILITIES,
    )
    assert first.cached and third.cached
    assert cache.contains(first.cache_key)
    assert not cache.contains(second.cache_key)
    assert cache.contains(third.cache_key)
    assert cache.resident_bytes == 80_000


def test_memory_pressure_reduces_budget_and_oversize_degrades_without_disappearing() -> None:
    source = (PACKAGE / "assets/source.svg").read_bytes()
    resolved, _ = resolve_asset_recipes(_book(), tier=PerformanceTier.CINEMATIC)
    cache = AssetRecipeCache(max_entries=8, max_bytes=160_000)
    variants = [
        cache.prepare(
            source,
            resolved[name],
            size=(100, 100),
            scale=1,
            tier=PerformanceTier.CINEMATIC,
            capabilities=DEFAULT_ASSET_CAPABILITIES,
        )
        for name in ("colored", "black", "white", "grayscale")
    ]
    assert cache.resident_bytes == 160_000

    cache.set_pressure(CachePressure.CRITICAL)
    assert cache.effective_max_bytes == 40_000
    assert cache.resident_bytes == 40_000
    assert sum(cache.contains(item.cache_key) for item in variants) == 1

    oversized = cache.prepare(
        source,
        resolved["outlineThick"],
        size=(200, 200),
        scale=1,
        tier=PerformanceTier.CINEMATIC,
        capabilities=DEFAULT_ASSET_CAPABILITIES,
    )
    assert oversized.cached is False
    assert oversized.fallback == "render-direct"
    assert cache.resident_bytes == 40_000

    cache.set_pressure(CachePressure.NORMAL)
    assert cache.effective_max_bytes == 160_000
    assert cache.resident_bytes == 40_000
