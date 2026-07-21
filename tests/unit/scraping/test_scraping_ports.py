# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes dos DTOs e protocolos de scraping."""

from __future__ import annotations

import pytest

from steamzero.ports import GameIdentity, MediaCandidate


def test_game_identity_defaults() -> None:
    identity = GameIdentity(game_id="g1", title="Test", platform_slug="switch")
    assert identity.title_id is None
    assert identity.hashes == {}
    assert identity.region is None
    assert identity.serial is None


def test_game_identity_with_hashes() -> None:
    identity = GameIdentity(
        game_id="g1",
        title="Test",
        platform_slug="switch",
        title_id="0100ABCD12345678",
        hashes={"sha1": "abc123", "md5": "def456"},
        region="us",
        serial="LA-H-ABCDE",
    )
    assert identity.title_id == "0100ABCD12345678"
    assert identity.hashes["sha1"] == "abc123"
    assert identity.hashes["md5"] == "def456"
    assert identity.region == "us"
    assert identity.serial == "LA-H-ABCDE"


def test_game_identity_frozen() -> None:
    identity = GameIdentity(game_id="g1", title="Test", platform_slug="switch")
    with pytest.raises(AttributeError):
        identity.title = "Changed"


def test_media_candidate_defaults() -> None:
    c = MediaCandidate(
        url="https://example.com/art.png",
        media_kind="boxart",
        provider="test",
        confidence=1.0,
    )
    assert c.width is None
    assert c.height is None
    assert c.language is None
    assert c.region is None
    assert c.license == ""
    assert c.attribution == ""
    assert c.hash is None


def test_media_candidate_minimal_required() -> None:
    c = MediaCandidate(
        url="https://example.com/art.png",
        media_kind="boxart",
        provider="test",
        confidence=0.5,
    )
    assert c.url == "https://example.com/art.png"
    assert c.media_kind == "boxart"
    assert c.provider == "test"
    assert c.confidence == 0.5


def test_media_candidate_frozen() -> None:
    c = MediaCandidate(
        url="https://example.com/art.png",
        media_kind="boxart",
        provider="test",
        confidence=1.0,
    )
    with pytest.raises(AttributeError):
        c.url = "https://other.com/art.png"


def test_game_identity_protocol() -> None:
    identity = GameIdentity(
        game_id="g1",
        title="The Legend of Zelda",
        platform_slug="switch",
        title_id="0100ABCD12345678",
        hashes={"sha1": "a" * 40},
    )
    assert len(identity.game_id) > 0
    assert identity.platform_slug == "switch"
    assert "sha1" in identity.hashes
