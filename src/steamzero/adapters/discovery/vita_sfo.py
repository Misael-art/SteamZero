# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Leitura read-only da identidade Vita em arquivos, pastas e ZIPs."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from steamzero.adapters.discovery.ps5_sfo import parse_sfo
from steamzero.domain.game_identity import GameIdentity, identity_from_vita_title_id

_MAX_PARAM_BYTES = 1024 * 1024
_MAX_ZIP_ENTRIES = 8192


@dataclass(frozen=True)
class VitaMetadata:
    identity: GameIdentity | None
    title: str | None
    diagnosis: str


def _param_bytes(path: Path) -> bytes | None:
    if path.is_dir():
        candidate = path / "sce_sys" / "param.sfo"
        if candidate.is_symlink() or not candidate.is_file():
            return None
        try:
            if candidate.stat().st_size > _MAX_PARAM_BYTES:
                return None
            return candidate.read_bytes()
        except OSError:
            return None
    if path.suffix.casefold() != ".zip" or path.is_symlink():
        return None
    try:
        with zipfile.ZipFile(path) as archive:
            if len(archive.infolist()) > _MAX_ZIP_ENTRIES:
                return None
            entries = [
                info
                for info in archive.infolist()
                if info.filename.casefold().strip("/") == "sce_sys/param.sfo"
            ]
            if len(entries) != 1 or entries[0].file_size > _MAX_PARAM_BYTES:
                return None
            return archive.read(entries[0])
    except (OSError, ValueError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return None


def read_vita_metadata(path: Path) -> VitaMetadata:
    """Retorna título/Title ID sem extrair nem alterar o conteúdo."""
    data = _param_bytes(path)
    if data is None:
        return VitaMetadata(None, None, "vita-param-sfo-missing")
    parsed = parse_sfo(data)
    if parsed is None:
        return VitaMetadata(None, None, "vita-param-sfo-invalid")
    identity = identity_from_vita_title_id(parsed.title_id or "") if parsed.title_id else None
    if identity is None:
        return VitaMetadata(None, parsed.title, "vita-title-id-invalid")
    title = " ".join((parsed.title or "").replace("™", " ").replace("®", " ").split())
    return VitaMetadata(identity, title or None, "vita-param-sfo")


def read_vita_identity(path: Path) -> tuple[GameIdentity | None, str]:
    metadata = read_vita_metadata(path)
    return metadata.identity, metadata.diagnosis
