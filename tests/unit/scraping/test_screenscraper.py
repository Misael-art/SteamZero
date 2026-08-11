# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do adapter ScreenScraper.fr — fixtures JSON (``output=json``)."""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import patch

import pytest

from fixtures.scraping.synthetic import (
    screenscraper_error_json,
    screenscraper_error_xml,
    screenscraper_json,
)
from steamzero.adapters.scraping.screenscraper import (
    _MEDIA_KIND_MAP,
    _PLATFORM_MAP,
    ScreenScraperAdapter,
    _accepted_media_types,
)
from steamzero.core.errors import SteamZeroError
from steamzero.core.net import FakeTransport, HttpClient
from steamzero.ports import GameIdentity

_JSON_OK = json.dumps(
    {
        "response": {
            "jeu": {
                "id": 1234,
                "medias": [
                    {
                        "type": "box-2d",
                        "region": "us",
                        "format": "png",
                        "url": "https://example.com/box2d.png",
                        "width": 400,
                        "height": 300,
                    },
                    {
                        "type": "ss",
                        "region": "us",
                        "format": "jpg",
                        "url": "https://example.com/ss.jpg",
                        "width": 640,
                        "height": 480,
                    },
                    {
                        "type": "wheel",
                        "region": "us",
                        "format": "png",
                        "url": "https://example.com/wheel.png",
                        "width": 200,
                        "height": 200,
                    },
                ],
            }
        }
    }
).encode()

_JSON_ERROR = json.dumps({"error": {"code": "403"}}).encode()

_JSON_EMPTY = json.dumps({"response": {}}).encode()

_JSON_NOTFOUND = b"Erreur : Rom/Iso/Dossier non trouv\xc3\xa9"

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
    assert "playstation" in platforms
    assert all(p in _PLATFORM_MAP for p in platforms)


def test_credential_missing_raises() -> None:
    adapter = ScreenScraperAdapter(devid=None, devpassword=None)
    identity = GameIdentity(game_id="g1", title="Test", platform_slug="switch")
    with pytest.raises(SteamZeroError) as exc:
        adapter.search(identity, ["boxart"])
    assert exc.value.code == "E-SCRAPE-CREDENTIAL-MISSING"


