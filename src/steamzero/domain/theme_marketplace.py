# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Marketplace de temas: catálogo remoto, cache, busca e instalação."""

from __future__ import annotations

import contextlib
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from steamzero.core import fs, log, paths
from steamzero.core.errors import SteamZeroError
from steamzero.core.net import HttpClient, fetch_bytes
from steamzero.domain.themes import ThemeManifest

_DEFAULT_CATALOG_URL = "https://themes.steamzero.org/catalog-v1.json"
_CATALOG_TTL_SECS = 3600
_CATALOG_MAX_BYTES = 2 * 1024 * 1024


def _catalog_url() -> str:
    return os.environ.get("STEAMZERO_THEMES_CATALOG_URL") or _DEFAULT_CATALOG_URL


@dataclass
class MarketplaceTheme:
    id: str
    name: str
    version: str
    author: str
    license: str
    description: str
    compatibility: dict[str, object] = field(default_factory=dict)
    curated: bool = False
    verified: bool = False
    download_url: str = ""
    checksum_sha256: str = ""
    size: int = 0
    tags: list[str] = field(default_factory=list)
    rating: float = 0.0
    download_count: int = 0
    homepage: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> MarketplaceTheme:
        compat = raw.get("compatibility")
        raw_tags = raw.get("tags")
        return cls(
            id=str(raw["id"]),
            name=str(raw.get("name", "")),
            version=str(raw.get("version", "")),
            author=str(raw.get("author", "")),
            license=str(raw.get("license", "")),
            description=str(raw.get("description", "")),
            compatibility=dict(compat) if isinstance(compat, dict) else {},
            curated=bool(raw.get("curated", False)),
            verified=bool(raw.get("verified", False)),
            download_url=str(raw.get("downloadUrl", "")),
            checksum_sha256=str(raw.get("checksumSha256", "")),
            size=int(str(raw.get("size") or 0)),
            tags=list(raw_tags) if isinstance(raw_tags, list) else [],
            rating=float(str(raw.get("rating") or 0.0)),
            download_count=int(str(raw.get("downloadCount") or 0)),
            homepage=str(raw.get("homepage", "")),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "license": self.license,
            "description": self.description,
            "compatibility": self.compatibility,
            "curated": self.curated,
            "verified": self.verified,
            "downloadUrl": self.download_url,
            "checksumSha256": self.checksum_sha256,
            "size": self.size,
            "tags": self.tags,
            "rating": self.rating,
            "downloadCount": self.download_count,
            "homepage": self.homepage,
        }


class ThemeMarketplace:
    def __init__(
        self,
        catalog_url: str | None = None,
        http_client: HttpClient | None = None,
    ) -> None:
        self._catalog_url = catalog_url or _catalog_url()
        self._http_client = http_client
        self._entries: list[MarketplaceTheme] | None = None

    def search(self, query: str = "", *, refresh: bool = False) -> list[MarketplaceTheme]:
        if self._entries is None or refresh:
            self._entries = self._load_catalog()
        q = query.strip().casefold()
        if not q:
            return list(self._entries)
        results: list[MarketplaceTheme] = []
        for entry in self._entries:
            if (q in entry.id.casefold()
                    or q in entry.name.casefold()
                    or q in entry.author.casefold()
                    or q in entry.description.casefold()
                    or any(q in t.casefold() for t in entry.tags)):
                results.append(entry)
        return results

    def get(self, theme_id: str) -> MarketplaceTheme:
        entries = self.search()
        for entry in entries:
            if entry.id == theme_id:
                return entry
        raise SteamZeroError(
            "E-THEME-NOT-FOUND",
            detail=f"tema '{theme_id}' não encontrado no catálogo remoto",
        )

    def install(
        self,
        theme_id: str,
        *,
        force: bool = False,
        yes: bool = False,
        validate: Callable[[Path], ThemeManifest] | None = None,
    ) -> dict[str, str]:
        from steamzero.domain.theme_install import ThemeInstaller as _ThemeInstaller

        entry = self.get(theme_id)
        if not entry.download_url:
            raise SteamZeroError(
                "E-THEME-DOWNLOAD-FAILED",
                detail=f"tema '{theme_id}' não possui URL de download",
            )

        checksum = entry.checksum_sha256 or None
        installer = _ThemeInstaller(validate=validate)
        return installer.install(
            entry.download_url,
            force=force,
            yes=yes,
            checksum_sha256=checksum,
            http_client=self._http_client,
        )

    def _load_catalog(self) -> list[MarketplaceTheme]:
        data = self._try_cache()
        if data is not None:
            return data

        raw = self._fetch_catalog()
        self._write_cache(raw)
        return self._parse_catalog(raw)

    def _try_cache(self) -> list[MarketplaceTheme] | None:
        cache_path = paths.theme_catalog_cache_path()
        if not cache_path.is_file():
            return None
        try:
            mtime = cache_path.stat().st_mtime
            if time.time() - mtime > _CATALOG_TTL_SECS:
                return None
            raw = cache_path.read_bytes()
            return self._parse_catalog(raw)
        except Exception:
            return None

    def _fetch_catalog(self) -> bytes:
        try:
            return fetch_bytes(
                self._catalog_url,
                max_bytes=_CATALOG_MAX_BYTES,
                client=self._http_client,
            )
        except Exception as exc:
            cache = self._load_cache_stale()
            if cache is not None:
                log.get_logger().warning("theme_marketplace.cache-stale", url=self._catalog_url)
                return cache
            raise SteamZeroError(
                "E-THEME-CATALOG-FAILED",
                detail=str(exc),
            ) from exc

    def _load_cache_stale(self) -> bytes | None:
        cache_path = paths.theme_catalog_cache_path()
        if cache_path.is_file():
            with contextlib.suppress(Exception):
                return cache_path.read_bytes()
        return None

    def _write_cache(self, data: bytes) -> None:
        try:
            fs.ensure_dir(paths.theme_catalog_cache_path().parent)
            fs.write_atomic(paths.theme_catalog_cache_path(), data)
        except Exception:
            log.get_logger().warning("theme_marketplace.cache-write-failed")

    def _parse_catalog(self, raw: bytes) -> list[MarketplaceTheme]:
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SteamZeroError(
                "E-THEME-CATALOG-FAILED",
                detail=f"catálogo inválido: {exc}",
            ) from exc
        if not isinstance(doc, dict) or "entries" not in doc:
            raise SteamZeroError(
                "E-THEME-CATALOG-FAILED",
                detail="catálogo remoto não contém 'entries'",
            )
        entries_raw = doc["entries"]
        if not isinstance(entries_raw, list):
            raise SteamZeroError(
                "E-THEME-CATALOG-FAILED",
                detail="'entries' precisa ser uma lista",
            )
        return [MarketplaceTheme.from_dict(item) for item in entries_raw if isinstance(item, dict)]
