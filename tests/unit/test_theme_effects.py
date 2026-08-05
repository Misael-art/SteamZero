from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from steamzero.domain.media_recipes import (
    MediaRecipe,
    MediaRole,
    MediaSourceKind,
    choose_media_source,
    parse_media_recipes,
)
from steamzero.domain.theme_effects import (
    ALL_EFFECT_CAPABILITIES,
    EffectSpec,
    EffectType,
    PerformanceTier,
    parse_effect_stacks,
    resolve_effect_stacks,
)
from steamzero.domain.themes import ThemeManifest, ThemeResolver

_SCHEMA = Path("src/steamzero/schemas/theme-manifest-v1.schema.json")


def _stacks() -> dict[str, tuple[EffectSpec, ...]]:
    return {
        "backdrop": (
            EffectSpec.from_dict({"type": "blur", "radius": 32}),
            EffectSpec.from_dict({"type": "reflection", "opacity": 0.4}),
        )
    }


def test_effect_stack_is_closed_and_parameter_bounds_are_checked() -> None:
    with pytest.raises(ValueError, match="não permitidos"):
        EffectSpec.from_dict({"type": "blur", "shader": "unsafe"})
    with pytest.raises(ValueError, match="fora"):
        EffectSpec.from_dict({"type": "blur", "radius": 65})


def test_direct_manifest_parsing_rejects_an_untyped_effect_namespace() -> None:
    with pytest.raises(ValueError, match="effects precisa"):
        ThemeManifest.from_dict({"effects": []})


