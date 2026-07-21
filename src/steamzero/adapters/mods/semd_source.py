# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Fonte de mods via Switch Emulator Mod Database (SEMD).

Raspagem do repositório GitHub theboy181/switch-mod-database que cataloga mods
de emuladores Switch por Title ID.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from typing import Any

from steamzero.ports import ModCandidate, ModCatalogPort, ModIdentity

_log = logging.getLogger(__name__)

SEMD_REPO = "theboy181/switch-mod-database"
SEMD_INDEX_URL = f"https://api.github.com/repos/{SEMD_REPO}/contents/mods"
GITHUB_RAW = "https://raw.githubusercontent.com"

_TITLE_ID_RE = re.compile(r"[0-9a-fA-F]{16}")


class SemdSource(ModCatalogPort):
    """Raspagem do Switch Emulator Mod Database via API GitHub.

    O SEMD organiza mods em pastas nomeadas por Title ID, cada uma contendo
    arquivos de descrição e links para download.
    """

    def __init__(self) -> None:
        self._local_cache: list[ModCandidate] = []

    # --- ModCatalogPort ------------------------------------------------------

    def search_by_title_id(self, title_id: str) -> list[ModCandidate]:
        self._ensure_cached()
        return [c for c in self._local_cache if c.title_id == title_id]

    def search_by_build_id(self, title_id: str, build_id: str) -> list[ModCandidate]:
        self._ensure_cached()
        return [c for c in self._local_cache if c.title_id == title_id and c.build_id == build_id]

    def refresh_catalog(self) -> int:
        self._local_cache.clear()
        return self._fetch_all()

    def _ensure_cached(self) -> None:
        if not self._local_cache:
            self._fetch_all()

    def _fetch_all(self) -> int:
        title_ids = self._list_title_id_dirs()
        count = 0
        for tid in title_ids:
            try:
                mod_entries = self._fetch_mods_for_title(tid)
                self._local_cache.extend(mod_entries)
                count += len(mod_entries)
            except Exception as exc:
                _log.debug("semd error para %s: %s", tid, exc)
        return count

    def _list_title_id_dirs(self) -> list[str]:
        url = SEMD_INDEX_URL
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "SteamZero",
        }
        req = urllib.request.Request(url, headers=headers)  # noqa: S310
        try:
            resp = urllib.request.urlopen(req, timeout=15)  # noqa: S310
            raw = resp.read()
        except Exception:
            return []
        try:
            entries: list[dict[str, Any]] = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return [
            e["name"]
            for e in entries
            if e.get("type") == "dir" and _TITLE_ID_RE.fullmatch(e["name"])
        ]

    def _fetch_mods_for_title(self, title_id: str) -> list[ModCandidate]:
        url = f"{SEMD_INDEX_URL}/{title_id}"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "SteamZero",
        }
        req = urllib.request.Request(url, headers=headers)  # noqa: S310
        try:
            resp = urllib.request.urlopen(req, timeout=15)  # noqa: S310
            raw = resp.read()
        except Exception:
            return []
        try:
            entries: list[dict[str, Any]] = json.loads(raw)
        except json.JSONDecodeError:
            return []

        candidates: list[ModCandidate] = []
        for entry in entries:
            name: str = entry.get("name", "")
            download_url: str = entry.get("download_url") or ""
            mod_id = ModIdentity(
                name=name,
                mod_type=_guess_mod_type_semd(name),
                source="semdb",
                source_url=download_url
                or f"https://github.com/{SEMD_REPO}/blob/main/mods/{title_id}/{name}",
                version=None,
                description=None,
                author="theboy181",
            )
            candidates.append(
                ModCandidate(
                    title_id=title_id,
                    build_id=None,
                    identity=mod_id,
                    match_confidence=0.8,
                )
            )
        return candidates


def _guess_mod_type_semd(name: str) -> str:
    lower = name.lower()
    if "60fps" in lower or "fps" in lower or "perf" in lower:
        return "performance"
    if "visual" in lower or "graphic" in lower or "reso" in lower or "1080p" in lower:
        return "graphics"
    if "ultrawide" in lower or "21by9" in lower:
        return "ultrawide"
    if "gameplay" in lower or "qol" in lower:
        return "gameplay"
    if "patch" in lower or "fix" in lower:
        return "patch"
    return "other"
