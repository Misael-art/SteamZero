# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Defesa em profundidade para impedir testes contra os homes XDG reais.

O módulo define as variáveis de ambiente no CARREGAMENTO (antes da coleta)
quando ``STEAMZERO_TEST_XDG_ROOT`` não está presente — ou seja, em invocações
diretas de ``pytest`` sem o runner. O ``atexit`` garante limpeza.
"""

from __future__ import annotations

import atexit
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
_HOME_SUBDIR = "home"
_TEST_ROOT_ENV = "STEAMZERO_TEST_XDG_ROOT"


def _configure_xdg(root: Path) -> None:
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    home_dir = root / _HOME_SUBDIR
    home_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    home_dir.chmod(0o700)
    os.environ["HOME"] = str(home_dir)
    for variable, directory in _XDG_LAYOUT.items():
        target = root / directory
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.chmod(0o700)
        os.environ[variable] = str(target)
    os.environ[_TEST_ROOT_ENV] = str(root)


def _assert_xdg_matches(root: Path) -> None:
    expected_root = root.resolve(strict=True)
    home_val = os.environ.get("HOME")
    if home_val is None:
        raise pytest.UsageError("HOME ausente no ambiente de teste")
    actual_home = Path(home_val).resolve(strict=True)
    expected_home = (expected_root / _HOME_SUBDIR).resolve(strict=True)
    if actual_home != expected_home:
        raise pytest.UsageError(
            f"HOME escapa do isolamento: esperado {expected_home}, recebido {actual_home}"
        )
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


# Isolamento no carregamento do módulo — antes da coleta — para invocações
# diretas de ``pytest`` sem o runner.
_env_cleanup: tempfile.TemporaryDirectory[str] | None = None
if os.environ.get(_TEST_ROOT_ENV) is None:
    _env_cleanup = tmp = tempfile.TemporaryDirectory(prefix="steamzero-conftest-")
    _configure_xdg(Path(tmp.name))
    atexit.register(tmp.cleanup)


@pytest.fixture(scope="session", autouse=True)
def isolated_xdg_root() -> Iterator[Path]:
    """Mantém os cinco homes + HOME isolados até quando pytest é chamado diretamente."""
    existing = os.environ.get(_TEST_ROOT_ENV)
    if existing is not None:
        root = Path(existing)
        _assert_xdg_matches(root)
        yield root
        return

    original = {
        variable: os.environ.get(variable) for variable in ("HOME", *_XDG_LAYOUT, _TEST_ROOT_ENV)
    }
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
    """Restaura os cinco homes + HOME após qualquer teste que altere ``os.environ``."""
    monkeypatch.setenv("HOME", str(isolated_xdg_root / _HOME_SUBDIR))
    for variable, directory in _XDG_LAYOUT.items():
        monkeypatch.setenv(variable, str(isolated_xdg_root / directory))
    monkeypatch.setenv(_TEST_ROOT_ENV, str(isolated_xdg_root))
