# SPDX-License-Identifier: GPL-3.0-or-later
"""Testes para dispatch flatpak no ToolRegistry (flatpak_which)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from steamzero.adapters.converters import flatpak_which


def test_falls_back_to_shutil_which() -> None:
    resolved = shutil.which("python3")
    assert resolved is not None
    assert flatpak_which("python3") == resolved


def test_returns_none_for_nonexistent_tool() -> None:
    assert flatpak_which("this-tool-definitely-does-not-exist-99999") is None


def test_resolves_via_flatpak_export_dir(tmp_path: Path) -> None:
    flatpak_bin = tmp_path / "flatpak-export" / "bin"
    flatpak_bin.mkdir(parents=True)
    tool_path = flatpak_bin / "org.example.Emulator"
    tool_path.write_text("")
    tool_path.chmod(0o755)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "steamzero.adapters.converters._FLATPAK_BIN_DIRS",
            (str(flatpak_bin),),
        )
        resolved = flatpak_which("org.example.Emulator")
        assert resolved is not None
        assert Path(resolved).name == "org.example.Emulator"


def test_prefers_shutil_which_over_flatpak(tmp_path: Path) -> None:
    real_bin = tmp_path / "real" / "bin"
    real_bin.mkdir(parents=True)
    flatpak_bin = tmp_path / "flatpak" / "bin"
    flatpak_bin.mkdir(parents=True)

    real_tool = real_bin / "mytool"
    real_tool.write_text("")
    real_tool.chmod(0o755)
    flatpak_tool = flatpak_bin / "mytool"
    flatpak_tool.write_text("")
    flatpak_tool.chmod(0o755)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("steamzero.adapters.converters._FLATPAK_BIN_DIRS", (str(flatpak_bin),))
        mp.setenv("PATH", f"{real_bin}:{os.environ.get('PATH', '')}")
        resolved = flatpak_which("mytool")
        assert resolved == str(real_tool.resolve())
