# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Adapter para SteamGridDB — capas, grids, hero/banner, logos e ícones.

API v2 (``https://www.steamgriddb.com/api/v2``):
- Grids (boxart), Heroes (banners), Logos, Icons.
- Matching por Steam App ID ou por nome.
- Rate limit: 8 req/s com chave gratuita.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

from steamzero.adapters.scraping.base import BaseMediaProvider, RateLimiter
from steamzero.core.errors import SteamZeroError
from steamzero.ports import GameIdentity, MediaCandidate

_API_BASE = "https://www.steamgriddb.com/api/v2"
_MAX_RETRIES = 2

_KIND_MAP: dict[str, str] = {
    "grid": "grids",
    "hero": "heroes",
    "logo": "logos",
    "icon": "icons",
}
_SUPPORTED_KINDS = frozenset(_KIND_MAP)


class SteamGridDbAdapter(BaseMediaProvider):
    """Adapter para SteamGridDB API v2.

    Requer ``api_key`` configurada pelo usuário.
    Matching prioritário por ``title_id`` como Steam App ID numérico.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        super().__init__(rate_limiter=rate_limiter)
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "steamgriddb"

    def supported_kinds(self) -> frozenset[str]:
        return _SUPPORTED_KINDS

    def supported_platforms(self) -> frozenset[str]:
        return frozenset({"switch", "pc", "steam"})

    def search(
        self,
        identity: GameIdentity,
        media_kinds: list[str],
        region_priority: list[str] | None = None,
    ) -> list[MediaCandidate]:
        if not self._api_key:
            raise SteamZeroError(
                "E-SCRAPE-CREDENTIAL-MISSING",
                detail="SteamGridDB requer API key configurada em Settings > Scraping",
            )

        kinds_to_fetch = set(media_kinds) & _SUPPORTED_KINDS
        if not kinds_to_fetch:
            return []

        game_id = self._resolve_game_id(identity)
        if game_id is None:
            return []

        candidates: list[MediaCandidate] = []
        for kind in kinds_to_fetch:
            endpoint = _KIND_MAP[kind]
            url = f"{_API_BASE}/{endpoint}/game/{game_id}"
            results = self._fetch_json(url)
            if not results:
                continue
            for item in results:
                media_url = item.get("url", "")
                if not media_url:
                    continue
                candidates.append(
                    MediaCandidate(
                        url=media_url.replace("http://", "https://"),
                        media_kind=kind,
                        provider=self.name,
                        confidence=0.9,
                        width=item.get("width"),
                        height=item.get("height"),
                        license="SteamGridDB",
                        attribution="SteamGridDB",
                        hash=item.get("hash") or None,
                    )
                )

        candidates.sort(key=lambda c: (-c.confidence, c.media_kind))
        return candidates

    def test_connection(self) -> bool:
        if not self._api_key:
            raise SteamZeroError(
                "E-SCRAPE-CREDENTIAL-MISSING",
                detail="SteamGridDB requer API key",
            )
        try:
            req = urllib.request.Request(  # noqa: S310
                f"{_API_BASE}/games/steam/1",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=15.0) as resp:  # noqa: S310
                body = resp.read()
                payload = json.loads(body)
                if isinstance(payload, dict) and payload.get("success"):
                    return True
                raise SteamZeroError(
                    "E-SCRAPE-CREDENTIAL-REJECTED",
                    detail="chave SteamGridDB rejeitada pela API",
                )
        except urllib.error.HTTPError as exc:
            if exc.code == 401 or exc.code == 403:
                raise SteamZeroError(
                    "E-SCRAPE-CREDENTIAL-REJECTED",
                    detail="chave SteamGridDB rejeitada (401/403)",
                ) from exc
            raise SteamZeroError(
                "E-SCRAPE-HTTP-ERROR",
                detail=f"HTTP {exc.code} do SteamGridDB",
            ) from exc
        except (OSError, urllib.error.URLError) as exc:
            raise SteamZeroError(
                "E-SCRAPE-OFFLINE",
                detail="não foi possível conectar ao SteamGridDB",
            ) from exc

    def _resolve_game_id(self, identity: GameIdentity) -> int | None:
        """Resolve o SteamGridDB game_id a partir do Title ID."""
        self._rate_limit()
        title_id = identity.title_id
        if title_id:
            url = f"{_API_BASE}/games/rom/{title_id}"
            results = self._fetch_json(url)
            if results:
                return results[0].get("id")

        self._rate_limit()
        params = urlencode({"term": identity.title, "platform": identity.platform_slug})
        url = f"{_API_BASE}/games/autocomplete?{params}"
        results = self._fetch_json(url)
        if results:
            return results[0].get("id")
        return None

    def _fetch_json(self, url: str) -> list[dict[str, Any]]:
        """Chama API e retorna ``data`` como lista de dicts."""
        url = url.replace("http://", "https://")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }
        req = urllib.request.Request(url, headers=headers)  # noqa: S310
        try:
            with urllib.request.urlopen(req, timeout=15.0) as resp:  # noqa: S310
                body = resp.read()
                payload = json.loads(body)
                if not isinstance(payload, dict):
                    return []
                success = payload.get("success", False)
                data = payload.get("data", [])
                if not success or not isinstance(data, list):
                    return []
                return data
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            return []
