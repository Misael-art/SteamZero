# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Receitas declarativas para derivar variantes de um único asset-fonte.

O pacote fornece somente a fonte e este contrato. O renderer confiável aplica
nodes fechados sobre alpha; QML, JavaScript, Python, shell, binários e shaders
fornecidos pelo tema nunca atravessam esta fronteira.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from steamzero.domain.theme_effects import EffectCost, PerformanceTier

ASSET_RECIPE_SCHEMA_VERSION = 1
MAX_ASSET_RECIPES = 32
MAX_ASSET_NODES = 12
MAX_OUTLINE_WIDTH = 32.0
_RECIPE_NAME = re.compile(r"^[a-z][a-zA-Z0-9]{0,63}$")


class AssetRecipeNodeType(StrEnum):
    RECOLOR = "recolor"
    GRAYSCALE = "grayscale"
    SILHOUETTE = "silhouette"
    INVERT = "invert"
    HUE_ROTATE = "hueRotate"
    OUTLINE = "outline"
    GLOW = "glow"
    SHADOW = "shadow"


class AssetRecipeFallback(StrEnum):
    SOURCE = "source"
    OUTER = "outer"


@dataclass(frozen=True)
class _NodeRule:
    capability: str
    cost: EffectCost
    defaults: Mapping[str, Any]
    bounds: Mapping[str, tuple[float, float]]
    colors: frozenset[str] = frozenset()
    enums: Mapping[str, frozenset[str]] = field(default_factory=dict)


_NODE_RULES: dict[AssetRecipeNodeType, _NodeRule] = {
    AssetRecipeNodeType.RECOLOR: _NodeRule(
        "graphics.asset.recolor",
        EffectCost.LOW,
        {"color": "#ffffff", "opacity": 1.0},
        {"opacity": (0.0, 1.0)},
        frozenset({"color"}),
    ),
    AssetRecipeNodeType.GRAYSCALE: _NodeRule(
        "graphics.asset.grayscale",
        EffectCost.LOW,
        {"amount": 1.0},
        {"amount": (0.0, 1.0)},
    ),
    AssetRecipeNodeType.SILHOUETTE: _NodeRule(
        "graphics.asset.silhouette",
        EffectCost.LOW,
        {"color": "#000000", "opacity": 1.0},
        {"opacity": (0.0, 1.0)},
        frozenset({"color"}),
    ),
    AssetRecipeNodeType.INVERT: _NodeRule(
        "graphics.asset.invert",
        EffectCost.LOW,
        {"amount": 1.0},
        {"amount": (0.0, 1.0)},
    ),
    AssetRecipeNodeType.HUE_ROTATE: _NodeRule(
        "graphics.asset.hue-rotate",
        EffectCost.MEDIUM,
        {"degrees": 0.0},
        {"degrees": (-360.0, 360.0)},
    ),
    AssetRecipeNodeType.OUTLINE: _NodeRule(
        "graphics.asset.outline.outer",
        EffectCost.MEDIUM,
        {
            "width": 1.0,
            "color": "#ffffff",
            "opacity": 1.0,
            "position": "outer",
            "mask": "alpha",
        },
        {"width": (1.0, MAX_OUTLINE_WIDTH), "opacity": (0.0, 1.0)},
        frozenset({"color"}),
        {
            "position": frozenset({"inner", "outer"}),
            "mask": frozenset({"alpha", "sdf"}),
        },
    ),
    AssetRecipeNodeType.GLOW: _NodeRule(
        "graphics.effect.glow",
        EffectCost.HIGH,
        {"color": "#ffffff", "strength": 0.25, "blur": 16.0},
        {"strength": (0.0, 1.0), "blur": (0.0, 48.0)},
        frozenset({"color"}),
    ),
    AssetRecipeNodeType.SHADOW: _NodeRule(
        "graphics.effect.shadow",
        EffectCost.MEDIUM,
        {
            "color": "#000000",
            "opacity": 0.35,
            "blur": 12.0,
            "offsetX": 0.0,
            "offsetY": 4.0,
        },
        {
            "opacity": (0.0, 1.0),
            "blur": (0.0, 48.0),
            "offsetX": (-48.0, 48.0),
            "offsetY": (-48.0, 48.0),
        },
        frozenset({"color"}),
    ),
}

