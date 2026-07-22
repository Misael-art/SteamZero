# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Leitura de caches de ícones e metadados criados por emuladores Switch.

Ryujinx / Ryubing: ``~/.local/share/Ryujinx/system/icon-cache/``
Yuzu / Eden / Citron / Suyu: ``~/.local/share/yuzu/cache/icons/`` (ou ``<data_home>/cache/icons/``)

Reaproveitar o cache do emulador evita reprocessar a ROM para extrair
o ícone nativo.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from steamzero.ports import EmulatorCachePort

_log = logging.getLogger(__name__)

# Caminhos comuns de cache de ícones por emulador
_EMULATOR_ICON_PATHS: dict[str, list[str]] = {
    "ryubing": [
        "Ryujinx",
        "system",
        "icon-cache",
    ],
    "ryujinx": [
        "Ryujinx",
        "system",
        "icon-cache",
    ],
    "yuzu": [
        "yuzu",
        "cache",
        "icons",
    ],
    "eden": [
        "yuzu",
        "cache",
        "icons",
    ],
    "citron": [
        "yuzu",
        "cache",
        "icons",
    ],
    "suyu": [
        "yuzu",
        "cache",
        "icons",
    ],
}


class EmulatorCacheReader(EmulatorCachePort):
    """Leitor de caches de emuladores Switch no sistema de arquivos local."""

    def __init__(self, data_home: Path) -> None:
        self._data_home = data_home

    def _icon_cache_dir(self, emulator_id: str) -> Path | None:
        parts = _EMULATOR_ICON_PATHS.get(emulator_id)
        if parts is None:
            parts = _EMULATOR_ICON_PATHS.get(
                {"eden": "yuzu", "citron": "yuzu", "suyu": "yuzu"}.get(emulator_id, emulator_id)
            )
        if parts is None:
            return None
        candidate = self._data_home.joinpath(*parts)
        if candidate.is_dir():
            return candidate
        return None

    def find_icon(self, title_id: str) -> Path | None:
        for emulator_id in _EMULATOR_ICON_PATHS:
            cache_dir = self._icon_cache_dir(emulator_id)
            if cache_dir is None:
                continue
            # Ryujinx: <title_id>.jpg / <title_id>_<name>.jpg
            for pattern in (f"{title_id}.jpg", f"{title_id}.png"):
                candidate = cache_dir / pattern
                if candidate.is_file():
                    return candidate
            # Ryujinx também pode usar arquivos json com caminhos
            json_file = cache_dir / f"{title_id}.json"
            if json_file.is_file():
                try:
                    data = json.loads(json_file.read_text("utf-8"))
                    icon_path = cache_dir / (data.get("path") or "")
                    if icon_path.is_file():
                        return icon_path
                except (OSError, json.JSONDecodeError, TypeError) as exc:
                    _log.debug("cache de ícone inválido em %s: %s", json_file, exc)
                    continue
            # Scan de arquivos que começam com o title_id
            for child in sorted(cache_dir.iterdir()):
                if child.stem.startswith(title_id) and child.suffix in (
                    ".jpg",
                    ".png",
                ):
                    return child
        return None

    def find_title(self, title_id: str) -> str | None:
        # Tenta ler o nome do jogo do cache do Ryujinx (arquivos json)
        for emulator_id in _EMULATOR_ICON_PATHS:
            cache_dir = self._icon_cache_dir(emulator_id)
            if cache_dir is None:
                continue
            json_file = cache_dir / f"{title_id}.json"
            if json_file.is_file():
                try:
                    data = json.loads(json_file.read_text("utf-8"))
                    name: str | None = data.get("name") or data.get("title")
                    return name
                except (OSError, json.JSONDecodeError, TypeError) as exc:
                    _log.debug("metadado de emulador inválido em %s: %s", json_file, exc)
        return None
