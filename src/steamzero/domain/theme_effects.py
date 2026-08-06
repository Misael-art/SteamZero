# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Pilha declarativa e fechada de efeitos de mídia para temas.

O manifesto descreve intenção, nunca QML, shader ou código executável. Este
módulo é a única lista de efeitos que o renderer pode receber; a negociação de
capabilities transforma a declaração em uma lista pequena e determinística de
efeitos suportados, acompanhada de diagnósticos para qualquer degradação.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

EFFECT_STACK_SCHEMA_VERSION = 1


class EffectType(StrEnum):
    BLUR = "blur"
    SATURATION = "saturation"
    BRIGHTNESS = "brightness"
    CONTRAST = "contrast"
    COLORIZE = "colorize"
    OPACITY = "opacity"
    SHADOW = "shadow"
    GLOW = "glow"
    REFLECTION = "reflection"
    GRADIENT_MASK = "gradientMask"
    VIGNETTE = "vignette"


class PerformanceTier(StrEnum):
    CINEMATIC = "cinematic"
    BALANCED = "balanced"
    ECONOMY = "economy"
    ACCESSIBLE = "accessible"


class EffectFallback(StrEnum):
    OMIT = "omit"
    MINIMAL = "minimal"


class EffectCost(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class _EffectRule:
    capability: str
    cost: EffectCost
    defaults: Mapping[str, Any]
    bounds: Mapping[str, tuple[float, float]]
    colors: frozenset[str] = frozenset()
    reduced_motion: str = "keep"
    high_contrast: str = "omit"
    economy: str = "keep"
    balanced_scale: frozenset[str] = frozenset()


_RULES: dict[EffectType, _EffectRule] = {
    EffectType.BLUR: _EffectRule(
        "graphics.effect.blur",
        EffectCost.HIGH,
        {"radius": 16.0},
        {"radius": (0, 64)},
        economy="omit",
        balanced_scale=frozenset({"radius"}),
    ),
    EffectType.SATURATION: _EffectRule(
        "graphics.effect.saturation", EffectCost.LOW, {"amount": 0.0}, {"amount": (-1, 1)}
    ),
    EffectType.BRIGHTNESS: _EffectRule(
        "graphics.effect.saturation", EffectCost.LOW, {"amount": 0.0}, {"amount": (-1, 1)}
    ),
    EffectType.CONTRAST: _EffectRule(
        "graphics.effect.saturation", EffectCost.LOW, {"amount": 0.0}, {"amount": (-1, 1)}
    ),
    EffectType.COLORIZE: _EffectRule(
        "graphics.effect.colorize",
        EffectCost.MEDIUM,
        {"color": "#000000", "strength": 0.0},
        {"strength": (0, 1)},
        frozenset({"color"}),
    ),
    EffectType.OPACITY: _EffectRule(
        "graphics.effect.saturation", EffectCost.LOW, {"amount": 1.0}, {"amount": (0, 1)}
    ),
    EffectType.SHADOW: _EffectRule(
        "graphics.effect.shadow",
        EffectCost.MEDIUM,
        {"color": "#000000", "opacity": 0.35, "blur": 12.0, "offsetX": 0.0, "offsetY": 4.0},
        {"opacity": (0, 1), "blur": (0, 48), "offsetX": (-48, 48), "offsetY": (-48, 48)},
        frozenset({"color"}),
        balanced_scale=frozenset({"blur", "offsetX", "offsetY"}),
    ),
    EffectType.GLOW: _EffectRule(
        "graphics.effect.glow",
        EffectCost.HIGH,
        {"color": "#ffffff", "strength": 0.25, "blur": 16.0},
        {"strength": (0, 1), "blur": (0, 48)},
        frozenset({"color"}),
        economy="omit",
        balanced_scale=frozenset({"strength", "blur"}),
    ),
    EffectType.REFLECTION: _EffectRule(
        "graphics.effect.reflection",
        EffectCost.HIGH,
        {"opacity": 0.2, "scale": 0.35},
        {"opacity": (0, 1), "scale": (0, 1)},
        reduced_motion="omit",
        economy="omit",
        balanced_scale=frozenset({"opacity", "scale"}),
    ),
    EffectType.GRADIENT_MASK: _EffectRule(
        "graphics.mask.gradient",
        EffectCost.MEDIUM,
        {"start": 1.0, "end": 0.0},
        {"start": (0, 1), "end": (0, 1)},
    ),
    EffectType.VIGNETTE: _EffectRule(
        "graphics.effect.colorize",
        EffectCost.HIGH,
        {"color": "#000000", "strength": 0.25},
        {"strength": (0, 1)},
        frozenset({"color"}),
        economy="omit",
        balanced_scale=frozenset({"strength"}),
    ),
}

ALL_EFFECT_CAPABILITIES = frozenset(rule.capability for rule in _RULES.values()) | frozenset(
    {"graphics.palette.dynamic"}
)
# A implementação QML usa MultiEffect e fontes de máscara locais geradas pelo
# renderer. Nenhum tema pode fornecer shader ou fonte adicional.
DEFAULT_RENDERER_CAPABILITIES = frozenset(
    {
        "graphics.effect.blur",
        "graphics.effect.saturation",
        "graphics.effect.colorize",
        "graphics.effect.shadow",
        "graphics.effect.glow",
        "graphics.effect.reflection",
        "graphics.mask.gradient",
    }
)


def _color(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
        raise ValueError(f"{field} precisa ser cor #RRGGBB")
    try:
        int(value[1:], 16)
    except ValueError as exc:
        raise ValueError(f"{field} precisa ser cor #RRGGBB") from exc
    return value.lower()


@dataclass(frozen=True)
class EffectSpec:
    """Uma declaração segura de efeito, independente de qualquer backend."""

    type: EffectType
    parameters: Mapping[str, Any]
    fallback: EffectFallback = EffectFallback.OMIT

    def __post_init__(self) -> None:
        rule = _RULES[self.type]
        unknown = set(self.parameters) - set(rule.defaults)
        if unknown:
            raise ValueError(f"parâmetros não permitidos para {self.type.value}: {sorted(unknown)}")
        for name, value in self.parameters.items():
            if name in rule.colors:
                _color(value, name)
                continue
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueError(f"{name} de {self.type.value} precisa ser número")
            low, high = rule.bounds[name]
            if not low <= float(value) <= high:
                raise ValueError(f"{name} de {self.type.value} fora de [{low}, {high}]")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> EffectSpec:
        try:
            effect_type = EffectType(payload["type"])
        except (KeyError, ValueError) as exc:
            raise ValueError("type de efeito desconhecido") from exc
        try:
            fallback = EffectFallback(payload.get("fallback", "omit"))
        except ValueError as exc:
            raise ValueError("fallback de efeito desconhecido") from exc
        return cls(
            type=effect_type,
            parameters={
                key: value for key, value in payload.items() if key not in {"type", "fallback"}
            },
            fallback=fallback,
        )

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type.value, **dict(self.parameters), "fallback": self.fallback.value}


@dataclass(frozen=True)
class ResolvedEffect:
    type: EffectType
    parameters: Mapping[str, Any]
    capability: str
    cost: EffectCost

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "parameters": dict(self.parameters),
            "capability": self.capability,
            "cost": self.cost.value,
        }


