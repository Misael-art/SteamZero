# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Seleção segura de origens locais de BIOS para a bridge Desktop.

As origens são diretórios conhecidos do usuário. A identidade retornada aqui é
somente interna: a bridge a troca por um handle aleatório, válido apenas na
sessão que o emitiu. Nenhum caminho é aceito do cliente.
"""

from __future__ import annotations

import hashlib
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from steamzero.core import paths

_BIDI_CONTROLS = frozenset({"LRE", "RLE", "LRO", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI"})


@dataclass(frozen=True)
class BiosSource:
    """Origem aprovada, ainda privada ao processo da bridge."""

    source_id: str
    label: str
    path: Path


def approved_bios_sources(
    *,
    home: Path | None = None,
    managed_dir: Path | None = None,
) -> list[BiosSource]:
    """Lista diretórios reais, não gerenciados e sem aliases por symlink."""
    user_home = home or Path.home()
    store = (managed_dir or paths.bios_dir()).resolve(strict=False)
    candidates = (
        user_home / "Emulation" / "bios",
        user_home / "emulation" / "bios",
        user_home / ".config" / "retroarch" / "system",
        user_home / ".local" / "share" / "retroarch" / "system",
    )
    sources: list[BiosSource] = []
    seen: set[Path] = set()
    for candidate in candidates:
        source = _approved_directory(candidate, store)
        if source is None or source in seen:
            continue
        seen.add(source)
        sources.append(
            BiosSource(
                source_id=_internal_source_id(source),
                label=sanitize_bios_source_label(source, user_home),
                path=source,
            )
        )
    return sources


def resolve_approved_bios_source(source_id: str) -> Path | None:
    """Revalida a origem no instante de uso, evitando TOCTOU por aliases."""
    for source in approved_bios_sources():
        if source.source_id == source_id:
            return source.path
    return None


def _approved_directory(candidate: Path, managed_dir: Path) -> Path | None:
    absolute = candidate.absolute()
    if candidate.is_symlink() or any(parent.is_symlink() for parent in absolute.parents):
        return None
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None
    if resolved != absolute or not resolved.is_dir():
        return None
    if resolved == managed_dir or resolved.is_relative_to(managed_dir):
        return None
    return resolved


def _internal_source_id(path: Path) -> str:
    return hashlib.sha256(os.fsencode(path)).hexdigest()[:24]


def sanitize_bios_source_label(path: Path, home: Path) -> str:
    value = str(path)
    home_value = str(home)
    if value == home_value:
        value = "~"
    elif value.startswith(home_value + os.sep):
        value = "~" + value[len(home_value) :]
    return "".join(
        character
        for character in value
        if unicodedata.category(character) != "Cc"
        and unicodedata.bidirectional(character) not in _BIDI_CONTROLS
    )
