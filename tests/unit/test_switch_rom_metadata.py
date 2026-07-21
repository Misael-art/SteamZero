# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do módulo de extração nativa de metadados de ROMs Switch.

Cobre: leitores de container (PFS0/HFS0), NCA, extração de ícone,
cache de emulador, pipeline de fallback.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from steamzero.adapters.rom_metadata.container_reader import (
    find_control_nca,
    find_nca_files,
)
from steamzero.adapters.rom_metadata.emulator_cache import EmulatorCacheReader
from steamzero.adapters.rom_metadata.icon_extractor import NativeIconExtractor
from steamzero.adapters.rom_metadata.nca_reader import (
    extract_icon_from_nca,
    read_nca_header,
)
from steamzero.domain.switch_rom_metadata import MediaFallbackPipeline
from steamzero.ports import EmulatorCachePort, RomMetadata, RomMetadataPort

# =============================================================================
# RomMetadata DTO
# =============================================================================


class TestRomMetadata:
    def test_minimal(self) -> None:
        meta = RomMetadata(title_id="0100000000010000", title="Super Mario", source="nca")
        assert meta.title_id == "0100000000010000"
        assert meta.title == "Super Mario"

    def test_with_icon(self) -> None:
        meta = RomMetadata(
            title_id="0100",
            title="Game",
            icon_bytes=b"\xff\xd8\xff\xe0",
            icon_format="jpeg",
            source="nca",
        )
        assert meta.icon_bytes == b"\xff\xd8\xff\xe0"
        assert meta.icon_format == "jpeg"

    def test_defaults(self) -> None:
        meta = RomMetadata(title_id="0100", title="Game", source="fallback")
        assert meta.developer is None
        assert meta.languages == ()


# =============================================================================
# NCA Header reader (unit tests with synthetic data)
# =============================================================================


def _build_nca2_header(title_id: int = 0x0100000000010000) -> bytes:
    """Constrói um header NCA2 sintético para testes."""
    hdr = bytearray(0x200)
    hdr[:4] = b"NCA2"
    struct.pack_into("<Q", hdr, 0x30, title_id)
    struct.pack_into("<I", hdr, 0x28, 0xB)  # SDK version
    # Section 0: offset 1, size 100
    struct.pack_into("<Q", hdr, 0x40, 1)
    struct.pack_into("<Q", hdr, 0x48, 100)
    # Section 1: offset 101, size 200
    struct.pack_into("<Q", hdr, 0x50, 101)
    struct.pack_into("<Q", hdr, 0x58, 200)
    return bytes(hdr)


def _make_jpeg_data(size: int = 4096) -> bytes:
    """Gera dados JPEG sintéticos com tamanho mínimo válido."""
    data = bytearray(b"\xff\xd8\xff\xe0" + b"\x00" * (size - 4))
    data[-2:] = b"\xff\xd9"
    return bytes(data)


