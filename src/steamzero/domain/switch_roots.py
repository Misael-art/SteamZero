# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Auditoria e mutações seguras de raízes de ROMs Switch."""

from __future__ import annotations

import hashlib
import json
import os
import unicodedata
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from steamzero.core import fs, ids, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain.switch_library import (
    SwitchLibraryOrganizer,
    SwitchLibraryScanner,
    SwitchRomMatch,
)

_ROM_FORMATS = frozenset({".nsp", ".nsz", ".xci", ".xcz", ".nro"})
_INCOMPATIBLE_FORMATS = frozenset({".7z", ".rar", ".zip"})
_SPECIAL_ROOT_NAMES = frozenset(
    {
        "firmware",
        "keys",
        "bios",
        "saves",
        "cache",
        "media",
        "screenshots",
        "mods",
        "cheats",
        "dlc",
        "updates",
        "patches",
        "shader",
        "nand",
        "system",
    }
)
_BIDI_CONTROLS = frozenset({"LRE", "RLE", "LRO", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI"})


def root_id(root: Path) -> str:
    """Identidade opaca estável; a UI nunca precisa devolver um caminho."""
    return hashlib.sha256(os.fsencode(root)).hexdigest()[:24]


def sanitize_display_path(root: Path) -> str:
    value = str(root)
    home = str(Path.home())
    if value == home:
        value = "~"
    elif value.startswith(home + os.sep):
        value = "~" + value[len(home) :]
    return "".join(
        character
        for character in value
        if unicodedata.category(character) != "Cc"
        and unicodedata.bidirectional(character) not in _BIDI_CONTROLS
    )


def validate_rom_root(
    selected: Path,
    *,
    managed_roots: Sequence[Path] = (),
    require_exists: bool = True,
) -> Path:
    """Recusa aliases, symlinks, raízes especiais e diretórios gerenciados."""
    if not selected.is_absolute():
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="a raiz de ROMs deve ser absoluta")
    absolute = selected.absolute()
    if selected.is_symlink() or any(parent.is_symlink() for parent in absolute.parents):
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="raiz de ROMs não pode conter symlink")
    try:
        resolved = selected.resolve(strict=require_exists)
    except OSError as exc:
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="raiz de ROMs inacessível") from exc
    if resolved != absolute:
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="raiz de ROMs não é um caminho real")
    if require_exists and not resolved.is_dir():
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="raiz de ROMs inválida")
    if resolved.name.casefold() in _SPECIAL_ROOT_NAMES:
        raise SteamZeroError(
            "E-CONTENT-UNSAFE-PATH",
            detail="firmware, keys e caches não podem ser raízes de ROMs",
        )
    for managed in managed_roots:
        managed_resolved = managed.resolve(strict=False)
        if resolved == managed_resolved or resolved.is_relative_to(managed_resolved):
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-PATH",
                detail="diretório gerenciado não pode ser raiz de ROMs",
            )
    return resolved


