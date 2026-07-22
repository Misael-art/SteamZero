# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Extrator de ícones nativos de ROMs Switch — fachada dos leitores de container/NCA.

Combina PFS0/HFS0 parsing com NCA scanning para extrair o ícone oficial
do jogo diretamente do arquivo de ROM, sem depender de chaves criptográficas
ou serviços externos.
"""

from __future__ import annotations

import logging
from pathlib import Path

from steamzero.adapters.rom_metadata.container_reader import (
    find_control_nca,
)
from steamzero.adapters.rom_metadata.nca_reader import (
    extract_icon_from_nca,
    extract_icon_from_rom,
    extract_title_id_from_rom,
    read_nca_header,
)
from steamzero.ports import EmulatorCachePort, RomMetadata, RomMetadataPort

_log = logging.getLogger(__name__)


class NativeIconExtractor(RomMetadataPort):
    """Extrai metadados e ícone nativo de arquivos de ROM Switch.

    Fluxo:
    1. Se o arquivo é .nsp/.xci → parseia container PFS0/HFS0 → localiza control.nca
    2. Parseia header NCA → obtém Title ID
    3. Escaneia o corpo do NCA por magic bytes JPEG/PNG → extrai imagem
    4. Fallback: cache do emulador
    """

    _NATIVE_EXTENSIONS = frozenset({".nsp", ".xci", ".nca", ".nsz", ".xcz"})

    def __init__(self, emulator_cache: EmulatorCachePort | None = None) -> None:
        self._emulator_cache = emulator_cache

    # --- RomMetadataPort -----------------------------------------------------

    def extract_metadata(self, rom_path: Path) -> RomMetadata | None:
        if rom_path.suffix.lower() not in self._NATIVE_EXTENSIONS:
            return None
        if not rom_path.is_file():
            return None

        title_id: str | None = None
        icon: tuple[bytes, str] | None = None

        ext = rom_path.suffix.lower()
        if ext == ".nca":
            title_id = self._extract_title_id_nca(rom_path)
            icon = extract_icon_from_rom(rom_path, 0, rom_path.stat().st_size)
        elif ext in (".nsp", ".xci", ".nsz", ".xcz"):
            result = self._extract_from_container(rom_path)
            if result:
                title_id, icon = result

        if not title_id:
            return None

        return RomMetadata(
            title_id=title_id,
            title=title_id,
            icon_bytes=icon[0] if icon else None,
            icon_format=icon[1] if icon else "",
            source="nca-extracted" if icon else "nca-no-icon",
        )

    def extract_icon(self, rom_path: Path) -> tuple[bytes, str] | None:
        meta = self.extract_metadata(rom_path)
        if meta and meta.icon_bytes:
            return (meta.icon_bytes, meta.icon_format)
        if self._emulator_cache and meta:
            icon_path = self._emulator_cache.find_icon(meta.title_id)
            if icon_path and icon_path.is_file():
                try:
                    data = icon_path.read_bytes()
                    fmt = "jpeg" if icon_path.suffix == ".jpg" else "png"
                    return (data, fmt)
                except OSError:
                    pass
        return None

    # --- Internal helpers ----------------------------------------------------

    def _extract_title_id_nca(self, nca_path: Path) -> str | None:
        try:
            with open(nca_path, "rb") as f:
                header = f.read(0x200)
            hdr = read_nca_header(header)
            return hdr["title_id"] if hdr else None
        except OSError:
            return None

    def _extract_from_container(self, rom_path: Path) -> tuple[str, tuple[bytes, str]] | None:
        control = find_control_nca(rom_path)
        if control is None:
            return None

        _name, nca_offset, nca_size = control
        title_id = extract_title_id_from_rom(rom_path, nca_offset)
        if not title_id:
            return None

        try:
            with open(rom_path, "rb") as f:
                f.seek(nca_offset)
                nca_data = f.read(min(nca_size, 2 * 1024 * 1024))
            icon = extract_icon_from_nca(nca_data)
        except OSError:
            icon = None

        return (title_id, icon) if icon else (title_id, (b"", ""))
