# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Leitor somente leitura da identidade ``sce_sys/param.sfo`` de PS5."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

from steamzero.domain.game_identity import GameIdentity, IdentityScheme

_MAGIC = b"\x00PSF"
_HEADER = struct.Struct("<4s4I")
_INDEX = struct.Struct("<2H3I")
_MAX_SFO_BYTES = 1024 * 1024
_MAX_ENTRIES = 256
_STRING_FORMAT = 0x0204
_TARGET_KEYS = frozenset({"TITLE_ID", "TITLE"})


@dataclass(frozen=True)
class Ps5Sfo:
    title_id: str | None
    title: str | None


def parse_sfo(data: bytes) -> Ps5Sfo | None:
    """Extrai os campos seguros do SFO sem confiar em offsets fora do arquivo."""
    if len(data) > _MAX_SFO_BYTES or len(data) < _HEADER.size:
        return None
    magic, _version, key_offset, data_offset, entry_count = _HEADER.unpack_from(data)
    if magic != _MAGIC or entry_count > _MAX_ENTRIES:
        return None
    table_end = _HEADER.size + entry_count * _INDEX.size
    if (
        table_end > len(data)
        or key_offset < table_end
        or key_offset > len(data)
        or data_offset < key_offset
        or data_offset > len(data)
    ):
        return None
    values: dict[str, str] = {}
    for offset in range(_HEADER.size, table_end, _INDEX.size):
        key_rel, value_format, value_len, value_max, value_rel = _INDEX.unpack_from(data, offset)
        key_start = key_offset + key_rel
        value_start = data_offset + value_rel
        if (
            key_start < key_offset
            or key_start >= data_offset
            or value_start < data_offset
            or value_start > len(data)
            or value_len > value_max
            or value_len > len(data) - value_start
        ):
            return None
        key_end = data.find(b"\x00", key_start, data_offset)
        if key_end < 0:
            return None
        try:
            key = data[key_start:key_end].decode("utf-8", errors="strict")
        except UnicodeError:
            return None
        if key not in _TARGET_KEYS:
            continue
        if value_format != _STRING_FORMAT:
            return None
        try:
            values[key] = (
                data[value_start : value_start + value_len]
                .split(b"\x00", 1)[0]
                .decode("utf-8", errors="strict")
            )
        except UnicodeError:
            return None
    return Ps5Sfo(values.get("TITLE_ID"), values.get("TITLE"))


def read_ps5_identity(executable: Path) -> tuple[GameIdentity | None, str]:
    """Busca ``sce_sys/param.sfo`` acima do executável sem seguir symlinks."""
    for parent in executable.parents:
        if executable.anchor and parent == Path(executable.anchor):
            break
        metadata = parent / "sce_sys" / "param.sfo"
        if not metadata.is_file() or metadata.is_symlink():
            continue
        try:
            data = metadata.read_bytes()
        except OSError:
            return None, "ps5-param-sfo-read-failed"
        parsed = parse_sfo(data)
        if parsed is None:
            return None, "ps5-param-sfo-invalid"
        if parsed.title_id is None:
            return None, "ps5-title-id-missing"
        normalized = parsed.title_id.strip().upper()
        try:
            return GameIdentity("playstation-5", IdentityScheme.PS5_TITLE_ID, normalized), (
                "ps5-param-sfo"
            )
        except ValueError:
            return None, "ps5-title-id-invalid"
    return None, "ps5-param-sfo-missing"
