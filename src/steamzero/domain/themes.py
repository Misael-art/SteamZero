from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from steamzero.domain.media_recipes import (
    MediaRecipe,
    media_recipes_to_dict,
    parse_media_recipes,
    validate_recipe_effect_stacks,
)
from steamzero.domain.theme_effects import (
    EffectDiagnostic,
    EffectSpec,
    PerformanceTier,
    ResolvedEffect,
    effect_stacks_to_dict,
    parse_effect_stacks,
    resolve_effect_stacks,
)

THEME_MANIFEST_SCHEMA_VERSION = 1
THEME_API_VERSION = 1
THEME_DEFAULT_ID = "org.steamzero.default"
MAX_EXTENDS_DEPTH = 2
MAX_THEMES = 100
ASSET_SLOTS_ALLOWED = frozenset({"background", "logo", "sidebar"})


@dataclass(frozen=True)
class ThemeColorTokens:
    background: str = "#e7eceb"
    sidebar: str = "#d8dfdf"
    surface: str = "#f4f7f5"
    surfaceRaised: str = "#ffffff"
    surfaceSelected: str = "#dce8e8"
    border: str = "#aebdbe"
    text: str = "#16212a"
    textMuted: str = "#53616b"
    textDisabled: str = "#7a878b"
    accent: str = "#006f99"
    accentStrong: str = "#005471"
    success: str = "#167a45"
    successSurface: str = "#dff3e7"
    warning: str = "#9a5a00"
    warningSurface: str = "#fff0d5"
    danger: str = "#ae2634"
    dangerSurface: str = "#fbe2e5"
    focus: str = "#006f99"

    def to_dict(self) -> dict[str, str]:
        return {
            "background": self.background,
            "sidebar": self.sidebar,
            "surface": self.surface,
            "surfaceRaised": self.surfaceRaised,
            "surfaceSelected": self.surfaceSelected,
            "border": self.border,
            "text": self.text,
            "textMuted": self.textMuted,
            "textDisabled": self.textDisabled,
            "accent": self.accent,
            "accentStrong": self.accentStrong,
            "success": self.success,
            "successSurface": self.successSurface,
            "warning": self.warning,
            "warningSurface": self.warningSurface,
            "danger": self.danger,
            "dangerSurface": self.dangerSurface,
            "focus": self.focus,
        }

    @staticmethod
    def from_dict(data: dict[str, str]) -> ThemeColorTokens:
        fields = ThemeColorTokens.__dataclass_fields__
        return ThemeColorTokens(**{k: v for k, v in data.items() if k in fields})


@dataclass(frozen=True)
class ThemeGeometryTokens:
    radiusSmall: int = 6
    radiusMedium: int = 10
    radiusLarge: int = 16
    borderWidth: int = 1
    focusWidth: int = 2
    minimumTarget: int = 48
    spacingSmall: int = 8
    spacingMedium: int = 16
    spacingLarge: int = 24

    def to_dict(self) -> dict[str, int]:
        return {
            "radiusSmall": self.radiusSmall,
            "radiusMedium": self.radiusMedium,
            "radiusLarge": self.radiusLarge,
            "borderWidth": self.borderWidth,
            "focusWidth": self.focusWidth,
            "minimumTarget": self.minimumTarget,
            "spacingSmall": self.spacingSmall,
            "spacingMedium": self.spacingMedium,
            "spacingLarge": self.spacingLarge,
        }

    @staticmethod
    def from_dict(data: dict[str, int]) -> ThemeGeometryTokens:
        fields = ThemeGeometryTokens.__dataclass_fields__
        return ThemeGeometryTokens(**{k: v for k, v in data.items() if k in fields})


