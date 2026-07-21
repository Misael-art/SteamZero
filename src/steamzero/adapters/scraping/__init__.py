# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Adaptadores de scraping de mídia para jogos e emuladores.

Pacote com implementações concretas de ``MediaProviderPort`` (definido em
``steamzero.ports``), além do ``ScrapingCache`` SQLite, ``ProviderRegistry``
com cadeias de fallback por tipo de mídia e ``ScrapingDispatcher`` como
orquestrador principal.

Cada provider declara tipos de mídia e plataformas que suporta. A ordem de
fallback é configurável (default na ``ProviderRegistry``). O cache local
garante que a mesma consulta nunca seja refeita.
"""

from steamzero.adapters.scraping.base import BaseMediaProvider, RateLimiter, TokenBucket
from steamzero.adapters.scraping.cache import CacheEntry, ScrapingCache
from steamzero.adapters.scraping.dispatcher import ScrapingDispatcher
from steamzero.adapters.scraping.registry import ProviderRegistry

__all__ = [
    "BaseMediaProvider",
    "CacheEntry",
    "ProviderRegistry",
    "RateLimiter",
    "ScrapingCache",
    "ScrapingDispatcher",
    "TokenBucket",
]