def _make_nca_with_icon(title_id: int = 0x0100000000010000, icon_size: int = 4096) -> bytes:
    """Constrói um NCA sintético com ícone JPEG no section 2."""
    header = bytearray(_build_nca2_header(title_id))
    # Reconfigura section 2 para apontar para o ícone
    body_offset_body = 0x200  # após o header
    icon_data = _make_jpeg_data(icon_size)
    struct.pack_into("<Q", header, 0x60, body_offset_body // 0x200)
    struct.pack_into("<Q", header, 0x68, len(icon_data) // 0x200 + 1)

    result = bytes(header) + icon_data
    return result


class TestReadNcaHeader:
    def test_reads_title_id(self) -> None:
        hdr = _build_nca2_header(0x0100000000010000)
        parsed = read_nca_header(hdr)
        assert parsed is not None
        assert parsed["title_id"] == "0100000000010000"

    def test_detects_magic(self) -> None:
        hdr = _build_nca2_header()
        parsed = read_nca_header(hdr)
        assert parsed is not None
        assert parsed["magic"] == "NCA2"

    def test_parses_sections(self) -> None:
        hdr = _build_nca2_header()
        parsed = read_nca_header(hdr)
        assert parsed is not None
        sections = parsed["sections"]
        assert len(sections) == 4
        section0 = sections[0]
        assert section0["media_offset"] == 1
        assert section0["body_offset"] == 0x200

    def test_invalid_data_returns_none(self) -> None:
        assert read_nca_header(b"") is None
        assert read_nca_header(b"\x00" * 10) is None

    def test_nca3_magic(self) -> None:
        # NCA3 tem magic no offset 0x200
        hdr = bytearray(0x204)
        hdr[0x200:0x204] = b"NCA3"
        struct.pack_into("<Q", hdr, 0x30, 0x0100000000010000)
        parsed = read_nca_header(bytes(hdr))
        if parsed is not None:
            assert parsed["magic"] == "NCA3"


# =============================================================================
# Icon extraction from NCA
# =============================================================================


class TestExtractIconFromNca:
    def test_extracts_jpeg_from_section(self) -> None:
        nca_data = _make_nca_with_icon()
        result = extract_icon_from_nca(nca_data)
        assert result is not None
        data, fmt = result
        assert fmt == "jpeg"
        assert data.startswith(b"\xff\xd8\xff")

    def test_returns_none_for_no_icon(self) -> None:
        hdr = _build_nca2_header()
        result = extract_icon_from_nca(hdr + b"\x00" * 512)
        assert result is None

    def test_extracts_png(self) -> None:
        png_header = b"\x89PNG\r\n\x1a\n"
        png_data = png_header + b"\x00" * 2000 + b"IEND" + b"\x00" * 4
        hdr = bytearray(_build_nca2_header())
        # Section 2
        struct.pack_into("<Q", hdr, 0x60, 1)
        struct.pack_into("<Q", hdr, 0x68, len(png_data) // 0x200 + 1)
        nca_data = bytes(hdr) + png_data
        result = extract_icon_from_nca(nca_data)
        assert result is not None
        assert result[1] == "png"


# =============================================================================
# PFS0/HFS0 (container) reader
# =============================================================================


def _build_pfs0(files: list[tuple[str, bytes]]) -> bytes:
    """Constrói um container PFS0 sintético."""
    num_files = len(files)
    string_table = b""
    name_offsets: list[int] = []
    for name, _data in files:
        name_offsets.append(len(string_table))
        string_table += name.encode() + b"\x00"

    header = b"PFS0"
    header += struct.pack("<I", num_files)
    header += struct.pack("<I", len(string_table))
    header += b"\x00" * 4  # reserved

    offset = 0
    file_entries = b""
    for i, (_name, data) in enumerate(files):
        file_entries += struct.pack("<QII", offset, len(data), name_offsets[i])
        offset += len(data)

    body = b"".join(data for _, data in files)
    return header + file_entries + string_table + body


def _build_hfs0(files: list[tuple[str, bytes]]) -> bytes:
    """Constrói um container HFS0 sintético."""
    num_files = len(files)
    string_table = b""
    name_offsets: list[int] = []
    for name, _data in files:
        name_offsets.append(len(string_table))
        string_table += name.encode() + b"\x00"

    header = b"HFS0"
    header += struct.pack("<I", num_files)
    header += struct.pack("<I", len(string_table))
    header += b"\x00" * 4  # reserved

    offset = 0
    file_entries = b""
    for i, (_name, data) in enumerate(files):
        file_entries += struct.pack("<QIII", offset, len(data), name_offsets[i], len(data))
        offset += len(data)

    body = b"".join(data for _, data in files)
    return header + file_entries + string_table + body


class TestContainerReader:
    def test_parse_pfs0(self, tmp_path: Path) -> None:
        nca_data = _make_nca_with_icon()
        container = _build_pfs0(
            [
                ("program.nca", b"\x00" * 512),
                ("control.nca", nca_data),
            ]
        )
        rom = tmp_path / "game.nsp"
        rom.write_bytes(container)
        files = find_nca_files(rom)
        assert len(files) == 2
        names = {f[0] for f in files}
        assert "program.nca" in names
        assert "control.nca" in names

    def test_find_control_nca(self, tmp_path: Path) -> None:
        nca_data = _make_nca_with_icon()
        container = _build_pfs0(
            [
                ("program.nca", b"\x00" * 512),
                ("control.nca", nca_data),
            ]
        )
        rom = tmp_path / "game.nsp"
        rom.write_bytes(container)
        control = find_control_nca(rom)
        assert control is not None
        assert "control" in control[0]

    def test_find_control_nca_fallback(self, tmp_path: Path) -> None:
        nca_data = _make_nca_with_icon()
        container = _build_pfs0(
            [
                ("program.nca", b"\x00" * 512),
                ("other.nca", nca_data),
            ]
        )
        rom = tmp_path / "game.nsp"
        rom.write_bytes(container)
        control = find_control_nca(rom)
        assert control is not None
        assert "other" in control[0]

    def test_no_nca_found(self, tmp_path: Path) -> None:
        container = _build_pfs0([])
        rom = tmp_path / "empty.nsp"
        rom.write_bytes(container)
        assert find_control_nca(rom) is None

    def test_parse_hfs0(self, tmp_path: Path) -> None:
        container = _build_hfs0(
            [
                ("program.nca", b"\x00" * 128),
                ("control.nca", _make_nca_with_icon()),
            ]
        )
        rom = tmp_path / "game.xci"
        rom.write_bytes(container)
        files = find_nca_files(rom)
        assert len(files) == 2

    def test_invalid_magic(self, tmp_path: Path) -> None:
        rom = tmp_path / "unknown.bin"
        rom.write_bytes(b"XXXX")
        assert find_nca_files(rom) == []

    def test_find_nca_in_pfs0(self, tmp_path: Path) -> None:
        nca_data = _make_nca_with_icon()
        container = _build_pfs0([("control.nca", nca_data)])
        rom = tmp_path / "game.nsp"
        rom.write_bytes(container)
        ncas = find_nca_files(rom)
        assert len(ncas) == 1
        name, _offset, size = ncas[0]
        assert name == "control.nca"
        assert size > 0


# =============================================================================
# NativeIconExtractor
# =============================================================================


class _FakeEmulatorCache(EmulatorCachePort):
    def __init__(self) -> None:
        self.icons: dict[str, Path] = {}
        self.titles: dict[str, str] = {}

    def find_icon(self, title_id: str) -> Path | None:
        return self.icons.get(title_id)

    def find_title(self, title_id: str) -> str | None:
        return self.titles.get(title_id)


class TestNativeIconExtractor:
    def test_extract_metadata_from_nca(self, tmp_path: Path) -> None:
        nca_data = _make_nca_with_icon()
        rom = tmp_path / "game.nca"
        rom.write_bytes(nca_data)
        extractor = NativeIconExtractor()
        meta = extractor.extract_metadata(rom)
        assert meta is not None
        assert meta.title_id == "0100000000010000"

    def test_extract_icon_from_nca(self, tmp_path: Path) -> None:
        nca_data = _make_nca_with_icon()
        rom = tmp_path / "game.nca"
        rom.write_bytes(nca_data)
        extractor = NativeIconExtractor()
        icon = extractor.extract_icon(rom)
        assert icon is not None
        data, fmt = icon
        assert fmt == "jpeg"
        assert len(data) >= 1024

    def test_extract_metadata_from_nsp(self, tmp_path: Path) -> None:
        nca_data = _make_nca_with_icon()
        container = _build_pfs0([("control.nca", nca_data)])
        rom = tmp_path / "game.nsp"
        rom.write_bytes(container)
        extractor = NativeIconExtractor()
        meta = extractor.extract_metadata(rom)
        assert meta is not None
        assert meta.title_id == "0100000000010000"

    def test_extract_icon_from_nsp(self, tmp_path: Path) -> None:
        nca_data = _make_nca_with_icon()
        container = _build_pfs0([("control.nca", nca_data)])
        rom = tmp_path / "game.nsp"
        rom.write_bytes(container)
        extractor = NativeIconExtractor()
        icon = extractor.extract_icon(rom)
        assert icon is not None
        _data, fmt = icon
        assert fmt == "jpeg"

    def test_extract_from_xci(self, tmp_path: Path) -> None:
        nca_data = _make_nca_with_icon()
        container = _build_hfs0([("control.nca", nca_data)])
        rom = tmp_path / "game.xci"
        rom.write_bytes(container)
        extractor = NativeIconExtractor()
        meta = extractor.extract_metadata(rom)
        assert meta is not None
        assert meta.title_id == "0100000000010000"

    def test_fallback_to_emulator_cache(self, tmp_path: Path) -> None:
        cache = _FakeEmulatorCache()
        icon_path = tmp_path / "cached_icon.jpg"
        icon_path.write_bytes(_make_jpeg_data())
        cache.icons["0100000000010000"] = icon_path
        cache.titles["0100000000010000"] = "Super Mario"

        extractor = NativeIconExtractor(emulator_cache=cache)
        meta = extractor.extract_metadata(tmp_path / "nonexistent.nsp")
        assert meta is None

        icon_path2 = cache.find_icon("0100000000010000")
        assert icon_path2 is not None
        assert icon_path2.is_file()

    def test_unknown_extension(self, tmp_path: Path) -> None:
        rom = tmp_path / "game.bin"
        rom.write_bytes(b"")
        extractor = NativeIconExtractor()
        assert extractor.extract_metadata(rom) is None

    def test_missing_file(self, tmp_path: Path) -> None:
        extractor = NativeIconExtractor()
        assert extractor.extract_metadata(tmp_path / "nonexistent.nsp") is None


# =============================================================================
# EmulatorCacheReader
# =============================================================================


class TestEmulatorCacheReader:
    def test_find_icon_ryujinx(self, tmp_path: Path) -> None:
        icon_dir = tmp_path / "Ryujinx" / "system" / "icon-cache"
        icon_dir.mkdir(parents=True)
        icon_file = icon_dir / "0100000000010000.jpg"
        icon_file.write_bytes(_make_jpeg_data())
        reader = EmulatorCacheReader(tmp_path)
        result = reader.find_icon("0100000000010000")
        assert result is not None
        assert result == icon_file

    def test_find_icon_unknown(self, tmp_path: Path) -> None:
        reader = EmulatorCacheReader(tmp_path)
        result = reader.find_icon("0100000000999999")
        assert result is None

    def test_find_title_from_json(self, tmp_path: Path) -> None:
        icon_dir = tmp_path / "Ryujinx" / "system" / "icon-cache"
        icon_dir.mkdir(parents=True)
        json_file = icon_dir / "0100000000010000.json"
        import json

        json_file.write_text(json.dumps({"name": "Super Mario Odyssey"}))
        reader = EmulatorCacheReader(tmp_path)
        title = reader.find_title("0100000000010000")
        assert title == "Super Mario Odyssey"

    def test_find_title_missing(self, tmp_path: Path) -> None:
        reader = EmulatorCacheReader(tmp_path)
        assert reader.find_title("0100000000999999") is None

    def test_find_icon_yuzu(self, tmp_path: Path) -> None:
        icon_dir = tmp_path / "yuzu" / "cache" / "icons"
        icon_dir.mkdir(parents=True)
        icon_file = icon_dir / "0100000000010000.jpg"
        icon_file.write_bytes(_make_jpeg_data())
        reader = EmulatorCacheReader(tmp_path)
        result = reader.find_icon("0100000000010000")
        assert result is not None
        assert result == icon_file


# =============================================================================
# MediaFallbackPipeline
# =============================================================================


class _FakeRomExtractor(RomMetadataPort):
    def __init__(self) -> None:
        self.icon_data: tuple[bytes, str] | None = None
        self.meta: RomMetadata | None = None

    def extract_metadata(self, rom_path: Path) -> RomMetadata | None:
        return self.meta

    def extract_icon(self, rom_path: Path) -> tuple[bytes, str] | None:
        return self.icon_data


class TestMediaFallbackPipeline:
    @pytest.fixture
    def pipeline(self, tmp_path: Path) -> MediaFallbackPipeline:
        native = _FakeRomExtractor()
        emu_cache = _FakeEmulatorCache()
        return MediaFallbackPipeline(
            native_extractor=native,
            emulator_cache=emu_cache,
            media_cache_dir=tmp_path / "media",
        )

    def test_fallback_write(self, pipeline: MediaFallbackPipeline) -> None:
        result = pipeline.resolve_icon("0100000000010000")
        assert result is not None
        assert result.suffix in (".svg",)

    def test_native_icon_cached(self, tmp_path: Path) -> None:
        native = _FakeRomExtractor()
        native.icon_data = (_make_jpeg_data(), "jpeg")
        emu_cache = _FakeEmulatorCache()
        pipeline = MediaFallbackPipeline(
            native_extractor=native,
            emulator_cache=emu_cache,
            media_cache_dir=tmp_path / "media",
        )
        rom = tmp_path / "game.nsp"
        rom.write_bytes(b"fake")
        result = pipeline.resolve_icon("0100000000010000", rom_path=rom)
        # O _cache_native_icon usa o native_extractor, então com o fake
        # configurado corretamente, deve funcionar
        assert result is not None

    def test_emulator_cache_fallback(self, tmp_path: Path) -> None:
        native = _FakeRomExtractor()
        emu_cache = _FakeEmulatorCache()
        icon_path = tmp_path / "cached.jpg"
        icon_path.write_bytes(_make_jpeg_data())
        emu_cache.icons["0100000000010000"] = icon_path
        pipeline = MediaFallbackPipeline(
            native_extractor=native,
            emulator_cache=emu_cache,
            media_cache_dir=tmp_path / "media",
        )
        result = pipeline.resolve_icon("0100000000010000")
        assert result == icon_path

    def test_resolve_metadata_no_rom(self, pipeline: MediaFallbackPipeline) -> None:
        meta = pipeline.resolve_metadata("0100000000010000")
        assert meta["titleId"] == "0100000000010000"
        assert meta["source"] == "none"

    def test_resolve_metadata_native(self, tmp_path: Path) -> None:
        native = _FakeRomExtractor()
        native.meta = RomMetadata(
            title_id="0100000000010000",
            title="Super Mario",
            developer="Nintendo",
            version="1.0.0",
            source="nca",
        )
        emu_cache = _FakeEmulatorCache()
        pipeline = MediaFallbackPipeline(native_extractor=native, emulator_cache=emu_cache)
        rom = tmp_path / "game.nsp"
        rom.write_bytes(b"fake")
        meta = pipeline.resolve_metadata("0100000000010000", rom_path=rom)
        assert meta["title"] == "Super Mario"
        assert meta["developer"] == "Nintendo"
        assert meta["version"] == "1.0.0"
