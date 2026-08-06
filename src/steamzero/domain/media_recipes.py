# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Receitas declarativas para apresentar uma única mídia no renderer.

Receitas escolhem *papéis* de mídia e parâmetros de composição; elas jamais
contêm caminhos, bytes, shaders ou instruções executáveis. O read model continua
o dono da URL/master e o QML aplica a receita sobre a mesma source em runtime.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

MEDIA_RECIPE_SCHEMA_VERSION = 1


class MediaRole(StrEnum):
    CONTEXTUAL_BACKDROP = "contextualBackdrop"
    FOCUSED_COVER = "focusedCover"
    PERIPHERAL_COVER = "peripheralCover"
    SCREENSHOT = "screenshot"


class MediaSourceKind(StrEnum):
    HERO = "hero"
    FANART = "fanart"
    COVER = "cover"
    SCREENSHOT = "screenshot"
    BANNER = "banner"
    PLATFORM_ART = "platformArt"
    GEOMETRIC = "geometric"


class MediaFit(StrEnum):
    CROP = "crop"
    CONTAIN = "contain"


@dataclass(frozen=True)
class MediaRecipe:
    role: MediaRole
    source_order: tuple[MediaSourceKind, ...]
    fit: MediaFit = MediaFit.CROP
    focal_x: float = 0.5
    focal_y: float = 0.5
    effect_stack: str | None = None
    max_decode_width: int = 1920

    def __post_init__(self) -> None:
        if not self.source_order:
            raise ValueError("recipe precisa declarar sourceOrder")
        if len(self.source_order) != len(set(self.source_order)):
            raise ValueError("sourceOrder não pode repetir fontes")
        if not 0 <= self.focal_x <= 1 or not 0 <= self.focal_y <= 1:
            raise ValueError("focalX/focalY precisam estar entre 0 e 1")
        if not 64 <= self.max_decode_width <= 4096:
            raise ValueError("maxDecodeWidth precisa estar entre 64 e 4096")
        if self.effect_stack is not None and (
            not self.effect_stack
            or not self.effect_stack[0].islower()
            or len(self.effect_stack) > 64
        ):
            raise ValueError("effectStack inválido")

    @classmethod
    def from_dict(cls, role: str, payload: Mapping[str, Any]) -> MediaRecipe:
        try:
            recipe_role = MediaRole(role)
            sources = tuple(MediaSourceKind(item) for item in payload["sourceOrder"])
            fit = MediaFit(payload.get("fit", "crop"))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("receita de mídia inválida") from exc
        return cls(
            role=recipe_role,
            source_order=sources,
            fit=fit,
            focal_x=float(payload.get("focalX", 0.5)),
            focal_y=float(payload.get("focalY", 0.5)),
            effect_stack=payload.get("effectStack"),
            max_decode_width=int(payload.get("maxDecodeWidth", 1920)),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "sourceOrder": [source.value for source in self.source_order],
            "fit": self.fit.value,
            "focalX": self.focal_x,
            "focalY": self.focal_y,
            "maxDecodeWidth": self.max_decode_width,
        }
        if self.effect_stack is not None:
            result["effectStack"] = self.effect_stack
        return result


def parse_media_recipes(payload: Mapping[str, Any] | None) -> dict[str, MediaRecipe]:
    if not payload:
        return {}
    if payload.get("schemaVersion") != MEDIA_RECIPE_SCHEMA_VERSION:
        raise ValueError("schemaVersion de receitas de mídia incompatível")
    recipes = payload.get("recipes")
    if not isinstance(recipes, Mapping):
        raise ValueError("recipes de mídia precisa ser objeto")
    result: dict[str, MediaRecipe] = {}
    for role, recipe in recipes.items():
        if not isinstance(role, str) or not isinstance(recipe, Mapping):
            raise ValueError("receita de mídia precisa ser objeto")
        result[role] = MediaRecipe.from_dict(role, recipe)
    return result


def media_recipes_to_dict(recipes: Mapping[str, MediaRecipe]) -> dict[str, Any]:
    return {
        "schemaVersion": MEDIA_RECIPE_SCHEMA_VERSION,
        "recipes": {role: recipe.to_dict() for role, recipe in recipes.items()},
    }


def choose_media_source(
    recipe: MediaRecipe, available: Mapping[str, str | None]
) -> tuple[MediaSourceKind, str] | None:
    """Escolhe deterministicamente uma URL publicada; nunca consulta disco/rede."""
    for source in recipe.source_order:
        value = available.get(source.value)
        if isinstance(value, str) and value:
            return source, value
    return None


def validate_recipe_effect_stacks(
    recipes: Sequence[MediaRecipe], effect_stacks: Mapping[str, object]
) -> None:
    for recipe in recipes:
        if recipe.effect_stack is not None and recipe.effect_stack not in effect_stacks:
            raise ValueError(f"effectStack ausente para {recipe.role.value}")
