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
from collections.abc import Sequence
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


def _discovered_pack_directories(user_home: Path) -> list[Path]:
    """Diretórios de BIOS um nível abaixo de uma raiz de emulação.

    Pacotes de BIOS distribuídos por terceiros chegam como uma pasta própria
    dentro da raiz de emulação, com um `bios/` dentro. A lista fixa não os
    alcançava: medido no host em 2026-09-02, NENHUM dos quatro diretórios
    declarados existia, enquanto um pacote com 2008 arquivos — incluindo a BIOS
    de 3DO que o catálogo declara — estava a um nível de distância.

    A descoberta é por forma, não por nome: qualquer pasta com `bios/` dentro
    serve, e nenhum projeto de terceiro é citado (AGENTS.md §7).
    """
    found: list[Path] = []
    for root_name in ("Emulation", "emulation"):
        root = user_home / root_name
        try:
            children = sorted(root.iterdir(), key=lambda item: item.name.casefold())
        except OSError:
            continue
        for child in children:
            if child.is_symlink() or not child.is_dir():
                continue
            for leaf in ("bios", "BIOS"):
                found.append(child / leaf)
    return found


def approved_bios_sources(
    *,
    home: Path | None = None,
    managed_dir: Path | None = None,
    extra_candidates: Sequence[Path] | None = None,
) -> list[BiosSource]:
    """Lista diretórios reais, não gerenciados e sem aliases por symlink.

    ``extra_candidates`` recebe os diretórios de BIOS dos emuladores instalados,
    que só o adapter sabe resolver (nativo e Flatpak). O domínio não importa o
    registro de adapters; quem conhece a instalação passa a lista.
    """
    user_home = home or Path.home()
    store = (managed_dir or paths.bios_dir()).resolve(strict=False)
    candidates = (
        user_home / "Emulation" / "bios",
        user_home / "emulation" / "bios",
        user_home / ".config" / "retroarch" / "system",
        user_home / ".local" / "share" / "retroarch" / "system",
        *_discovered_pack_directories(user_home),
        *(extra_candidates or ()),
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
