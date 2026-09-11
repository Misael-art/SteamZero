# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded presentation window for the Cinema consumer of Theme Engine.

Navigation still belongs to the complete focus map. This window only bounds
render work; it neither removes games from the library nor chooses focus.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from steamzero.domain.scene_layout import (
    LayoutBounds,
    LayoutRecipe,
    LayoutRecipeBook,
    resolve_scene_layouts,
)


def cinema_metadata(record: Mapping[str, Any]) -> dict[str, Any]:
    """Project public display fields only; never pass arbitrary record data to QML."""
    result: dict[str, Any] = {}
    for key, limit in (
        ("description", 20000),
        ("releaseDate", 10),
        ("developer", 256),
        ("publisher", 256),
        ("ageRating", 64),
    ):
        value = record.get(key)
        if isinstance(value, str) and value:
            result[key] = value[:limit]
    for key, maximum in (("players", 64), ("playtime", 2**53 - 1)):
        value = record.get(key)
        if (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 0 <= value <= maximum
            and (key != "players" or value > 0)
        ):
            result[key] = value
    genres = record.get("genres")
    rating = record.get("rating")
    if isinstance(rating, (int, float)) and not isinstance(rating, bool) and 0 <= rating <= 100:
        result["rating"] = rating
    if isinstance(genres, list):
        result["genres"] = [
            value[:128] for value in genres[:16] if isinstance(value, str) and value
        ]
    media = record.get("media")
    if isinstance(media, Mapping):
        for role in ("cover", "fanart", "screenshot", "marquee", "video", "icon"):
            asset = media.get(role)
            path = asset.get("path") if isinstance(asset, Mapping) else None
            if (
                isinstance(path, str)
                and path.startswith("/")
                and not path.startswith("//")
                and len(path) <= 4096
                and "\x00" not in path
                and ".." not in path.split("/")
            ):
                result[role + "Url"] = "file://" + quote(path, safe="/")
    return result


@dataclass(frozen=True)
class CinemaWindow:
    items: tuple[Mapping[str, Any], ...]
    selected: int
    source_indices: tuple[int, ...]


def cinema_window(items: Sequence[Mapping[str, Any]], selected: int) -> CinemaWindow:
    """Return at most seven distinct neighbours, including the actual selection."""
    if not items:
        return CinemaWindow((), 0, ())
    if isinstance(selected, bool) or not 0 <= selected < len(items):
        raise ValueError("Cinema selection must address the current collection")
    count = min(7, len(items))
    before = (count - 1) // 2
    indices = tuple((selected + offset) % len(items) for offset in range(-before, count - before))
    return CinemaWindow(tuple(items[index] for index in indices), before, indices)


def resolve_cinema_covers(
    recipe: LayoutRecipe,
    items: Sequence[Mapping[str, Any]],
    selected: int,
    *,
    bounds: LayoutBounds,
) -> dict[str, Any]:
    """Use the validated theme recipe, rebasing selection to its bounded window.

    The caller supplies the theme recipe, not executable theme code. Returned
    source indices preserve identity for semantic hit targets in the shell.
    """
    window = cinema_window(items, selected)
    raw = recipe.to_dict()
    raw.update(source="cinema.items", selected=window.selected, maxItems=7)
    bounded = LayoutRecipe.from_dict(recipe.id, raw)
    resolved = resolve_scene_layouts(
        LayoutRecipeBook({recipe.id: bounded}),
        {"cinema": {"items": list(window.items)}},
        bounds=bounds,
    ).to_qml_object()
    resolved["sourceIndices"] = list(window.source_indices)
    resolved["selected"] = window.selected
    return resolved
