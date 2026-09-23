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
from steamzero.domain.library_derived import DERIVED_MANIFEST, read_derived_manifest
from steamzero.domain.platforms import PlatformRegistry
from steamzero.domain.switch_roots import root_id, sanitize_display_path, validate_rom_root

_QUARANTINABLE_CATEGORIES = frozenset(
    {
        "update",
        "dlc",
        "related",
        "derived",
        "duplicate",
        "incompatible",
        "corrupted",
        "unknown",
    }
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
        owner_paths: Sequence[Path] = (),
    ) -> dict[str, Any]:
        relative = path.relative_to(root)
        try:
            if path.is_dir():
                size = sum(
                    child.stat().st_size
                    for child in path.rglob("*")
                    if child.is_file() and not child.is_symlink()
                )
            else:
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
        if owner_paths:
            item["ownerPaths"] = [owner.relative_to(root).as_posix() for owner in owner_paths]
        return item

    @staticmethod
    def _has_symlink_component(root: Path, relative: Path) -> bool:
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                return True
        return False

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
                "derived",
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
                    if not related.path.exists() or related.path.is_symlink():
                        continue
                    if related.path.is_dir() and not any(
                        child.is_file() and not child.is_symlink()
                        for child in related.path.rglob("*")
                    ):
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
        self._append_derived(categories, claimed)
        return {
            "schemaVersion": 2,
            "rootId": root_id(self.root),
            "displayPath": sanitize_display_path(self.root),
            "auditedAt": datetime.now(UTC).isoformat(),
            "categories": categories,
            "counts": {key: len(value) for key, value in categories.items()},
            "relationshipPolicy": "manifest-directory-auxiliary-derived-v2",
            "errors": [],
        }

    def _append_derived(
        self, categories: dict[str, list[dict[str, Any]]], claimed: set[Path]
    ) -> None:
        """Expose only provenance-backed SteamZero outputs as related cleanup sets."""
        derived_root = self.root / ".steamzero" / "derived"
        if derived_root.is_symlink() or not derived_root.is_dir():
            return
        try:
            manifests = sorted(
                (
                    path
                    for path in derived_root.rglob("*")
                    if path.is_file()
                    and not path.is_symlink()
                    and (
                        path.name == DERIVED_MANIFEST
                        or path.name.endswith(".steamzero-derived.json")
                    )
                ),
                key=lambda item: item.as_posix().casefold(),
            )
        except OSError:
            return
        for manifest_path in manifests:
            if manifest_path.is_symlink():
                continue
            metadata = read_derived_manifest(manifest_path, self.root)
            if metadata is None:
                continue
            artifact = metadata["artifactPath"]
            if artifact in claimed or artifact.is_symlink():
                continue
            owner_paths = metadata["ownerPaths"]
            relative_manifest = manifest_path.relative_to(self.root).as_posix()
            item = self._item(
                artifact,
                self.root,
                category="derived",
                relation="generated-from",
                owner_path=owner_paths[0] if len(owner_paths) == 1 else None,
                owner_paths=owner_paths,
            )
            item["operation"] = metadata["operation"]
            item["platformId"] = metadata["platformId"]
            item["managementPaths"] = [
                artifact.relative_to(self.root).as_posix(),
                relative_manifest,
            ]
            categories["derived"].append(item)
            claimed.add(artifact)
            claimed.add(manifest_path)

        # Artefatos históricos sem sidecar continuam visíveis para limpeza, mas
        # nunca recebem um vínculo de origem inferido pelo nome da pasta.
        try:
            platform_entries = sorted(derived_root.iterdir(), key=lambda item: item.name.casefold())
        except OSError:
            return
        for platform_entry in platform_entries:
            if platform_entry.is_symlink():
                continue
            try:
                candidates = (
                    sorted(platform_entry.iterdir(), key=lambda item: item.name.casefold())
                    if platform_entry.is_dir()
                    else [platform_entry]
                )
            except OSError:
                continue
            for artifact in candidates:
                if artifact.is_symlink() or artifact in claimed:
                    continue
                relative = artifact.relative_to(self.root).as_posix()
                item = self._item(
                    artifact,
                    self.root,
                    category="derived",
                    relation="generated-unlinked",
                )
                item["operation"] = "unverified-legacy"
                item["platformId"] = platform_entry.name
                item["managementPaths"] = [relative]
                categories["derived"].append(item)
                claimed.add(artifact)

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
            raw_targets = item.get("managementPaths")
            target_paths = raw_targets if isinstance(raw_targets, list) else [key]
            source_paths: set[Path] = set()
            for raw_target in target_paths:
                if not isinstance(raw_target, str):
                    raise SteamZeroError("E-API-SCHEMA", detail="caminho gerenciado inválido")
                target_relative = Path(fs.validate_relative_entry(raw_target))
                if self._has_symlink_component(self.root, target_relative):
                    raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="conteúdo contém symlink")
                source = fs.resolve_within(self.root, self.root / target_relative)
                if source.is_symlink() or not source.exists():
                    raise SteamZeroError("E-TX-STALE-PLAN", detail=f"conteúdo mudou: {raw_target}")
                if source.is_file():
                    source_paths.add(source)
                elif source.is_dir() and item.get("category") in {"derived", "related"}:
                    for child in source.rglob("*"):
                        if child.is_symlink():
                            raise SteamZeroError(
                                "E-CONTENT-UNSAFE-PATH", detail="derivado contém symlink"
                            )
                        if child.is_file():
                            source_paths.add(fs.resolve_within(self.root, child))
                else:
                    raise SteamZeroError(
                        "E-TX-STALE-PLAN", detail=f"conteúdo não é arquivo gerenciado: {raw_target}"
                    )
            if not source_paths:
                raise SteamZeroError("E-TX-STALE-PLAN", detail=f"conteúdo vazio: {key}")
            for source in sorted(source_paths, key=lambda entry: entry.as_posix().casefold()):
                relative_source = source.relative_to(self.root)
                digest = fs.hash_file(source, algo="sha256")
                target = quarantine / relative_source
                if source in moves:
                    continue
                moves[source] = target
                entries.append(
                    {
                        "relativePath": relative_source.as_posix(),
                        "quarantinePath": relative_source.as_posix(),
                        "category": item.get("category", "related"),
                        "relation": item.get("relation"),
                        "ownerPath": item.get("ownerPath"),
                        "ownerPaths": item.get("ownerPaths", []),
                        "selectedSet": key,
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
