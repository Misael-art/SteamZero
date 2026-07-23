# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Fonte de mods via GitHub (StevensND, Fl4sh9174, KeatonTheBot, BoycottP).

Raspagem de arquivos de repositórios públicos conhecidos que catalogam mods
de emuladores Switch por Title ID + Build ID.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from steamzero.core import fs
from steamzero.core.net import NetworkFailure, fetch_bytes
from steamzero.ports import ModCandidate, ModCatalogPort, ModIdentity

_log = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

_KNOWN_SOURCES: dict[str, str] = {
    "stevensnd": "StevensND/switch-port-mods",
    "fl4sh9174": "Fl4sh9174/Switch-Ultrawide-Mods",
    "boycottp": "BoycottP/switch-mods",
}

_TITLE_ID_RE = re.compile(r"[0-9a-fA-F]{16}")
_BUILD_ID_RE = re.compile(r"[0-9a-fA-F]{32}")


class GithubModSource(ModCatalogPort):
    """Raspagem de repositórios GitHub para catálogo de mods.

    Usa a API pública do GitHub (sem token=rate limit reduzido).
    """

    def __init__(
        self,
        sources: dict[str, str] | None = None,
        cache_path: Path | None = None,
    ) -> None:
        self._sources = sources or dict(_KNOWN_SOURCES)
        self._cache_path = cache_path
        self._local_cache: list[ModCandidate] = []
        self._cache_timestamp: float | None = None

    # --- ModCatalogPort ------------------------------------------------------

    def search_by_title_id(self, title_id: str) -> list[ModCandidate]:
        self._ensure_cached()
        return [c for c in self._local_cache if c.title_id == title_id]

    def search_by_build_id(self, title_id: str, build_id: str) -> list[ModCandidate]:
        self._ensure_cached()
        return [c for c in self._local_cache if c.title_id == title_id and c.build_id == build_id]

    def refresh_catalog(self) -> int:
        return self._fetch_all_and_cache()

    def _ensure_cached(self) -> None:
        if not self._local_cache:
            self._fetch_all_and_cache()

    def _fetch_all_and_cache(self) -> int:
        all_candidates: list[ModCandidate] = []
        for source_key, repo in self._sources.items():
            try:
                candidates = self._fetch_repo_mods(repo, source_key)
                all_candidates.extend(candidates)
            except Exception as exc:
                _log.debug("erro fetch %s: %s", source_key, exc)
        self._local_cache = all_candidates
        self._cache_timestamp = datetime.now(UTC).timestamp()
        if self._cache_path and all_candidates:
            fs.ensure_dir(self._cache_path.parent)
            cache_data = [
                {
                    "titleId": c.title_id,
                    "buildId": c.build_id,
                    "name": c.identity.name,
                    "modType": c.identity.mod_type,
                    "source": c.identity.source,
                    "sourceUrl": c.identity.source_url,
                    "version": c.identity.version,
                    "description": c.identity.description,
                    "author": c.identity.author,
                }
                for c in all_candidates
            ]
            fs.write_atomic_text(self._cache_path, json.dumps(cache_data, indent=2))
        return len(all_candidates)

    def _fetch_repo_mods(self, repo: str, source_key: str) -> list[ModCandidate]:
        url = f"{GITHUB_API}/repos/{repo}/contents"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "SteamZero",
        }
        try:
            raw = fetch_bytes(
                url, max_bytes=4 * 1024 * 1024, timeout_seconds=15, headers=headers
            )
        except NetworkFailure as exc:
            _log.debug("erro urlopen %s: %s", url, exc)
            return []
        try:
            entries: list[dict[str, Any]] = json.loads(raw)
        except json.JSONDecodeError:
            return []

        candidates: list[ModCandidate] = []
        for entry in entries:
            name: str = entry.get("name", "")
            entry_type: str = entry.get("type", "")
            if entry_type != "dir":
                continue
            title_ids = _TITLE_ID_RE.findall(name)
            if not title_ids:
                continue
            tid = title_ids[0].upper()
            bid_match = _BUILD_ID_RE.search(name)
            bid = bid_match.group(0).upper() if bid_match else None
            download_url: str | None = entry.get("url")
            mod_id = ModIdentity(
                name=name,
                mod_type=_guess_mod_type(name),
                source=f"github:{source_key}",
                source_url=download_url or f"https://github.com/{repo}/tree/main/{name}",
                version=None,
                description=None,
                author=source_key,
            )
            candidates.append(
                ModCandidate(
                    title_id=tid,
                    build_id=bid,
                    identity=mod_id,
                    match_confidence=1.0 if bid else 0.7,
                )
            )
        return candidates


def _guess_mod_type(name: str) -> str:
    lower = name.lower()
    if "ultrawide" in lower or "21:" in lower or "32:" in lower:
        return "ultrawide"
    if "60fps" in lower or "fps" in lower or "performance" in lower:
        return "performance"
    if "graphic" in lower or "visual" in lower or "1080p" in lower or "resolution" in lower:
        return "graphics"
    if "gameplay" in lower or "quality" in lower:
        return "gameplay"
    if "patch" in lower or "fix" in lower:
        return "patch"
    return "other"
