# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Painéis de vidro declarativos com fallback sem backbuffer.

O tema descreve tint, blur e cromo estático. O renderer decide se o blur
offscreen cabe no tier; nunca aceita shader, QML ou região de captura arbitrária.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from steamzero.domain.theme_effects import PerformanceTier

DIAG_GLASS_TIER = "THEME-GLASS-TIER-001"
DIAG_GLASS_CAPABILITY = "THEME-GLASS-CAPABILITY-002"
MAX_PANELS = 8
DEFAULT_GLASS_CAPABILITIES = frozenset({"graphics.effect.glass", "graphics.palette.dynamic"})
_IDENTIFIER = re.compile(r"^[a-z][a-zA-Z0-9]{0,63}$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_PALETTE_BINDING = re.compile(
    r"^palette\.(dominant|vibrant|lightVibrant|darkVibrant|muted|lightMuted|darkMuted|complementary|accent|background|contrastText)$"
)


def _number(value: Any, *, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"{name} exige número finito")
    number = float(value)
    if not low <= number <= high:
        raise ValueError(f"{name} fora de {low:g}..{high:g}")
    return number


def _hex(value: Any, *, name: str) -> str:
    if not isinstance(value, str) or not _COLOR.fullmatch(value):
        raise ValueError(f"{name} inválida")
    return value.lower()


@dataclass(frozen=True)
class GlassTint:
    fallback: str
    binding: str | None = None

    def __post_init__(self) -> None:
        _hex(self.fallback, name="tint")
        if self.binding is not None and not _PALETTE_BINDING.fullmatch(self.binding):
            raise ValueError("binding de tint inválido")

    @classmethod
    def from_value(cls, raw: Any) -> GlassTint:
        if isinstance(raw, str):
            return cls(fallback=_hex(raw, name="tint"))
        if not isinstance(raw, Mapping) or "fallback" not in raw:
            raise ValueError("tint inválido")
        unknown = set(raw) - {"binding", "fallback"}
        if unknown:
            raise ValueError("tint inválido")
        binding = raw.get("binding")
        if binding is not None and not isinstance(binding, str):
            raise ValueError("binding de tint inválido")
        return cls(fallback=_hex(raw["fallback"], name="tint.fallback"), binding=binding)

    def resolve(self, palette: Mapping[str, str]) -> str:
        if self.binding is None:
            return self.fallback
        key = self.binding.split(".", 1)[1]
        value = palette.get(key)
        return value if isinstance(value, str) and _COLOR.fullmatch(value) else self.fallback


@dataclass(frozen=True)
class GlassPanel:
    id: str
    tint: GlassTint
    blur: float = 16.0
    tint_opacity: float = 0.4
    border_color: str = "#ffffff"
    border_opacity: float = 0.28
    highlight_opacity: float = 0.16
    shadow_opacity: float = 0.28
    sample_scale: float = 0.5
    fallback: str = "flat"

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.id):
            raise ValueError("glass.id inválido")
        _number(self.blur, name="blur", low=0, high=64)
        _number(self.tint_opacity, name="tintOpacity", low=0, high=1)
        _hex(self.border_color, name="borderColor")
        _number(self.border_opacity, name="borderOpacity", low=0, high=1)
        _number(self.highlight_opacity, name="highlightOpacity", low=0, high=1)
        _number(self.shadow_opacity, name="shadowOpacity", low=0, high=1)
        _number(self.sample_scale, name="sampleScale", low=0.25, high=1)
        if self.fallback not in {"flat", "omit"}:
            raise ValueError("fallback de glass inválido")

    @classmethod
    def from_dict(cls, panel_id: str, raw: Mapping[str, Any]) -> GlassPanel:
        allowed = {
            "blur",
            "tint",
            "tintOpacity",
            "borderColor",
            "borderOpacity",
            "highlightOpacity",
            "shadowOpacity",
            "sampleScale",
            "fallback",
        }
        unknown = set(raw) - allowed
        if unknown:
            raise ValueError(f"glass inválido: {sorted(unknown)}")
        return cls(
            id=panel_id,
            tint=GlassTint.from_value(raw.get("tint", "#132833")),
            blur=_number(raw.get("blur", 16), name="blur", low=0, high=64),
            tint_opacity=_number(raw.get("tintOpacity", 0.4), name="tintOpacity", low=0, high=1),
            border_color=_hex(raw.get("borderColor", "#ffffff"), name="borderColor"),
            border_opacity=_number(
                raw.get("borderOpacity", 0.28), name="borderOpacity", low=0, high=1
            ),
            highlight_opacity=_number(
                raw.get("highlightOpacity", 0.16), name="highlightOpacity", low=0, high=1
            ),
            shadow_opacity=_number(
                raw.get("shadowOpacity", 0.28), name="shadowOpacity", low=0, high=1
            ),
            sample_scale=_number(raw.get("sampleScale", 0.5), name="sampleScale", low=0.25, high=1),
            fallback=str(raw.get("fallback", "flat")),
        )

    def to_dict(self) -> dict[str, Any]:
        tint: str | dict[str, str] = self.tint.fallback
        if self.tint.binding is not None:
            tint = {"binding": self.tint.binding, "fallback": self.tint.fallback}
        return {
            "blur": self.blur,
            "tint": tint,
            "tintOpacity": self.tint_opacity,
            "borderColor": self.border_color,
            "borderOpacity": self.border_opacity,
            "highlightOpacity": self.highlight_opacity,
            "shadowOpacity": self.shadow_opacity,
            "sampleScale": self.sample_scale,
            "fallback": self.fallback,
        }


