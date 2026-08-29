# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""RT-06: conversão de ROM — original intacto sob falha/timeout/ENOSPC (AC-LB-02)."""

from __future__ import annotations

import errno
from pathlib import Path

import pytest

from steamzero.core import fs, paths
from steamzero.core.errors import SteamZeroError
from steamzero.domain.convert import (
    ConversionManager,
    ConversionPolicy,
    ConversionTimeout,
    ConvertResult,
)


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
        if self.mode == "mutate-input":
            fs.write_atomic(src, b"converter-corrompeu-a-copia")
            fs.write_atomic(dst, b"converted:unsafe")
            return True
        if self.mode == "error":
            raise OSError(errno.EIO, "falha sintética")
        fs.write_atomic(dst, b"converted:" + src.read_bytes())
        return True


def _optical_policy() -> ConversionPolicy:
    return ConversionPolicy(
        platform_id="test-optical",
        nature="optical",
        formats={"iso": ("iso",), "chd": ("chd",)},
        conversion_targets=("chd",),
        preferred_format="iso",
    )


def _convert(
    converter: FakeConverter, src: Path, target_format: str, *, dest_dir: Path | None = None
) -> ConvertResult:
    return ConversionManager(converter).convert(
        src, target_format, policy=_optical_policy(), dest_dir=dest_dir
    )


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
    result = _convert(FakeConverter(), src, "chd")
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
        _convert(FakeConverter(mode="fail"), src, "chd")
    assert ei.value.code == "E-CONVERT-FAILED"
    assert fs.hash_file(src) == before  # RT-06: original intacto
    assert not (paths.roms_dir() / "converted").exists()
    assert not any(paths.staging_dir().iterdir())


@pytest.mark.rt
def test_convert_empty_output_fails(src: Path) -> None:
    with pytest.raises(SteamZeroError) as ei:
        _convert(FakeConverter(mode="empty"), src, "chd")
    assert ei.value.code == "E-CONVERT-FAILED"
    assert src.exists()


@pytest.mark.rt
def test_convert_timeout_original_intact(src: Path) -> None:
    before = fs.hash_file(src)
    with pytest.raises(SteamZeroError) as ei:
        _convert(FakeConverter(mode="timeout"), src, "chd")
    assert ei.value.code == "E-CONVERT-TIMEOUT"
    assert fs.hash_file(src) == before
    assert not any(paths.staging_dir().iterdir())


@pytest.mark.rt
def test_convert_enospc_preflight(src: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    conv = FakeConverter()
    monkeypatch.setattr(fs, "free_space", lambda _p: 1)
    with pytest.raises(SteamZeroError) as ei:
        _convert(conv, src, "chd")
    assert ei.value.code == "E-STORAGE-SPACE"
    assert conv.called is False  # nem chamou a ferramenta
    assert src.exists()


def test_convert_rejects_format_traversal_before_converter(src: Path) -> None:
    converter = FakeConverter()
    with pytest.raises(SteamZeroError) as error:
        _convert(converter, src, "../../outside")
    assert error.value.code == "E-API-SCHEMA"
    assert converter.called is False
    assert src.read_bytes() == b"original-dump-bytes"


def test_convert_never_overwrites_same_name_or_existing_destination(src: Path) -> None:
    converter = FakeConverter()
    collision = src.parent / "Game.chd"
    fs.write_atomic(collision, b"existing-output")

    with pytest.raises(SteamZeroError) as error:
        _convert(converter, src, "chd", dest_dir=src.parent)

    assert error.value.code == "E-TX-STALE-PLAN"
    assert converter.called is False
    assert src.read_bytes() == b"original-dump-bytes"
    assert collision.read_bytes() == b"existing-output"


def test_convert_rejects_destination_equal_to_original(src: Path) -> None:
    converter = FakeConverter()
    before = fs.hash_file(src)

    with pytest.raises(SteamZeroError) as error:
        _convert(converter, src, "iso", dest_dir=src.parent)

    assert error.value.code == "E-TX-STALE-PLAN"
    assert converter.called is False
    assert fs.hash_file(src) == before


@pytest.mark.rt
def test_converter_only_receives_staged_copy_and_mutation_is_detected(src: Path) -> None:
    before = fs.hash_file(src)

    with pytest.raises(SteamZeroError) as error:
        _convert(FakeConverter(mode="mutate-input"), src, "chd")

    assert error.value.code == "E-TX-STALE-PLAN"
    assert fs.hash_file(src) == before
    assert not (paths.roms_dir() / "converted" / "Game.chd").exists()
    assert not any(paths.staging_dir().iterdir())


@pytest.mark.rt
def test_converter_oserror_is_mapped_and_staging_is_clean(src: Path) -> None:
    before = fs.hash_file(src)

    with pytest.raises(SteamZeroError) as error:
        _convert(FakeConverter(mode="error"), src, "chd")

    assert error.value.code == "E-CONVERT-FAILED"
    assert fs.hash_file(src) == before
    assert not any(paths.staging_dir().iterdir())


@pytest.mark.rt
def test_publish_enospc_removes_partial_and_preserves_original(
    src: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = fs.hash_file(src)

    def fail_publish(_source: Path, _destination: Path, **_kwargs: object) -> None:
        raise OSError(errno.ENOSPC, "sem espaço")

    original_copy = fs.copy_file_atomic
    calls = 0

    def copy_with_failure(source: Path, destination: Path, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            original_copy(source, destination, **kwargs)  # type: ignore[arg-type]
            return
        fail_publish(source, destination, **kwargs)

    monkeypatch.setattr(fs, "copy_file_atomic", copy_with_failure)
    with pytest.raises(SteamZeroError) as error:
        _convert(FakeConverter(), src, "chd")

    assert error.value.code == "E-STORAGE-SPACE"
    assert fs.hash_file(src) == before
    assert not (paths.roms_dir() / "converted" / "Game.chd").exists()
    assert not any(paths.staging_dir().iterdir())


def test_convert_rejects_target_not_declared_by_platform_before_converter(
    src: Path,
) -> None:
    nes = src.with_name("Game.nes")
    fs.write_atomic(nes, b"original-nes-bytes")
    converter = FakeConverter()
    policy = ConversionPolicy(
        platform_id="nes-famicom",
        nature="cartridge",
        formats={"nes": ("nes",), "fds": ("fds",)},
        conversion_targets=(),
    )

    with pytest.raises(SteamZeroError) as error:
        ConversionManager(converter).convert(nes, "chd", policy=policy)

    assert error.value.code == "E-CONTENT-UNSUPPORTED"
    assert "nes-famicom (cartridge) não declara conversão nes->chd" in error.value.detail
    assert converter.called is False
    assert nes.read_bytes() == b"original-nes-bytes"