# O backend Qt Quick atual implementa somente efeitos que podem ser compostos
# por MultiEffect e por uma textura alpha local. Invert, hue rotate e outline
# interno continuam allowlisted, mas degradam com diagnóstico até haver um node
# builtin revisado para esses capabilities.
DEFAULT_ASSET_CAPABILITIES = frozenset(
    {
        "graphics.asset.recolor",
        "graphics.asset.grayscale",
        "graphics.asset.silhouette",
        "graphics.asset.outline.outer",
        "graphics.effect.glow",
        "graphics.effect.shadow",
    }
)

_TIER_BUDGETS = {
    PerformanceTier.CINEMATIC: 24,
    PerformanceTier.BALANCED: 12,
    PerformanceTier.ECONOMY: 5,
    PerformanceTier.ACCESSIBLE: 5,
}


def _color(value: Any, field: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError(f"{field} precisa ser cor #RRGGBB")
    return value.lower()


def _number(value: Any, field: str, bounds: tuple[float, float]) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field} precisa ser número")
    result = float(value)
    low, high = bounds
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f"{field} fora de [{low}, {high}]")
    return result


@dataclass(frozen=True)
class AssetRecipeNode:
    type: AssetRecipeNodeType
    parameters: Mapping[str, Any]
    fallback: AssetRecipeFallback = AssetRecipeFallback.SOURCE

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AssetRecipeNode:
        try:
            node_type = AssetRecipeNodeType(payload["type"])
        except (KeyError, ValueError) as exc:
            raise ValueError("type de node desconhecido") from exc
        rule = _NODE_RULES[node_type]
        allowed = set(rule.defaults) | {"type", "fallback"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"parâmetros não permitidos para {node_type.value}: {sorted(unknown)}")
        default_fallback = "outer" if node_type is AssetRecipeNodeType.OUTLINE else "source"
        try:
            fallback = AssetRecipeFallback(payload.get("fallback", default_fallback))
        except ValueError as exc:
            raise ValueError("fallback de node desconhecido") from exc
        parameters = dict(rule.defaults)
        parameters.update(
            {key: value for key, value in payload.items() if key not in {"type", "fallback"}}
        )
        for name in rule.colors:
            parameters[name] = _color(parameters[name], name)
        for name, bounds in rule.bounds.items():
            parameters[name] = _number(parameters[name], name, bounds)
        for name, choices in rule.enums.items():
            value = parameters[name]
            if not isinstance(value, str) or value not in choices:
                raise ValueError(f"{name} precisa ser um de {sorted(choices)}")
        if node_type is AssetRecipeNodeType.SILHOUETTE and parameters["color"] not in {
            "#000000",
            "#ffffff",
        }:
            raise ValueError("silhouette aceita somente preto ou branco")
        if node_type is not AssetRecipeNodeType.OUTLINE and fallback is AssetRecipeFallback.OUTER:
            raise ValueError("fallback outer pertence somente a outline")
        return cls(node_type, parameters, fallback)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            **dict(self.parameters),
            "fallback": self.fallback.value,
        }


@dataclass(frozen=True)
class AssetRecipe:
    name: str
    source_slot: str
    nodes: tuple[AssetRecipeNode, ...]

    def node(self, node_type: AssetRecipeNodeType) -> AssetRecipeNode:
        for item in self.nodes:
            if item.type is node_type:
                return item
        raise KeyError(node_type.value)

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source_slot, "nodes": [node.to_dict() for node in self.nodes]}