@dataclass(frozen=True)
class ThemeTypographyTokens:
    scale: float = 1.0
    weightBody: int = 400
    weightStrong: int = 600
    weightHeading: int = 700
    display: int = 36
    heading: int = 24
    title: int = 20
    body: int = 16
    metadata: int = 14
    badge: int = 12
    caption: int = 12
    controlHint: int = 14
    diagnostic: int = 14
    family: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "scale": self.scale,
            "weightBody": self.weightBody,
            "weightStrong": self.weightStrong,
            "weightHeading": self.weightHeading,
            "display": self.display,
            "heading": self.heading,
            "title": self.title,
            "body": self.body,
            "metadata": self.metadata,
            "badge": self.badge,
            "caption": self.caption,
            "controlHint": self.controlHint,
            "diagnostic": self.diagnostic,
        }
        if self.family is not None:
            result["family"] = self.family
        return result

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ThemeTypographyTokens:
        return ThemeTypographyTokens(
            scale=data.get("scale", 1.0),
            weightBody=data.get("weightBody", 400),
            weightStrong=data.get("weightStrong", 600),
            weightHeading=data.get("weightHeading", 700),
            display=data.get("display", 36),
            heading=data.get("heading", 24),
            title=data.get("title", 20),
            body=data.get("body", 16),
            metadata=data.get("metadata", 14),
            badge=data.get("badge", 12),
            caption=data.get("caption", 12),
            controlHint=data.get("controlHint", 14),
            diagnostic=data.get("diagnostic", 14),
            family=data.get("family"),
        )


@dataclass(frozen=True)
class ThemeMotionTokens:
    durationFast: int = 120
    durationNormal: int = 180
    durationLong: int = 300
    hoverIntensity: float = 0.05
    focusIntensity: float = 0.1

    def to_dict(self) -> dict[str, Any]:
        return {
            "durationFast": self.durationFast,
            "durationNormal": self.durationNormal,
            "durationLong": self.durationLong,
            "hoverIntensity": self.hoverIntensity,
            "focusIntensity": self.focusIntensity,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ThemeMotionTokens:
        fields = ThemeMotionTokens.__dataclass_fields__
        return ThemeMotionTokens(**{k: v for k, v in data.items() if k in fields})


@dataclass(frozen=True)
class ThemeStateVariantTokens:
    """Estados visuais estáveis; o renderer anima somente sua transição."""

    focusedScale: float = 1.05
    peripheralOpacity: float = 0.58
    selectedOpacity: float = 1.0

    def to_dict(self) -> dict[str, float]:
        return {
            "focusedScale": self.focusedScale,
            "peripheralOpacity": self.peripheralOpacity,
            "selectedOpacity": self.selectedOpacity,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ThemeStateVariantTokens:
        fields = ThemeStateVariantTokens.__dataclass_fields__
        return ThemeStateVariantTokens(**{k: v for k, v in data.items() if k in fields})


@dataclass(frozen=True)
class ThemeInteractionTokens:
    """Contrato controller-first que um tema pode aprimorar, não remover."""

    focusVisible: bool = True
    minimumTarget: int = 48

    def to_dict(self) -> dict[str, Any]:
        return {"focusVisible": self.focusVisible, "minimumTarget": self.minimumTarget}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ThemeInteractionTokens:
        return ThemeInteractionTokens(
            focusVisible=bool(data.get("focusVisible", True)),
            minimumTarget=int(data.get("minimumTarget", 48)),
        )


@dataclass(frozen=True)
class ThemeAccessibilityTokens:
    """Políticas que preservam a precedência da preferência do sistema."""

    systemOverrides: bool = True

    def to_dict(self) -> dict[str, bool]:
        return {"systemOverrides": self.systemOverrides}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ThemeAccessibilityTokens:
        # Um tema não pode ignorar o sistema: false é normalizado para true.
        return ThemeAccessibilityTokens(systemOverrides=True)


@dataclass(frozen=True)
class ThemePerformanceTokens:
    defaultTier: PerformanceTier = PerformanceTier.CINEMATIC

    def to_dict(self) -> dict[str, str]:
        return {"defaultTier": self.defaultTier.value}

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ThemePerformanceTokens:
        try:
            tier = PerformanceTier(str(data.get("defaultTier", PerformanceTier.CINEMATIC.value)))
        except ValueError as exc:
            raise ValueError("defaultTier de performance inválido") from exc
        return ThemePerformanceTokens(defaultTier=tier)


@dataclass(frozen=True)
class ThemeAsset:
    slot: str
    path: str
    resolved_path: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"slot": self.slot, "path": self.path}


@dataclass(frozen=True)
class ThemeManifest:
    schemaVersion: int = THEME_MANIFEST_SCHEMA_VERSION
    kind: str = "steamzero-theme-v1"
    id: str = THEME_DEFAULT_ID
    name: str = "SteamZero"
    version: str = "1.0.0"
    author: str = "SteamZero contributors"
    license: str = "GPL-3.0-or-later"
    description: str = ""
    homepage: str | None = None
    compatibility: dict[str, Any] = field(default_factory=lambda: {"themeApi": 1})
    extends: str | None = None
    tokens: dict[str, Any] = field(default_factory=dict)
    assets: dict[str, str] = field(default_factory=dict)
    effects: dict[str, tuple[EffectSpec, ...]] = field(default_factory=dict)
    media_recipes: dict[str, MediaRecipe] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schemaVersion": self.schemaVersion,
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "license": self.license,
            "compatibility": self.compatibility,
        }
        if self.description:
            result["description"] = self.description
        if self.homepage is not None:
            result["homepage"] = self.homepage
        if self.extends is not None:
            result["extends"] = self.extends
        if self.tokens:
            result["tokens"] = self.tokens
        if self.assets:
            result["assets"] = self.assets
        if self.effects:
            result["effects"] = effect_stacks_to_dict(self.effects)
        if self.media_recipes:
            result["mediaRecipes"] = media_recipes_to_dict(self.media_recipes)
        return result

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ThemeManifest:
        raw_effects = data.get("effects")
        raw_media_recipes = data.get("mediaRecipes")
        if raw_effects is not None and not isinstance(raw_effects, dict):
            raise ValueError("effects precisa ser objeto")
        if raw_media_recipes is not None and not isinstance(raw_media_recipes, dict):
            raise ValueError("mediaRecipes precisa ser objeto")
        return ThemeManifest(
            schemaVersion=data.get("schemaVersion", THEME_MANIFEST_SCHEMA_VERSION),
            kind=data.get("kind", "steamzero-theme-v1"),
            id=data.get("id", THEME_DEFAULT_ID),
            name=data.get("name", ""),
            version=data.get("version", "0.0.0"),
            author=data.get("author", ""),
            license=data.get("license", ""),
            description=data.get("description", ""),
            homepage=data.get("homepage"),
            compatibility=data.get("compatibility", {"themeApi": 1}),
            extends=data.get("extends"),
            tokens=data.get("tokens", {}),
            assets=data.get("assets", {}),
            effects=parse_effect_stacks(raw_effects),
            media_recipes=parse_media_recipes(raw_media_recipes),
        )


