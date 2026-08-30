# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do ProviderRegistry e cadeia de fallback."""

from __future__ import annotations

import pytest

from steamzero.adapters.scraping.registry import _DEFAULT_FALLBACK, ProviderRegistry
from steamzero.core.errors import SteamZeroError
from steamzero.ports import GameIdentity, MediaCandidate


class FakeProvider:
    """Provider fictício para testes."""

    def __init__(self, name: str, kinds: frozenset[str], platforms: frozenset[str]) -> None:
        self._name = name
        self._kinds = kinds
        self._platforms = platforms
        self.calls: list[GameIdentity] = []

    @property
    def name(self) -> str:
        return self._name

    def supported_kinds(self) -> frozenset[str]:
        return self._kinds

    def supported_platforms(self) -> frozenset[str]:
        return self._platforms

    def search(
        self,
        identity: GameIdentity,
        media_kinds: list[str],
        region_priority: list[str] | None = None,
    ) -> list[MediaCandidate]:
        self.calls.append(identity)
        return []


def test_register_and_get() -> None:
    registry = ProviderRegistry()
    provider = FakeProvider("test", frozenset({"boxart"}), frozenset({"switch"}))
    registry.register(provider)
    assert registry.get("test") is provider


def test_get_unknown_raises() -> None:
    registry = ProviderRegistry()
    with pytest.raises(SteamZeroError):
        registry.get("nonexistent")


def test_list_providers() -> None:
    registry = ProviderRegistry()
    registry.register(FakeProvider("a", frozenset(), frozenset()))
    registry.register(FakeProvider("b", frozenset(), frozenset()))
    assert registry.list_providers() == frozenset({"a", "b"})


def test_providers_for_kind_respects_fallback_order() -> None:
    registry = ProviderRegistry()
    a = FakeProvider("a", frozenset({"boxart"}), frozenset({"switch"}))
    b = FakeProvider("b", frozenset({"boxart"}), frozenset({"switch"}))
    c = FakeProvider("c", frozenset({"boxart"}), frozenset({"switch"}))
    registry.register(a)
    registry.register(b)
    registry.register(c)
    registry.fallback_order["boxart"] = ["c", "a", "b"]
    result = registry.providers_for_kind("boxart")
    assert [p.name for p in result] == ["c", "a", "b"]


def test_providers_for_kind_filters_unsupported() -> None:
    registry = ProviderRegistry()
    a = FakeProvider("a", frozenset({"boxart"}), frozenset({"switch"}))
    b = FakeProvider("b", frozenset({"screenshot"}), frozenset({"switch"}))
    registry.register(a)
    registry.register(b)
    registry.fallback_order["boxart"] = ["a", "b"]
    result = registry.providers_for_kind("boxart")
    assert [p.name for p in result] == ["a"]


def test_search_best_skips_provider_outside_declared_platform() -> None:
    registry = ProviderRegistry()
    unsupported = FakeProvider("switch-only", frozenset({"boxart"}), frozenset({"switch"}))
    supported = FakeProvider("psx", frozenset({"boxart"}), frozenset({"playstation"}))
    registry.register(unsupported)
    registry.register(supported)
    registry.fallback_order["boxart"] = ["switch-only", "psx"]

    result = registry.search_best(
        GameIdentity(game_id="g1", title="Test", platform_slug="playstation"), "boxart"
    )

    assert result is None
    assert unsupported.calls == []
    assert [call.platform_slug for call in supported.calls] == ["playstation"]


def test_search_best_preserves_fallback_when_no_provider_declares_platform() -> None:
    registry = ProviderRegistry()
    legacy = FakeProvider("legacy", frozenset({"boxart"}), frozenset({"switch"}))
    registry.register(legacy)

    registry.search_best(
        GameIdentity(game_id="g1", title="Test", platform_slug="new-platform"), "boxart"
    )

    assert [call.platform_slug for call in legacy.calls] == ["new-platform"]


def test_search_best_returns_first_match() -> None:
    registry = ProviderRegistry()

    class FirstProvider:
        @property
        def name(self) -> str:
            return "first"

        def supported_kinds(self) -> frozenset[str]:
            return frozenset({"boxart"})

        def supported_platforms(self) -> frozenset[str]:
            return frozenset({"switch"})

        def search(self, identity, media_kinds, region_priority=None):
            return [
                MediaCandidate(
                    url="https://example.com/a.png",
                    media_kind="boxart",
                    provider="first",
                    confidence=0.9,
                )
            ]

    class SecondProvider:
        @property
        def name(self) -> str:
            return "second"

        def supported_kinds(self) -> frozenset[str]:
            return frozenset({"boxart"})

        def supported_platforms(self) -> frozenset[str]:
            return frozenset({"switch"})

        def search(self, identity, media_kinds, region_priority=None):
            msg = "should not be called"
            raise AssertionError(msg)

    registry.register(FirstProvider())
    registry.register(SecondProvider())
    identity = GameIdentity(game_id="g1", title="Test", platform_slug="switch")
    result = registry.search_best(identity, "boxart")
    assert result is not None
    assert result.url == "https://example.com/a.png"


def test_search_best_returns_none_when_no_match() -> None:
    registry = ProviderRegistry()

    class EmptyProvider:
        @property
        def name(self) -> str:
            return "empty"

        def supported_kinds(self) -> frozenset[str]:
            return frozenset({"boxart"})

        def supported_platforms(self) -> frozenset[str]:
            return frozenset({"switch"})

        def search(self, identity, media_kinds, region_priority=None):
            return []

    registry.register(EmptyProvider())
    identity = GameIdentity(game_id="g1", title="Test", platform_slug="switch")
    assert registry.search_best(identity, "boxart") is None


