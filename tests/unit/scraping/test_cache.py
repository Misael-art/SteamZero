# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do ScrapingCache SQLite."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.adapters.scraping.cache import ScrapingCache
from steamzero.core import ids
from steamzero.ports import MediaCandidate


@pytest.fixture
def cache(tmp_path: Path) -> ScrapingCache:
    return ScrapingCache(db_path=tmp_path / "test-scrape.db")


def test_cache_save_and_retrieve(cache: ScrapingCache) -> None:
    candidate = MediaCandidate(
        url="https://example.com/art.png",
        media_kind="boxart",
        provider="screenscraper",
        confidence=1.0,
        width=400,
        height=300,
        license="CC0",
        attribution="test",
    )
    key = "sha1:abc123"
    entry_id = cache.save_cache_entry(candidate, key)
    assert entry_id
    cached = cache.get_cached(key, "boxart", "screenscraper")
    assert cached is not None
    assert cached.url == "https://example.com/art.png"


def test_cache_miss_for_different_key(cache: ScrapingCache) -> None:
    candidate = MediaCandidate(
        url="https://example.com/art.png",
        media_kind="boxart",
        provider="test",
        confidence=1.0,
    )
    cache.save_cache_entry(candidate, "key1")
    assert cache.get_cached("key2", "boxart", "test") is None


def test_cache_miss_for_different_kind(cache: ScrapingCache) -> None:
    candidate = MediaCandidate(
        url="https://example.com/art.png",
        media_kind="boxart",
        provider="test",
        confidence=1.0,
    )
    cache.save_cache_entry(candidate, "key1")
    assert cache.get_cached("key1", "screenshot", "test") is None


def test_cache_miss_after_error(cache: ScrapingCache) -> None:
    cache.mark_error("key1", "boxart", "test", "E-SCRAPE-NOT-FOUND", 404)
    assert cache.get_cached("key1", "boxart", "test") is None


def test_cache_by_game(cache: ScrapingCache) -> None:
    game_id = ids.new_ulid()
    c1 = MediaCandidate(
        url="https://example.com/art1.png",
        media_kind="boxart",
        provider="p1",
        confidence=0.9,
    )
    c2 = MediaCandidate(
        url="https://example.com/art2.png",
        media_kind="boxart",
        provider="p2",
        confidence=0.8,
    )
    cache.save_cache_entry(c1, game_id)
    cache.save_cache_entry(c2, game_id)
    entries = cache.get_cached_by_game(game_id, "boxart")
    assert len(entries) >= 2


def test_save_and_commit_media(cache: ScrapingCache) -> None:
    candidate = MediaCandidate(
        url="https://example.com/art.png",
        media_kind="boxart",
        provider="test",
        confidence=1.0,
    )
    eid = cache.save_cache_entry(candidate, "key1")
    mid = cache.save_media(eid, "game1", "boxart", b"fake-png-data", width=100, height=200)
    assert mid
    cache.commit_media(mid)


def test_credential_roundtrip(cache: ScrapingCache) -> None:
    cache.set_credential("screenscraper", "devid", "my-dev-id")
    assert cache.get_credential("screenscraper", "devid") == "my-dev-id"
    cache.delete_credential("screenscraper", "devid")
    assert cache.get_credential("screenscraper", "devid") is None


def test_circuit_breaker(cache: ScrapingCache) -> None:
    assert not cache.circuit_is_open("test-provider", max_failures=3)
    for _ in range(3):
        cache.record_failure("test-provider")
    assert cache.circuit_is_open("test-provider", max_failures=3)


def test_record_success(cache: ScrapingCache) -> None:
    cache.record_success("test-provider", 1024)
    assert not cache.circuit_is_open("test-provider", max_failures=3)


def test_prune_expired(cache: ScrapingCache) -> None:
    num = cache.prune_expired(older_than_days=0)
    assert num == 0
