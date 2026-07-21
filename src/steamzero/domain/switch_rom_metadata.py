# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Pipeline de resolução de mídia de jogos Switch com fallback em cascata.

Ordem de prioridade para exibição de imagem:
1. Mídia customizada pelo usuário (media_scraper)
2. Ícone nativo extraído da ROM (NativeIconExtractor)
3. Cache do emulador (Ryujinx / Yuzu)
4. Fallback padrão (ícone azul do Switch)
"""

from __future__ import annotations

import logging
from pathlib import Path

from steamzero.core.fs import ensure_dir, symlink_atomic, write_atomic
from steamzero.ports import EmulatorCachePort, MediaProviderPort, RomMetadata, RomMetadataPort

_log = logging.getLogger(__name__)

# Fallback SVG: ícone azul do Switch em Base64
_FALLBACK_ICON = (
    b"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 256 256'>"
    b"<rect width='256' height='256' fill='#e60012' rx='32'/>"
    b"<text x='128' y='148' text-anchor='middle' font-size='72'"
    b" font-family='sans-serif' fill='white'>NS</text></svg>"
)


class MediaFallbackPipeline:
    """Pipeline de resolução de mídia com fallback em cascata.

    ``resolve_icon()`` retorna o caminho do ícone no cache local, ou None
    se nem o fallback padrão estiver disponível. ``resolve_metadata()``
    retorna um dicionário com title_id, título, developer, versão.
    """

    def __init__(
        self,
        native_extractor: RomMetadataPort,
        emulator_cache: EmulatorCachePort,
        media_provider: MediaProviderPort | None = None,
        media_cache_dir: Path | None = None,
    ) -> None:
        self._native_extractor = native_extractor
        self._emulator_cache = emulator_cache
        self._media_provider = media_provider
        self._media_cache_dir = media_cache_dir

    def resolve_icon(
        self,
        title_id: str,
        rom_path: Path | None = None,
        game_id: str | None = None,
    ) -> Path | None:
        """Resolve o ícone na ordem de prioridade.

        1. Cache de mídia do usuário (media_scraper)
        2. Ícone nativo da ROM
        3. Cache do emulador
        4. Fallback padrão
        """
        # 1. Mídia customizada do usuário
        cached = self._find_cached_media(title_id, game_id)
        if cached is not None:
            return cached

        # 2. Ícone nativo da ROM
        if rom_path and rom_path.is_file():
            native = self._cache_native_icon(title_id, rom_path)
            if native is not None:
                return native

        # 3. Cache do emulador
        emu_icon = self._emulator_cache.find_icon(title_id)
        if emu_icon is not None:
            return emu_icon

        # 4. Fallback padrão
        return self._write_fallback(title_id)

    def resolve_metadata(
        self,
        title_id: str,
        rom_path: Path | None = None,
    ) -> dict[str, str | None]:
        """Resolve metadados: nome, developer, versão, idiomas."""
        meta = self._extract_native_metadata(rom_path)
        if meta:
            return {
                "titleId": meta.title_id,
                "title": meta.title,
                "developer": meta.developer,
                "version": meta.version,
                "languages": ",".join(meta.languages),
                "source": meta.source,
            }

        emu_title = self._emulator_cache.find_title(title_id)
        if emu_title:
            return {
                "titleId": title_id,
                "title": emu_title,
                "developer": None,
                "version": None,
                "languages": "",
                "source": "emulator-cache",
            }

        return {
            "titleId": title_id,
            "title": title_id,
            "developer": None,
            "version": None,
            "languages": "",
            "source": "none",
        }

    # --- Internal ------------------------------------------------------------

    def _find_cached_media(self, title_id: str, game_id: str | None) -> Path | None:
        if self._media_cache_dir is None:
            return None
        for pattern in (
            f"{title_id}.jpg",
            f"{title_id}.png",
            f"{title_id}.svg",
            f"{game_id}.jpg" if game_id else None,
        ):
            if pattern is None:
                continue
            candidate = self._media_cache_dir / pattern
            if candidate.is_file():
                return candidate
        return None

    def _cache_native_icon(self, title_id: str, rom_path: Path) -> Path | None:
        if self._media_cache_dir is None:
            return None
        ensure_dir(self._media_cache_dir)
        icon_path = self._media_cache_dir / f"{title_id}.jpg"

        if icon_path.is_file():
            return icon_path

        meta = self._native_extractor.extract_icon(rom_path)
        if meta is None:
            return None
        icon_bytes, fmt = meta
        ext = ".jpg" if fmt == "jpeg" else f".{fmt}"
        dest = self._media_cache_dir / f"{title_id}{ext}"
        write_atomic(dest, icon_bytes)
        if ext != ".jpg":
            symlink_atomic(dest, icon_path)
        return dest

    def _write_fallback(self, title_id: str) -> Path | None:
        if self._media_cache_dir is None:
            return None
        ensure_dir(self._media_cache_dir)
        fallback_path = self._media_cache_dir / f"{title_id}.svg"
        if not fallback_path.is_file():
            write_atomic(fallback_path, _FALLBACK_ICON)
        return fallback_path

    def _extract_native_metadata(self, rom_path: Path | None) -> RomMetadata | None:
        if rom_path is None or not rom_path.is_file():
            return None
        return self._native_extractor.extract_metadata(rom_path)
