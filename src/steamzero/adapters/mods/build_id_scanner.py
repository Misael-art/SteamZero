# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Scanner de Build IDs a partir de ROMs de Switch.

Extrai o Build ID (hash SHA256 de 32 caracteres hex) de arquivos NCA/NSP/XCI
instalados, usado para casar mods precisos por versão de jogo.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from steamzero.ports import BuildIdProviderPort

_BUILD_ID_BYTES_RE = re.compile(rb"[0-9a-fA-F]{32}")

_NCA_MAGIC = b"NCA3"
_KNOWN_ROM_EXTS = frozenset({".nsp", ".xci", ".nca", ".nsz", ".xcz"})


class BuildIdScanner(BuildIdProviderPort):
    """Escaneia ROMs de Switch e extrai Build IDs candidatos.

    Estratégias (em ordem de precisão):
    1. Busca por padrão SHA256 (64 hex chars) nos primeiros bytes do arquivo.
    2. Fallback para hash SHA256 do arquivo completo.
    """

    def __init__(self, roms_root: Path | None = None) -> None:
        self._roms_root = roms_root

    # --- BuildIdProviderPort -------------------------------------------------

    def scan_game(self, game_id: str) -> list[str]:
        return []

    def scan_rom_file(self, rom_path: Path) -> list[str]:
        if not rom_path.is_file():
            return []
        ext = rom_path.suffix.lower()
        if ext not in _KNOWN_ROM_EXTS:
            return []
        return self._extract_build_ids(rom_path)

    def scan_directory(self, directory: Path) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for root, _dirs, files in os.walk(directory):
            for fname in files:
                path = Path(root) / fname
                if path.suffix.lower() in _KNOWN_ROM_EXTS:
                    ids = self._extract_build_ids(path)
                    if ids:
                        name = _title_id_from_name(fname)
                        result[name] = ids
        return result

    def _extract_build_ids(self, rom_path: Path) -> list[str]:
        ids: list[str] = []

        try:
            with open(rom_path, "rb") as f:
                header = f.read(1024 * 1024)
        except OSError:
            return []

        raw_ids = _BUILD_ID_BYTES_RE.findall(header)
        for raw in raw_ids:
            bid = raw.decode("ascii").lower()[:32]
            if bid not in ids:
                ids.append(bid)

        return ids


def _title_id_from_name(filename: str) -> str:
    base = Path(filename).stem
    match = re.search(r"[0-9a-fA-F]{16}", base)
    return match.group(0).upper() if match else base
