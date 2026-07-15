# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Extração segura de arquivos compactados (PATH-SAFETY §3, FM-14, FI-16/17/18).

Defesas (todas verificadas contando bytes REAIS, não cabeçalhos que podem mentir):
- traversal / absoluto / NUL / symlink em entrada  -> E-CONTENT-UNSAFE-PATH;
- zip bomb (entrada ou total acima do teto) / contagem / profundidade excessiva
  -> E-CONTENT-UNSAFE-ARCHIVE.

Toda materialização vai para ``staging/<opId>/`` via core.fs (nunca fora). O
chamador (Library import) coloca o arquivo suspeito em quarentena — aqui só
validamos e extraímos confinadamente, nunca parcialmente fora do staging (AC-LB-03).
"""

from __future__ import annotations

import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from steamzero.core import fs
from steamzero.core.errors import SteamZeroError

_CHUNK = 1 << 16


@dataclass(frozen=True)
class SafeZipLimits:
    max_entries: int = 10_000
    max_total_bytes: int = 2 * 1024**3  # 2 GiB
    max_entry_bytes: int = 1024**3  # 1 GiB
    max_depth: int = 16
    max_ratio: int = 200  # descomprimido / comprimido


DEFAULT_LIMITS = SafeZipLimits()


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _read_capped(src: IO[bytes], cap: int) -> bytes:
    """Lê o stream com teto rígido; estoura => E-CONTENT-UNSAFE-ARCHIVE (bomb)."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = src.read(_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > cap:
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-ARCHIVE", detail=f"entrada excede o teto de {cap} bytes"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def extract_safe(
    zip_path: Path, operation_id: str, *, limits: SafeZipLimits = DEFAULT_LIMITS
) -> list[Path]:
    """Valida e extrai ``zip_path`` para ``staging/<opId>/``. Retorna paths extraídos."""
    if not zipfile.is_zipfile(zip_path):
        raise SteamZeroError("E-CONTENT-UNSAFE-ARCHIVE", detail="não é um zip válido")
    extracted: list[Path] = []
    total = 0
    compressed_total = 0
    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        if len(infos) > limits.max_entries:
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-ARCHIVE", detail=f"contagem de entradas > {limits.max_entries}"
            )
        for info in infos:
            name = info.filename
            if name.endswith("/"):
                continue  # diretório: staging cria conforme necessário
            if _is_symlink(info):
                raise SteamZeroError(
                    "E-CONTENT-UNSAFE-PATH", detail=f"symlink em archive: {name!r}"
                )
            rel = fs.validate_relative_entry(name)  # traversal/NUL/absoluto
            if len(rel.parts) > limits.max_depth:
                raise SteamZeroError(
                    "E-CONTENT-UNSAFE-ARCHIVE", detail=f"profundidade > {limits.max_depth}"
                )
            with zf.open(info) as src:
                data = _read_capped(src, limits.max_entry_bytes)
            total += len(data)
            compressed_total += info.compress_size
            if total > limits.max_total_bytes:
                raise SteamZeroError(
                    "E-CONTENT-UNSAFE-ARCHIVE", detail=f"total > {limits.max_total_bytes} bytes"
                )
            extracted.append(fs.stage_bytes(operation_id, str(rel), data))
    if compressed_total > 0 and total > limits.max_ratio * compressed_total:
        raise SteamZeroError(
            "E-CONTENT-UNSAFE-ARCHIVE", detail=f"razão de expansão > {limits.max_ratio}"
        )
    return extracted
