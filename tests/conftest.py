# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Defesa em profundidade para impedir testes contra os homes XDG reais."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

_XDG_LAYOUT = {
    "XDG_STATE_HOME": "state",
    "XDG_DATA_HOME": "data",
    "XDG_CONFIG_HOME": "config",
    "XDG_CACHE_HOME": "cache",
    "XDG_RUNTIME_DIR": "runtime",
}
_TEST_ROOT_ENV = "STEAMZERO_TEST_XDG_ROOT"


def _configure_xdg(root: Path) -> None:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    for variable, directory in _XDG_LAYOUT.items():
        target = root / directory
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.chmod(0o700)
        os.environ[variable] = str(target)
    os.environ[_TEST_ROOT_ENV] = str(root)


def _assert_xdg_matches(root: Path) -> None:
    expected_root = root.resolve(strict=True)
    for variable, directory in _XDG_LAYOUT.items():
        value = os.environ.get(variable)
        if value is None:
            raise pytest.UsageError(f"{variable} ausente no ambiente de teste")
        actual = Path(value).resolve(strict=True)
        expected = (expected_root / directory).resolve(strict=True)
        if actual != expected:
            raise pytest.UsageError(
                f"{variable} escapa do isolamento: esperado {expected}, recebido {actual}"
            )


@pytest.fixture(scope="session", autouse=True)
def isolated_xdg_root() -> Iterator[Path]:
    """Mantém os cinco homes isolados até quando pytest é chamado diretamente."""
    existing = os.environ.get(_TEST_ROOT_ENV)
    if existing is not None:
        root = Path(existing)
        _assert_xdg_matches(root)
        yield root
        return

    original = {variable: os.environ.get(variable) for variable in (*_XDG_LAYOUT, _TEST_ROOT_ENV)}
    with tempfile.TemporaryDirectory(prefix="steamzero-pytest-fixture-") as temporary:
        root = Path(temporary)
        _configure_xdg(root)
        _assert_xdg_matches(root)
        try:
            yield root
        finally:
            for variable, value in original.items():
                if value is None:
                    os.environ.pop(variable, None)
                else:
                    os.environ[variable] = value


@pytest.fixture(autouse=True)
def enforce_xdg_for_each_test(isolated_xdg_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Restaura os cinco homes após qualquer teste que altere ``os.environ``."""
    for variable, directory in _XDG_LAYOUT.items():
        monkeypatch.setenv(variable, str(isolated_xdg_root / directory))
    monkeypatch.setenv(_TEST_ROOT_ENV, str(isolated_xdg_root))
