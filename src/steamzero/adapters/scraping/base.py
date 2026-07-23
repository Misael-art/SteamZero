# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Classes base para provedores de mídia e controle de taxa.

``BaseMediaProvider``: classe abstrata que implementa a validação comum e
fornece ``_fetch_url()`` para download com limite de tamanho.

``TokenBucket`` e ``RateLimiter``: controle de concorrência por provider
(tokens por segundo, rajada máxima).
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from steamzero.core.errors import SteamZeroError
from steamzero.core.fs import hash_bytes
from steamzero.core.net import NetworkFailure, fetch_bytes
from steamzero.ports import GameIdentity, MediaCandidate

_MAGIC_BY_PNG = b"\x89PNG\r\n\x1a\n"
_MAGIC_JPEG = b"\xff\xd8\xff"
_MAGIC_WEBP = b"RIFF"
_MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024


class TokenBucket:
    """Token bucket para rate limiting.

    ``capacity``: número máximo de tokens (rajada).
    ``rate``: tokens por segundo.
    """

    def __init__(self, capacity: float, rate: float) -> None:
        if capacity <= 0 or rate <= 0:
            raise ValueError("capacity e rate precisam ser positivos")
        self._capacity = capacity
        self._rate = rate
        self._tokens = capacity
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

    def acquire(self, tokens: float = 1.0) -> float:
        """Consome ``tokens`` e retorna o tempo de espera (0 se disponível)."""
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return 0.0
        deficit = tokens - self._tokens
        wait = deficit / self._rate
        return wait

    def wait_if_needed(self, tokens: float = 1.0) -> None:
        """Bloqueia até ter tokens suficientes."""
        wait = self.acquire(tokens)
        if wait > 0:
            time.sleep(wait)
            self._tokens = 0.0
            self._last_refill = time.monotonic()


@dataclass
class RateLimiter:
    """Rate limiter por provider: token bucket + bloqueio de cota diária.

    ``daily_limit``: máximo de requisições por dia (0 = ilimitado).
    ``threads``: número máximo de requisições simultâneas.
    """

    provider: str
    requests_per_second: float = 4.0
    burst: int = 8
    daily_limit: int = 0
    _bucket: TokenBucket = field(init=False)

    def __post_init__(self) -> None:
        self._bucket = TokenBucket(float(self.burst), self.requests_per_second)

    def acquire(self) -> None:
        self._bucket.wait_if_needed()


class BaseMediaProvider(ABC):
    """Classe base para provedores de mídia.

    Implementa o contrato ``MediaProviderPort`` e fornece:
    - ``_fetch_url()``: download HTTPS com validação de tamanho e redirect.
    - ``_validate_media()``: verificação de magic bytes.
    - ``_normalize_platform()``: conversão de slug SteamZero para slug do provider.
    """

    def __init__(self, *, rate_limiter: RateLimiter | None = None) -> None:
        self._rate_limiter = rate_limiter or RateLimiter(provider=self.name)

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def supported_kinds(self) -> frozenset[str]: ...

    @abstractmethod
    def supported_platforms(self) -> frozenset[str]: ...

    @abstractmethod
    def search(
        self,
        identity: GameIdentity,
        media_kinds: list[str],
        region_priority: list[str] | None = None,
    ) -> list[MediaCandidate]: ...

    def _rate_limit(self) -> None:
        limiter = self._rate_limiter
        if limiter is not None:
            limiter.acquire()

    def _fetch_url(self, url: str, max_bytes: int = _MAX_DOWNLOAD_BYTES) -> bytes:
        """Baixa conteúdo de ``url`` com validação de segurança."""
        try:
            return fetch_bytes(url, max_bytes=max_bytes)
        except NetworkFailure as exc:
            if exc.status == 429:
                raise SteamZeroError(
                    "E-SCRAPE-RATE-LIMITED", detail=f"{self.name}: rate limit (HTTP 429)"
                ) from exc
            if exc.status == 403:
                raise SteamZeroError(
                    "E-SCRAPE-QUOTA-EXCEEDED", detail=f"{self.name}: quota/cota excedida (HTTP 403)"
                ) from exc
            if exc.status == 404:
                raise SteamZeroError(
                    "E-SCRAPE-NOT-FOUND", detail=f"{self.name}: recurso não encontrado (HTTP 404)"
                ) from exc
            if exc.code in {
                "E-NET-INSECURE-URL",
                "E-NET-HOST-DENIED",
                "E-NET-REDIRECT-DENIED",
                "E-NET-CONTENT-LIMIT",
            }:
                raise SteamZeroError("E-SCRAPE-DOWNLOAD-FAILED", detail=exc.detail) from exc
            raise SteamZeroError(
                "E-SCRAPE-PROVIDER-UNREACHABLE",
                detail=f"{self.name}: {exc.detail}",
            ) from exc

    @staticmethod
    def _validate_media(data: bytes, expected_kind: str | None = None) -> str | None:
        """Valida magic bytes e retorna extensão ou None se inválido."""
        if len(data) < 4:
            return None
        if data.startswith(_MAGIC_BY_PNG):
            return ".png"
        if data.startswith(_MAGIC_JPEG):
            return ".jpg"
        if data.startswith(_MAGIC_WEBP) and data[8:12] == b"WEBP":
            return ".webp"
        return None

    @staticmethod
    def _media_hash(data: bytes) -> str:
        return hash_bytes(data, algo="sha256")

    @staticmethod
    def _normalize_platform(platform_slug: str) -> str:
        """Converte slug SteamZero para slug do provider.

        Sobrescrever quando os slugs do provider diferirem dos slugs internos.
        """
        return platform_slug
