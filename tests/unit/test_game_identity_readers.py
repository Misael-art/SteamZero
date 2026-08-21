# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Onda 1: leitura de identidade por plataforma (adapters/discovery)."""

from __future__ import annotations

import zlib
from pathlib import Path

import pytest

from steamzero.adapters.discovery.format_parsers import read_game_identity
from steamzero.core import fs
from steamzero.domain.game_identity import IdentityScheme

# --- Fixtures sintéticas ----------------------------------------------------

# Layout determinístico: setor 16 = PVD, setor 17 = diretório raiz,
# setores 18+ = arquivos na ordem declarada (e blocos de subdiretórios).


def _iso9660_pvd(volume_id: bytes, root_extent: int = 17, root_size: int = 2048) -> bytes:
    pvd = bytearray(2048)
    pvd[0] = 1  # tipo: PVD
    pvd[1:6] = b"CD001"
    pvd[6] = 1
    pvd[0x20 : 0x20 + len(volume_id)] = volume_id
    # registro do diretório raiz em 156 (0x9C)
    rec = bytearray(34)
    rec[0] = 34
    rec[2:10] = root_extent.to_bytes(8, "little")
    rec[10:18] = root_size.to_bytes(8, "little")
    rec[25] = 0x02  # diretório
    rec[32] = 1
    rec[33] = 0x00
    pvd[0x9C : 0x9C + 34] = rec
    return bytes(pvd)


def _dir_record(name: str, flags: int, extent: int, size: int) -> bytes:
    raw = name.encode("ascii")
    padded = raw + (b"\x00" if len(raw) % 2 == 0 else b"")
    record = bytearray(34 + len(padded))
    record[0] = 34 + len(padded)
    record[2:10] = extent.to_bytes(8, "little")
    record[10:18] = size.to_bytes(8, "little")
    record[25] = flags
    record[32] = len(raw)
    record[33 : 33 + len(raw)] = raw
    return bytes(record)


def _dir_block(entries: bytes, *, size: int | None = None) -> bytes:
    block = entries + b"\x00" * ((2048 - len(entries) % 2048) % 2048)
    return block if size is None else block[:size]


def _pad_sector(data: bytes) -> bytes:
    return data + b"\x00" * ((2048 - len(data) % 2048) % 2048)


def _iso_image(volume_id: bytes, files: list[tuple[str, bytes, int]]) -> bytes:
    """Monta ISO9660 sintético: arquivos na raiz (setores 18+), subdiretório
    opcional via flag 0x02 (bloco próprio de um setor)."""
    image = bytearray(0x8000)  # setores 0..15
    image[0x8000:0x8800] = _iso9660_pvd(volume_id)
    entries = _dir_record(".", 0x02, 17, 2048) + _dir_record("..", 0x02, 17, 2048)
    current = 18
    sub_blocks: list[tuple[str, bytes]] = []
    for name, data, flags in files:
        if flags & 0x02:
            payload = _dir_block(
                _dir_record(".", 0x02, current, 2048) + _dir_record("..", 0x02, current, 2048)
            )
            sub_blocks.append((name, payload))
            entries += _dir_record(name, flags, current, len(payload))
            current += (len(payload) + 2047) // 2048
        else:
            entries += _dir_record(name, flags, current, len(data))
            current += (len(data) + 2047) // 2048
    root_dir = entries + b"\x00" * ((2048 - len(entries) % 2048) % 2048)
    image += root_dir
    for _name, data in sub_blocks:
        image += data
    for _name, data, flags in files:
        if flags & 0x02:
            continue
        image += _pad_sector(data)
    image += b"\x00" * 2048
    return bytes(image)


class _MemoryReader:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def __call__(self, offset: int, length: int) -> bytes:
        return self._data[offset : offset + length]


def _iso_image_nested(
    volume_id: bytes, subdir: str, subdir_files: list[tuple[str, bytes]]
) -> bytes:
    """ISO com um subdiretório ``subdir`` contendo ``subdir_files``."""
    image = bytearray(0x8000)
    image[0x8000:0x8800] = _iso9660_pvd(volume_id)
    sub_extent = 18
    next_extent = sub_extent + 1
    sub_entries = _dir_record(".", 0x02, sub_extent, 2048) + _dir_record("..", 0x02, 17, 2048)
    for name, data in subdir_files:
        sub_entries += _dir_record(name, 0, next_extent, len(data))
        next_extent += (len(data) + 2047) // 2048
    sub_block = _dir_block(sub_entries)
    root_entries = (
        _dir_record(".", 0x02, 17, 2048)
        + _dir_record("..", 0x02, 17, 2048)
        + _dir_record(subdir, 0x02, sub_extent, len(sub_block))
    )
    parent = _dir_block(root_entries)
    image += parent
    image += sub_block
    for _name, data in subdir_files:
        image += _pad_sector(data)
    image += b"\x00" * 2048
    return bytes(image)


