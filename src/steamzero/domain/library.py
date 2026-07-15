# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Library: scan read-only, import verificado, dedupe, multidisco (F-LB-01/02/04/06).

- Scan: leitura pura (hash blake2b + classificação); NUNCA escreve fora do state
  (AC-LB-01).
- Import: cópia com verificação de hash; a origem NUNCA é alterada (import é
  cópia — RT-07/AC-LB-02). Dedupe por hash. Archive passa por safezip; inseguro =>
  staging limpo + E-CONTENT-UNSAFE-ARCHIVE, origem intocada (AC-LB-03).
- Multidisco: agrupa "(Disc N)" no mesmo multi_disc_group.

Conteúdo é sempre do usuário (CONTENT-POLICY): nada é obtido, sugerido ou baixado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from steamzero.core import fs, ids, paths, safezip
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore

_DISC_RE = re.compile(r"\s*\((?:disc|disk)\s*(\d+)\)", re.IGNORECASE)

_FORMAT_BY_EXT = {
    ".chd": "chd",
    ".rvz": "rvz",
    ".iso": "iso",
    ".cue": "cue",
    ".bin": "bin",
    ".m3u": "m3u",
    ".zip": "zip",
    ".7z": "7z",
    ".nes": "nes",
    ".sfc": "snes",
    ".smc": "snes",
    ".gba": "gba",
    ".nds": "nds",
}


def detect_format(name: str) -> str:
    return _FORMAT_BY_EXT.get(Path(name).suffix.lower(), "unknown")


def disc_group(title: str) -> tuple[str, int | None]:
    """Retorna (título-base, número do disco|None) para agrupamento multidisco."""
    match = _DISC_RE.search(title)
    if match is None:
        return title, None
    base = _DISC_RE.sub("", title).strip()
    return base, int(match.group(1))


@dataclass(frozen=True)
class ScannedRom:
    relpath: str
    size: int
    hash_blake2b: str
    format: str


@dataclass
class ImportResult:
    status: str  # imported | duplicate
    rom_id: str | None
    relpath: str | None
    hash_blake2b: str


class LibraryScanner:
    """Scan read-only de uma árvore de ROMs (AC-LB-01)."""

    def __init__(self, store: StateStore) -> None:
        self._store = store

    def scan(self, root: Path) -> list[ScannedRom]:
        results: list[ScannedRom] = []
        for path in fs.iter_files(root):
            rel = path.relative_to(root)
            results.append(
                ScannedRom(
                    relpath=str(rel),
                    size=path.stat().st_size,
                    hash_blake2b=fs.hash_file(path),
                    format=detect_format(path.name),
                )
            )
        return results


class LibraryImporter:
    """Import de dumps do usuário (cópia verificada; origem intocada)."""

    def __init__(self, store: StateStore) -> None:
        self._store = store

    def import_file(
        self, src: Path, platform_slug: str, *, title: str | None = None
    ) -> ImportResult:
        slug = ids.require_slug(platform_slug)
        src_hash = fs.hash_file(src)  # origem só é LIDA
        dup = self._store.find_rom_by_hash(src_hash)
        if dup is not None:
            return ImportResult("duplicate", dup["id"], dup["relpath"], src_hash)

        roms = paths.roms_dir()
        dest = fs.resolve_within(roms, roms / slug / src.name)
        data = src.read_bytes()
        fs.write_atomic(dest, data)
        if fs.hash_file(dest) != src_hash:  # cópia corrompida
            fs.remove_file(dest)
            raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="cópia divergente da origem")

        rom_id = self._register(dest, slug, src_hash, title or src.stem)
        return ImportResult("imported", rom_id, str(dest.relative_to(roms)), src_hash)

    def import_archive(self, src: Path, platform_slug: str) -> list[ImportResult]:
        op_id = ids.new_ulid()
        try:
            extracted = safezip.extract_safe(src, op_id)
        except SteamZeroError as exc:
            fs.remove_tree(paths.staging_for(op_id))  # nunca deixa parcial fora
            self._store.append_event(
                "alert", entity=f"import:{src.name}", payload={"code": exc.code}
            )
            raise
        try:
            return [self.import_file(p, platform_slug) for p in extracted]
        finally:
            fs.remove_tree(paths.staging_for(op_id))  # limpa staging após import

    def _register(self, dest: Path, slug: str, rom_hash: str, title: str) -> str:
        self._store.save_platform({"id": slug, "name": slug.upper()})
        base_title, disc = disc_group(title)
        group = base_title if disc is not None else None
        game_id = ids.new_ulid()
        self._store.save_game(
            {
                "id": game_id,
                "platform_id": slug,
                "title": base_title,
                "multi_disc_group": group,
                "state": "ready",
            }
        )
        rom_id = ids.new_ulid()
        self._store.save_rom(
            {
                "id": rom_id,
                "game_id": game_id,
                "volume_id": None,
                "relpath": str(dest.relative_to(paths.roms_dir())),
                "size": dest.stat().st_size,
                "hash_blake2b": rom_hash,
                "format": detect_format(dest.name),
                "verified_at": _now_iso(),
            }
        )
        self._store.append_event(
            "entity.changed", entity=f"rom:{rom_id}", payload={"title": base_title}
        )
        return rom_id


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