class SwitchRootManager:
    """Produz preview, quarentena e rename confinados a uma raiz registrada."""

    def __init__(self, root: Path) -> None:
        self.root = validate_rom_root(root)
        self._scanner = SwitchLibraryScanner()

    def audit(self) -> dict[str, Any]:
        categories: dict[str, list[dict[str, Any]]] = {
            key: []
            for key in (
                "base",
                "update",
                "dlc",
                "duplicate",
                "incompatible",
                "corrupted",
                "unknown",
            )
        }
        errors: list[dict[str, str]] = []
        seen_hashes: dict[str, str] = {}
        for candidate in sorted(self.root.rglob("*")):
            try:
                lexical_relative = candidate.relative_to(self.root)
            except ValueError:
                lexical_relative = Path(candidate.name)
            if lexical_relative.parts and lexical_relative.parts[0] == ".steamzero-quarantine":
                continue
            relative = self._safe_relative(candidate)
            if relative is None:
                errors.append({"code": "E-CONTENT-UNSAFE-PATH", "entry": candidate.name})
                continue
            if candidate.is_dir():
                continue
            suffix = candidate.suffix.casefold()
            if suffix not in _ROM_FORMATS:
                category = "incompatible" if suffix in _INCOMPATIBLE_FORMATS else "unknown"
                categories[category].append(self._item(candidate, relative, sha256=None))
                continue
            try:
                if candidate.stat().st_size == 0:
                    categories["corrupted"].append(self._item(candidate, relative, sha256=None))
                    continue
                digest = fs.hash_file(candidate, algo="sha256")
                duplicate_of = seen_hashes.get(digest)
                if duplicate_of is not None:
                    item = self._item(candidate, relative, sha256=digest)
                    item["duplicateOf"] = duplicate_of
                    categories["duplicate"].append(item)
                    continue
                seen_hashes[digest] = relative.as_posix()
                fmt = suffix.lstrip(".")
                title_id = self._scanner._title_id_from_path(candidate, self.root)
                kind, _parent, _version, _source = self._scanner.classify(
                    candidate,
                    root=self.root,
                    fmt=fmt,
                    title_id=title_id,
                )
                categories[kind].append(self._item(candidate, relative, sha256=digest))
            except (OSError, SteamZeroError):
                categories["corrupted"].append(self._item(candidate, relative, sha256=None))
        return {
            "schemaVersion": 1,
            "rootId": root_id(self.root),
            "displayPath": sanitize_display_path(self.root),
            "auditedAt": datetime.now(UTC).isoformat(),
            "categories": categories,
            "counts": {key: len(value) for key, value in categories.items()},
            "errors": errors[:50],
        }

    def plan_quarantine(
        self,
        audit: Mapping[str, Any],
        approved_paths: Sequence[str],
    ) -> tuple[transaction.Plan, str]:
        allowed: dict[str, Mapping[str, Any]] = {}
        categories = audit.get("categories")
        if not isinstance(categories, Mapping):
            raise SteamZeroError("E-API-SCHEMA", detail="preview de auditoria inválido")
        for category in ("duplicate", "incompatible", "corrupted", "unknown"):
            items = categories.get(category, [])
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, Mapping) and isinstance(item.get("relativePath"), str):
                    allowed[str(item["relativePath"])] = {**dict(item), "category": category}

        operation_id = ids.new_ulid()
        quarantine = self.root / ".steamzero-quarantine" / operation_id
        moves: dict[Path, Path] = {}
        entries: list[dict[str, Any]] = []
        for raw_relative in approved_paths:
            relative = fs.validate_relative_entry(raw_relative)
            key = relative.as_posix()
            item = allowed.get(key)
            if item is None:
                raise SteamZeroError(
                    "E-CONTENT-UNSAFE-PATH",
                    detail=f"arquivo não aprovado pelo preview: {key}",
                )
            source = fs.resolve_within(self.root, self.root / relative)
            if source.is_symlink() or not source.is_file():
                raise SteamZeroError("E-TX-STALE-PLAN", detail=f"arquivo mudou: {key}")
            digest = fs.hash_file(source, algo="sha256")
            preview_hash = item.get("sha256")
            if preview_hash is not None and digest != preview_hash:
                raise SteamZeroError("E-TX-STALE-PLAN", detail=f"arquivo mudou: {key}")
            target = quarantine / relative
            moves[source] = target
            entries.append(
                {
                    "relativePath": key,
                    "quarantinePath": relative.as_posix(),
                    "category": item["category"],
                    "sha256": digest,
                    "sizeBytes": source.stat().st_size,
                }
            )
        if not moves:
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail="selecione no preview ao menos um arquivo não jogável",
            )
        manifest = {
            "schemaVersion": 1,
            "operationId": operation_id,
            "rootId": root_id(self.root),
            "createdAt": datetime.now(UTC).isoformat(),
            "entries": entries,
        }
        plan = transaction.plan_move_files(
            moves,
            root=self.root,
            kind="switch-library.quarantine",
            writes={
                quarantine / "manifest.json": json.dumps(
                    manifest,
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode()
            },
        )
        return plan, operation_id

    def plan_rename(self, games: Sequence[Mapping[str, Any]]) -> transaction.Plan:
        matches: list[SwitchRomMatch] = []
        for game in games:
            raw_path = game.get("path")
            canonical_name = game.get("name")
            if not isinstance(raw_path, str) or not isinstance(canonical_name, str):
                continue
            path = Path(raw_path)
            try:
                source = fs.resolve_within(self.root, path)
            except SteamZeroError:
                continue
            if source.is_symlink() or not source.is_file():
                raise SteamZeroError("E-TX-STALE-PLAN", detail="ROM mudou após a varredura")
            fmt = source.suffix.lstrip(".").casefold()
            if f".{fmt}" not in _ROM_FORMATS:
                continue
            matches.append(
                SwitchRomMatch(
                    path=source,
                    sha256=fs.hash_file(source, algo="sha256"),
                    format=fmt,
                    title_id=str(game["titleId"]) if game.get("titleId") else None,
                    canonical_name=canonical_name,
                    region=None,
                )
            )
        return SwitchLibraryOrganizer().plan_rename(self.root, matches)

    def _safe_relative(self, candidate: Path) -> Path | None:
        if candidate.is_symlink():
            return None
        try:
            resolved = candidate.resolve(strict=True)
            relative = resolved.relative_to(self.root)
        except (OSError, ValueError):
            return None
        if relative.parts and relative.parts[0] == ".steamzero-quarantine":
            return None
        return relative

    @staticmethod
    def _item(candidate: Path, relative: Path, *, sha256: str | None) -> dict[str, Any]:
        try:
            size = candidate.stat().st_size
        except OSError:
            size = 0
        return {
            "relativePath": relative.as_posix(),
            "sizeBytes": size,
            "sha256": sha256,
        }
