# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do ScrapingCache SQLite."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import closing
from pathlib import Path

import pytest

from fixtures.scraping.synthetic import PNG_BYTES
from steamzero.adapters.scraping.cache import ScrapingCache
from steamzero.core import ids
from steamzero.ports import MediaCandidate


def _candidate(url: str = "https://example.com/art.png", provider: str = "test") -> MediaCandidate:
    return MediaCandidate(
        url=url,
        media_kind="boxart",
        provider=provider,
        confidence=1.0,
        width=400,
        height=300,
        license="CC0",
        attribution="test",
    )


@pytest.fixture
def cache(tmp_path: Path) -> ScrapingCache:
    value = ScrapingCache(db_path=tmp_path / "test-scrape.db")
    yield value
    value.close()


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


def test_cache_schema_does_not_serialize_credentials(cache: ScrapingCache) -> None:
    import sqlite3

    with closing(sqlite3.connect(cache.path)) as connection:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "scraping_credential" not in tables
    assert not hasattr(cache, "set_credential")
    assert not hasattr(cache, "get_credential")


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


# -- atomicidade ------------------------------------------------------------


def test_atomic_commit_publishes_entry_and_media(cache: ScrapingCache) -> None:
    with cache.atomic():
        entry_id = cache.save_cache_entry(_candidate(), "key1")
        cache.save_media(entry_id, "game1", "boxart", PNG_BYTES)
    cached = cache.get_cached("key1", "boxart", "test")
    assert cached is not None
    assert cached.url == "https://example.com/art.png"


def test_atomic_rollback_does_not_publish_partial_entry(cache: ScrapingCache) -> None:
    with pytest.raises(RuntimeError), cache.atomic():
        cache.save_cache_entry(_candidate(), "partial-key")
        raise RuntimeError("escrita interrompida")
    assert cache.get_cached("partial-key", "boxart", "test") is None
    with closing(sqlite3.connect(cache.path)) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM scraping_cache_entry WHERE lookup_key='partial-key'"
        ).fetchone()[0]
    assert count == 0


def test_atomic_rollback_removes_media_too(cache: ScrapingCache) -> None:
    with pytest.raises(RuntimeError), cache.atomic():
        entry_id = cache.save_cache_entry(_candidate(), "media-key")
        cache.save_media(entry_id, "game1", "boxart", PNG_BYTES)
        raise RuntimeError("escrita interrompida")
    with closing(sqlite3.connect(cache.path)) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM scraping_media WHERE game_id='game1'"
        ).fetchone()[0]
    assert count == 0


# -- deduplicação de falhas -------------------------------------------------


def test_mark_error_dedups_same_key_kind_provider(cache: ScrapingCache) -> None:
    cache.mark_error("key1", "boxart", "test", "E-SCRAPE-NOT-FOUND", 404)
    cache.mark_error("key1", "boxart", "test", "E-SCRAPE-NOT-FOUND", 404)
    with closing(sqlite3.connect(cache.path)) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM scraping_cache_entry"
            " WHERE lookup_key='key1' AND media_kind='boxart' AND provider='test'"
            " AND error IS NOT NULL"
        ).fetchone()[0]
    assert count == 1


def test_mark_error_keeps_distinct_keys_separate(cache: ScrapingCache) -> None:
    cache.mark_error("key1", "boxart", "test", "E-SCRAPE-NOT-FOUND", 404)
    cache.mark_error("key2", "boxart", "test", "E-SCRAPE-NOT-FOUND", 404)
    with closing(sqlite3.connect(cache.path)) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM scraping_cache_entry WHERE error IS NOT NULL"
        ).fetchone()[0]
    assert count == 2


# -- chave de provider ------------------------------------------------------


def test_get_cached_wildcard_provider_matches_any(cache: ScrapingCache) -> None:
    cache.save_cache_entry(_candidate(provider="screenscraper"), "key1")
    cached = cache.get_cached("key1", "boxart", "*")
    assert cached is not None
    assert cached.provider == "screenscraper"


def test_get_cached_specific_provider_still_filters(cache: ScrapingCache) -> None:
    cache.save_cache_entry(_candidate(provider="screenscraper"), "key1")
    assert cache.get_cached("key1", "boxart", "steamgriddb") is None


# -- concorrência -----------------------------------------------------------


def test_concurrent_same_key_no_corruption(tmp_path: Path) -> None:
    db_path = tmp_path / "concurrent.db"
    barrier = threading.Barrier(4)
    errors: list[BaseException] = []

    def writer(index: int) -> None:
        cache = ScrapingCache(db_path=db_path)
        try:
            barrier.wait(timeout=10)
            for _ in range(5):
                with cache.atomic():
                    entry_id = cache.save_cache_entry(
                        _candidate(url=f"https://example.com/{index}.png"), "shared-key"
                    )
                    cache.save_media(entry_id, "game-x", "boxart", PNG_BYTES)
        except BaseException as exc:
            errors.append(exc)
        finally:
            cache.close()

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    probe = ScrapingCache(db_path=db_path)
    try:
        cached = probe.get_cached("shared-key", "boxart", "*")
        assert cached is not None
        assert cached.url.startswith("https://example.com/")
        with closing(sqlite3.connect(db_path)) as connection:
            entries = connection.execute(
                "SELECT id FROM scraping_cache_entry WHERE lookup_key='shared-key'"
            ).fetchall()
            assert entries
            media_orphans = connection.execute(
                "SELECT COUNT(*) FROM scraping_media m"
                " LEFT JOIN scraping_cache_entry e ON e.id = m.cache_entry_id"
                " WHERE e.id IS NULL"
            ).fetchone()[0]
        assert media_orphans == 0
    finally:
        probe.close()


# -- persistência -----------------------------------------------------------


def test_cache_never_persists_credentials_or_api_urls(cache: ScrapingCache) -> None:
    candidate = MediaCandidate(
        url="https://example.com/art.png",
        media_kind="boxart",
        provider="screenscraper",
        confidence=1.0,
    )
    cache.save_cache_entry(candidate, "key1")
    cache.mark_error("key2", "boxart", "screenscraper", "E-SCRAPE-RATE-LIMITED", 429)
    with closing(sqlite3.connect(cache.path)) as connection:
        rows = connection.execute("SELECT url, error FROM scraping_cache_entry").fetchall()
    for url, _error in rows:
        assert "devpassword" not in (url or "")
        assert "api_key" not in (url or "")
        assert "sspassword" not in (url or "")
        assert "Authorization" not in (url or "")
        assert "devid" not in (url or "")
    with closing(sqlite3.connect(cache.path)) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(scraping_media)")}
    assert "payload" not in columns
    assert "data" not in columns