@dataclass(frozen=True)
class ResolvedTheme:
    id: str
    name: str
    version: str
    author: str
    license: str
    description: str
    color: ThemeColorTokens = field(default_factory=ThemeColorTokens)
    geometry: ThemeGeometryTokens = field(default_factory=ThemeGeometryTokens)
    typography: ThemeTypographyTokens = field(default_factory=ThemeTypographyTokens)
    motion: ThemeMotionTokens = field(default_factory=ThemeMotionTokens)
    state_variants: ThemeStateVariantTokens = field(default_factory=ThemeStateVariantTokens)
    interaction: ThemeInteractionTokens = field(default_factory=ThemeInteractionTokens)
    accessibility: ThemeAccessibilityTokens = field(default_factory=ThemeAccessibilityTokens)
    performance: ThemePerformanceTokens = field(default_factory=ThemePerformanceTokens)
    assets: dict[str, ThemeAsset] = field(default_factory=dict)
    effects: dict[str, tuple[ResolvedEffect, ...]] = field(default_factory=dict)
    media_recipes: dict[str, MediaRecipe] = field(default_factory=dict)
    effect_diagnostics: tuple[EffectDiagnostic, ...] = ()
    high_contrast: bool = False
    reduced_motion: bool = False

    def apply_accessibility(self, high_contrast: bool, reduced_motion: bool) -> ResolvedTheme:
        if not high_contrast and not reduced_motion:
            return self
        color = self.color
        motion = self.motion
        if high_contrast:
            color = ThemeColorTokens(
                background="#000000",
                sidebar="#000000",
                surface="#000000",
                surfaceRaised="#1a1a1a",
                surfaceSelected="#2a2a2a",
                border="#ffffff",
                text="#ffffff",
                textMuted="#e8e8e8",
                textDisabled="#aaaaaa",
                accent="#00e5ff",
                accentStrong="#003d4d",
                success="#5eff62",
                successSurface="#1a4a1e",
                warning="#ffc400",
                warningSurface="#4a3a00",
                danger="#ff8a90",
                dangerSurface="#4a1818",
                focus="#00e5ff",
            )
        if reduced_motion:
            motion = ThemeMotionTokens(
                durationFast=0,
                durationNormal=0,
                durationLong=0,
                hoverIntensity=0,
                focusIntensity=0,
            )
        return ResolvedTheme(
            id=self.id,
            name=self.name,
            version=self.version,
            author=self.author,
            license=self.license,
            description=self.description,
            color=color,
            geometry=self.geometry,
            typography=self.typography,
            motion=motion,
            state_variants=self.state_variants,
            interaction=self.interaction,
            accessibility=self.accessibility,
            performance=self.performance,
            assets=self.assets,
            effects={
                stack: tuple(
                    effect
                    for effect in entries
                    if not (high_contrast or (reduced_motion and effect.type.value == "reflection"))
                )
                for stack, entries in self.effects.items()
            },
            media_recipes=self.media_recipes,
            effect_diagnostics=self.effect_diagnostics,
            high_contrast=high_contrast,
            reduced_motion=reduced_motion,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "license": self.license,
            "description": self.description,
            "highContrast": self.high_contrast,
            "reducedMotion": self.reduced_motion,
            "tokens": {
                "color": self.color.to_dict(),
                "geometry": self.geometry.to_dict(),
                "typography": self.typography.to_dict(),
                "motion": self.motion.to_dict(),
                "stateVariants": self.state_variants.to_dict(),
                "interaction": self.interaction.to_dict(),
                "accessibility": self.accessibility.to_dict(),
                "performance": self.performance.to_dict(),
            },
            "assets": {slot: asset.to_dict() for slot, asset in self.assets.items()},
            "effects": {
                stack: [effect.to_dict() for effect in entries]
                for stack, entries in self.effects.items()
            },
            "mediaRecipes": {role: recipe.to_dict() for role, recipe in self.media_recipes.items()},
            "effectDiagnostics": [item.to_dict() for item in self.effect_diagnostics],
        }

    def to_theme_qml_object(self) -> dict[str, Any]:
        tokens = self.to_dict()["tokens"]
        return {
            "schemaVersion": 1,
            "themeId": self.id,
            "themeVersion": self.version,
            "highContrast": self.high_contrast,
            "reducedMotion": self.reduced_motion,
            "resolved": tokens,
            "effects": {
                stack: [effect.to_dict() for effect in entries]
                for stack, entries in self.effects.items()
            },
            "mediaRecipes": {role: recipe.to_dict() for role, recipe in self.media_recipes.items()},
            "effectDiagnostics": [item.to_dict() for item in self.effect_diagnostics],
        }


