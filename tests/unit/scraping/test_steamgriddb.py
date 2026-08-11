# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do adapter SteamGridDB — classificação HTTP e sanitização.

Todo acesso usa ``HttpClient`` com ``FakeTransport``; nenhuma chamada real.
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from fixtures.scraping.synthetic import steamgriddb_json
from steamzero.adapters.scraping.steamgriddb import SteamGridDbAdapter
from steamzero.core.errors import SteamZeroError
from steamzero.core.net import FakeResponse, FakeTransport, HttpClient
from steamzero.ports import GameIdentity

_API_URL = "https://www.steamgriddb.com/api/v2"


def _adapter(*outcomes: object) -> tuple[SteamGridDbAdapter, FakeTransport]:
    transport = FakeTransport(list(outcomes))  # type: ignore[list-item]
    adapter = SteamGridDbAdapter(
        api_key="fixture-key",
        rate_limiter=None,
        client=HttpClient(transport=transport),
    )
    return adapter, transport


def _ok(*data: object) -> FakeResponse:
    return FakeResponse(
        body=steamgriddb_json(list(data)),
        url=_API_URL,
        headers={"Content-Type": "application/json"},
    )


def _http_error(status: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(_API_URL, status, "fixture", {}, None)


def _identity(*, title_id: str | None = "0100ABCD12345678") -> GameIdentity:
    return GameIdentity(
        game_id="g1",
        title="Test Game",
        platform_slug="switch",
        title_id=title_id,
    )


def test_name() -> None:
    assert _adapter()[0].name == "steamgriddb"


def test_search_success() -> None:
    adapter, transport = _adapter(
        _ok({"id": 7}),
        _ok({"url": "http://example.invalid/grid.png", "width": 600, "height": 400}),
    )
    results = adapter.search(_identity(), ["grid"])
    assert len(results) == 1
    assert results[0].url == "https://example.invalid/grid.png"
    assert results[0].provider == "steamgriddb"
    assert results[0].media_kind == "grid"
    assert results[0].width == 600
    assert len(transport.requests) == 2


def test_search_missing_credentials_raises() -> None:
    adapter = SteamGridDbAdapter(rate_limiter=None)
    with pytest.raises(SteamZeroError) as exc:
        adapter.search(_identity(), ["grid"])
    assert exc.value.code == "E-SCRAPE-CREDENTIAL-MISSING"


def test_search_401_classified_as_auth() -> None:
    adapter, _ = _adapter(_http_error(401))
    with pytest.raises(SteamZeroError) as exc:
        adapter.search(_identity(), ["grid"])
    assert exc.value.code == "E-SCRAPE-CREDENTIAL-REJECTED"


def test_search_403_classified_as_auth() -> None:
    adapter, _ = _adapter(_http_error(403))
    with pytest.raises(SteamZeroError) as exc:
        adapter.search(_identity(), ["grid"])
    assert exc.value.code == "E-SCRAPE-CREDENTIAL-REJECTED"


def test_search_429_classified_as_rate_limited() -> None:
    adapter, _ = _adapter(_http_error(429))
    with pytest.raises(SteamZeroError) as exc:
        adapter.search(_identity(), ["grid"])
    assert exc.value.code == "E-SCRAPE-RATE-LIMITED"


def test_search_5xx_classified_as_unreachable() -> None:
    adapter, _ = _adapter(_http_error(500))
    with pytest.raises(SteamZeroError) as exc:
        adapter.search(_identity(), ["grid"])
    assert exc.value.code == "E-SCRAPE-PROVIDER-UNREACHABLE"


def test_search_timeout_classified_as_offline() -> None:
    adapter, _ = _adapter(TimeoutError("timed out"))
    with pytest.raises(SteamZeroError) as exc:
        adapter.search(_identity(), ["grid"])
    assert exc.value.code == "E-SCRAPE-OFFLINE"


def test_search_dns_failure_returns_empty_absence() -> None:
    adapter, _ = _adapter(
        urllib.error.URLError("offline"),
        urllib.error.URLError("offline"),
    )
    assert adapter.search(_identity(), ["grid"]) == []


def test_search_404_is_absence_and_falls_back_to_autocomplete() -> None:
    adapter, _ = _adapter(
        _http_error(404),
        _ok({"id": 9}),
        _http_error(404),
    )
    assert adapter.search(_identity(), ["grid"]) == []


def test_search_invalid_json_is_absence() -> None:
    adapter, _ = _adapter(
        FakeResponse(body=b"{broken", url=_API_URL),
        _ok({"id": 9}),
    )
    assert adapter.search(_identity(title_id=None), ["grid"]) == []


def test_search_over_limit_response_rejected() -> None:
    outcome = FakeResponse(
        body=steamgriddb_json([{"id": 7}]),
        url=_API_URL,
        headers={"Content-Length": "999999999"},
    )
    adapter, _ = _adapter(outcome)
    with pytest.raises(SteamZeroError) as exc:
        adapter.search(_identity(), ["grid"])
    assert exc.value.code == "E-SCRAPE-CORRUPT-MEDIA"


def test_search_filters_unsafe_media_urls() -> None:
    adapter, _ = _adapter(
        _ok({"id": 7}),
        _ok({"url": "file:///tmp/grid.png"}, {"url": "https://ok.example/grid.png"}),
    )
    results = adapter.search(_identity(), ["grid"])
    assert len(results) == 1
    assert results[0].url == "https://ok.example/grid.png"


def test_search_error_does_not_leak_api_key() -> None:
    adapter, transport = _adapter(_http_error(401))
    with pytest.raises(SteamZeroError) as exc:
        adapter.search(_identity(), ["grid"])
    rendered = f"{exc.value.code}: {exc.value.detail}"
    assert "fixture-key" not in rendered
    assert "Authorization" not in rendered
    _, _, headers = transport.requests[0]
    assert headers.get("Authorization") == "Bearer fixture-key"


def test_search_results_do_not_contain_api_key() -> None:
    adapter, _ = _adapter(
        _ok({"id": 7}),
        _ok({"url": "https://ok.example/grid.png"}),
    )
    results = adapter.search(_identity(), ["grid"])
    assert all("fixture-key" not in c.url for c in results)
    assert all(c.url.startswith("https://") for c in results)


def test_connection_success() -> None:
    adapter, _ = _adapter(FakeResponse(body=json.dumps({"success": True}).encode(), url=_API_URL))
    assert adapter.test_connection() is True


def test_connection_401_classified_as_auth() -> None:
    adapter, _ = _adapter(_http_error(401))
    with pytest.raises(SteamZeroError) as exc:
        adapter.test_connection()
    assert exc.value.code == "E-SCRAPE-CREDENTIAL-REJECTED"


def test_connection_offline_classified_as_offline() -> None:
    adapter, _ = _adapter(urllib.error.URLError("offline"))
    with pytest.raises(SteamZeroError) as exc:
        adapter.test_connection()
    assert exc.value.code == "E-SCRAPE-OFFLINE"