# --- PS1 / PS2 --------------------------------------------------------------


def test_ps1_iso_serial_from_pvd() -> None:
    rom = _iso_image(b"SLUS_005.55", [])
    identity, diagnosis = read_game_identity(
        Path("/roms/playstation/x.iso"),
        platform="playstation",
        read_at=_MemoryReader(rom),
    )
    assert diagnosis == "pvd-serial"
    assert identity is not None
    assert identity.scheme is IdentityScheme.PSX_SERIAL
    assert identity.value == "SLUS_005.55"


def test_ps2_iso_serial_from_pvd() -> None:
    rom = _iso_image(b"SLUS-20152", [])
    identity, diagnosis = read_game_identity(
        Path("/roms/ps2/x.iso"),
        platform="playstation-2",
        read_at=_MemoryReader(rom),
    )
    assert diagnosis == "pvd-serial"
    assert identity is not None
    assert identity.scheme is IdentityScheme.PS2_SERIAL


def test_ps2_elf_crc32_fallback() -> None:
    elf = b"\x7fELF" + b"\x00" * 100 + b"payload"
    cnf = b"BOOT2 = cdrom0:\\SLUS_201.52\\SLUS_201.52_0.ELF"
    rom = _iso_image(
        b"SOME PS2 GAME TITLE",
        [("SYSTEM.CNF", cnf, 0), ("SLUS_201.52_0.ELF", elf, 0)],
    )
    identity, diagnosis = read_game_identity(
        Path("/roms/ps2/x.iso"),
        platform="playstation-2",
        read_at=_MemoryReader(rom),
    )
    # serial do PVD inexistente -> CRC32 do ELF
    assert diagnosis == "elf-crc32"
    assert identity is not None
    assert identity.scheme is IdentityScheme.PS2_ELF_CRC32
    assert identity.value == format(zlib.crc32(elf) & 0xFFFFFFFF, "08X")


def test_ps2_no_cnf_no_serial_unknown() -> None:
    rom = _iso_image(b"NO SERIAL HERE", [])
    identity, diagnosis = read_game_identity(
        Path("/roms/ps2/x.iso"),
        platform="playstation-2",
        read_at=_MemoryReader(rom),
    )
    assert identity is None
    assert diagnosis == "pvd-no-serial"


def test_ps1_not_iso9660_is_unknown() -> None:
    identity, diagnosis = read_game_identity(
        Path("/roms/ps1/x.bin"),
        platform="playstation",
        read_at=_MemoryReader(b"Q\x00" * 0x9000),
    )
    assert identity is None
    assert diagnosis == "not-iso9660"


def test_truncated_rom_is_unknown_not_exception() -> None:
    identity, diagnosis = read_game_identity(
        Path("/roms/ps1/x.iso"),
        platform="playstation",
        read_at=_MemoryReader(b"\x00" * 64),
    )
    assert identity is None
    assert diagnosis == "not-iso9660"


# --- GC / Wii ---------------------------------------------------------------

# Magic de disco: Wii em 0x18, GC em 0x1C (mesmos offsets de domain.library).

_GC_HEADER = b"GM8E01" + b"\x00" * 22 + b"\xc2\x33\x9f\x3d\x00\x00\x00\x00"
_WII_HEADER = b"RZDE01" + b"\x00" * 18 + b"\x5d\x1c\x9e\xa3\x00\x00\x00\x00"


@pytest.mark.parametrize(
    ("header", "expected_scheme", "expected_value"),
    [
        (_GC_HEADER, IdentityScheme.GC_GAME_ID, "GM8E01"),
        (_WII_HEADER, IdentityScheme.WII_GAME_ID, "RZDE01"),
    ],
)
def test_gc_wii_disc_header(
    header: bytes, expected_scheme: IdentityScheme, expected_value: str
) -> None:
    identity, diagnosis = read_game_identity(
        Path("/roms/gc/x.iso"),
        platform="nintendo-console",
        read_at=_MemoryReader(header + b"\x00" * 4096),
    )
    assert diagnosis in {"disc-header-magic", "disc-header"}
    assert identity is not None
    assert identity.scheme is expected_scheme
    assert identity.value == expected_value


def test_gc_wii_junk_header_is_unknown() -> None:
    identity, diagnosis = read_game_identity(
        Path("/roms/gc/x.iso"),
        platform="nintendo-console",
        read_at=_MemoryReader(b"!@#$%^" + b"\x00" * 4096),
    )
    assert identity is None
    assert diagnosis == "invalid-disc-id"


def test_gc_wii_truncated_header_is_unknown() -> None:
    identity, diagnosis = read_game_identity(
        Path("/roms/gc/x.iso"),
        platform="nintendo-console",
        read_at=_MemoryReader(b"GM8"),
    )
    assert identity is None
    assert diagnosis == "truncated-header"


