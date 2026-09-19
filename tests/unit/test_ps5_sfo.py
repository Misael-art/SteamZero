# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Fixtures mínimas para identidade PS5 via param.sfo."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from steamzero.adapters.discovery.ps5_sfo import parse_sfo, read_ps5_identity
from steamzero.domain.game_identity import IdentityScheme


def _sfo(values: dict[str, str]) -> bytes:
    keys = b"".join(key.encode() + b"\x00" for key in values)
    key_offsets: dict[str, int] = {}
    cursor = 0
    for key in values:
        key_offsets[key] = cursor
        cursor += len(key.encode()) + 1
    payload = b"".join(value.encode() + b"\x00" for value in values.values())
    header_size = 20
    index_size = 16 * len(values)
    key_offset = header_size + index_size
    data_offset = key_offset + len(keys)
    entries = []
    data_cursor = 0
    for key, value in values.items():
        encoded = value.encode() + b"\x00"
        entries.append(
            struct.pack("<2H3I", key_offsets[key], 0x0204, len(encoded), len(encoded), data_cursor)
        )
        data_cursor += len(encoded)
    return (
        struct.pack("<4s4I", b"\x00PSF", 0x101, key_offset, data_offset, len(values))
        + b"".join(entries)
        + keys
        + payload
    )


def test_parse_sfo_returns_ps5_title_id() -> None:
    parsed = parse_sfo(_sfo({"TITLE_ID": "PPSA12345_00", "TITLE": "Demo PS5"}))
    assert parsed is not None
    assert parsed.title_id == "PPSA12345_00"


def test_parse_sfo_rejects_overlapping_tables_and_invalid_lengths() -> None:
    overlapping = bytearray(_sfo({"TITLE_ID": "PPSA12345_00"}))
    struct.pack_into("<I", overlapping, 8, 20)
    assert parse_sfo(bytes(overlapping)) is None

    invalid_length = bytearray(_sfo({"TITLE_ID": "PPSA12345_00"}))
    struct.pack_into("<I", invalid_length, 20 + 8, 1)
    assert parse_sfo(bytes(invalid_length)) is None


def test_parse_sfo_rejects_non_string_target_fields() -> None:
    invalid_format = bytearray(_sfo({"TITLE_ID": "PPSA12345_00"}))
    struct.pack_into("<H", invalid_format, 20 + 2, 0x0004)
    assert parse_sfo(bytes(invalid_format)) is None


def test_read_ps5_identity_finds_sce_sys_without_following_symlink(tmp_path: Path) -> None:
    dump = tmp_path / "Game"
    (dump / "sce_sys").mkdir(parents=True)
    (dump / "sce_sys" / "param.sfo").write_bytes(
        _sfo({"TITLE_ID": "PPSA12345_00", "TITLE": "Demo PS5"})
    )
    executable = dump / "eboot.bin"
    executable.write_bytes(b"ELF")

    identity, diagnosis = read_ps5_identity(executable)

    assert identity is not None
    assert identity.scheme is IdentityScheme.PS5_TITLE_ID
    assert identity.value == "PPSA12345_00"
    assert diagnosis == "ps5-param-sfo"


def test_read_ps5_identity_rejects_symlinked_param_sfo(tmp_path: Path) -> None:
    dump = tmp_path / "Game"
    (dump / "sce_sys").mkdir(parents=True)
    outside = tmp_path / "outside-param.sfo"
    outside.write_bytes(_sfo({"TITLE_ID": "PPSA12345_00", "TITLE": "External"}))
    (dump / "sce_sys" / "param.sfo").symlink_to(outside)
    executable = dump / "eboot.bin"
    executable.write_bytes(b"ELF")

    identity, diagnosis = read_ps5_identity(executable)

    assert identity is None
    assert diagnosis == "ps5-param-sfo-missing"


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ({"TITLE": "Sem ID"}, "ps5-title-id-missing"),
        ({"TITLE_ID": "INVALID", "TITLE": "ID inválido"}, "ps5-title-id-invalid"),
    ],
)
def test_read_ps5_identity_reports_unusable_title_id(
    tmp_path: Path, values: dict[str, str], expected: str
) -> None:
    dump = tmp_path / "Game"
    (dump / "sce_sys").mkdir(parents=True)
    (dump / "sce_sys" / "param.sfo").write_bytes(_sfo(values))
    executable = dump / "eboot.bin"
    executable.write_bytes(b"ELF")

    identity, diagnosis = read_ps5_identity(executable)

    assert identity is None
    assert diagnosis == expected


def test_read_ps5_identity_reports_corrupt_sfo(tmp_path: Path) -> None:
    dump = tmp_path / "Game"
    (dump / "sce_sys").mkdir(parents=True)
    (dump / "sce_sys" / "param.sfo").write_bytes(b"not-an-sfo")
    executable = dump / "eboot.bin"
    executable.write_bytes(b"ELF")

    identity, diagnosis = read_ps5_identity(executable)

    assert identity is None
    assert diagnosis == "ps5-param-sfo-invalid"
