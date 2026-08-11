# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Orquestrador principal de scraping: identifica, busca, baixa e canonicaliza.

``ScrapingDispatcher`` coordena:
1. Identificação por hash (SHA1/MD5/CRC32/Title ID/nome).
2. Cache-first: consulta o cache local antes de chamar providers.
3. Busca em múltiplos providers com fallback por tipo de mídia.
4. Download, validação e staging dos artefatos.
5. Commit ao repositório canônico de mídia (via MediaLibrary).

Fluxo completo::

    dispatcher.scrape_game(identity, kinds=["boxart", "screenshot"])
      -> cache hit? retorna imediatamente
      -> ProviderRegistry.search_best() para cada kind
      -> download, validate magic bytes, compute hash
      -> save to cache + stage to staging/<op_id>
      -> plan reconcile via MediaLibrary
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from steamzero.adapters.scraping.base import BaseMediaProvider
from steamzero.adapters.scraping.cache import ScrapingCache
from steamzero.adapters.scraping.registry import ProviderRegistry
from steamzero.core import fs, ids, paths, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain.media import MediaAssignment, MediaLibrary
from steamzero.ports import GameIdentity, MediaCandidate

_DEFAULT_MEDIA_ROOT = paths.media_dir()  # evaluated at import time


@dataclass
class ScrapeResult:
    """Resultado do scraping para um jogo.

    ``downloaded``: tipos de mídia que foram baixados com sucesso.
    ``failed``: tipos de mídia que não foram encontrados ou falharam.
    ``skipped``: tipos de mídia em que todos os providers estavam em circuit-breaker.
    """

    game_id: str
    downloaded: dict[str, MediaCandidate] = field(default_factory=dict)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return bool(self.downloaded)


@dataclass
class ScrapeConfig:
    """Configuração global de scraping.

    ``media_root``: raiz do repositório canônico de mídia.
    ``region_priority``: ordem de preferência de região (padrão: wor -> us -> eu -> br -> jp).
    ``max_download_bytes``: limite por arquivo baixado.
    ``cache_max_age_hours``: idade máxima do cache antes de re-consultar.
    ``min_confidence``: confiança mínima para aceitar um candidato.
    """

    media_root: Path = _DEFAULT_MEDIA_ROOT
    region_priority: list[str] = field(default_factory=lambda: ["wor", "us", "eu", "br", "jp"])
    max_download_bytes: int = 32 * 1024 * 1024
    cache_max_age_hours: int = 24 * 7
    min_confidence: float = 0.5


