# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Leitura somente leitura do tipo de app no ``appinfo.vdf`` do Steam."""

from __future__ import annotations

import struct
from pathlib import Path

_MAGIC_V29 = 0x07564429
_HEADER_SIZE = 16
_ENTRY_METADATA_SIZE = 60
_NESTED, _STRING, _INT32, _UINT64, _END = 0x00, 0x01, 0x02, 0x07, 0x08

# ``appmanifest_*.acf`` não distingue jogos de ferramentas. ``appinfo.vdf``
# declara o tipo; só estes tipos chegam à grade do usuário.
PLAYABLE_APP_TYPES = frozenset({"game", "demo"})


def app_types(path: Path | None = None) -> dict[str, str]:
    """Retorna ``{appid: tipo}``, ou vazio quando o cache não é legível."""
    source = path if path is not None else default_appinfo_path()
    try:
        blob = source.read_bytes()
        return _parse(blob)
    except (OSError, struct.error, ValueError, IndexError):
        return {}


def default_appinfo_path() -> Path:
    return Path.home() / ".local/share/Steam/appcache/appinfo.vdf"


def _parse(blob: bytes) -> dict[str, str]:
    magic = struct.unpack_from("<I", blob, 0)[0]
    if magic != _MAGIC_V29:
        return {}
    table_offset = struct.unpack_from("<q", blob, 8)[0]
    if not 0 < table_offset <= len(blob) - 4:
        return {}
    keys = _string_table(blob, table_offset)

    types: dict[str, str] = {}
    cursor = _HEADER_SIZE
    while cursor + 8 <= table_offset:
        app_id, size = struct.unpack_from("<II", blob, cursor)
        if app_id == 0:
            break
        entry_end = cursor + 8 + size
        if not cursor < entry_end <= table_offset:
            break
        declared = _entry_type(blob, cursor + 8 + _ENTRY_METADATA_SIZE, entry_end, keys)
        if declared:
            types[str(app_id)] = declared
        cursor = entry_end
    return types


def _string_table(blob: bytes, offset: int) -> list[str]:
    count = struct.unpack_from("<I", blob, offset)[0]
    keys: list[str] = []
    cursor = offset + 4
    for _ in range(count):
        end = blob.index(b"\x00", cursor)
        keys.append(blob[cursor:end].decode("utf-8", "replace"))
        cursor = end + 1
    return keys


def _entry_type(blob: bytes, cursor: int, end: int, keys: list[str]) -> str:
    path: list[str] = []
    while cursor < end:
        marker = blob[cursor]
        cursor += 1
        if marker == _END:
            if not path:
                break
            path.pop()
            continue
        if cursor + 4 > end:
            break
        key_index = struct.unpack_from("<I", blob, cursor)[0]
        cursor += 4
        key = keys[key_index] if key_index < len(keys) else ""
        if marker == _NESTED:
            path.append(key)
        elif marker == _STRING:
            terminator = blob.index(b"\x00", cursor)
            value = blob[cursor:terminator].decode("utf-8", "replace")
            cursor = terminator + 1
            if key == "type" and path[-1:] == ["common"]:
                return value.strip().lower()
        elif marker == _INT32:
            cursor += 4
        elif marker == _UINT64:
            cursor += 8
        else:
            break
    return ""