@dataclass(frozen=True)
class EffectDiagnostic:
    stack: str
    effect: EffectType
    reason: str
    fallback: EffectFallback

    def to_dict(self) -> dict[str, str]:
        return {
            "stack": self.stack,
            "effect": self.effect.value,
            "reason": self.reason,
            "fallback": self.fallback.value,
        }


def parse_effect_stacks(payload: Mapping[str, Any] | None) -> dict[str, tuple[EffectSpec, ...]]:
    """Lê o namespace ``effects`` do manifesto, preservando a versão do stack."""
    if not payload:
        return {}
    if payload.get("schemaVersion") != EFFECT_STACK_SCHEMA_VERSION:
        raise ValueError("schemaVersion da pilha de efeitos incompatível")
    raw_stacks = payload.get("stacks")
    if not isinstance(raw_stacks, Mapping):
        raise ValueError("stacks de efeitos precisa ser objeto")
    parsed: dict[str, tuple[EffectSpec, ...]] = {}
    for name, entries in raw_stacks.items():
        if not isinstance(name, str) or not isinstance(entries, list):
            raise ValueError("stack de efeitos inválido")
        parsed[name] = tuple(
            EffectSpec.from_dict(entry) for entry in entries if isinstance(entry, Mapping)
        )
        if len(parsed[name]) != len(entries):
            raise ValueError("efeito precisa ser objeto")
    return parsed


def effect_stacks_to_dict(stacks: Mapping[str, tuple[EffectSpec, ...]]) -> dict[str, Any]:
    return {
        "schemaVersion": EFFECT_STACK_SCHEMA_VERSION,
        "stacks": {name: [item.to_dict() for item in entries] for name, entries in stacks.items()},
    }


def resolve_effect_stacks(
    stacks: Mapping[str, tuple[EffectSpec, ...]],
    *,
    capabilities: frozenset[str] = DEFAULT_RENDERER_CAPABILITIES,
    tier: PerformanceTier = PerformanceTier.CINEMATIC,
    high_contrast: bool = False,
    reduced_motion: bool = False,
) -> tuple[dict[str, tuple[ResolvedEffect, ...]], tuple[EffectDiagnostic, ...]]:
    """Negocia stack por capability e política de acessibilidade/performance."""
    resolved: dict[str, tuple[ResolvedEffect, ...]] = {}
    diagnostics: list[EffectDiagnostic] = []
    for stack_name, entries in stacks.items():
        accepted: list[ResolvedEffect] = []
        for entry in entries:
            rule = _RULES[entry.type]
            reason: str | None = None
            if rule.capability not in capabilities:
                reason = f"capability ausente: {rule.capability}"
            elif high_contrast or tier is PerformanceTier.ACCESSIBLE:
                reason = "omitido para preservar contraste e legibilidade"
            elif reduced_motion and rule.reduced_motion == "omit":
                reason = "omitido com movimento reduzido"
            elif tier is PerformanceTier.ECONOMY and rule.economy == "omit":
                reason = "omitido no tier economy"
            if reason is not None:
                diagnostics.append(EffectDiagnostic(stack_name, entry.type, reason, entry.fallback))
                continue
            parameters = dict(rule.defaults)
            parameters.update(entry.parameters)
            if tier is PerformanceTier.BALANCED:
                for name in rule.balanced_scale:
                    parameters[name] = round(float(parameters[name]) * 0.5, 4)
            accepted.append(ResolvedEffect(entry.type, parameters, rule.capability, rule.cost))
        resolved[stack_name] = tuple(accepted)
    return resolved, tuple(diagnostics)