class ScrapingDispatcher:
    """Orquestrador do pipeline de scraping.

    Uso típico::

        cache = ScrapingCache()
        registry = ProviderRegistry()
        registry.register(ScreenScraperAdapter(devid=..., devpassword=...))
        dispatcher = ScrapingDispatcher(cache, registry)
        result = dispatcher.scrape_game(identity, ["boxart", "screenshot"])
    """

    def __init__(
        self,
        cache: ScrapingCache,
        registry: ProviderRegistry,
        config: ScrapeConfig | None = None,
    ) -> None:
        self._cache = cache
        self._registry = registry
        self._config = config or ScrapeConfig()

    def scrape_game(
        self,
        identity: GameIdentity,
        media_kinds: list[str] | None = None,
    ) -> ScrapeResult:
        """Raspa todos os tipos de mídia para um jogo.

        1. Para cada tipo de mídia, verifica cache primeiro.
        2. Se cache miss, busca no provider registry com fallback.
        3. Baixa, valida e faz staging do artefato.
        4. Retorna resultado consolidado.

        O commit ao repositório canônico é feito separadamente via
        ``commit_staged()``.
        """
        result = ScrapeResult(game_id=identity.game_id)
        kinds = media_kinds or list(self._registry.fallback_order)

        for kind in kinds:
            cached = self._cache.get_cached(
                self._lookup_key(identity),
                kind,
                "*",
                max_age_hours=self._config.cache_max_age_hours,
            )
            if cached is not None and cached.url:
                continue

            candidate = self._registry.search_best(
                identity,
                kind,
                min_confidence=self._config.min_confidence,
                region_priority=self._config.region_priority,
            )
            if candidate is None:
                result.failed.append(kind)
                continue

            try:
                data = self._download_and_validate(
                    candidate, expected_kind=_expected_kind_for(kind)
                )
            except SteamZeroError:
                result.failed.append(kind)
                continue

            with self._cache.atomic():
                cache_entry_id = self._cache.save_cache_entry(
                    candidate, self._lookup_key(identity), platform_slug=identity.platform_slug
                )
                self._cache.save_media(
                    cache_entry_id,
                    identity.game_id,
                    kind,
                    data,
                    width=candidate.width,
                    height=candidate.height,
                )
            result.downloaded[kind] = candidate

        return result

    def commit_staged(
        self,
        game_id: str,
        downloaded: dict[str, MediaCandidate],
        *,
        root: Path | None = None,
    ) -> transaction.Plan:
        """Prepara plano transacional para canonicalizar mídia baixada.

        O plano move os artefatos do staging para ``canonical/<game_id>/<kind>.<ext>``
        na raiz de mídia. Deve ser aplicado com ``MediaLibrary.apply()``.
        """
        media_root = root or self._config.media_root
        assignments: dict[str, MediaAssignment] = {}
        staging_dir = paths.staging_for(ids.new_ulid())

        for kind, candidate in downloaded.items():
            ext = _kind_extension(kind)
            staging_path = staging_dir / f"{kind}{ext}"
            fs.ensure_dir(staging_path.parent)

            try:
                data = self._download_and_validate(
                    candidate, expected_kind=_expected_kind_for(kind)
                )
                fs.write_atomic(staging_path, data)
            except SteamZeroError:
                continue

            rel = str(staging_path.relative_to(media_root))
            assignments[rel] = MediaAssignment(
                game_id=game_id,
                kind=kind,
                provider=candidate.provider,
                license=candidate.license,
            )

        media_lib = MediaLibrary()
        return media_lib.plan_reconcile(media_root, assignments)

    def _lookup_key(self, identity: GameIdentity) -> str:
        sha1 = identity.hashes.get("sha1")
        if sha1:
            return sha1.strip().lower()
        md5 = identity.hashes.get("md5")
        if md5:
            return md5.strip().lower()
        if identity.title_id:
            return f"tid:{identity.title_id.strip()}"
        if identity.serial:
            return f"serial:{identity.serial.strip()}"
        return f"name:{identity.platform_slug.strip().lower()}:{identity.title.strip().lower()}"

    def _download_and_validate(
        self,
        candidate: MediaCandidate,
        *,
        expected_kind: str | None = None,
    ) -> bytes:
        provider = self._registry.get(candidate.provider)
        if not isinstance(provider, BaseMediaProvider):
            raise SteamZeroError(
                "E-SCRAPE-DOWNLOAD-FAILED",
                detail=f"provider {candidate.provider} não suporta download direto",
            )
        data = provider._fetch_url(candidate.url)
        if provider._validate_media(data, expected_kind=expected_kind) is None:
            raise SteamZeroError(
                "E-SCRAPE-CORRUPT-MEDIA",
                detail=(
                    f"{candidate.provider}: conteúdo sem assinatura de mídia "
                    "reconhecida (não é imagem, vídeo ou PDF)"
                ),
            )
        return data


def _kind_extension(kind: str) -> str:
    ext_map = {
        "boxart": ".png",
        "wheel": ".png",
        "screenshot": ".png",
        "fanart": ".jpg",
        "marquee": ".png",
        "video": ".mp4",
        "grid": ".png",
        "hero": ".jpg",
        "icon": ".png",
        "manual": ".pdf",
        "title": ".png",
    }
    return ext_map.get(kind, ".png")


def _expected_kind_for(kind: str) -> str | None:
    """Família de assinatura esperada para cada tipo de mídia."""
    if kind == "video":
        return "video"
    if kind == "manual":
        return "manual"
    if kind in {
        "boxart",
        "wheel",
        "screenshot",
        "fanart",
        "marquee",
        "grid",
        "hero",
        "icon",
        "title",
    }:
        return "image"
    return None