def test_schema_refuses_code_and_unknown_effect_properties() -> None:
    schema = json.loads(_SCHEMA.read_text(encoding="utf-8"))
    manifest = {
        "schemaVersion": 1,
        "kind": "steamzero-theme-v1",
        "id": "org.test.effects",
        "name": "Effects",
        "version": "1.0.0",
        "author": "Test",
        "license": "MIT",
        "compatibility": {"themeApi": 1},
        "effects": {
            "schemaVersion": 1,
            "stacks": {"backdrop": [{"type": "blur", "qml": "evil.qml"}]},
        },
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(manifest, schema)


def test_missing_capability_omits_effect_and_records_diagnostic() -> None:
    effects, diagnostics = resolve_effect_stacks(_stacks(), capabilities=frozenset())
    assert effects["backdrop"] == ()
    assert [item.effect for item in diagnostics] == [EffectType.BLUR, EffectType.REFLECTION]
    assert all("capability ausente" in item.reason for item in diagnostics)


def test_balanced_scales_only_declared_costly_parameters() -> None:
    effects, diagnostics = resolve_effect_stacks(
        _stacks(), capabilities=ALL_EFFECT_CAPABILITIES, tier=PerformanceTier.BALANCED
    )
    assert not diagnostics
    assert effects["backdrop"][0].parameters["radius"] == 16.0
    assert effects["backdrop"][1].parameters["opacity"] == 0.2


@pytest.mark.parametrize("tier", [PerformanceTier.ECONOMY, PerformanceTier.ACCESSIBLE])
def test_economy_and_accessible_have_deterministic_fallbacks(tier: PerformanceTier) -> None:
    effects, diagnostics = resolve_effect_stacks(
        _stacks(),
        capabilities=ALL_EFFECT_CAPABILITIES,
        tier=tier,
        high_contrast=tier is PerformanceTier.ACCESSIBLE,
    )
    assert effects["backdrop"] == ()
    assert len(diagnostics) == 2


def test_reduced_motion_removes_reflection_but_keeps_static_blur() -> None:
    effects, diagnostics = resolve_effect_stacks(
        _stacks(), capabilities=ALL_EFFECT_CAPABILITIES, reduced_motion=True
    )
    assert [item.type for item in effects["backdrop"]] == [EffectType.BLUR]
    assert diagnostics[0].effect is EffectType.REFLECTION


def test_manifest_effects_merge_and_negotiation_are_exposed() -> None:
    manifest = ThemeManifest(
        id="org.test.effects",
        name="Effects",
        version="1.0.0",
        author="Test",
        license="MIT",
        effects=_stacks(),
    )
    resolved = ThemeResolver({manifest.id: manifest}).resolve(
        manifest.id, effect_capabilities=frozenset({"graphics.effect.blur"})
    )
    assert [item.type for item in resolved.effects["backdrop"]] == [EffectType.BLUR]
    assert resolved.effect_diagnostics[0].effect is EffectType.REFLECTION


def test_theme_resolver_records_the_accessibility_fallback() -> None:
    manifest = ThemeManifest(
        id="org.test.contrast",
        name="Contrast",
        version="1.0.0",
        author="Test",
        license="MIT",
        effects=_stacks(),
    )
    resolved = ThemeResolver({manifest.id: manifest}).resolve(
        manifest.id, effect_capabilities=ALL_EFFECT_CAPABILITIES, high_contrast=True
    )
    assert resolved.effects["backdrop"] == ()
    assert all("contraste" in item.reason for item in resolved.effect_diagnostics)


def test_effect_namespace_round_trips_with_its_own_version() -> None:
    raw = {"schemaVersion": 1, "stacks": {"cover": [{"type": "opacity", "amount": 0.5}]}}
    parsed = parse_effect_stacks(raw)
    manifest = ThemeManifest(
        id="org.test.roundtrip",
        name="Roundtrip",
        version="1.0.0",
        author="Test",
        license="MIT",
        effects=parsed,
    )
    assert manifest.to_dict()["effects"] == {
        "schemaVersion": 1,
        "stacks": {"cover": [{"type": "opacity", "amount": 0.5, "fallback": "omit"}]},
    }


def test_renderer_uses_one_source_and_never_accepts_a_theme_shader() -> None:
    component = Path("src/steamzero/ui/qml/MediaEffectLayer.qml").read_text(encoding="utf-8")
    assert component.count("source: root.source") == 1
    assert "source: mediaTexture" in component
    assert "ShaderEffect {" not in component
    assert "ReflectionLayer" in component
    assert "VignetteLayer" in component


def test_default_renderer_negotiates_trusted_reflection_and_gradient_mask() -> None:
    stacks = {
        "media": (
            EffectSpec.from_dict({"type": "reflection", "opacity": 0.3, "scale": 0.2}),
            EffectSpec.from_dict({"type": "gradientMask", "start": 0.8, "end": 0.1}),
        )
    }
    effects, diagnostics = resolve_effect_stacks(stacks)
    assert not diagnostics
    assert [effect.type for effect in effects["media"]] == [
        EffectType.REFLECTION,
        EffectType.GRADIENT_MASK,
    ]


def test_editorial_library_accepts_semantic_navigation_without_raw_key_capture() -> None:
    component = Path("src/steamzero/ui/qml/EditorialLibrary.qml").read_text(encoding="utf-8")
    assert "function handleNavigationIntent(intent)" in component
    assert "Keys." not in component


def test_typography_roles_are_versioned_and_reach_the_theme_qml_payload() -> None:
    manifest = ThemeManifest(
        id="org.test.typography",
        name="Typography",
        version="1.0.0",
        author="Test",
        license="MIT",
        tokens={"typography": {"display": 40, "caption": 13, "diagnostic": 15}},
    )
    resolved = ThemeResolver({manifest.id: manifest}).resolve(manifest.id)
    typography = resolved.to_theme_qml_object()["resolved"]["typography"]
    assert typography["display"] == 40
    assert typography["caption"] == 13
    assert typography["diagnostic"] == 15


def test_media_recipe_selects_one_published_source_without_io() -> None:
    recipe = MediaRecipe(
        role=MediaRole.CONTEXTUAL_BACKDROP,
        source_order=(MediaSourceKind.HERO, MediaSourceKind.COVER, MediaSourceKind.GEOMETRIC),
        effect_stack="backdrop",
    )
    assert choose_media_source(recipe, {"cover": "file:///cover.png"}) == (
        MediaSourceKind.COVER,
        "file:///cover.png",
    )
    assert choose_media_source(recipe, {}) is None


def test_media_recipe_is_versioned_and_requires_known_effect_stack() -> None:
    raw = {
        "schemaVersion": 1,
        "recipes": {
            "focusedCover": {
                "sourceOrder": ["cover", "hero"],
                "fit": "contain",
                "effectStack": "focusedCover",
                "maxDecodeWidth": 1024,
            }
        },
    }
    recipes = parse_media_recipes(raw)
    manifest = ThemeManifest(
        id="org.test.recipe",
        name="Recipe",
        version="1.0.0",
        author="Test",
        license="MIT",
        effects={"focusedCover": ()},
        media_recipes=recipes,
    )
    resolved = ThemeResolver({manifest.id: manifest}).resolve(manifest.id)
    assert resolved.to_theme_qml_object()["mediaRecipes"]["focusedCover"]["fit"] == "contain"
