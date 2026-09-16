# SPDX-License-Identifier: GPL-3.0-or-later
"""Projection of the canonical media registry into the AURA Launcher model.

The launcher consumes a read model only.  This adapter reads the registry
published by the media pipeline, checks every path against the managed media
root, and emits the existing local URL contract.  Missing, stale, symlinked or
hostile entries are ignored so the caller keeps the textual fallback.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote

_MAX_GAMES = 4096
_MAX_SCREENSHOTS = 8
_MAX_RELATIVE_PATH = 512


def launcher_media_metadata(
    *,
    media_root: Path,
    assignments_path: Path | None = None,
) -> dict[str, dict[str, object]]:
    """Return safe ``game_id -> Cinema`` media fields from the registry.

    ``assignments-v1.json`` is the canonical source of truth.  The registry
    stores paths relative to ``media_root``; the resulting ``file://`` URLs are
    limited to regular files beneath that root and only to managed media
    directories.  A malformed registry degrades to an empty projection.
    """
    registry_path = assignments_path or (media_root / "registry" / "assignments-v1.json")
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return {}
    entries = payload.get("entries") if isinstance(payload, Mapping) else None
    if not isinstance(entries, list):
        return {}

    resolved_root = media_root.resolve(strict=False)
    result: dict[str, dict[str, object]] = {}
    for raw in entries[:_MAX_GAMES]:
        if not isinstance(raw, Mapping):
            continue
        game_id = raw.get("gameId")
        masters = raw.get("masters")
        if not isinstance(game_id, str) or not game_id or not isinstance(masters, Mapping):
            continue
        projected: dict[str, object] = {}
        screenshot_urls: list[str] = []
        # The serialized registry normally sorts master roles, but older
        # clients do not necessarily do so. Ordering here makes the
        # carousel/detail page deterministic and keeps screenshot 1 before
        # screenshot 2 when a future importer uses numbered role names.
        ordered_masters = sorted(masters.items(), key=lambda item: _media_kind_order(item[0]))
        for kind, value in ordered_masters:
            if not isinstance(kind, str) or not isinstance(value, str):
                continue
            url = _managed_media_url(resolved_root, value)
            if url is None:
                continue
            if kind in {"box2d", "boxart", "grid"} and "coverUrl" not in projected:
                projected["coverUrl"] = url
            elif kind in {"hero", "fanart"} and "fanartUrl" not in projected:
                projected["fanartUrl"] = url
            elif _is_screenshot_kind(kind) and len(screenshot_urls) < _MAX_SCREENSHOTS:
                screenshot_urls.append(url)
            elif kind == "logo" and "logoUrl" not in projected:
                projected["logoUrl"] = url
            elif kind == "icon" and "iconUrl" not in projected:
                projected["iconUrl"] = url
            elif kind == "marquee" and "marqueeUrl" not in projected:
                projected["marqueeUrl"] = url
            elif kind == "video" and "videoUrl" not in projected:
                projected["videoUrl"] = url
        if screenshot_urls:
            projected["screenshotUrls"] = screenshot_urls
        if projected:
            result[game_id] = projected
    return result


def _is_screenshot_kind(kind: str) -> bool:
    """Accept the canonical role and numbered roles from older importers."""
    if kind == "screenshot":
        return True
    return kind.startswith("screenshot") and kind[10:].isdigit()


def _media_kind_order(kind: object) -> tuple[int, int, str]:
    """Sort stable roles before numbered screenshot variants."""
    text = kind if isinstance(kind, str) else ""
    if text == "screenshot":
        return (1, 0, text)
    if _is_screenshot_kind(text):
        return (1, int(text[10:]), text)
    return (0, 0, text)


def _managed_media_url(root: Path, relative: str) -> str | None:
    """Resolve one registry path without allowing traversal or symlink escape."""
    if (
        not relative
        or len(relative) > _MAX_RELATIVE_PATH
        or "\x00" in relative
        or ".." in Path(relative).parts
    ):
        return None
    candidate = Path(relative)
    if (
        candidate.is_absolute()
        or not candidate.parts
        or candidate.parts[0]
        not in {
            "masters",
            "optimized",
        }
    ):
        return None
    path = root / candidate
    try:
        if path.is_symlink() or not path.is_file():
            return None
        resolved = path.resolve(strict=True)
    except OSError:
        return None
    if not resolved.is_relative_to(root) or not resolved.is_file():
        return None
    return "file://" + quote(str(resolved), safe="/")