@dataclass(frozen=True)
class GlassBook:
    panels: Mapping[str, GlassPanel]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("schemaVersion de glass inválido")
        if not self.panels or len(self.panels) > MAX_PANELS:
            raise ValueError(f"glass.panels exige 1..{MAX_PANELS} entradas")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> GlassBook:
        if set(raw) != {"schemaVersion", "panels"}:
            raise ValueError("glass inválido")
        panels = raw["panels"]
        if not isinstance(panels, Mapping) or not panels or len(panels) > MAX_PANELS:
            raise ValueError("glass.panels inválido")
        parsed: dict[str, GlassPanel] = {}
        for panel_id, recipe in panels.items():
            if not isinstance(recipe, Mapping):
                raise ValueError("glass panel exige objeto")
            parsed[str(panel_id)] = GlassPanel.from_dict(str(panel_id), recipe)
        return cls(panels=parsed, schema_version=raw["schemaVersion"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "panels": {key: value.to_dict() for key, value in self.panels.items()},
        }


@dataclass(frozen=True)
class GlassDiagnostic:
    code: str
    panel: str
    reason: str
    fallback: str = "flat"

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "panel": self.panel,
            "reason": self.reason,
            "fallback": self.fallback,
        }


@dataclass(frozen=True)
class ResolvedGlassPanel:
    id: str
    tint: str
    blur: float
    tint_opacity: float
    border_color: str
    border_opacity: float
    highlight_opacity: float
    shadow_opacity: float
    sample_scale: float
    blur_enabled: bool
    fallback: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tint": self.tint,
            "blur": self.blur,
            "tintOpacity": self.tint_opacity,
            "borderColor": self.border_color,
            "borderOpacity": self.border_opacity,
            "highlightOpacity": self.highlight_opacity,
            "shadowOpacity": self.shadow_opacity,
            "sampleScale": self.sample_scale,
            "blurEnabled": self.blur_enabled,
            "fallback": self.fallback,
        }


@dataclass(frozen=True)
class GlassResolution:
    panels: Mapping[str, ResolvedGlassPanel]
    diagnostics: tuple[GlassDiagnostic, ...] = ()

    def to_qml_object(self) -> dict[str, Any]:
        return {
            "panels": {key: value.to_dict() for key, value in self.panels.items()},
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


def resolve_glass_panels(
    raw_book: Mapping[str, Any] | GlassBook,
    *,
    palette: Mapping[str, str],
    tier: PerformanceTier = PerformanceTier.CINEMATIC,
    capabilities: frozenset[str] = DEFAULT_GLASS_CAPABILITIES,
    high_contrast: bool = False,
) -> GlassResolution:
    book = raw_book if isinstance(raw_book, GlassBook) else GlassBook.from_dict(raw_book)
    panels: dict[str, ResolvedGlassPanel] = {}
    diagnostics: list[GlassDiagnostic] = []
    for panel_id, recipe in book.panels.items():
        blur_enabled = True
        fallback = "none"
        blur = recipe.blur
        sample_scale = recipe.sample_scale
        if "graphics.effect.glass" not in capabilities:
            blur_enabled = False
            fallback = recipe.fallback
            diagnostics.append(
                GlassDiagnostic(
                    code=DIAG_GLASS_CAPABILITY,
                    panel=panel_id,
                    reason="capability ausente: graphics.effect.glass",
                    fallback=recipe.fallback,
                )
            )
        elif high_contrast or tier in {PerformanceTier.ECONOMY, PerformanceTier.ACCESSIBLE}:
            blur_enabled = False
            fallback = recipe.fallback
            diagnostics.append(
                GlassDiagnostic(
                    code=DIAG_GLASS_TIER,
                    panel=panel_id,
                    reason=f"blur desligado no tier {tier.value}",
                    fallback=recipe.fallback,
                )
            )
        elif tier is PerformanceTier.BALANCED:
            blur = round(recipe.blur * 0.5, 4)
            sample_scale = max(0.25, round(recipe.sample_scale * 0.75, 4))
        panels[panel_id] = ResolvedGlassPanel(
            id=panel_id,
            tint=recipe.tint.resolve(palette),
            blur=blur,
            tint_opacity=recipe.tint_opacity,
            border_color=recipe.border_color,
            border_opacity=recipe.border_opacity,
            highlight_opacity=recipe.highlight_opacity,
            shadow_opacity=recipe.shadow_opacity,
            sample_scale=sample_scale,
            blur_enabled=blur_enabled,
            fallback=fallback,
        )
    return GlassResolution(panels=panels, diagnostics=tuple(diagnostics))
