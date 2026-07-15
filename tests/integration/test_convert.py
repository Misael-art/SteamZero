# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""RT-06: conversão de ROM — original intacto sob falha/timeout/ENOSPC (AC-LB-02)."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.core import fs, paths
from steamzero.core.errors import SteamZeroError
from steamzero.domain.convert import ConversionManager, ConversionTimeout


class FakeConverter:
    def __init__(self, *, mode: str = "ok") -> None:
        self.mode = mode
        self.called = False

    def convert(self, src: Path, dst: Path, target_format: str) -> bool:
        self.called = True
        if self.mode == "timeout":
            raise ConversionTimeout("ferramenta travou")
        if self.mode == "fail":
            return False  # sem saída
        if self.mode == "empty":
            fs.write_atomic(dst, b"")
            return True
        fs.write_atomic(dst, b"converted:" + src.read_bytes())
        return True


@pytest.fixture
def src(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    fs.ensure_state_layout()
    rom = tmp_path / "Game.iso"
    fs.write_atomic(rom, b"original-dump-bytes")
    return rom


@pytest.mark.rt
def test_convert_success_source_intact(src: Path) -> None:
    before = fs.hash_file(src)
    result = ConversionManager(FakeConverter()).convert(src, "chd")
    assert result.dest.exists()
    assert result.dest.read_bytes() == b"converted:original-dump-bytes"
    # AC-LB-02: original mantido (até commit) e intacto
    assert src.exists()
    assert fs.hash_file(src) == before
    assert not any(paths.staging_dir().iterdir())  # staging limpo


@pytest.mark.rt
def test_convert_failure_original_intact(src: Path) -> None:
    before = fs.hash_file(src)
    with pytest.raises(SteamZeroError) as ei:
        ConversionManager(FakeConverter(mode="fail")).convert(src, "chd")
    assert ei.value.code == "E-CONVERT-FAILED"
    assert fs.hash_file(src) == before  # RT-06: original intacto
    assert not (paths.roms_dir() / "converted").exists()
    assert not any(paths.staging_dir().iterdir())


@pytest.mark.rt
def test_convert_empty_output_fails(src: Path) -> None:
    with pytest.raises(SteamZeroError) as ei:
        ConversionManager(FakeConverter(mode="empty")).convert(src, "chd")
    assert ei.value.code == "E-CONVERT-FAILED"
    assert src.exists()


@pytest.mark.rt
def test_convert_timeout_original_intact(src: Path) -> None:
    before = fs.hash_file(src)
    with pytest.raises(SteamZeroError) as ei:
        ConversionManager(FakeConverter(mode="timeout")).convert(src, "chd")
    assert ei.value.code == "E-CONVERT-TIMEOUT"
    assert fs.hash_file(src) == before
    assert not any(paths.staging_dir().iterdir())


@pytest.mark.rt
def test_convert_enospc_preflight(src: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conv = FakeConverter()
    monkeypatch.setattr(fs, "free_space", lambda _p: 1)
    with pytest.raises(SteamZeroError) as ei:
        ConversionManager(conv).convert(src, "chd")
    assert ei.value.code == "E-STORAGE-SPACE"
    assert conv.called is False  # nem chamou a ferramenta
    assert src.exists()
