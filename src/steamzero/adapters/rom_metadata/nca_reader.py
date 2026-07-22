# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Leitor de cabeçalho NCA (Nintendo Content Archive) e extração de ícone nativo.

O cabeçalho NCA (0x200 bytes) não é criptografado e contém:
- Magic (NCA2 / NCA3)
- Title ID (8 bytes)
- SDK version
- Section table (4 entradas de 0x10 com offset/tamanho)
- Section headers (4 entradas de 0x20)

O ícone do jogo está tipicamente no section 2 (RomFS) do control.nca,
embutido como JPEG. Sem chaves criptográficas, usamos heurística de
byte-scanning para localizar JPEG/PNG no corpo do NCA.
"""

from __future__ import annotations

import logging
import struct
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

NCA_HEADER_SIZE = 0x200
NCA_MAGICS = {b"NCA2", b"NCA3"}

# Marcadores mágicos de imagem
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Tamanho mínimo de imagem em bytes
MIN_IMAGE_SIZE = 1024  # 1KB
MAX_IMAGE_SIZE = 512 * 1024  # 512KB


def read_nca_header(nca_data: bytes) -> dict[str, Any] | None:
    """Parseia o cabeçalho NCA (0x200 bytes) e retorna metadados.

    Retorna dict com magic, title_id, sdk_version, sections, ou None
    se não for um NCA válido.
    """
    if len(nca_data) < NCA_HEADER_SIZE:
        return None
    # O magic está no offset 0x200 no NCA3 mas no início para NCA2
    hdr_magic = nca_data[:4]
    if hdr_magic not in NCA_MAGICS:
        # Tenta ler em offset 0x200 (variação de formato)
        if len(nca_data) >= 0x204:
            hdr_magic = nca_data[0x200:0x204]
            if hdr_magic not in NCA_MAGICS:
                return None
            # NCA3 com magic no final do header
            return _parse_nca3_header(nca_data)
        return None

    # NCA2: magic no início
    return _parse_nca2_header(nca_data)


def _parse_nca2_header(nca_data: bytes) -> dict[str, Any]:
    """Parseia header NCA2."""
    hdr = nca_data[:NCA_HEADER_SIZE]
    title_id = struct.unpack("<Q", hdr[0x30:0x38])[0]
    sdk_version = struct.unpack("<I", hdr[0x28:0x2C])[0]

    # Section table offsets (at 0x40, 4 entries of 0x10)
    sections: list[dict[str, Any]] = []
    for i in range(4):
        off = 0x40 + i * 0x10
        media_offset = struct.unpack("<Q", hdr[off : off + 8])[0]
        media_size = struct.unpack("<Q", hdr[off + 8 : off + 0x10])[0]
        sections.append(
            {
                "index": i,
                "media_offset": media_offset,
                "media_size": media_size,
                "body_offset": media_offset * 0x200,
                "body_size": media_size * 0x200,
            }
        )

    return {
        "magic": "NCA2",
        "title_id": f"{title_id:016X}",
        "sdk_version": sdk_version,
        "sections": sections,
        "nca_data": nca_data,
    }


def _parse_nca3_header(nca_data: bytes) -> dict[str, Any]:
    """Parseia header NCA3 (magic no final do header)."""
    hdr = nca_data[:NCA_HEADER_SIZE]
    title_id = struct.unpack("<Q", hdr[0x30:0x38])[0]

    sections: list[dict[str, Any]] = []
    for i in range(4):
        off = 0x40 + i * 0x10
        media_offset = struct.unpack("<Q", hdr[off : off + 8])[0]
        media_size = struct.unpack("<Q", hdr[off + 8 : off + 0x10])[0]
        sections.append(
            {
                "index": i,
                "media_offset": media_offset,
                "media_size": media_size,
                "body_offset": media_offset * 0x200,
                "body_size": media_size * 0x200,
            }
        )

    return {
        "magic": "NCA3",
        "title_id": f"{title_id:016X}",
        "sdk_version": 0,
        "sections": sections,
        "nca_data": nca_data,
    }


def extract_icon_from_nca(nca_data: bytes) -> tuple[bytes, str] | None:
    """Extrai ícone JPEG/PNG do corpo de um NCA via byte-scanning.

    Varre as seções do NCA (ou o arquivo todo como fallback) procurando
    magic bytes de JPEG ou PNG. Retorna (dados, formato) ou None.
    """
    # Primeiro tenta via parsing estruturado das seções
    hdr = read_nca_header(nca_data)
    if hdr:
        for section in hdr.get("sections", []):
            body_off = section["body_offset"]
            body_sz = section["body_size"]
            if body_sz < MIN_IMAGE_SIZE or body_sz > MAX_IMAGE_SIZE:
                continue
            if body_off >= len(nca_data):
                continue
            section_data = nca_data[body_off:]
            found = _search_image_in_data(section_data)
            if found:
                return found

    # Fallback: scan heurístico no arquivo todo
    return _search_image_in_data(nca_data)


def _search_image_in_data(data: bytes) -> tuple[bytes, str] | None:
    """Busca JPEG ou PNG no dado binário."""
    # JPEG scan
    idx = 0
    while True:
        pos = data.find(JPEG_MAGIC, idx)
        if pos < 0:
            break
        # Encontra o marcador EOI (FF D9)
        end = data.find(b"\xff\xd9", pos + 2)
        if end > pos:
            jpeg_data = data[pos : end + 2]
            if len(jpeg_data) >= MIN_IMAGE_SIZE:
                return (jpeg_data, "jpeg")
        idx = pos + 1

    # PNG scan
    pos = data.find(PNG_MAGIC)
    if pos >= 0:
        # PNG termina com IEND
        end = data.find(b"IEND", pos + 4)
        if end > pos:
            png_data = data[pos : end + 8]
            if len(png_data) >= MIN_IMAGE_SIZE:
                return (png_data, "png")

    return None


def extract_icon_from_rom(
    rom_path: Path, nca_offset: int, nca_size: int
) -> tuple[bytes, str] | None:
    """Extrai ícone de um NCA dentro de um container NSP/XCI."""
    try:
        with open(rom_path, "rb") as f:
            f.seek(nca_offset)
            nca_data = f.read(min(nca_size, MAX_IMAGE_SIZE * 4))
        return extract_icon_from_nca(nca_data)
    except OSError:
        return None


def extract_title_id_from_rom(rom_path: Path, nca_offset: int = 0) -> str | None:
    """Extrai Title ID de um NCA sem precisar do container parsing."""
    try:
        with open(rom_path, "rb") as f:
            f.seek(nca_offset)
            header = f.read(NCA_HEADER_SIZE)
        hdr = read_nca_header(header)
        return hdr["title_id"] if hdr else None
    except OSError:
        return None
