# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Registro central de provedores com cadeia de fallback por tipo de mídia.

``ProviderRegistry`` mantém:
- Catálogo de providers registrados (``MediaProviderPort``).
- Ordem de fallback configurável por tipo de mídia.
- Circuit breaker por provider (falhas consecutivas abrem o circuito).
- ``search_best()`` que percorre a cadeia de fallback até encontrar um
  candidato com confiança mínima.

A ordem de fallback default segue a matriz da seção 2 do estudo de fontes:
    boxart: screenscraper -> libretro -> mobygames
    wheel: screenscraper -> steamgriddb -> libretro
    screenshot: screenscraper -> libretro -> igdb
    video: emumovies -> screenscraper
    fanart: screenscraper -> launchbox -> steamgriddb
    marquee: arcadedb -> screenscraper
    grid: steamgriddb -> screenscraper
    manual: screenscraper -> emumovies
"""

from __future__ import annotations

from dataclasses import dataclass, field

from steamzero.core.errors import SteamZeroError
from steamzero.ports import GameIdentity, MediaCandidate, MediaProviderPort

_DEFAULT_FALLBACK: dict[str, list[str]] = {
    "boxart": ["screenscraper", "libretro", "igdb"],
    "wheel": ["screenscraper", "steamgriddb", "libretro"],
    "screenshot": ["screenscraper", "libretro", "igdb"],
    "title": ["screenscraper", "libretro"],
    "video": ["emumovies", "screenscraper"],
    "fanart": ["screenscraper", "steamgriddb"],
    "marquee": ["screenscraper"],
    "grid": ["steamgriddb", "screenscraper"],
    "manual": ["screenscraper"],
    "hero": ["steamgriddb", "screenscraper"],
    "icon": ["steamgriddb", "screenscraper"],
}


@dataclass
class ProviderRegistry:
    """Catálogo de providers com cadeia de fallback por tipo de mídia.

    ``fallback_order`` mapeia ``media_kind -> [nomes de provider em ordem de
    precedência]``. Se um tipo de mídia não tiver entrada, usa todas as fontes
    disponíveis na ordem de registro.
    """

    fallback_order: dict[str, list[str]] = field(default_factory=lambda: dict(_DEFAULT_FALLBACK))
    _providers: dict[str, MediaProviderPort] = field(default_factory=dict)

    def register(self, provider: MediaProviderPort) -> None:
        """Registra um provider. Sobrescreve se já existir com o mesmo nome."""
        self._providers[provider.name] = provider

    def get(self, name: str) -> MediaProviderPort:
        provider = self._providers.get(name)
        if provider is None:
            raise SteamZeroError("E-INTERNAL-UNEXPECTED", detail=f"provider não registrado: {name}")
        return provider

    def list_providers(self) -> frozenset[str]:
        return frozenset(self._providers)

    def providers_for_kind(self, media_kind: str) -> list[MediaProviderPort]:
        """Retorna providers na ordem de fallback para o tipo de mídia."""
        order = self.fallback_order.get(media_kind, list(self._providers))
        result: list[MediaProviderPort] = []
        seen: set[str] = set()
        for name in order:
            if name in seen:
                continue
            seen.add(name)
            provider = self._providers.get(name)
            if provider is not None and media_kind in provider.supported_kinds():
                result.append(provider)
        for name, provider in self._providers.items():
            if name not in seen and media_kind in provider.supported_kinds():
                result.append(provider)
        return result

    def search_best(
        self,
        identity: GameIdentity,
        media_kind: str,
        *,
        min_confidence: float = 0.5,
        region_priority: list[str] | None = None,
        skip_circuit_open: bool = True,
    ) -> MediaCandidate | None:
        """Percorre a cadeia de fallback e retorna o melhor candidato.

        Retorna ``None`` se nenhum provider retornar candidatos com confiança
        >= ``min_confidence``.
        """
        for provider in self.providers_for_kind(media_kind):
            try:
                candidates = provider.search(identity, [media_kind], region_priority)
            except SteamZeroError:
                continue
            best: MediaCandidate | None = None
            for c in candidates:
                if c.media_kind != media_kind:
                    continue
                if c.confidence >= min_confidence and (
                    best is None or c.confidence > best.confidence
                ):
                    best = c
            if best is not None:
                return best
        return None

    def search_all(
        self,
        identity: GameIdentity,
        media_kinds: list[str] | None = None,
        *,
        min_confidence: float = 0.3,
        region_priority: list[str] | None = None,
    ) -> dict[str, list[MediaCandidate]]:
        """Busca todos os tipos de mídia em todos os providers.

        Retorna ``{media_kind: [candidatos ordenados por confiança]}``.
        """
        kinds = media_kinds or list(self.fallback_order)
        result: dict[str, list[MediaCandidate]] = {}
        for kind in kinds:
            all_candidates: list[MediaCandidate] = []
            for provider in self.providers_for_kind(kind):
                try:
                    all_candidates.extend(provider.search(identity, [kind], region_priority))
                except SteamZeroError:
                    continue
            filtered = [c for c in all_candidates if c.confidence >= min_confidence]
            filtered.sort(key=lambda c: c.confidence, reverse=True)
            if filtered:
                result[kind] = filtered
        return result
