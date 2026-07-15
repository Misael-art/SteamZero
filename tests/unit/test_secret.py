# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do tipo Secret (SR-13)."""

from __future__ import annotations

from steamzero.core.secret import MASK, Secret


def test_reveal_returns_value() -> None:
    assert Secret("token-abc").reveal() == "token-abc"


def test_repr_and_str_are_masked() -> None:
    s = Secret("token-abc")
    assert "token-abc" not in repr(s)
    assert "token-abc" not in str(s)
    assert str(s) == MASK
    assert repr(s) == f"Secret({MASK!r})"


def test_fstring_does_not_leak() -> None:
    s = Secret("leak-me")
    assert "leak-me" not in f"{s}"
