# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do RateLimiter, TokenBucket e validação de mídia."""

from __future__ import annotations

import time
import urllib.error

import pytest

from fixtures.scraping.synthetic import HTML_BYTES, JPEG_BYTES, MP4_BYTES, PDF_BYTES, PNG_BYTES
from steamzero.adapters.scraping.base import BaseMediaProvider, RateLimiter, TokenBucket
from steamzero.core.errors import SteamZeroError
from steamzero.core.net import FakeResponse, FakeTransport, HttpClient


class _FetchProvider(BaseMediaProvider):
    @property
    def name(self) -> str:
        return "fetch"

    def supported_kinds(self) -> frozenset[str]:
        return frozenset({"boxart"})

    def supported_platforms(self) -> frozenset[str]:
        return frozenset({"switch"})

    def search(
        self,
        identity: object,
        media_kinds: list[str],
        region_priority: list[str] | None = None,
    ) -> list[object]:
        del identity, media_kinds, region_priority
        return []


def _http_error(status: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://example.invalid/media", status, "fixture", {}, None)


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


# -- transporte injetável ---------------------------------------------------


def _client_with(outcome: object) -> tuple[HttpClient, FakeTransport]:
    transport = FakeTransport([outcome])  # type: ignore[list-item]
    return HttpClient(transport=transport), transport


def _signed_png_outcome() -> FakeResponse:
    return FakeResponse(body=PNG_BYTES, url="https://example.invalid/media.png")


def test_fetch_url_accepts_injected_client() -> None:
    client, transport = _client_with(_signed_png_outcome())
    provider = _FetchProvider(rate_limiter=None, client=client)
    assert provider._fetch_url("https://example.invalid/media.png") == PNG_BYTES
    assert len(transport.requests) == 1


def test_fetch_url_records_bounded_timeout_by_default() -> None:
    client, transport = _client_with(_signed_png_outcome())
    provider = _FetchProvider(rate_limiter=None, client=client)
    provider._fetch_url("https://example.invalid/media.png")
    _, timeout, _ = transport.requests[0]
    assert timeout <= 30.0
    assert timeout > 0.0


def test_fetch_url_accepts_explicit_timeout() -> None:
    client, transport = _client_with(_signed_png_outcome())
    provider = _FetchProvider(rate_limiter=None, client=client)
    provider._fetch_url("https://example.invalid/media.png", timeout_seconds=7.5)
    _, timeout, _ = transport.requests[0]
    assert timeout == 7.5


def test_fetch_url_classifies_401_as_auth() -> None:
    client, _ = _client_with(_http_error(401))
    provider = _FetchProvider(rate_limiter=None, client=client)
    with pytest.raises(SteamZeroError) as exc:
        provider._fetch_url("https://example.invalid/media.png")
    assert exc.value.code == "E-SCRAPE-CREDENTIAL-REJECTED"


def test_fetch_url_classifies_429_as_rate_limit() -> None:
    client, _ = _client_with(_http_error(429))
    provider = _FetchProvider(rate_limiter=None, client=client)
    with pytest.raises(SteamZeroError) as exc:
        provider._fetch_url("https://example.invalid/media.png")
    assert exc.value.code == "E-SCRAPE-RATE-LIMITED"


def test_fetch_url_classifies_404_as_not_found() -> None:
    client, _ = _client_with(_http_error(404))
    provider = _FetchProvider(rate_limiter=None, client=client)
    with pytest.raises(SteamZeroError) as exc:
        provider._fetch_url("https://example.invalid/media.png")
    assert exc.value.code == "E-SCRAPE-NOT-FOUND"


def test_fetch_url_classifies_5xx_as_unreachable() -> None:
    client, _ = _client_with(_http_error(500))
    provider = _FetchProvider(rate_limiter=None, client=client)
    with pytest.raises(SteamZeroError) as exc:
        provider._fetch_url("https://example.invalid/media.png")
    assert exc.value.code == "E-SCRAPE-PROVIDER-UNREACHABLE"


def test_fetch_url_classifies_timeout_as_offline() -> None:
    client, _ = _client_with(TimeoutError("timed out"))
    provider = _FetchProvider(rate_limiter=None, client=client)
    with pytest.raises(SteamZeroError) as exc:
        provider._fetch_url("https://example.invalid/media.png")
    assert exc.value.code == "E-SCRAPE-OFFLINE"


def test_fetch_url_classifies_dns_failure_as_unreachable() -> None:
    client, _ = _client_with(urllib.error.URLError("offline"))
    provider = _FetchProvider(rate_limiter=None, client=client)
    with pytest.raises(SteamZeroError) as exc:
        provider._fetch_url("https://example.invalid/media.png")
    assert exc.value.code == "E-SCRAPE-PROVIDER-UNREACHABLE"


def test_fetch_url_rejects_file_scheme() -> None:
    client, _ = _client_with(_signed_png_outcome())
    provider = _FetchProvider(rate_limiter=None, client=client)
    with pytest.raises(SteamZeroError) as exc:
        provider._fetch_url("file:///tmp/media.pdf")
    assert exc.value.code == "E-SCRAPE-DOWNLOAD-FAILED"


def test_fetch_url_rejects_insecure_redirect() -> None:
    outcome = FakeResponse(body=PNG_BYTES, url="http://evil.example/media.png")
    client, _ = _client_with(outcome)
    provider = _FetchProvider(rate_limiter=None, client=client)
    with pytest.raises(SteamZeroError) as exc:
        provider._fetch_url("https://example.invalid/media.png")
    assert exc.value.code == "E-SCRAPE-DOWNLOAD-FAILED"


def test_fetch_url_rejects_cross_host_redirect() -> None:
    outcome = FakeResponse(body=PNG_BYTES, url="https://other.example/media.png")
    client, _ = _client_with(outcome)
    provider = _FetchProvider(rate_limiter=None, client=client)
    with pytest.raises(SteamZeroError) as exc:
        provider._fetch_url("https://example.invalid/media.png")
    assert exc.value.code == "E-SCRAPE-DOWNLOAD-FAILED"


def test_fetch_url_rejects_body_over_limit() -> None:
    outcome = FakeResponse(body=PNG_BYTES + b"\x00" * 100, url="https://example.invalid/media.png")
    client, _ = _client_with(outcome)
    provider = _FetchProvider(rate_limiter=None, client=client)
    with pytest.raises(SteamZeroError) as exc:
        provider._fetch_url("https://example.invalid/media.png", max_bytes=64)
    assert exc.value.code == "E-SCRAPE-DOWNLOAD-FAILED"


# -- assinatura de conteúdo por kind ---------------------------------------


def test_validate_media_video_mp4_signature() -> None:
    assert BaseMediaProvider._validate_media(MP4_BYTES, expected_kind="video") == ".mp4"


def test_validate_media_manual_pdf_signature() -> None:
    assert BaseMediaProvider._validate_media(PDF_BYTES, expected_kind="manual") == ".pdf"


def test_validate_media_video_rejects_image_bytes() -> None:
    assert BaseMediaProvider._validate_media(PNG_BYTES, expected_kind="video") is None


def test_validate_media_manual_rejects_html() -> None:
    assert BaseMediaProvider._validate_media(HTML_BYTES, expected_kind="manual") is None


def test_validate_media_image_rejects_html_despite_no_kind() -> None:
    assert BaseMediaProvider._validate_media(HTML_BYTES) is None
    assert BaseMediaProvider._validate_media(HTML_BYTES, expected_kind="boxart") is None


def test_validate_media_image_accepts_png_jpeg_webp() -> None:
    assert BaseMediaProvider._validate_media(PNG_BYTES, expected_kind="boxart") == ".png"
    assert BaseMediaProvider._validate_media(JPEG_BYTES, expected_kind="boxart") == ".jpg"
    assert (
        BaseMediaProvider._validate_media(
            b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 60, expected_kind="boxart"
        )
        == ".webp"
    )


def test_validate_media_truncated_signature_rejected() -> None:
    assert BaseMediaProvider._validate_media(b"\x89PN", expected_kind="boxart") is None


def test_validate_media_asserts_mimetype_independent() -> None:
    # content-type enganoso: header diz image/png, corpo é HTML — só a
    # assinatura decide.
    assert BaseMediaProvider._validate_media(HTML_BYTES, expected_kind="boxart") is None


# -- normalização de URL ----------------------------------------------------


def test_normalize_media_url_accepts_https() -> None:
    assert (
        BaseMediaProvider._normalize_media_url("https://example.com/x.png")
        == "https://example.com/x.png"
    )


def test_normalize_media_url_upgrades_http() -> None:
    assert (
        BaseMediaProvider._normalize_media_url("http://example.com/x.png")
        == "https://example.com/x.png"
    )


def test_normalize_media_url_upgrades_protocol_relative() -> None:
    assert (
        BaseMediaProvider._normalize_media_url("//example.com/x.png") == "https://example.com/x.png"
    )


def test_normalize_media_url_rejects_other_schemes() -> None:
    assert BaseMediaProvider._normalize_media_url("file:///tmp/x.png") is None
    assert BaseMediaProvider._normalize_media_url("ftp://example.com/x.png") is None
    assert BaseMediaProvider._normalize_media_url("data:image/png;base64,xx") is None


def test_normalize_media_url_rejects_blank() -> None:
    assert BaseMediaProvider._normalize_media_url("") is None
    assert BaseMediaProvider._normalize_media_url("   ") is None
