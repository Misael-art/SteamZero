# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Acervo Steam instalado no formato consumido pela home do Launcher."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from steamzero.adapters.launcher_catalog import CatalogGame
from steamzero.adapters.lsfg import LSFG_APP_ID
from steamzero.adapters.steam_appinfo import PLAYABLE_APP_TYPES, app_types
from steamzero.adapters.steam_gameplay import (
    default_steam_roots,
    library_roots,
    parse_app_manifest,
)

STEAM_SECTION = "steam"


def steam_catalog_games(
    *,
    roots: Sequence[Path] | None = None,
    types: Mapping[str, str] | None = None,
) -> tuple[CatalogGame, ...]:
    """Lista jogos Steam, filtrando ferramentas quando há classificação."""
    resolved = tuple(roots) if roots is not None else default_steam_roots()
    source_types = app_types() if types is None else types
    declared = {key: str(value).strip().lower() for key, value in source_types.items()}
    games: dict[str, CatalogGame] = {}
    for root in library_roots(resolved):
        steamapps = root / "steamapps"
        try:
            manifests = sorted(steamapps.glob("appmanifest_*.acf"))
        except OSError:
            continue
        for manifest in manifests:
            parsed = parse_app_manifest(manifest)
            if parsed is None:
                continue
            app_id, name = parsed
            if app_id == LSFG_APP_ID:
                continue
            kind = declared.get(app_id)
            if kind is not None and kind not in PLAYABLE_APP_TYPES:
                continue
            games[app_id] = CatalogGame(
                id=app_id,
                title=name,
                platform=STEAM_SECTION,
                cover_url=_cover_url(root, app_id),
                kind="steam",
            )
    return tuple(games.values())


def _cover_url(root: Path, app_id: str) -> str:
    library_cache = root / "appcache" / "librarycache"
    for name in (f"{app_id}_library_600x900.jpg", f"{app_id}p.jpg"):
        candidate = library_cache / name
        try:
            if candidate.is_file():
                return candidate.resolve().as_uri()
        except OSError:
            continue
    return ""
