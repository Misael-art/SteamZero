# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Leitura de containers PFS0 (NSP) e HFS0 (XCI) para extrair NCAs de jogos Switch.

PFS0 é o formato de empacotamento usado por NSP (eShop dumps). HFS0 é o
formato usado por XCI (cartuchos). Ambos contêm arquivos NCA que por sua
vez carregam o jogo, metadados de controle e ícones.
"""

from __future__ import annotations

import logging
import struct
from pathlib import Path
from typing import BinaryIO

from steamzero.core import fs
from steamzero.core.errors import SteamZeroError

_log = logging.getLogger(__name__)

_PFS0_MAGIC = b"PFS0"
_HFS0_MAGIC = b"HFS0"
_NCA3_MAGIC = b"NCA3"
_NCA2_MAGIC = b"NCA2"

# Extensões de arquivo que contêm NCAs
_VALID_NCA_NAMES = frozenset({"program.nca", "control.nca", "main.nca"})
_MAX_CONTAINER_FILES = 10_000
_MAX_STRING_TABLE = 16 * 1024 * 1024
_MAX_IN_MEMORY_NCA = 64 * 1024 * 1024


def find_nca_files(rom_path: Path) -> list[tuple[str, int, int]]:
    """Escaneia um arquivo NSP/XCI e retorna (nome, offset, tamanho) de cada NCA."""
    with open(rom_path, "rb") as f:
        magic = f.read(4)
        f.seek(0)
        if magic == _PFS0_MAGIC:
            return _parse_pfs0(f)
        if magic == _HFS0_MAGIC:
            return _parse_hfs0(f)
    return []


def find_control_nca(rom_path: Path) -> tuple[str, int, int] | None:
    """Localiza o control.nca dentro de um NSP/XCI."""
    ncas = find_nca_files(rom_path)
    for name, offset, size in ncas:
        if "control" in name.lower():
            return (name, offset, size)
    # Fallback: qualquer NCA que não seja program
    for name, offset, size in ncas:
        if "program" not in name.lower():
            return (name, offset, size)
    return None


def _parse_pfs0(f: BinaryIO) -> list[tuple[str, int, int]]:
    """Parseia header PFS0 (NSP)."""
    magic = f.read(4)
    if magic != _PFS0_MAGIC:
        return []
    fixed = f.read(12)
    if len(fixed) != 12:
        return []
    num_files, string_table_size, _reserved = struct.unpack("<II4s", fixed)
    if num_files > _MAX_CONTAINER_FILES or string_table_size > _MAX_STRING_TABLE:
        return []

    entries: list[tuple[int, int, int]] = []
    for _ in range(num_files):
        raw = f.read(16)
        if len(raw) != 16:
            return []
        data = struct.unpack("<QII", raw)
        entries.append(data)

    string_table_offset = f.tell()
    data_offset = string_table_offset + string_table_size
    f.seek(0, 2)
    file_size = f.tell()
    results: list[tuple[str, int, int]] = []
    for offset, size, name_offset_rel in entries:
        if name_offset_rel >= string_table_size:
            continue
        name_offset = string_table_offset + name_offset_rel
        f.seek(name_offset)
        name_bytes = b""
        while len(name_bytes) <= 4096:
            b = f.read(1)
            if b == b"\x00" or not b:
                break
            name_bytes += b
        name = name_bytes.decode("utf-8", errors="replace")
        absolute_offset = data_offset + offset
        if absolute_offset + size <= file_size:
            results.append((name, absolute_offset, size))

    return results


def _parse_hfs0(f: BinaryIO) -> list[tuple[str, int, int]]:
    """Parseia header HFS0 (XCI)."""
    magic = f.read(4)
    if magic != _HFS0_MAGIC:
        return []
    fixed = f.read(12)
    if len(fixed) != 12:
        return []
    num_files, string_table_size, _reserved = struct.unpack("<II4s", fixed)
    if num_files > _MAX_CONTAINER_FILES or string_table_size > _MAX_STRING_TABLE:
        return []

    # HFS0 tem uma estrutura similar ao PFS0
    entries: list[tuple[int, int, int, int]] = []
    for _ in range(num_files):
        raw = f.read(20)
        if len(raw) != 20:
            return []
        data = struct.unpack("<QIII", raw)
        entries.append(data)

    string_table_offset = f.tell()
    data_offset = string_table_offset + string_table_size
    f.seek(0, 2)
    file_size = f.tell()
    results: list[tuple[str, int, int]] = []
    for offset, size, _name_offset, _hashed_size in entries:
        if _name_offset >= string_table_size:
            continue
        name_offset = string_table_offset + _name_offset
        f.seek(name_offset)
        name_bytes = b""
        while len(name_bytes) <= 4096:
            b = f.read(1)
            if b == b"\x00" or not b:
                break
            name_bytes += b
        name = name_bytes.decode("utf-8", errors="replace")
        absolute_offset = data_offset + offset
        if absolute_offset + size <= file_size:
            results.append((name, absolute_offset, size))

    return results


def extract_nca_bytes(rom_path: Path, nca_offset: int, nca_size: int) -> bytes | None:
    """Extrai os bytes crus de um NCA do container."""
    if nca_offset < 0 or nca_size < 0 or nca_size > _MAX_IN_MEMORY_NCA:
        return None
    try:
        with open(rom_path, "rb") as f:
            f.seek(nca_offset)
            return f.read(nca_size)
    except OSError:
        return None


def extract_nca_to_path(rom_path: Path, nca_offset: int, nca_size: int, dest: Path) -> bool:
    """Extrai um NCA em streaming e publica o destino atomicamente."""
    try:
        fs.copy_file_range_atomic(rom_path, dest, offset=nca_offset, length=nca_size)
        return True
    except (OSError, ValueError, SteamZeroError):
        return False
