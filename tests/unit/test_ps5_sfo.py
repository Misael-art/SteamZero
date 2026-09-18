# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Fixtures mínimas para identidade PS5 via param.sfo."""

from __future__ import annotations

import struct
from pathlib import Path

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