def test_connection_uses_lightweight_user_endpoint(
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


def test_search_returns_candidates_from_json(
    adapter: ScreenScraperAdapter, identity: GameIdentity
) -> None:
    with patch.object(adapter, "_fetch_url", return_value=_JSON_OK):
        results = adapter.search(identity, ["boxart", "screenshot", "wheel"])
    assert len(results) == 3
    kinds_found = {c.media_kind for c in results}
    assert "boxart" in kinds_found
    assert "screenshot" in kinds_found
    assert "wheel" in kinds_found
    for c in results:
        assert c.provider == "screenscraper"


def test_search_parses_url_and_dimensions(
    adapter: ScreenScraperAdapter, identity: GameIdentity
) -> None:
    with patch.object(adapter, "_fetch_url", return_value=_JSON_OK):
        results = adapter.search(identity, ["boxart"])
    assert len(results) == 1
    assert results[0].url == "https://example.com/box2d.png"
    assert results[0].width == 400
    assert results[0].height == 300


def test_search_notfound_returns_empty(
    adapter: ScreenScraperAdapter, identity: GameIdentity
) -> None:
    with patch.object(adapter, "_fetch_url", return_value=_JSON_NOTFOUND):
        results = adapter.search(identity, ["boxart"])
    assert results == []


def test_search_quota_error(adapter: ScreenScraperAdapter, identity: GameIdentity) -> None:
    with (
        patch.object(adapter, "_fetch_url", return_value=_JSON_ERROR),
        pytest.raises(SteamZeroError) as exc,
    ):
        adapter.search(identity, ["boxart"])
    assert exc.value.code == "E-SCRAPE-QUOTA-EXCEEDED"


def test_search_empty_response(adapter: ScreenScraperAdapter) -> None:
    identity = GameIdentity(game_id="g1", title="Unknown", platform_slug="switch")
    with patch.object(adapter, "_fetch_url", return_value=_JSON_EMPTY):
        results = adapter.search(identity, ["boxart"])
    assert results == []


def test_search_build_params_uses_json_output(adapter: ScreenScraperAdapter) -> None:
    params = adapter._build_params(GameIdentity(game_id="g1", title="Test", platform_slug="switch"))
    assert params.get("output") == "json"


def test_search_build_params_includes_romtype(adapter: ScreenScraperAdapter) -> None:
    params = adapter._build_params(GameIdentity(game_id="g1", title="Test", platform_slug="switch"))
    assert params.get("romtype") == "rom"


def test_build_params_uses_correct_platform_id(adapter: ScreenScraperAdapter) -> None:
    identity = GameIdentity(game_id="g1", title="Test", platform_slug="switch")
    params = adapter._build_params(identity)
    assert params.get("systemeid") == "225"


def test_build_params_falls_back_to_romnom(adapter: ScreenScraperAdapter) -> None:
    identity = GameIdentity(game_id="g1", title="Some Game Name", platform_slug="switch")
    params = adapter._build_params(identity)
    assert params.get("romnom") == "Some Game Name"
    assert "sha1" not in params
    assert "md5" not in params
    assert "crc" not in params


def test_search_xml_fallback(adapter: ScreenScraperAdapter, identity: GameIdentity) -> None:
    with patch.object(adapter, "_fetch_url", return_value=_XML_OK):
        results = adapter.search(identity, ["boxart", "screenshot", "wheel"])
    assert len(results) == 3
    kinds_found = {c.media_kind for c in results}
    assert "boxart" in kinds_found
    assert "screenshot" in kinds_found
    assert "wheel" in kinds_found


def test_search_xml_quota(adapter: ScreenScraperAdapter, identity: GameIdentity) -> None:
    with (
        patch.object(adapter, "_fetch_url", return_value=_XML_ERROR),
        pytest.raises(SteamZeroError) as exc,
    ):
        adapter.search(identity, ["boxart"])
    assert exc.value.code == "E-SCRAPE-QUOTA-EXCEEDED"


def test_media_kind_map_has_known_kinds() -> None:
    assert _MEDIA_KIND_MAP["boxart"] == "box-2D"
    assert _MEDIA_KIND_MAP["wheel"] == "wheel"
    assert _MEDIA_KIND_MAP["screenshot"] == "ss"
    assert _MEDIA_KIND_MAP["video"] == "video"
    assert _MEDIA_KIND_MAP["marquee"] == "marquee"
    assert _MEDIA_KIND_MAP["manual"] == "manuel"


def test_accepted_media_types_known() -> None:
    boxart_types = _accepted_media_types("boxart")
    assert "box-2d" in boxart_types
    assert "box-2d-side" in boxart_types

    wheel_types = _accepted_media_types("wheel")
    assert "wheel" in wheel_types
    assert "wheel-hd" in wheel_types


def test_platform_map_covers_supported_platforms(adapter: ScreenScraperAdapter) -> None:
    for slug in adapter.supported_platforms():
        assert slug in _PLATFORM_MAP, f"slug {slug} not in _PLATFORM_MAP"


def test_platform_map_switch_is_225() -> None:
    assert _PLATFORM_MAP["switch"] == "225"


def test_platform_map_wii_is_16() -> None:
    assert _PLATFORM_MAP["wii"] == "16"


def test_platform_map_playstation_is_57() -> None:
    assert _PLATFORM_MAP["playstation"] == "57"


def test_platform_map_saturn_is_22() -> None:
    assert _PLATFORM_MAP["saturn"] == "22"


def test_platform_map_3do_is_29() -> None:
    assert _PLATFORM_MAP["3do"] == "29"


def test_platform_map_playstationvita_is_62() -> None:
    assert _PLATFORM_MAP["playstationvita"] == "62"


def test_platform_map_gamecube_exists() -> None:
    assert _PLATFORM_MAP["gamecube"] == "13"


def test_platform_map_playstation2_is_58() -> None:
    assert _PLATFORM_MAP["playstation2"] == "58"


def test_platform_map_neogeo_is_142() -> None:
    assert _PLATFORM_MAP["neogeo"] == "142"


# -- classificação de erro no corpo ----------------------------------------


def test_search_json_401_classified_as_auth(
    adapter: ScreenScraperAdapter, identity: GameIdentity
) -> None:
    with (
        patch.object(adapter, "_fetch_url", return_value=screenscraper_error_json("401")),
        pytest.raises(SteamZeroError) as exc,
    ):
        adapter.search(identity, ["boxart"])
    assert exc.value.code == "E-SCRAPE-CREDENTIAL-REJECTED"


def test_search_xml_401_classified_as_auth(
    adapter: ScreenScraperAdapter, identity: GameIdentity
) -> None:
    with (
        patch.object(adapter, "_fetch_url", return_value=screenscraper_error_xml("401")),
        pytest.raises(SteamZeroError) as exc,
    ):
        adapter.search(identity, ["boxart"])
    assert exc.value.code == "E-SCRAPE-CREDENTIAL-REJECTED"


def test_search_json_429_classified_as_rate_limit(
    adapter: ScreenScraperAdapter, identity: GameIdentity
) -> None:
    with (
        patch.object(adapter, "_fetch_url", return_value=screenscraper_error_json("429")),
        pytest.raises(SteamZeroError) as exc,
    ):
        adapter.search(identity, ["boxart"])
    assert exc.value.code == "E-SCRAPE-RATE-LIMITED"


# -- sanitização de URL de mídia -------------------------------------------


def _client_with(outcome: object) -> HttpClient:
    return HttpClient(transport=FakeTransport([outcome]))  # type: ignore[list-item]


def test_search_filters_unsafe_media_urls(identity: GameIdentity) -> None:
    payload = screenscraper_json(
        [
            {
                "type": "box-2d",
                "region": "us",
                "url": "file:///tmp/box.png",
                "width": 400,
                "height": 300,
            },
            {
                "type": "ss",
                "region": "us",
                "url": "https://example.com/ss.jpg",
                "width": 640,
                "height": 480,
            },
        ]
    )
    adapter = ScreenScraperAdapter(devid="test-dev", devpassword="test-pass", rate_limiter=None)
    with patch.object(adapter, "_fetch_url", return_value=payload):
        results = adapter.search(identity, ["boxart", "screenshot"])
    kinds = {c.media_kind for c in results}
    assert "boxart" not in kinds
    assert "screenshot" in kinds


def test_search_upgrades_http_and_protocol_relative_urls(identity: GameIdentity) -> None:
    payload = screenscraper_json(
        [
            {
                "type": "box-2d",
                "region": "us",
                "url": "http://example.com/box.png",
            },
            {
                "type": "ss",
                "region": "us",
                "url": "//example.com/ss.jpg",
            },
        ]
    )
    adapter = ScreenScraperAdapter(devid="test-dev", devpassword="test-pass", rate_limiter=None)
    with patch.object(adapter, "_fetch_url", return_value=payload):
        results = adapter.search(identity, ["boxart", "screenshot"])
    urls = {c.url for c in results}
    assert "https://example.com/box.png" in urls
    assert "https://example.com/ss.jpg" in urls


def test_search_xml_filters_unsafe_media_urls(identity: GameIdentity) -> None:
    payload = b"""<?xml version="1.0"?>
<data>
  <jeu>
    <media type="box-2d" region="us">file:///tmp/box.png</media>
    <media type="ss" region="us">ftp://example.com/ss.jpg</media>
  </jeu>
</data>
"""
    adapter = ScreenScraperAdapter(devid="test-dev", devpassword="test-pass", rate_limiter=None)
    with patch.object(adapter, "_fetch_url", return_value=payload):
        results = adapter.search(identity, ["boxart", "screenshot"])
    assert results == []


# -- credenciais nunca vazam -----------------------------------------------


def test_search_error_does_not_leak_credentials(identity: GameIdentity) -> None:
    adapter = ScreenScraperAdapter(
        devid="test-dev",
        devpassword="super-secret-pass",
        rate_limiter=None,
        client=_client_with(urllib.error.HTTPError("https://x/api", 500, "fixture", {}, None)),
    )
    with pytest.raises(SteamZeroError) as exc:
        adapter.search(identity, ["boxart"])
    rendered = f"{exc.value.code}: {exc.value.detail}"
    assert "super-secret-pass" not in rendered
    assert "test-dev" not in rendered
    assert "devpassword" not in rendered
    assert "https://" not in rendered


def test_search_results_do_not_contain_credentials(
    adapter: ScreenScraperAdapter, identity: GameIdentity
) -> None:
    with patch.object(adapter, "_fetch_url", return_value=_JSON_OK):
        results = adapter.search(identity, ["boxart", "screenshot", "wheel"])
    assert all("devpassword" not in c.url for c in results)
    assert all("test-pass" not in c.url for c in results)
    assert all(c.url.startswith("https://") for c in results)
