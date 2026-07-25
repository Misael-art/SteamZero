# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors

from __future__ import annotations

import pytest

from steamzero import i18n


def test_has_key_returns_true_for_existing_key() -> None:
    assert i18n.has_key("error.E-TX-STALE-PLAN.title")


def test_has_key_returns_false_for_missing_key() -> None:
    assert not i18n.has_key("nonexistent.key")


def test_has_key_with_missing_locale_falls_back_to_empty() -> None:
    assert not i18n.has_key("any.key", locale="en-US")


def test_t_returns_template_without_params() -> None:
    result = i18n.t("error.E-TX-STALE-PLAN.title")
    assert isinstance(result, str)
    assert result == "Plano desatualizado"


def test_t_raises_key_error_for_missing_key() -> None:
    with pytest.raises(KeyError, match="chave i18n ausente"):
        i18n.t("nonexistent.key")


def test_t_with_params_still_returns_template() -> None:
    result = i18n.t("error.E-TX-STALE-PLAN.title", _ignored="unused")
    assert isinstance(result, str)
    assert result == "Plano desatualizado"


def test_t_with_missing_locale_uses_default() -> None:
    result = i18n.t("error.E-TX-STALE-PLAN.title", locale="en-US")
    assert isinstance(result, str)
    assert result == "Plano desatualizado"


def test_all_keys_includes_error_keys() -> None:
    keys = i18n.all_keys()
    assert "error.E-TX-STALE-PLAN.title" in keys
    assert "error.E-TX-STALE-PLAN.what" in keys
    assert isinstance(keys, frozenset)
