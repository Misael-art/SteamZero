# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do ScrapingDispatcher — pipeline, cache e isolamento.

Todo acesso remoto passa por ``HttpClient`` com ``FakeTransport``; o guard do
``conftest`` desta pasta reprova qualquer tentativa de rede real.
"""

from __future__ import annotations

import sqlite3

import pytest

from fixtures.scraping.synthetic import (
    HTML_BYTES,
    PNG_BYTES,
    screenscraper_json,
)
from steamzero.adapters.scraping.cache import ScrapingCache
from steamzero.adapters.scraping.dispatcher import ScrapingDispatcher
from steamzero.adapters.scraping.registry import ProviderRegistry
from steamzero.adapters.scraping.screenscraper import ScreenScraperAdapter
from steamzero.core.errors import SteamZeroError
from steamzero.core.net import FakeResponse, FakeTransport, HttpClient
from steamzero.ports import GameIdentity, MediaCandidate


def _ss_ok_payload() -> bytes:
    return screenscraper_json(
        [
            {
                "type": "box-2d",
                "region": "us",
                "url": "https://media.example/box.png",
                "width": 400,
                "height": 300,
            }
        ]
    )


def _identity(*, title: str = "Test Game", sha1: str = "a" * 40) -> GameIdentity:
    return GameIdentity(
        game_id="g1",
        title=title,
        platform_slug="switch",
        hashes={"sha1": sha1},
    )


def _make_dispatcher(
    outcomes: list[object],
    tmp_path,
) -> tuple[ScrapingDispatcher, ScrapingCache, FakeTransport]:
    transport = FakeTransport(outcomes)  # type: ignore[arg-type]
    adapter = ScreenScraperAdapter(
        devid="test-dev",
        devpassword="test-pass",
        rate_limiter=None,
        client=HttpClient(transport=transport),
    )
    registry = ProviderRegistry(fallback_order={"boxart": ["screenscraper"]})
    registry.register(adapter)
    cache = ScrapingCache(db_path=tmp_path / "dispatcher.db")
    dispatcher = ScrapingDispatcher(cache, registry)
    return dispatcher, cache, transport


def test_scrape_game_success_downloads_and_caches(tmp_path) -> None:
    dispatcher, cache, transport = _make_dispatcher(
        [
            FakeResponse(body=_ss_ok_payload(), url="https://www.screenscraper.fr/api2"),
            FakeResponse(body=PNG_BYTES, url="https://media.example/box.png"),
        ],
        tmp_path,
    )
    result = dispatcher.scrape_game(_identity(), ["boxart"])
    assert result.success
    assert "boxart" in result.downloaded
    assert result.downloaded["boxart"].provider == "screenscraper"
    cached = cache.get_cached(_identity().hashes["sha1"], "boxart", "*")
    assert cached is not None
    assert cached.url == "https://media.example/box.png"
    assert len(transport.requests) == 2


def test_cache_hit_reuses_without_provider_calls(tmp_path) -> None:
    dispatcher, _, transport = _make_dispatcher(
        [
            FakeResponse(body=_ss_ok_payload(), url="https://www.screenscraper.fr/api2"),
            FakeResponse(body=PNG_BYTES, url="https://media.example/box.png"),
        ],
        tmp_path,
    )
    first = dispatcher.scrape_game(_identity(), ["boxart"])
    assert first.success
    assert len(transport.requests) == 2
    second = dispatcher.scrape_game(_identity(), ["boxart"])
    assert second.downloaded == {}
    assert len(transport.requests) == 2


def test_corrupt_payload_is_failed_and_not_cached(tmp_path) -> None:
    dispatcher, cache, _ = _make_dispatcher(
        [
            FakeResponse(body=_ss_ok_payload(), url="https://www.screenscraper.fr/api2"),
            FakeResponse(
                body=HTML_BYTES,
                url="https://media.example/box.png",
                headers={"Content-Type": "image/png"},
            ),
        ],
        tmp_path,
    )
    result = dispatcher.scrape_game(_identity(), ["boxart"])
    assert not result.success
    assert "boxart" in result.failed
    assert cache.get_cached(_identity().hashes["sha1"], "boxart", "*") is None
    with sqlite3.connect(cache.path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM scraping_media WHERE game_id='g1'").fetchone()[
                0
            ]
            == 0
        )


def test_interrupted_write_publishes_no_partial_entry(tmp_path, monkeypatch) -> None:
    dispatcher, cache, _ = _make_dispatcher(
        [
            FakeResponse(body=_ss_ok_payload(), url="https://www.screenscraper.fr/api2"),
            FakeResponse(body=PNG_BYTES, url="https://media.example/box.png"),
        ],
        tmp_path,
    )

    def _broken_save_media(*_args, **_kwargs) -> str:
        raise sqlite3.OperationalError("escrita interrompida")

    monkeypatch.setattr(cache, "save_media", _broken_save_media)
    with pytest.raises(sqlite3.OperationalError):
        dispatcher.scrape_game(_identity(), ["boxart"])
    assert cache.get_cached(_identity().hashes["sha1"], "boxart", "*") is None
    with sqlite3.connect(cache.path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM scraping_cache_entry WHERE lookup_key=?", ("a" * 40,)
            ).fetchone()[0]
            == 0
        )


def test_quota_failure_is_failed_and_not_cached_as_absence(tmp_path) -> None:
    dispatcher, cache, _ = _make_dispatcher(
        [
            FakeResponse(
                body=screenscraper_json({}),
                url="https://www.screenscraper.fr/api2",
                status=429,
                headers={"Content-Type": "application/json"},
            )
        ],
        tmp_path,
    )
    result = dispatcher.scrape_game(_identity(), ["boxart"])
    assert not result.success
    assert "boxart" in result.failed
    assert cache.get_cached(_identity().hashes["sha1"], "boxart", "*") is None


def test_all_providers_failing_returns_failed_without_crash(tmp_path) -> None:
    dispatcher, _, _ = _make_dispatcher(
        [FakeResponse(body=HTML_BYTES, url="https://www.screenscraper.fr/api2")],
        tmp_path,
    )
    result = dispatcher.scrape_game(_identity(), ["boxart"])
    assert not result.success
    assert "boxart" in result.failed


def test_empty_legitimate_result_is_failed_not_success(tmp_path) -> None:
    dispatcher, _, _ = _make_dispatcher(
        [
            FakeResponse(
                body=screenscraper_json([]),
                url="https://www.screenscraper.fr/api2",
            )
        ],
        tmp_path,
    )
    result = dispatcher.scrape_game(_identity(), ["boxart"])
    assert not result.success
    assert "boxart" in result.failed


def test_fallback_after_recoverable_provider_failure(tmp_path) -> None:
    class BrokenProvider:
        @property
        def name(self) -> str:
            return "broken"

        def supported_kinds(self) -> frozenset[str]:
            return frozenset({"boxart"})

        def supported_platforms(self) -> frozenset[str]:
            return frozenset({"switch"})

        def search(self, identity, media_kinds, region_priority=None):
            raise SteamZeroError("E-SCRAPE-PROVIDER-UNREACHABLE", detail="quota de teste")

    registry = ProviderRegistry(fallback_order={"boxart": ["broken", "screenscraper"]})
    registry.register(BrokenProvider())
    transport = FakeTransport(
        [
            FakeResponse(body=_ss_ok_payload(), url="https://www.screenscraper.fr/api2"),
            FakeResponse(body=PNG_BYTES, url="https://media.example/box.png"),
        ]
    )
    registry.register(
        ScreenScraperAdapter(
            devid="test-dev",
            devpassword="test-pass",
            rate_limiter=None,
            client=HttpClient(transport=transport),
        )
    )
    cache = ScrapingCache(db_path=tmp_path / "fallback.db")
    dispatcher = ScrapingDispatcher(cache, registry)
    result = dispatcher.scrape_game(_identity(), ["boxart"])
    assert result.success
    assert result.downloaded["boxart"].provider == "screenscraper"


def test_credentials_never_persist_in_cache(tmp_path) -> None:
    dispatcher, cache, transport = _make_dispatcher(
        [
            FakeResponse(body=_ss_ok_payload(), url="https://www.screenscraper.fr/api2"),
            FakeResponse(body=PNG_BYTES, url="https://media.example/box.png"),
        ],
        tmp_path,
    )
    dispatcher.scrape_game(_identity(), ["boxart"])
    api_url, _, _headers = transport.requests[0]
    assert "devpassword" in api_url
    assert "test-pass" in api_url
    with sqlite3.connect(cache.path) as connection:
        rows = connection.execute("SELECT url, error FROM scraping_cache_entry").fetchall()
    for url, error in rows:
        for secret in ("test-pass", "devpassword", "test-dev", "Authorization"):
            assert secret not in (url or "")
            assert secret not in (error or "")


def test_lookup_key_normalizes_identity(tmp_path) -> None:
    dispatcher, _, _ = _make_dispatcher([], tmp_path)
    assert dispatcher._lookup_key(
        GameIdentity("g", "  Zelda   ", "switch")
    ) == dispatcher._lookup_key(GameIdentity("g", "zelda", "switch"))
    assert dispatcher._lookup_key(
        GameIdentity("g", "Title", "switch", hashes={"sha1": "ABCDEF"})
    ) == dispatcher._lookup_key(GameIdentity("g", "Title", "switch", hashes={"sha1": "abcdef"}))
    assert dispatcher._lookup_key(
        GameIdentity("g", "Title", " switch ", serial=" SLUS-12345 ")
    ) == dispatcher._lookup_key(GameIdentity("g", "Title", "switch", serial="SLUS-12345"))


def test_error_aggregation_stays_sanitized(tmp_path) -> None:
    dispatcher, cache, _ = _make_dispatcher(
        [
            FakeResponse(
                body=HTML_BYTES,
                url="https://www.screenscraper.fr/api2",
                status=500,
                headers={"Content-Type": "application/json"},
            )
        ],
        tmp_path,
    )
    result = dispatcher.scrape_game(_identity(), ["boxart"])
    assert "boxart" in result.failed
    assert cache.get_cached(_identity().hashes["sha1"], "boxart", "*") is None


def test_download_and_validate_rejects_unknown_provider(tmp_path) -> None:
    dispatcher, _, _ = _make_dispatcher([], tmp_path)
    with pytest.raises(SteamZeroError):
        dispatcher._download_and_validate(
            MediaCandidate(
                url="https://media.example/box.png",
                media_kind="boxart",
                provider="missing",
                confidence=1.0,
            )
        )
