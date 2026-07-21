# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Fonte de cheats via Nintendo Switch Emulator Cheats Manager (NSECM).

Raspagem de repositórios públicos de cheats (cheatslips, GBAtemp, tomad)
organizados por Title ID + Build ID no formato Atmosphere.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from typing import Any

from steamzero.ports import CheatCandidate, CheatCatalogPort, CheatIdentity

_log = logging.getLogger(__name__)

# Fontes conhecidas de cheats
_CHEAT_SOURCES: dict[str, str] = {
    "tomad": "tomad/cheatslips",
    "gbatemp": "gbatemp/cheats",
}

_GITHUB_API = "https://api.github.com"
_GITHUB_RAW = "https://raw.githubusercontent.com"

_TITLE_ID_RE = re.compile(r"[0-9a-fA-F]{16}")
_BUILD_ID_RE = re.compile(r"[0-9a-fA-F]{32}")
_CODE_LINE_RE = re.compile(r"^[0-9a-fA-F]{8}\s+[0-9a-fA-F]{8}")


def _parse_cheat_text(text: str) -> tuple[tuple[str, ...], str, str | None]:
    """Extrai códigos, nome e Build ID de um arquivo de cheat Atmosphere."""
    codes: list[str] = []
    name = "unknown"
    build_id: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("#"):
            lower = stripped.lower()
            if "buildid" in lower or "build_id" in lower:
                match = _BUILD_ID_RE.search(stripped)
                if match:
                    build_id = match.group(0).upper()
            name_match = re.search(r"//\s*(.+)", stripped)
            if name_match and name == "unknown":
                name = name_match.group(1).strip()
            continue
        if _CODE_LINE_RE.match(stripped):
            codes.append(stripped)
    return (tuple(codes), name, build_id)


def _guess_cheat_type(name: str) -> str:
    lower = name.lower()
    if "gold" in lower or "money" in lower or "rupee" in lower:
        return "gold"
    if "inf" in lower or "moon" in lower or "health" in lower or "hp " in lower:
        return "infinite"
    if "speed" in lower or "move" in lower:
        return "speed"
    if "item" in lower or "inventory" in lower or "material" in lower:
        return "items"
    if "unlock" in lower or "all" in lower:
        return "unlock"
    if "stat" in lower or "exp" in lower or "level" in lower:
        return "stats"
    return "other"


class NsecmSource(CheatCatalogPort):
    """Catálogo de cheats via raspagem de repositórios GitHub públicos.

    Simula o comportamento do NSECM: auto-popula cheats por Title ID,
    suporta múltiplos provedores e instalação na estrutura Atmosphere.
    """

    def __init__(self, sources: dict[str, str] | None = None) -> None:
        self._sources = sources or dict(_CHEAT_SOURCES)
        self._local_cache: list[CheatCandidate] = []

    # --- CheatCatalogPort ----------------------------------------------------

    def search_by_title_id(self, title_id: str) -> list[CheatCandidate]:
        self._ensure_cached()
        return [c for c in self._local_cache if c.title_id == title_id]

    def search_by_build_id(self, title_id: str, build_id: str) -> list[CheatCandidate]:
        self._ensure_cached()
        return [c for c in self._local_cache if c.title_id == title_id and c.build_id == build_id]

    def refresh_catalog(self) -> int:
        self._local_cache.clear()
        return self._fetch_all()

    def _ensure_cached(self) -> None:
        if not self._local_cache:
            self._fetch_all()

    def _fetch_all(self) -> int:
        all_candidates: list[CheatCandidate] = []
        for source_key, repo in self._sources.items():
            try:
                candidates = self._fetch_repo_cheats(repo, source_key)
                all_candidates.extend(candidates)
            except Exception as exc:
                _log.debug("erro fetch cheats %s: %s", source_key, exc)
        self._local_cache = all_candidates
        return len(all_candidates)

    def _fetch_repo_cheats(self, repo: str, source_key: str) -> list[CheatCandidate]:
        url = f"{_GITHUB_API}/repos/{repo}/contents"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "SteamZero",
        }
        req = urllib.request.Request(url, headers=headers)  # noqa: S310
        try:
            resp = urllib.request.urlopen(req, timeout=15)  # noqa: S310
            raw = resp.read()
        except Exception as exc:
            _log.debug("erro urlopen %s: %s", url, exc)
            return []
        try:
            entries: list[dict[str, Any]] = json.loads(raw)
        except json.JSONDecodeError:
            return []

        candidates: list[CheatCandidate] = []
        for entry in entries:
            name: str = entry.get("name", "")
            entry_type: str = entry.get("type", "")
            if entry_type != "dir":
                continue
            title_ids = _TITLE_ID_RE.findall(name)
            if not title_ids:
                continue
            tid = title_ids[0].upper()
            try:
                mod_candidates = self._fetch_cheats_for_title(repo, tid, source_key)
                candidates.extend(mod_candidates)
            except Exception as exc:
                _log.debug("erro cheats para %s: %s", tid, exc)
        return candidates

    def _fetch_cheats_for_title(
        self, repo: str, title_id: str, source_key: str
    ) -> list[CheatCandidate]:
        url = f"{_GITHUB_API}/repos/{repo}/contents/{title_id}"
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

        candidates: list[CheatCandidate] = []
        for entry in entries:
            name: str = entry.get("name", "")
            download_url: str = entry.get("download_url") or ""
            if not download_url:
                continue
            try:
                raw_content = urllib.request.urlopen(  # noqa: S310
                    download_url, timeout=15
                ).read()
                text = raw_content.decode("utf-8", errors="replace")
            except Exception as exc:
                _log.debug("erro download cheat: %s", exc)
                continue

            codes, parsed_name, build_id = _parse_cheat_text(text)
            if not codes:
                continue

            cheat_ident = CheatIdentity(
                name=parsed_name,
                cheat_type=_guess_cheat_type(parsed_name),
                source=f"nsecm:{source_key}",
                source_url=download_url,
                description=f"From {source_key} / {name}",
                author=source_key,
            )
            candidates.append(
                CheatCandidate(
                    title_id=title_id,
                    build_id=build_id,
                    identity=cheat_ident,
                    codes=codes,
                    match_confidence=1.0 if build_id else 0.7,
                )
            )
        return candidates