# --- PS3 --------------------------------------------------------------------


def test_ps3_sfb_title_id_from_iso() -> None:
    sfb = b"..S" + b"\x00" * 16 + b"BLUS30443" + b"\x00" * 32
    rom = _iso_image(b"BLUS30443", [("PS3_DISC.SFB", sfb, 0)])
    identity, diagnosis = read_game_identity(
        Path("/roms/ps3/x.iso"),
        platform="playstation-3",
        read_at=_MemoryReader(rom),
    )
    assert diagnosis == "sfb-title-id"
    assert identity is not None
    assert identity.scheme is IdentityScheme.PS3_TITLE_ID
    assert identity.value == "BLUS30443"


def test_ps3_iso_without_sfb_is_unknown() -> None:
    rom = _iso_image(b"SOME PS3 GAME", [])
    identity, diagnosis = read_game_identity(
        Path("/roms/ps3/x.iso"),
        platform="playstation-3",
        read_at=_MemoryReader(rom),
    )
    assert identity is None
    assert diagnosis == "no-sfb"


def test_ps3_sfb_found_in_subdirectory() -> None:
    sfb = b"..S" + b"\x00" * 16 + b"BCES00001" + b"\x00" * 32
    rom = _iso_image_nested(b"BCES00001", "PS3_GAME", [("PS3_DISC.SFB", sfb)])
    identity, diagnosis = read_game_identity(
        Path("/roms/ps3/x.iso"),
        platform="playstation-3",
        read_at=_MemoryReader(rom),
    )
    assert diagnosis == "sfb-title-id"
    assert identity is not None
    assert identity.value == "BCES00001"


# --- Wii U ------------------------------------------------------------------


def test_wiiu_sibling_meta_xml(tmp_path: Path) -> None:
    rom = tmp_path / "game.wud"
    rom.write_bytes(b"\x00" * 4096)
    (tmp_path / "meta.xml").write_text("<meta><product_id>WUPPAYME</product_id></meta>")
    identity, diagnosis = read_game_identity(rom, platform="wii-u")
    assert diagnosis == "meta-xml-product-id"
    assert identity is not None
    assert identity.scheme is IdentityScheme.WIIU_PRODUCT_ID


def test_wiiu_without_meta_xml_is_unknown(tmp_path: Path) -> None:
    rom = tmp_path / "game.wud"
    rom.write_bytes(b"\x00" * 4096)
    identity, diagnosis = read_game_identity(rom, platform="wii-u")
    assert identity is None
    assert diagnosis == "no-meta-xml"


# --- Degradação -------------------------------------------------------------


@pytest.mark.parametrize(
    ("suffix", "diagnosis"),
    [(".rvz", "compressed-format"), (".chd", "compressed-format"), (".zip", "compressed-format")],
)
def test_compressed_formats_degrade_with_diagnosis(
    tmp_path: Path, suffix: str, diagnosis: str
) -> None:
    rom = tmp_path / f"game{suffix}"
    rom.write_bytes(b"\x00" * 512)
    identity, found = read_game_identity(rom, platform="playstation")
    assert identity is None
    assert found == diagnosis


def test_no_platform_is_unknown() -> None:
    identity, diagnosis = read_game_identity(Path("/roms/x.iso"), platform=None)
    assert identity is None
    assert diagnosis == "no-platform"


def test_unknown_platform_degrades() -> None:
    identity, diagnosis = read_game_identity(
        Path("/roms/snes/x.sfc"),
        platform="snes",
        read_at=_MemoryReader(b"\x00" * 4096),
    )
    assert identity is None
    assert diagnosis == "no-reader"


def test_missing_file_is_unknown_not_exception(tmp_path: Path) -> None:
    identity, diagnosis = read_game_identity(
        tmp_path / "not-there.iso",
        platform="playstation",
    )
    assert identity is None
    assert diagnosis in {"read-failed", "not-iso9660"}


def test_real_fs_read_at_reader(tmp_path: Path) -> None:
    rom = _iso_image(b"SLUS_005.55", [])
    path = tmp_path / "real.iso"
    fs.write_atomic(path, rom)
    identity, diagnosis = read_game_identity(path, platform="playstation")
    assert diagnosis == "pvd-serial"
    assert identity is not None
    assert identity.value == "SLUS_005.55"


def test_symlink_read_is_refused(tmp_path: Path) -> None:
    rom = _iso_image(b"SLUS_005.55", [])
    target = tmp_path / "target.iso"
    fs.write_atomic(target, rom)
    link = tmp_path / "link.iso"
    fs.symlink_atomic(target, link)
    identity, diagnosis = read_game_identity(link, platform="playstation")
    assert identity is None
    assert diagnosis == "read-failed"
