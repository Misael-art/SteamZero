from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

THEME_MANIFEST_SCHEMA_VERSION = 1
THEME_API_VERSION = 1
THEME_DEFAULT_ID = "org.steamzero.default"
MAX_EXTENDS_DEPTH = 2
MAX_THEMES = 100
ASSET_SLOTS_ALLOWED = frozenset({"background", "logo", "sidebar"})


@dataclass(frozen=True)
class ThemeColorTokens:
    background: str = "#071019"
    sidebar: str = "#09131d"
    surface: str = "#0d1924"
    surfaceRaised: str = "#122131"
    surfaceSelected: str = "#1a2b3c"
    border: str = "#2a3a49"
    text: str = "#f2f6fb"
    textMuted: str = "#9eabba"
    textDisabled: str = "#667481"
    accent: str = "#13bdf2"
    accentStrong: str = "#0a5f85"
    success: str = "#59d35d"
    successSurface: str = "#1a3a1e"
    warning: str = "#ff9f1a"
    warningSurface: str = "#3a2a0a"
    danger: str = "#ff6b73"
    dangerSurface: str = "#3a1518"
    focus: str = "#13bdf2"

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
    family: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "scale": self.scale,
            "weightBody": self.weightBody,
            "weightStrong": self.weightStrong,
            "weightHeading": self.weightHeading,
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
        return result

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ThemeManifest:
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
    assets: dict[str, ThemeAsset] = field(default_factory=dict)
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
            assets=self.assets,
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
            },
            "assets": {slot: asset.to_dict() for slot, asset in self.assets.items()},
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
        }


class ThemeResolver:
    """Resolve um tema: mescla herança, aplica defaults e valida limites."""

    def __init__(self, manifests: dict[str, ThemeManifest]) -> None:
        self._manifests = manifests

    def resolve(self, theme_id: str) -> ResolvedTheme:
        manifest = self._manifests.get(theme_id)
        if manifest is None:
            raise ValueError(f"tema não encontrado: {theme_id}")
        chain = self._build_chain(theme_id)
        return self._merge_chain(chain)

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

    def _merge_chain(self, chain: list[ThemeManifest]) -> ResolvedTheme:
        color = ThemeColorTokens()
        geometry = ThemeGeometryTokens()
        typography = ThemeTypographyTokens()
        motion = ThemeMotionTokens()
        assets: dict[str, str] = {}
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
            if manifest.assets:
                assets.update(manifest.assets)

        resolved_assets = {
            slot: ThemeAsset(slot=slot, path=path) for slot, path in assets.items()
        }
        top = chain[-1]
        return ResolvedTheme(
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
            assets=resolved_assets,
        )

    @property
    def _visiting(self) -> set[str]:
        if not hasattr(self, "_chain_visiting"):
            self._chain_visiting: set[str] = set()
        return self._chain_visiting