@dataclass(frozen=True)
class AssetRecipeBook:
    source_slot: str
    recipes: Mapping[str, AssetRecipe]
    schema_version: int = ASSET_RECIPE_SCHEMA_VERSION

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AssetRecipeBook:
        unknown = set(payload) - {"schemaVersion", "sourceSlot", "recipes"}
        if unknown:
            raise ValueError(f"campos não permitidos em assetRecipes: {sorted(unknown)}")
        if payload.get("schemaVersion") != ASSET_RECIPE_SCHEMA_VERSION:
            raise ValueError("schemaVersion de assetRecipes incompatível")
        source_slot = payload.get("sourceSlot")
        if not isinstance(source_slot, str) or not _RECIPE_NAME.fullmatch(source_slot):
            raise ValueError("sourceSlot de assetRecipes inválido")
        raw_recipes = payload.get("recipes")
        if not isinstance(raw_recipes, Mapping) or not raw_recipes:
            raise ValueError("recipes de assetRecipes precisa ser objeto não vazio")
        if len(raw_recipes) > MAX_ASSET_RECIPES:
            raise ValueError(f"assetRecipes excede {MAX_ASSET_RECIPES} receitas")
        recipes: dict[str, AssetRecipe] = {}
        for name, raw_recipe in raw_recipes.items():
            if not isinstance(name, str) or not _RECIPE_NAME.fullmatch(name):
                raise ValueError("nome de receita inválido")
            if not isinstance(raw_recipe, Mapping):
                raise ValueError(f"receita {name} precisa ser objeto")
            recipe_unknown = set(raw_recipe) - {"source", "nodes"}
            if recipe_unknown:
                raise ValueError(
                    f"campos não permitidos na receita {name}: {sorted(recipe_unknown)}"
                )
            recipe_source = raw_recipe.get("source")
            if recipe_source != source_slot:
                raise ValueError(f"receita {name} precisa usar a fonte única {source_slot}")
            raw_nodes = raw_recipe.get("nodes", [])
            if not isinstance(raw_nodes, list):
                raise ValueError(f"nodes da receita {name} precisa ser array")
            if len(raw_nodes) > MAX_ASSET_NODES:
                raise ValueError(f"nodes da receita {name} excede {MAX_ASSET_NODES}")
            nodes = tuple(
                AssetRecipeNode.from_dict(node) for node in raw_nodes if isinstance(node, Mapping)
            )
            if len(nodes) != len(raw_nodes):
                raise ValueError(f"node da receita {name} precisa ser objeto")
            _validate_composition(name, nodes)
            recipes[name] = AssetRecipe(name=name, source_slot=source_slot, nodes=nodes)
        return cls(source_slot=source_slot, recipes=recipes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "sourceSlot": self.source_slot,
            "recipes": {name: recipe.to_dict() for name, recipe in self.recipes.items()},
        }


def _validate_composition(name: str, nodes: tuple[AssetRecipeNode, ...]) -> None:
    types = [node.type for node in nodes]
    if len(types) != len(set(types)):
        raise ValueError(f"receita {name} repete node")
    color_nodes = {AssetRecipeNodeType.RECOLOR, AssetRecipeNodeType.SILHOUETTE}
    if len(color_nodes.intersection(types)) > 1:
        raise ValueError(f"receita {name} combina recolor e silhouette")
    ambient = {AssetRecipeNodeType.GLOW, AssetRecipeNodeType.SHADOW}
    if len(ambient.intersection(types)) > 1:
        raise ValueError(f"receita {name} combina glow e shadow acima do orçamento do slice")


@dataclass(frozen=True)
class ResolvedAssetNode:
    type: AssetRecipeNodeType
    parameters: Mapping[str, Any]
    capability: str
    cost: EffectCost
    fallback: AssetRecipeFallback

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "parameters": dict(self.parameters),
            "capability": self.capability,
            "cost": self.cost.value,
            "fallback": self.fallback.value,
        }


@dataclass(frozen=True)
class ResolvedAssetRecipe:
    name: str
    source_slot: str
    nodes: tuple[ResolvedAssetNode, ...]
    tier: PerformanceTier
    reduced_motion_safe: bool = True

    def node(self, node_type: AssetRecipeNodeType) -> ResolvedAssetNode:
        for item in self.nodes:
            if item.type is node_type:
                return item
        raise KeyError(node_type.value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source_slot,
            "nodes": [node.to_dict() for node in self.nodes],
            "tier": self.tier.value,
            "fallback": "source",
            "reducedMotionSafe": self.reduced_motion_safe,
        }


@dataclass(frozen=True)
class AssetRecipeDiagnostic:
    recipe: str
    node: AssetRecipeNodeType | None
    reason: str
    fallback: str

    def to_dict(self) -> dict[str, str]:
        return {
            "recipe": self.recipe,
            "node": self.node.value if self.node is not None else "recipe",
            "reason": self.reason,
            "fallback": self.fallback,
        }


