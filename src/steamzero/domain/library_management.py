# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Auditoria e quarentena transacionais para todas as plataformas."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from steamzero.core import fs, ids, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain.library import PlatformDirectoryInventory
from steamzero.domain.platforms import PlatformRegistry
from steamzero.domain.switch_roots import root_id, sanitize_display_path, validate_rom_root

_QUARANTINABLE_CATEGORIES = frozenset(
    {"update", "dlc", "related", "duplicate", "incompatible", "corrupted", "unknown"}
)
_FILENAME_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _canonical_game_stem(value: str) -> str:
    normalized = unicodedata.normalize("NFC", " ".join(value.split()))
    normalized = _FILENAME_FORBIDDEN.sub("-", normalized).rstrip(" .")
    return normalized or "Game"


class LibraryRootManager:
    """Produz auditoria e quarentena para ROMs de qualquer plataforma.

    O inventário declarativo é a fonte de relação: jogo-base nunca é
    selecionável por acidente, enquanto membros internos, updates, DLCs e
    desconhecidos aparecem no preview com o vínculo que os levou até ali.
    """

    def __init__(self, root: Path) -> None:
        self.root = validate_rom_root(root)
        self._inventory = PlatformDirectoryInventory.from_registry(PlatformRegistry.bundled())

    @staticmethod
    def _item(
        path: Path,
        root: Path,
        *,
        category: str,
        relation: str | None = None,
        owner_path: Path | None = None,
    ) -> dict[str, Any]:
        relative = path.relative_to(root)
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        item: dict[str, Any] = {
            "relativePath": relative.as_posix(),
            "sizeBytes": size,
            "sha256": None,
            "category": category,
        }
        if relation is not None:
            item["relation"] = relation
        if owner_path is not None:
            item["ownerPath"] = owner_path.relative_to(root).as_posix()
        return item

    def audit(
        self,
        *,
        safepoint: Callable[[], None] | None = None,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> dict[str, Any]:
        categories: dict[str, list[dict[str, Any]]] = {
            key: []
            for key in (
                "base",
                "update",
                "dlc",
                "duplicate",
                "incompatible",
                "corrupted",
                "related",
                "unknown",
            )
        }
        claimed: set[Path] = set()
        rows = self._inventory.inventory(
            self.root,
            include_unclaimed=True,
            safepoint=safepoint,
            progress=progress,
        )
        for row in rows:
            if safepoint is not None:
                safepoint()
            if row.disposition == "matched":
                for game in row.selected_games:
                    claimed.add(game.path)
                    categories["base"].append(
                        self._item(game.path, self.root, category="base", relation="game-base")
                    )
                for related in row.related_content:
                    if not related.path.is_file() or related.path.is_symlink():
                        continue
                    claimed.add(related.path)
                    category = (
                        related.content_kind
                        if related.content_kind in {"update", "dlc"}
                        else "related"
                    )
                    categories[category].append(
                        self._item(
                            related.path,
                            self.root,
                            category=category,
                            relation=related.relation,
                            owner_path=related.owner_path,
                        )
                    )
            for path in row.unclaimed_content:
                if path in claimed or path.is_symlink():
                    continue
                claimed.add(path)
                categories["unknown"].append(
                    self._item(path, self.root, category="unknown", relation="unclaimed")
                )

        # Arquivos diretamente na raiz não pertencem a uma pasta de plataforma,
        # mas continuam selecionáveis para revisão humana.
        try:
            root_files = sorted(
                (path for path in self.root.iterdir() if path.is_file() and not path.is_symlink()),
                key=lambda item: item.name.casefold(),
            )
        except OSError:
            root_files = []
        for path in root_files:
            if path in claimed:
                continue
            claimed.add(path)
            categories["unknown"].append(
                self._item(path, self.root, category="unknown", relation="unclaimed")
            )
        return {
            "schemaVersion": 2,
            "rootId": root_id(self.root),
            "displayPath": sanitize_display_path(self.root),
            "auditedAt": datetime.now(UTC).isoformat(),
            "categories": categories,
            "counts": {key: len(value) for key, value in categories.items()},
            "relationshipPolicy": "manifest-directory-and-auxiliary-v1",
            "errors": [],
        }

    def plan_rename(self, games: Sequence[Mapping[str, Any]]) -> transaction.Plan:
        """Plane nomes canônicos para qualquer plataforma, sem tocar diretórios.

        Diretórios de jogo (como uma app Vita3K) permanecem intocados: eles
        precisam da operação explícita de empacotamento. Arquivos-base recebem
        o título já resolvido pelo scan, preservam a extensão suportada e, na
        Vita, mantêm o Title ID no nome para que a identidade técnica não se
        perca. Colisões nunca sobrescrevem: recebem sufixo determinístico.
        """
        entries: list[tuple[Path, str, str | None, str | None]] = []
        seen: set[Path] = set()
        for game in games:
            content_kind = str(game.get("contentKind") or game.get("content_kind") or "base")
            if content_kind != "base":
                continue
            raw_path = game.get("path")
            title = game.get("name") or game.get("canonicalName")
            if not isinstance(raw_path, str) or not isinstance(title, str) or not title.strip():
                continue
            lexical = Path(raw_path)
            if lexical.is_symlink():
                raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="origem de rename é symlink")
            source = fs.resolve_within(self.root, lexical)
            if source in seen:
                raise SteamZeroError("E-TX-STALE-PLAN", detail=f"origem duplicada: {source}")
            if not source.exists():
                raise SteamZeroError("E-TX-STALE-PLAN", detail=f"origem ausente: {source}")
            if source.is_dir():
                continue
            if not source.is_file():
                raise SteamZeroError("E-TX-STALE-PLAN", detail=f"origem inválida: {source}")
            try:
                relative = source.relative_to(self.root)
            except ValueError as exc:
                raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="origem fora da raiz") from exc
            if any(part in {".steamzero", ".steamzero-quarantine"} for part in relative.parts):
                continue
            seen.add(source)
            platform = str(game.get("platform") or game.get("platformId") or "")
            raw_title_id = game.get("titleId")
            entries.append(
                (
                    source,
                    title,
                    platform,
                    str(raw_title_id) if isinstance(raw_title_id, str) else None,
                )
            )

        used_by_parent: dict[Path, set[str]] = {}
        for source, _title, _platform, _title_id in entries:
            used_by_parent.setdefault(source.parent, set()).add(source.name.casefold())
        moves: dict[Path, Path] = {}
        for source, title, entry_platform, vita_title_id in sorted(
            entries, key=lambda item: str(item[0])
        ):
            used = used_by_parent[source.parent]
            used.discard(source.name.casefold())
            stem = _canonical_game_stem(title)
            if entry_platform == "playstation-vita" and vita_title_id:
                stem = f"{stem} [{vita_title_id.strip().upper()}]"
            extension = source.suffix
            candidate = f"{stem}{extension}"
            suffix_index = 2
            while candidate.casefold() in used:
                candidate = f"{stem} ({suffix_index}){extension}"
                suffix_index += 1
            target = fs.resolve_within(self.root, source.parent / candidate)
            if target != source:
                moves[source] = target
            used.add(candidate.casefold())
        return transaction.plan_move_files(moves, root=self.root, kind="library.rename")

    def plan_quarantine(
        self, audit: Mapping[str, Any], approved_paths: Sequence[str]
    ) -> tuple[transaction.Plan, str]:
        categories = audit.get("categories")
        if not isinstance(categories, Mapping):
            raise SteamZeroError("E-API-SCHEMA", detail="preview de auditoria inválido")
        allowed: dict[str, Mapping[str, Any]] = {}
        for category in _QUARANTINABLE_CATEGORIES:
            items = categories.get(category, [])
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, Mapping) and isinstance(item.get("relativePath"), str):
                    allowed[str(item["relativePath"])] = item

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
                    "E-CONTENT-UNSAFE-PATH", detail=f"arquivo não aprovado pelo preview: {key}"
                )
            source = fs.resolve_within(self.root, self.root / relative)
            if source.is_symlink() or not source.is_file():
                raise SteamZeroError("E-TX-STALE-PLAN", detail=f"arquivo mudou: {key}")
            digest = fs.hash_file(source, algo="sha256")
            moves[source] = quarantine / relative
            entries.append(
                {
                    "relativePath": key,
                    "quarantinePath": relative.as_posix(),
                    "category": item.get("category", "related"),
                    "relation": item.get("relation"),
                    "ownerPath": item.get("ownerPath"),
                    "sha256": digest,
                    "sizeBytes": source.stat().st_size,
                }
            )
        if not moves:
            raise SteamZeroError("E-API-SCHEMA", detail="selecione conteúdo não-base no preview")
        manifest = {
            "schemaVersion": 2,
            "operationId": operation_id,
            "rootId": root_id(self.root),
            "createdAt": datetime.now(UTC).isoformat(),
            "entries": entries,
        }
        plan = transaction.plan_move_files(
            moves,
            root=self.root,
            kind="library.quarantine",
            writes={
                quarantine / "manifest.json": json.dumps(
                    manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":")
                ).encode()
            },
        )
        return plan, operation_id
