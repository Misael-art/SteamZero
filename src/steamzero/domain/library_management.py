# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Auditoria e quarentena transacionais para todas as plataformas."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
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
                "related",
                "unknown",
            )
        }
        claimed: set[Path] = set()
        rows = self._inventory.inventory(self.root, include_unclaimed=True)
        for row in rows:
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