def _node_cost(node: AssetRecipeNode) -> int:
    rule = _NODE_RULES[node.type]
    base = {EffectCost.LOW: 1, EffectCost.MEDIUM: 2, EffectCost.HIGH: 3}[rule.cost]
    if node.type is AssetRecipeNodeType.OUTLINE:
        base += max(0, math.ceil(float(node.parameters["width"]) / 4.0) - 1)
    return base


def resolve_asset_recipes(
    book: AssetRecipeBook,
    *,
    capabilities: frozenset[str] = DEFAULT_ASSET_CAPABILITIES,
    tier: PerformanceTier = PerformanceTier.CINEMATIC,
    reduced_motion: bool = False,
) -> tuple[dict[str, ResolvedAssetRecipe], tuple[AssetRecipeDiagnostic, ...]]:
    """Negocia capabilities e orçamento sem nunca perder a fonte segura."""
    del reduced_motion  # todos os nodes deste slice são estáticos
    resolved: dict[str, ResolvedAssetRecipe] = {}
    diagnostics: list[AssetRecipeDiagnostic] = []
    for name, recipe in book.recipes.items():
        accepted: list[ResolvedAssetNode] = []
        fallback_to_source = False
        for node in recipe.nodes:
            rule = _NODE_RULES[node.type]
            parameters = dict(node.parameters)
            capability = rule.capability
            if node.type is AssetRecipeNodeType.OUTLINE and parameters["position"] == "inner":
                capability = "graphics.asset.outline.inner"
            if capability not in capabilities:
                if (
                    node.type is AssetRecipeNodeType.OUTLINE
                    and parameters["position"] == "inner"
                    and node.fallback is AssetRecipeFallback.OUTER
                    and "graphics.asset.outline.outer" in capabilities
                ):
                    parameters["position"] = "outer"
                    diagnostics.append(
                        AssetRecipeDiagnostic(
                            name,
                            node.type,
                            "capability ausente: graphics.asset.outline.inner",
                            "outer",
                        )
                    )
                    capability = "graphics.asset.outline.outer"
                else:
                    diagnostics.append(
                        AssetRecipeDiagnostic(
                            name,
                            node.type,
                            f"capability ausente: {capability}",
                            "source",
                        )
                    )
                    fallback_to_source = True
                    break
            accepted.append(
                ResolvedAssetNode(
                    type=node.type,
                    parameters=parameters,
                    capability=capability,
                    cost=rule.cost,
                    fallback=node.fallback,
                )
            )
        cost = sum(_node_cost(node) for node in recipe.nodes)
        if not fallback_to_source and cost > _TIER_BUDGETS[tier]:
            diagnostics.append(
                AssetRecipeDiagnostic(
                    name,
                    None,
                    f"orçamento excedido no tier {tier.value}: {cost} > {_TIER_BUDGETS[tier]}",
                    "source",
                )
            )
            fallback_to_source = True
        resolved[name] = ResolvedAssetRecipe(
            name=name,
            source_slot=recipe.source_slot,
            nodes=() if fallback_to_source else tuple(accepted),
            tier=tier,
        )
    return resolved, tuple(diagnostics)


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class PreparedAssetVariant:
    cache_key: str
    source_hash: str
    recipe_hash: str
    size: tuple[int, int]
    scale: float
    tier: PerformanceTier
    capabilities: tuple[str, ...]
    recipe: ResolvedAssetRecipe

    def to_dict(self) -> dict[str, Any]:
        return {
            "cacheKey": self.cache_key,
            "sourceHash": self.source_hash,
            "recipeHash": self.recipe_hash,
            "size": list(self.size),
            "scale": self.scale,
            "tier": self.tier.value,
            "capabilities": list(self.capabilities),
            "recipe": self.recipe.to_dict(),
        }


