# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do RateLimiter, TokenBucket e validação de mídia."""

from __future__ import annotations

import time

import pytest

from steamzero.adapters.scraping.base import BaseMediaProvider, RateLimiter, TokenBucket


def test_token_bucket_refill() -> None:
    bucket = TokenBucket(capacity=10, rate=5)
    assert bucket.acquire(10) == 0.0
    wait = bucket.acquire(1)
    assert wait > 0.0


def test_token_bucket_capacity() -> None:
    bucket = TokenBucket(capacity=5, rate=10)
    assert bucket.acquire(5) == 0.0
    assert bucket.acquire(1) > 0.0


def test_token_bucket_negative_raises() -> None:
    with pytest.raises(ValueError):
        TokenBucket(capacity=0, rate=1)
    with pytest.raises(ValueError):
        TokenBucket(capacity=1, rate=0)


def test_rate_limiter_defaults() -> None:
    limiter = RateLimiter(provider="test")
    assert limiter.requests_per_second == 4.0
    assert limiter.burst == 8


def test_rate_limiter_acquire() -> None:
    limiter = RateLimiter(provider="test", requests_per_second=100, burst=50)
    t0 = time.monotonic()
    limiter.acquire()
    elapsed = time.monotonic() - t0
    assert elapsed < 0.1  # must be instant with enough tokens


def test_validate_media_png() -> None:
    data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    assert BaseMediaProvider._validate_media(data) == ".png"


def test_validate_media_jpeg() -> None:
    data = b"\xff\xd8\xff" + b"\x00" * 100
    assert BaseMediaProvider._validate_media(data) == ".jpg"


def test_validate_media_webp() -> None:
    data = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 100
    assert BaseMediaProvider._validate_media(data) == ".webp"


def test_validate_media_too_short() -> None:
    assert BaseMediaProvider._validate_media(b"abc") is None


def test_validate_media_unknown() -> None:
    assert BaseMediaProvider._validate_media(b"\x00\x01\x02\x03" + b"\x00" * 100) is None


def test_media_hash() -> None:
    data = b"test-data"
    h = BaseMediaProvider._media_hash(data)
    assert len(h) == 64  # sha256 hex
    assert h == BaseMediaProvider._media_hash(data)  # deterministic
    assert h != BaseMediaProvider._media_hash(b"other")


def test_normalize_platform_pass_through() -> None:
    assert BaseMediaProvider._normalize_platform("switch") == "switch"
