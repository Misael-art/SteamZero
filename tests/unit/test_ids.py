# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes de core.ids: ULID e slugs."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from steamzero.core import ids


def test_ulid_format_and_length() -> None:
    u = ids.new_ulid()
    assert len(u) == 26
    assert ids.is_ulid(u)
    assert ids.ULID_RE.match(u)


def test_ulid_excludes_ambiguous_letters() -> None:
    # Crockford base32 exclui I, L, O, U — 200 amostras não devem conter nenhum.
    for _ in range(200):
        u = ids.new_ulid()
        assert not (set(u) & set("ILOU"))


def test_ulid_monotonic_across_time() -> None:
    a = ids.new_ulid(ts_ms=1_000)
    b = ids.new_ulid(ts_ms=2_000)
    assert a < b  # ordenação lexicográfica reflete o tempo


def test_ulid_unique_same_ms() -> None:
    ts = 1_700_000_000_000
    seen = {ids.new_ulid(ts_ms=ts) for _ in range(1000)}
    assert len(seen) == 1000  # aleatoriedade de 80 bits evita colisão


def test_ulid_rejects_out_of_range_timestamp() -> None:
    with pytest.raises(ValueError):
        ids.new_ulid(ts_ms=1 << 48)


@pytest.mark.parametrize("good", ["a", "psx", "duck-station", "rp2", "a" * 63])
def test_valid_slugs(good: str) -> None:
    assert ids.is_slug(good)
    assert ids.require_slug(good) == good


@pytest.mark.parametrize("bad", ["", "-x", "A", "psx_1", "a" * 64, "com espaço", "../x", "x.y"])
def test_invalid_slugs(bad: str) -> None:
    assert not ids.is_slug(bad)
    with pytest.raises(ValueError):
        ids.require_slug(bad)


@given(st.integers(min_value=0, max_value=(1 << 48) - 1))
def test_ulid_property_always_valid(ts: int) -> None:
    assert ids.is_ulid(ids.new_ulid(ts_ms=ts))
