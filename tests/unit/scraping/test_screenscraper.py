# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do adapter ScreenScraper.fr."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from steamzero.adapters.scraping.screenscraper import (
    _MEDIA_KIND_MAP,
    _PLATFORM_MAP,
    ScreenScraperAdapter,
)
from steamzero.core.errors import SteamZeroError
from steamzero.ports import GameIdentity

_XML_OK = b"""<?xml version="1.0"?>
<data>
  <jeu>
    <media type="box-2d" region="us" width="400" height="300">
      <url>https://example.com/box2d.png</url>
      <crc>abc123</crc>
    </media>
    <media type="ss" region="us" width="640" height="480">
      <url>https://example.com/ss.png</url>
    </media>
    <media type="wheel" region="us" width="200" height="200">
      <url>https://example.com/wheel.png</url>
    </media>
  </jeu>
</data>
"""

_XML_ERROR = b"""<?xml version="1.0"?>
<data>
  <error>
    <code>403</code>
  </error>
</data>
"""

_XML_USER_OK = b"""<?xml version="1.0"?>
<data><ssuser><id>test-user</id></ssuser></data>
"""


@pytest.fixture
def adapter() -> ScreenScraperAdapter:
    return ScreenScraperAdapter(
        devid="test-dev",
        devpassword="test-pass",
        rate_limiter=None,
    )


@pytest.fixture
def identity() -> GameIdentity:
    return GameIdentity(
        game_id="g1",
        title="Test Game",
        platform_slug="switch",
        hashes={"sha1": "a" * 40},
    )


def test_name(adapter: ScreenScraperAdapter) -> None:
    assert adapter.name == "screenscraper"


def test_supported_kinds(adapter: ScreenScraperAdapter) -> None:
    kinds = adapter.supported_kinds()
    assert "boxart" in kinds
    assert "screenshot" in kinds
    assert "wheel" in kinds
    assert "video" in kinds
    assert "fanart" in kinds


def test_supported_platforms(adapter: ScreenScraperAdapter) -> None:
    platforms = adapter.supported_platforms()
    assert "switch" in platforms
    assert "nes" in platforms
    assert "snes" in platforms
    assert "megadrive" in platforms
    assert "psx" in platforms
    assert all(p in _PLATFORM_MAP for p in platforms)


def test_credential_missing_raises() -> None:
    adapter = ScreenScraperAdapter(devid=None, devpassword=None)
    identity = GameIdentity(game_id="g1", title="Test", platform_slug="switch")
    with pytest.raises(SteamZeroError) as exc:
        adapter.search(identity, ["boxart"])
    assert exc.value.code == "E-SCRAPE-CREDENTIAL-MISSING"


def test_connection_uses_lightweight_user_endpoint_without_media(
    adapter: ScreenScraperAdapter,
) -> None:
    with patch.object(adapter, "_fetch_url", return_value=_XML_USER_OK) as fetch:
        assert adapter.test_connection() is True
    url = fetch.call_args.args[0]
    assert "ssuserInfos.php" in url
    assert "jeuInfos.php" not in url
    assert fetch.call_args.kwargs == {"max_bytes": 256 * 1024}


def test_connection_rejects_error_response(adapter: ScreenScraperAdapter) -> None:
    error_xml = b"<data><error><code>401</code></error></data>"
    with (
        patch.object(adapter, "_fetch_url", return_value=error_xml),
        pytest.raises(SteamZeroError) as exc,
    ):
        adapter.test_connection()
    assert exc.value.code == "E-SCRAPE-CREDENTIAL-REJECTED"


def test_search_returns_candidates(adapter: ScreenScraperAdapter, identity: GameIdentity) -> None:
    with patch.object(adapter, "_fetch_url", return_value=_XML_OK):
        results = adapter.search(identity, ["boxart", "screenshot", "wheel"])
    assert len(results) == 3
    kinds_found = {c.media_kind for c in results}
    assert "boxart" in kinds_found
    assert "screenshot" in kinds_found
    assert "wheel" in kinds_found
    for c in results:
        assert c.provider == "screenscraper"


def test_search_quota_error(adapter: ScreenScraperAdapter, identity: GameIdentity) -> None:
    with (
        patch.object(adapter, "_fetch_url", return_value=_XML_ERROR),
        pytest.raises(SteamZeroError) as exc,
    ):
        adapter.search(identity, ["boxart"])
    assert exc.value.code == "E-SCRAPE-QUOTA-EXCEEDED"


def test_search_empty_response(adapter: ScreenScraperAdapter) -> None:
    empty_xml = b"<?xml version='1.0'?><data></data>"
    identity = GameIdentity(game_id="g1", title="Unknown", platform_slug="switch")
    with patch.object(adapter, "_fetch_url", return_value=empty_xml):
        results = adapter.search(identity, ["boxart"])
    assert results == []


def test_media_kind_map_has_known_kinds() -> None:
    assert _MEDIA_KIND_MAP["boxart"] == "box-2D"
    assert _MEDIA_KIND_MAP["wheel"] == "wheel"
    assert _MEDIA_KIND_MAP["screenshot"] == "ss"
    assert _MEDIA_KIND_MAP["video"] == "video"
    assert _MEDIA_KIND_MAP["marquee"] == "marquee"
    assert _MEDIA_KIND_MAP["manual"] == "manuel"