class ThemeResolver:
    """Resolve um tema: mescla herança, aplica defaults e valida limites."""

    def __init__(self, manifests: dict[str, ThemeManifest]) -> None:
        self._manifests = manifests

    def resolve(
        self,
        theme_id: str,
        *,
        effect_capabilities: frozenset[str] | None = None,
        performance_tier: PerformanceTier | None = None,
        high_contrast: bool = False,
        reduced_motion: bool = False,
    ) -> ResolvedTheme:
        manifest = self._manifests.get(theme_id)
        if manifest is None:
            raise ValueError(f"tema não encontrado: {theme_id}")
        chain = self._build_chain(theme_id)
        return self._merge_chain(
            chain,
            effect_capabilities=effect_capabilities,
            performance_tier=performance_tier,
            high_contrast=high_contrast,
            reduced_motion=reduced_motion,
        )

    def _build_chain(self, theme_id: str, depth: int = 0) -> list[ThemeManifest]:
        if depth > MAX_EXTENDS_DEPTH:
            raise ValueError(f"profundidade de herança excedida para {theme_id}")
        manifest = self._manifests.get(theme_id)
        if manifest is None:
            raise ValueError(f"tema não encontrado na cadeia: {theme_id}")
        if theme_id in self._visiting:
            raise ValueError(f"ciclo de herança detectado: {theme_id}")
        self._visiting.add(theme_id)
        try:
            if manifest.extends is None or manifest.extends == THEME_DEFAULT_ID:
                base = self._manifests.get(THEME_DEFAULT_ID)
                if base is not None and base.id != theme_id:
                    return [*self._build_chain(THEME_DEFAULT_ID, depth + 1), manifest]
                return [manifest]
            return [*self._build_chain(manifest.extends, depth + 1), manifest]
        finally:
            self._visiting.discard(theme_id)

    def _merge_chain(
        self,
        chain: list[ThemeManifest],
        *,
        effect_capabilities: frozenset[str] | None,
        performance_tier: PerformanceTier | None,
        high_contrast: bool,
        reduced_motion: bool,
    ) -> ResolvedTheme:
        color = ThemeColorTokens()
        geometry = ThemeGeometryTokens()
        typography = ThemeTypographyTokens()
        motion = ThemeMotionTokens()
        state_variants = ThemeStateVariantTokens()
        interaction = ThemeInteractionTokens()
        accessibility = ThemeAccessibilityTokens()
        performance = ThemePerformanceTokens()
        assets: dict[str, str] = {}
        effects: dict[str, tuple[EffectSpec, ...]] = {}
        media_recipes: dict[str, MediaRecipe] = {}
        name = ""
        version = ""
        author = ""
        license_val = ""
        description = ""
        for manifest in chain:
            name = manifest.name or name
            version = manifest.version or version
            author = manifest.author or author
            license_val = manifest.license or license_val
            description = manifest.description or description
            tokens = manifest.tokens
            if "color" in tokens:
                c = color.to_dict()
                c.update(tokens["color"])
                color = ThemeColorTokens.from_dict(c)
            if "geometry" in tokens:
                g = geometry.to_dict()
                for k, v in tokens["geometry"].items():
                    if v is not None:
                        g[k] = int(v)
                geometry = ThemeGeometryTokens.from_dict(g)
            if "typography" in tokens:
                t = typography.to_dict()
                t.update(tokens["typography"])
                typography = ThemeTypographyTokens.from_dict(t)
            if "motion" in tokens:
                m = motion.to_dict()
                m.update(tokens["motion"])
                motion = ThemeMotionTokens.from_dict(m)
            if "stateVariants" in tokens:
                v = state_variants.to_dict()
                v.update(tokens["stateVariants"])
                state_variants = ThemeStateVariantTokens.from_dict(v)
            if "interaction" in tokens:
                i = interaction.to_dict()
                i.update(tokens["interaction"])
                interaction = ThemeInteractionTokens.from_dict(i)
            if "accessibility" in tokens:
                a = accessibility.to_dict()
                a.update(tokens["accessibility"])
                accessibility = ThemeAccessibilityTokens.from_dict(a)
            if "performance" in tokens:
                p = performance.to_dict()
                p.update(tokens["performance"])
                performance = ThemePerformanceTokens.from_dict(p)
            if manifest.assets:
                assets.update(manifest.assets)
            if manifest.effects:
                effects.update(manifest.effects)
            if manifest.media_recipes:
                media_recipes.update(manifest.media_recipes)

        validate_recipe_effect_stacks(tuple(media_recipes.values()), effects)

        resolved_assets = {slot: ThemeAsset(slot=slot, path=path) for slot, path in assets.items()}
        effect_kwargs: dict[str, Any] = {
            "tier": performance_tier or performance.defaultTier,
            "high_contrast": high_contrast,
            "reduced_motion": reduced_motion,
        }
        if effect_capabilities is not None:
            effect_kwargs["capabilities"] = effect_capabilities
        resolved_effects, effect_diagnostics = resolve_effect_stacks(effects, **effect_kwargs)
        top = chain[-1]
        resolved = ResolvedTheme(
            id=top.id,
            name=name,
            version=version,
            author=author,
            license=license_val,
            description=description,
            color=color,
            geometry=geometry,
            typography=typography,
            motion=motion,
            state_variants=state_variants,
            interaction=interaction,
            accessibility=accessibility,
            performance=performance,
            assets=resolved_assets,
            effects=resolved_effects,
            media_recipes=media_recipes,
            effect_diagnostics=effect_diagnostics,
        )
        return resolved.apply_accessibility(high_contrast, reduced_motion)

    @property
    def _visiting(self) -> set[str]:
        if not hasattr(self, "_chain_visiting"):
            self._chain_visiting: set[str] = set()
        return self._chain_visiting