def test_search_best_skips_low_confidence() -> None:
    registry = ProviderRegistry()

    class LowConfProvider:
        @property
        def name(self) -> str:
            return "low"

        def supported_kinds(self) -> frozenset[str]:
            return frozenset({"boxart"})

        def supported_platforms(self) -> frozenset[str]:
            return frozenset({"switch"})

        def search(self, identity, media_kinds, region_priority=None):
            return [
                MediaCandidate(
                    url="https://example.com/b.png",
                    media_kind="boxart",
                    provider="low",
                    confidence=0.3,
                )
            ]

    registry.register(LowConfProvider())
    identity = GameIdentity(game_id="g1", title="Test", platform_slug="switch")
    assert registry.search_best(identity, "boxart", min_confidence=0.5) is None


def test_search_all_returns_all_kinds() -> None:
    registry = ProviderRegistry()

    class MultiProvider:
        @property
        def name(self) -> str:
            return "multi"

        def supported_kinds(self) -> frozenset[str]:
            return frozenset({"boxart", "screenshot"})

        def supported_platforms(self) -> frozenset[str]:
            return frozenset({"switch"})

        def search(self, identity, media_kinds, region_priority=None):
            results = []
            for kind in media_kinds:
                results.append(
                    MediaCandidate(
                        url=f"https://example.com/{kind}.png",
                        media_kind=kind,
                        provider="multi",
                        confidence=0.8,
                    )
                )
            return results

    registry.register(MultiProvider())
    identity = GameIdentity(game_id="g1", title="Test", platform_slug="switch")
    result = registry.search_all(identity, ["boxart", "screenshot"])
    assert "boxart" in result
    assert "screenshot" in result


def test_default_fallback_has_key_kinds() -> None:
    assert "boxart" in _DEFAULT_FALLBACK
    assert "screenshot" in _DEFAULT_FALLBACK
    assert "wheel" in _DEFAULT_FALLBACK
    assert "video" in _DEFAULT_FALLBACK
    assert "fanart" in _DEFAULT_FALLBACK
    assert all(len(v) >= 1 for v in _DEFAULT_FALLBACK.values())


# -- isolamento: exceção não-SteamZeroError não derruba o fallback -----------


def test_search_best_survives_non_steamzero_provider_exception() -> None:
    registry = ProviderRegistry()

    class BoomProvider:
        @property
        def name(self) -> str:
            return "boom"

        def supported_kinds(self) -> frozenset[str]:
            return frozenset({"boxart"})

        def supported_platforms(self) -> frozenset[str]:
            return frozenset({"switch"})

        def search(self, identity, media_kinds, region_priority=None):
            raise RuntimeError("vazamento interno")

    class OkProvider:
        @property
        def name(self) -> str:
            return "ok"

        def supported_kinds(self) -> frozenset[str]:
            return frozenset({"boxart"})

        def supported_platforms(self) -> frozenset[str]:
            return frozenset({"switch"})

        def search(self, identity, media_kinds, region_priority=None):
            return [
                MediaCandidate(
                    url="https://example.com/ok.png",
                    media_kind="boxart",
                    provider="ok",
                    confidence=0.9,
                )
            ]

    registry.register(BoomProvider())
    registry.register(OkProvider())
    identity = GameIdentity(game_id="g1", title="Test", platform_slug="switch")
    result = registry.search_best(identity, "boxart")
    assert result is not None
    assert result.provider == "ok"


def test_search_all_survives_non_steamzero_provider_exception() -> None:
    registry = ProviderRegistry()

    class BoomProvider:
        @property
        def name(self) -> str:
            return "boom"

        def supported_kinds(self) -> frozenset[str]:
            return frozenset({"boxart"})

        def supported_platforms(self) -> frozenset[str]:
            return frozenset({"switch"})

        def search(self, identity, media_kinds, region_priority=None):
            raise ValueError("shape inesperado")

    class OkProvider:
        @property
        def name(self) -> str:
            return "ok"

        def supported_kinds(self) -> frozenset[str]:
            return frozenset({"boxart"})

        def supported_platforms(self) -> frozenset[str]:
            return frozenset({"switch"})

        def search(self, identity, media_kinds, region_priority=None):
            return [
                MediaCandidate(
                    url="https://example.com/ok.png",
                    media_kind="boxart",
                    provider="ok",
                    confidence=0.9,
                )
            ]

    registry.register(BoomProvider())
    registry.register(OkProvider())
    identity = GameIdentity(game_id="g1", title="Test", platform_slug="switch")
    result = registry.search_all(identity, ["boxart"])
    assert result["boxart"][0].provider == "ok"


def test_fallback_order_is_deterministic_across_calls() -> None:
    registry = ProviderRegistry()
    names = ["alpha", "beta", "gamma"]
    for name in names:
        registry.register(FakeProvider(name, frozenset({"boxart"}), frozenset({"switch"})))
    registry.fallback_order["boxart"] = ["gamma", "alpha", "beta"]
    first = [p.name for p in registry.providers_for_kind("boxart")]
    for _ in range(5):
        assert [p.name for p in registry.providers_for_kind("boxart")] == first
