# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression coverage for adapters added by the media correction line.

These tests intentionally exercise the real parsing, fallback and error
semantics.  All network and subprocess boundaries are replaced by deterministic
fakes; no personal media, credentials or external services are used.
"""

from __future__ import annotations

import io
import json
import subprocess
import urllib.error
from pathlib import Path
from typing import Any

import pytest

from steamzero.adapters.cheats.nsecm_source import (
    NsecmSource,
    _guess_cheat_type,
    _parse_cheat_text,
)
from steamzero.adapters.mods.ns_emu_mod_downloader import NsEmuModDownloaderSource
from steamzero.adapters.mods.semd_source import SemdSource, _guess_mod_type_semd
from steamzero.adapters.scraping.base import BaseMediaProvider
from steamzero.adapters.scraping.cache import ScrapingCache
from steamzero.adapters.scraping.dispatcher import (
    ScrapeConfig,
    ScrapingDispatcher,
    _kind_extension,
)
from steamzero.adapters.scraping.registry import ProviderRegistry
from steamzero.adapters.scraping.steamgriddb import SteamGridDbAdapter
from steamzero.core.errors import SteamZeroError
from steamzero.ports import GameIdentity, MediaCandidate


class _Response:
    def __init__(
        self,
        payload: bytes,
        *,
        url: str = "https://example.invalid/media.png",
        headers: dict[str, str] | None = None,
    ) -> None:
        self._stream = io.BytesIO(payload)
        self._url = url
        self.headers = headers or {}

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def geturl(self) -> str:
        return self._url


class _Provider(BaseMediaProvider):
    @property
    def name(self) -> str:
        return "fake"

    def supported_kinds(self) -> frozenset[str]:
        return frozenset({"boxart", "hero"})

    def supported_platforms(self) -> frozenset[str]:
        return frozenset({"switch"})

    def search(
        self,
        identity: GameIdentity,
        media_kinds: list[str],
        region_priority: list[str] | None = None,
    ) -> list[MediaCandidate]:
        del identity, region_priority
        return [
            MediaCandidate(
                url="https://example.invalid/media.png",
                media_kind=kind,
                provider=self.name,
                confidence=0.9,
                license="fixture",
                attribution="fixture",
            )
            for kind in media_kinds
        ]

    def _fetch_url(self, url: str, max_bytes: int = 32 * 1024 * 1024) -> bytes:
        del url, max_bytes
        return b"\x89PNG\r\n\x1a\nfixture"


def _completed(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["fixture"], returncode, stdout=stdout, stderr="")


def test_ns_emu_downloader_parses_json_text_and_subprocess_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    payload = json.dumps(
        [
            {
                "titleId": "0100abcd00000000",
                "buildId": "aabb",
                "mod_name": "Smooth",
                "mod_type": "60fps",
                "url": "https://example.invalid/mod",
                "version": "1",
                "description": "fixture",
                "repo": "fixture-author",
            },
            {"name": "missing-title"},
        ]
    )

    def run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        if "--version" in argv:
            return _completed()
        if "list" in argv:
            return _completed(stdout=payload)
        return _completed()

    monkeypatch.setattr(subprocess, "run", run)
    source = NsEmuModDownloaderSource("fixture-tool")
    assert source.refresh_catalog() == 1
    assert source.search_by_title_id("0100ABCD00000000")[0].identity.mod_type == "performance"
    assert source.search_by_build_id("0100ABCD00000000", "AABB")
    assert source.download_for_game(
        "0100ABCD00000000", tmp_path, build_id="AABB", emulator_id="ryubing"
    ) == 0
    assert calls[-1][-4:] == ["--build-id", "AABB", "--emulator", "ryubing"]

    text = "\n".join(
        [
            "# comment",
            "invalid",
            "not-a-title ignored",
            "0100abcd00000000 Text Mod",
        ]
    )
    parsed = source._parse_list_output(text)
    assert parsed[0].title_id == "0100ABCD00000000"
    assert source._parse_list_output("") == []
    assert source._parse_list_output("[broken") == []

    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _completed(returncode=1))
    unavailable = NsEmuModDownloaderSource("fixture-tool")
    assert unavailable.refresh_catalog() == 0
    assert unavailable.download_for_game("0100ABCD00000000", tmp_path) == 0

    def missing(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", missing)
    missing_source = NsEmuModDownloaderSource("missing")
    assert missing_source.search_by_title_id("0100ABCD00000000") == []

    timeouts = NsEmuModDownloaderSource("slow")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_k: (_ for _ in ()).throw(subprocess.TimeoutExpired("slow", 1)),
    )
    assert timeouts.refresh_catalog() == 0
    timeouts._available = True
    assert timeouts.download_for_game("0100ABCD00000000", tmp_path) == 1


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Infinite health", "infinite"),
        ("Speed boost", "speed"),
        ("All items", "items"),
        ("Unlock all", "unlock"),
        ("Max EXP level", "stats"),
        ("Gold money", "gold"),
        ("Cosmetic", "other"),
    ],
)
def test_nsecm_parsers_and_type_classification(name: str, expected: str) -> None:
    assert _guess_cheat_type(name) == expected
    codes, parsed_name, build_id = _parse_cheat_text(
        "// Fixture cheat\n"
        "// BuildID: AABBCCDDEEFF00112233445566778899\n"
        "04000000 00000000\n"
        "not a code\n"
    )
    assert codes == ("04000000 00000000",)
    assert parsed_name == "Fixture cheat"
    assert build_id == "AABBCCDDEEFF00112233445566778899"


def test_nsecm_fetches_valid_entries_and_degrades_per_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root_entries = json.dumps(
        [
            {"name": "README", "type": "file"},
            {"name": "bad", "type": "dir"},
            {"name": "0100abcd00000000", "type": "dir"},
        ]
    ).encode()
    title_entries = json.dumps(
        [
            {"name": "missing-url.txt", "download_url": None},
            {"name": "broken.txt", "download_url": "https://example.invalid/broken"},
            {"name": "empty.txt", "download_url": "https://example.invalid/empty"},
            {"name": "valid.txt", "download_url": "https://example.invalid/valid"},
        ]
    ).encode()

    def urlopen(request: object, timeout: int = 15) -> _Response:
        del timeout
        url = getattr(request, "full_url", str(request))
        if url.endswith("/contents"):
            return _Response(root_entries)
        if url.endswith("/0100ABCD00000000"):
            return _Response(title_entries)
        if url.endswith("/broken"):
            raise OSError("fixture failure")
        if url.endswith("/empty"):
            return _Response(b"// no executable codes")
        return _Response(
            b"// Infinite gold\n// BuildID: AABBCCDDEEFF00112233445566778899\n"
            b"04000000 00000000\n"
        )

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    source = NsecmSource({"fixture": "owner/repo"})
    assert source.refresh_catalog() == 1
    assert source.search_by_title_id("0100ABCD00000000")[0].identity.cheat_type == "gold"
    assert source.search_by_build_id(
        "0100ABCD00000000", "AABBCCDDEEFF00112233445566778899"
    )

    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_k: _Response(b"{broken"))
    assert NsecmSource({"bad": "owner/repo"}).refresh_catalog() == 0
    monkeypatch.setattr(
        NsecmSource,
        "_fetch_repo_cheats",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("fixture")),
    )
    assert NsecmSource({"bad": "owner/repo"}).refresh_catalog() == 0


def test_steamgriddb_search_resolution_connection_and_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = GameIdentity(
        game_id="game-1",
        title="Fixture Game",
        platform_slug="switch",
        title_id="0100ABCD00000000",
    )
    adapter = SteamGridDbAdapter(api_key="fixture")
    monkeypatch.setattr(adapter, "_rate_limit", lambda: None)

    def fetch(url: str) -> list[dict[str, Any]]:
        if "/games/rom/" in url:
            return [{"id": 7}]
        if "/grids/" in url:
            return [
                {
                    "url": "http://example.invalid/grid.png",
                    "width": 600,
                    "height": 900,
                    "hash": "abc",
                },
                {"url": ""},
            ]
        return []

    monkeypatch.setattr(adapter, "_fetch_json", fetch)
    candidates = adapter.search(identity, ["grid", "unsupported"])
    assert candidates[0].url.startswith("https://")
    assert candidates[0].hash == "abc"
    assert adapter.search(identity, ["unsupported"]) == []

    monkeypatch.setattr(adapter, "_fetch_json", lambda _url: [])
    assert adapter.search(identity, ["grid"]) == []
    by_name = GameIdentity(game_id="g", title="Name", platform_slug="switch")
    monkeypatch.setattr(
        adapter,
        "_fetch_json",
        lambda url: [{"id": 9}] if "autocomplete" in url else [],
    )
    assert adapter._resolve_game_id(by_name) == 9

    no_key = SteamGridDbAdapter()
    with pytest.raises(SteamZeroError):
        no_key.search(identity, ["grid"])
    with pytest.raises(SteamZeroError):
        no_key.test_connection()

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_a, **_k: _Response(json.dumps({"success": True}).encode()),
    )
    assert adapter.test_connection() is True
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_a, **_k: _Response(json.dumps({"success": False}).encode()),
    )
    with pytest.raises(SteamZeroError):
        adapter.test_connection()

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_a, **_k: (_ for _ in ()).throw(
            urllib.error.HTTPError("https://example.invalid", 401, "fixture", {}, None)
        ),
    )
    with pytest.raises(SteamZeroError) as exc:
        adapter.test_connection()
    assert exc.value.code == "E-SCRAPE-CREDENTIAL-REJECTED"

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_a, **_k: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )
    with pytest.raises(SteamZeroError) as exc:
        adapter.test_connection()
    assert exc.value.code == "E-SCRAPE-OFFLINE"


def test_steamgriddb_fetch_json_validates_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = SteamGridDbAdapter(api_key="fixture")
    payloads: list[bytes | BaseException] = [
        json.dumps({"success": True, "data": [{"id": 1}]}).encode(),
        b"[]",
        json.dumps({"success": False, "data": []}).encode(),
        json.dumps({"success": True, "data": {}}).encode(),
        b"{broken",
        OSError("offline"),
    ]
    results: list[list[dict[str, Any]]] = []
    for payload in payloads:
        if isinstance(payload, BaseException):
            monkeypatch.setattr(
                "urllib.request.urlopen",
                lambda *_a, _payload=payload, **_k: (_ for _ in ()).throw(_payload),
            )
        else:
            monkeypatch.setattr(
                "urllib.request.urlopen",
                lambda *_a, _payload=payload, **_k: _Response(_payload),
            )
        results.append(adapter._fetch_json("http://example.invalid/api"))
    assert results[0] == [{"id": 1}]
    assert all(result == [] for result in results[1:])


def test_scraping_dispatcher_cache_download_commit_and_lookup_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cache = ScrapingCache(tmp_path / "cache.db")
    registry = ProviderRegistry(fallback_order={"boxart": ["fake"], "hero": ["fake"]})
    provider = _Provider()
    registry.register(provider)
    config = ScrapeConfig(media_root=tmp_path / "media")
    dispatcher = ScrapingDispatcher(cache, registry, config)
    identity = GameIdentity(
        game_id="game-1",
        title="Fixture",
        platform_slug="switch",
        hashes={"sha1": "sha-one"},
    )

    result = dispatcher.scrape_game(identity, ["boxart"])
    assert result.success
    assert "boxart" in result.downloaded
    cache.save_cache_entry(
        MediaCandidate(
            url="https://example.invalid/cached",
            media_kind="boxart",
            provider="*",
            confidence=1,
        ),
        "sha-one",
        platform_slug="switch",
    )
    cached = dispatcher.scrape_game(identity, ["boxart"])
    assert cached.downloaded == {}

    monkeypatch.setattr(registry, "search_best", lambda *_a, **_k: None)
    missing = dispatcher.scrape_game(identity, ["hero"])
    assert missing.failed == ["hero"]

    monkeypatch.setattr(
        registry,
        "search_best",
        lambda *_a, **_k: MediaCandidate(
            url="https://example.invalid/fail",
            media_kind="hero",
            provider="fake",
            confidence=1,
        ),
    )
    monkeypatch.setattr(
        provider,
        "_fetch_url",
        lambda *_a, **_k: (_ for _ in ()).throw(
            SteamZeroError("E-SCRAPE-DOWNLOAD-FAILED", detail="fixture")
        ),
    )
    failed = dispatcher.scrape_game(identity, ["hero"])
    assert failed.failed == ["hero"]

    monkeypatch.setattr(provider, "_fetch_url", lambda *_a, **_k: b"\x89PNG\r\n\x1a\nfixture")
    monkeypatch.setattr(
        "steamzero.adapters.scraping.dispatcher.paths.staging_for",
        lambda _op: config.media_root / "staging",
    )
    plan = dispatcher.commit_staged(
        "game-1",
        {
            "boxart": MediaCandidate(
                url="https://example.invalid/media",
                media_kind="boxart",
                provider="fake",
                confidence=1,
            )
        },
    )
    assert plan.actions

    identities = [
        GameIdentity("g", "Name", "switch", hashes={"md5": "md-five"}),
        GameIdentity("g", "Name", "switch", title_id="tid"),
        GameIdentity("g", "Name", "switch", serial="serial"),
        GameIdentity("g", "Name", "switch"),
    ]
    assert [dispatcher._lookup_key(value) for value in identities] == [
        "md-five",
        "tid:tid",
        "serial:serial",
        "name:switch:name",
    ]
    assert _kind_extension("hero") == ".jpg"
    assert _kind_extension("unknown") == ".png"

    with pytest.raises(SteamZeroError):
        dispatcher._download_and_validate(
            MediaCandidate(
                url="https://example.invalid",
                media_kind="boxart",
                provider="missing",
                confidence=1,
            )
        )


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("60FPS", "performance"),
        ("1080p graphics", "graphics"),
        ("ultrawide 21by9", "ultrawide"),
        ("gameplay qol", "gameplay"),
        ("bug fix patch", "patch"),
        ("cosmetic", "other"),
    ],
)
def test_semd_catalog_and_mod_classification(
    monkeypatch: pytest.MonkeyPatch, name: str, expected: str
) -> None:
    assert _guess_mod_type_semd(name) == expected
    root = json.dumps(
        [
            {"name": "0100abcd00000000", "type": "dir"},
            {"name": "invalid", "type": "dir"},
            {"name": "0100abcd00000001", "type": "file"},
        ]
    ).encode()
    mods = json.dumps(
        [
            {"name": "60FPS patch", "download_url": "https://example.invalid/mod"},
            {"name": "Fallback URL", "download_url": None},
        ]
    ).encode()

    def urlopen(request: object, timeout: int = 15) -> _Response:
        del timeout
        url = getattr(request, "full_url", str(request))
        return _Response(mods if url.endswith("0100abcd00000000") else root)

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    source = SemdSource()
    assert source.refresh_catalog() == 2
    assert source.search_by_title_id("0100abcd00000000")
    assert source.search_by_build_id("0100abcd00000000", "none") == []
    assert source._local_cache[1].identity.source_url.startswith("https://github.com/")

    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_k: _Response(b"{broken"))
    assert SemdSource().refresh_catalog() == 0
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("offline")),
    )
    assert SemdSource().refresh_catalog() == 0

    source = SemdSource()
    monkeypatch.setattr(source, "_list_title_id_dirs", lambda: ["0100abcd00000000"])
    monkeypatch.setattr(
        source,
        "_fetch_mods_for_title",
        lambda _tid: (_ for _ in ()).throw(RuntimeError("fixture")),
    )
    assert source.refresh_catalog() == 0