class AssetRecipeCache:
    """LRU descartável de planos derivados e decodificação lógica da fonte.

    A textura física continua pertencendo ao renderer QML. Esta cache garante
    a identidade determinística e evita revalidar/decodificar a mesma fonte
    quando somente a receita muda.
    """

    def __init__(self, *, max_entries: int = 128) -> None:
        if max_entries < 1 or max_entries > 4096:
            raise ValueError("max_entries fora de [1, 4096]")
        self._max_entries = max_entries
        self._entries: OrderedDict[str, PreparedAssetVariant] = OrderedDict()
        self._decoded_sources: set[str] = set()
        self.source_decodes = 0

    def prepare(
        self,
        source: bytes,
        recipe: ResolvedAssetRecipe,
        *,
        size: tuple[int, int],
        scale: float,
        tier: PerformanceTier,
        capabilities: frozenset[str],
    ) -> PreparedAssetVariant:
        if not source:
            raise ValueError("asset-fonte vazio")
        width, height = size
        if width < 1 or height < 1 or width > 8192 or height > 8192:
            raise ValueError("tamanho de derivado fora de [1, 8192]")
        if not math.isfinite(scale) or not 0.5 <= scale <= 4.0:
            raise ValueError("escala fora de [0.5, 4.0]")
        source_hash = hashlib.sha256(source).hexdigest()
        if source_hash not in self._decoded_sources:
            validate_asset_source(source)
            self._decoded_sources.add(source_hash)
            self.source_decodes += 1
        recipe_payload = recipe.to_dict()
        recipe_hash = hashlib.sha256(_canonical_json(recipe_payload)).hexdigest()
        capability_list = tuple(sorted(capabilities))
        key_payload: dict[str, Any] = {
            "source": source_hash,
            "recipe": recipe_hash,
            "size": [width, height],
            "scale": round(float(scale), 4),
            "tier": tier.value,
            "capabilities": capability_list,
        }
        cache_key = hashlib.sha256(_canonical_json(key_payload)).hexdigest()
        cached = self._entries.get(cache_key)
        if cached is not None:
            self._entries.move_to_end(cache_key)
            return cached
        prepared = PreparedAssetVariant(
            cache_key=cache_key,
            source_hash=source_hash,
            recipe_hash=recipe_hash,
            size=size,
            scale=round(float(scale), 4),
            tier=tier,
            capabilities=capability_list,
            recipe=recipe,
        )
        self._entries[cache_key] = prepared
        self._entries.move_to_end(cache_key)
        while len(self._entries) > self._max_entries:
            self._entries.popitem(last=False)
        return prepared


def validate_asset_source(source: bytes) -> None:
    """Valida a fonte antes que catálogo, cache ou renderer a consumam."""
    if not source or len(source) > 16 * 1024 * 1024:
        raise ValueError("asset-fonte vazio ou acima de 16 MiB")
    stripped = source.lstrip()
    if stripped.startswith(b"<svg") or b"<svg" in stripped[:256]:
        lowered = stripped.lower()
        prohibited = (
            b"<!doctype",
            b"<!entity",
            b"<script",
            b"<foreignobject",
            b"javascript:",
            b"data:text/html",
        )
        if any(marker in lowered for marker in prohibited):
            raise ValueError("asset SVG contém conteúdo ativo")
        if re.search(rb"\bon[a-z]+\s*=", lowered):
            raise ValueError("asset SVG contém event handler")
        return
    # PNG, JPEG, WebP e AVIF são validados pelo loader confiável do Qt/Pillow
    # no adapter. O domínio ao menos rejeita conteúdo sem assinatura conhecida.
    signatures = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"RIFF", b"\x00\x00\x00")
    if not source.startswith(signatures):
        raise ValueError("formato de asset-fonte desconhecido")


__all__ = [
    "ASSET_RECIPE_SCHEMA_VERSION",
    "DEFAULT_ASSET_CAPABILITIES",
    "MAX_ASSET_NODES",
    "MAX_ASSET_RECIPES",
    "MAX_OUTLINE_WIDTH",
    "AssetRecipe",
    "AssetRecipeBook",
    "AssetRecipeCache",
    "AssetRecipeDiagnostic",
    "AssetRecipeFallback",
    "AssetRecipeNode",
    "AssetRecipeNodeType",
    "PreparedAssetVariant",
    "ResolvedAssetNode",
    "ResolvedAssetRecipe",
    "resolve_asset_recipes",
    "validate_asset_source",
]
