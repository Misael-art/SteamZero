# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Transactional authoring sessions for the existing Experience Journey sidecar."""

from __future__ import annotations

import builtins
import json
import os
import secrets
import threading
from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from steamzero.domain.experience_journey import (
    MAX_CONNECTIONS,
    MAX_DOCUMENT_BYTES,
    MAX_FILTERS_PER_MENU,
    MAX_MENUS,
    MAX_NAVIGATION_HISTORY,
    MAX_ORGANIZATION_NODES,
    JourneyBudgetError,
    JourneyDocument,
    JourneyStore,
    query_public_records,
    resolve_theme_coverage,
    summarize_theme_coverage,
)

_HISTORY_LIMIT = 100
MAX_PUBLIC_RECORDS = 20_000
MAX_PREVIEW_ROWS = 64
_DEFAULT_READ_MODEL = "library.games"


@dataclass
class _EditSession:
    session_id: str
    data: dict[str, Any]
    saved_payload: bytes | None
    undo_stack: list[dict[str, Any]] = field(default_factory=list)
    redo_stack: list[dict[str, Any]] = field(default_factory=list)
    generation: int = 0


class JourneyStudioService:
    """Create/edit/save journeys without exposing mutable validated documents.

    Mutations use an allowlisted operation vocabulary and full JSON snapshots.
    The same document schema and ``JourneyStore`` are used for local persistence,
    export/import and runtime validation.
    """

    def __init__(self, root: Path) -> None:
        self._store = JourneyStore(root)
        self._root = root
        self._sessions: dict[str, _EditSession] = {}
        self._lock = threading.RLock()

    def list(self) -> list[dict[str, str]]:
        if self._root.is_symlink() or not self._root.is_dir():
            return []
        journeys: list[dict[str, str]] = []
        for path in sorted(self._root.glob("*.journey.json")):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                document = JourneyDocument.parse(path.read_bytes())
            except (OSError, ValueError):
                continue
            journeys.append({"id": document.id, "name": str(document.data["name"])})
        return journeys

    def create(
        self, *, name: str = "Minha jornada", journey_id: str | None = None
    ) -> dict[str, Any]:
        identity = journey_id or f"org.steamzero.journey-{secrets.token_hex(4)}"
        home_id = "home"
        raw = {
            "schemaVersion": 2,
            "kind": "steamzero-experience-journey-v2",
            "id": identity,
            "name": name,
            "entryMenuId": home_id,
            "organization": [
                {
                    "id": "menu-home",
                    "kind": "menu",
                    "label": "Início",
                    "parentId": None,
                    "menuId": home_id,
                }
            ],
            "menus": [
                {
                    "id": home_id,
                    "name": "Início",
                    "source": {"readModelId": _DEFAULT_READ_MODEL},
                    "filters": [],
                    "sort": [],
                    "groupBy": [],
                }
            ],
            "connections": [],
            "sessionStages": [],
        }
        return self._open(raw, saved_payload=None)

    def load(self, journey_id: str) -> dict[str, Any]:
        document = self._store.load(journey_id)
        return self._open(dict(document.data), saved_payload=document.serialize())

    def import_copy(self, bundle: bytes, *, copy_name: str) -> dict[str, Any]:
        copy_id = f"org.steamzero.copy-{secrets.token_hex(4)}"
        document = self._store.import_copy(bundle, copy_id=copy_id, copy_name=copy_name)
        snapshot = self._open(dict(document.data), saved_payload=None)
        snapshot["dependencies"] = [
            {
                "themeId": theme_id,
                "version": None,
                "state": "version-not-declared",
            }
            for theme_id in self._theme_dependency_ids(document)
        ]
        snapshot["packageContents"] = ["experience.json"]
        return snapshot

    def import_file(self, source: Path, *, copy_name: str) -> dict[str, Any]:
        if source.is_symlink():
            raise ValueError("pacote selecionado não pode ser link simbólico")
        try:
            descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except OSError as exc:
            raise ValueError("não foi possível abrir o pacote selecionado") from exc
        with os.fdopen(descriptor, "rb") as stream:
            if os.fstat(stream.fileno()).st_size > MAX_DOCUMENT_BYTES + 65536:
                raise JourneyBudgetError(
                    "JOURNEY-BUDGET-ARCHIVE",
                    "pacote de jornada excede o limite compactado publicado",
                )
            bundle = stream.read(MAX_DOCUMENT_BYTES + 65537)
        if len(bundle) > MAX_DOCUMENT_BYTES + 65536:
            raise JourneyBudgetError(
                "JOURNEY-BUDGET-ARCHIVE",
                "pacote de jornada excede o limite compactado publicado",
            )
        return self.import_copy(bundle, copy_name=copy_name)

    def export_copy(self, session_id: str) -> bytes:
        document = self._document(session_id)
        document.ensure_activatable()
        return self._store.export_copy(document)

    def preview_menu(
        self,
        session_id: str,
        menu_id: str,
        *,
        rows: builtins.list[dict[str, Any]] | None,
        published_fields: dict[str, str],
        published_read_models: Mapping[str, Iterable[str] | Mapping[str, str]] | None = None,
        context_filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Preview a menu using caller-supplied, already-public projected rows."""
        document = self._document(session_id)
        document.ensure_activatable(published_read_models)
        menu = self._menu(dict(document.data), menu_id)
        derived_filters = [
            {"fieldId": field_id, "operator": "equals", "value": value}
            for field_id, value in (context_filters or {}).items()
        ]
        result = query_public_records(
            rows,
            [*menu["filters"], *derived_filters],
            published_fields=published_fields,
            sort=menu["sort"],
            group_by=menu.get("groupBy", []),
        )
        preview_rows = [dict(row) for row in result.rows[:MAX_PREVIEW_ROWS]]
        groups = [
            {"values": dict(group["values"]), "count": int(group["count"])}
            for group in result.groups[:MAX_PREVIEW_ROWS]
        ]
        truncated = result.result_count > len(preview_rows)
        return {
            "menuId": menu_id,
            "readModelId": menu["source"]["readModelId"],
            "sourceState": result.source_state,
            "resultState": result.result_state,
            "rows": preview_rows,
            "totalCount": result.total_count,
            "resultCount": result.result_count,
            "returnedCount": len(preview_rows),
            "previewLimit": MAX_PREVIEW_ROWS,
            "truncated": truncated,
            "groups": groups,
            "groupsTruncated": len(result.groups) > len(groups),
            "unknownValueCounts": dict(result.unknown_value_counts),
            "recoveryAction": ("refine-filters" if truncated else result.recovery_action),
            "diagnosticCode": (
                "JOURNEY-PREVIEW-TRUNCATED" if truncated else result.diagnostic_code
            ),
            "diagnosticMessage": (
                f"Prévia limitada a {MAX_PREVIEW_ROWS} de {result.result_count} registros."
                if truncated
                else result.diagnostic_message
            ),
        }

    def coverage(
        self,
        session_id: str,
        *,
        used_stages: builtins.list[str],
        themes: dict[str, dict[str, Any]],
        aura_version: str,
        required_theme_capabilities: dict[str, builtins.list[str]] | None = None,
        adapter_capabilities: builtins.list[str] | None = None,
        operation_requirements: dict[str, builtins.list[str]] | None = None,
    ) -> dict[str, Any]:
        document = self._document(session_id)
        coverage = resolve_theme_coverage(
            document,
            used_stages=used_stages,
            themes=themes,
            aura_version=aura_version,
            required_theme_capabilities=required_theme_capabilities,
            adapter_capabilities=adapter_capabilities,
            operation_requirements=operation_requirements,
        )
        return {"stages": coverage, "summary": summarize_theme_coverage(coverage)}

    def snapshot(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._session(session_id)
            payload = self._serialize(session.data)
            diagnostics = [item.to_dict() for item in self._document(session_id).diagnostics()]
            return {
                "sessionId": session.session_id,
                "generation": session.generation,
                "document": deepcopy(session.data),
                "isNew": session.saved_payload is None,
                "dirty": session.saved_payload is None or payload != session.saved_payload,
                "history": {
                    "canUndo": bool(session.undo_stack),
                    "canRedo": bool(session.redo_stack),
                    "undoDepth": len(session.undo_stack),
                    "redoDepth": len(session.redo_stack),
                },
                "diagnostics": diagnostics,
                "budgets": {
                    "maxDocumentBytes": MAX_DOCUMENT_BYTES,
                    "maxMenus": MAX_MENUS,
                    "maxConnections": MAX_CONNECTIONS,
                    "maxOrganizationNodes": MAX_ORGANIZATION_NODES,
                    "maxFiltersPerMenu": MAX_FILTERS_PER_MENU,
                    "maxNavigationHistory": MAX_NAVIGATION_HISTORY,
                    "maxUndoEntries": _HISTORY_LIMIT,
                    "maxPublicRecords": MAX_PUBLIC_RECORDS,
                    "maxPreviewRows": MAX_PREVIEW_ROWS,
                },
            }

    def transact(
        self,
        session_id: str,
        operation: str,
        payload: dict[str, Any],
        *,
        expected_generation: int | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            session = self._session(session_id)
            if expected_generation is not None and expected_generation != session.generation:
                raise ValueError("rascunho mudou; recarregue antes de aplicar esta edição")
            candidate = deepcopy(session.data)
            self._apply_operation(candidate, operation, payload)
            document = JourneyDocument.parse(candidate)
            serialized = document.serialize()
            if serialized != self._serialize(session.data):
                session.undo_stack.append(deepcopy(session.data))
                if len(session.undo_stack) > _HISTORY_LIMIT:
                    del session.undo_stack[0]
                session.redo_stack.clear()
                session.data = dict(document.data)
                session.generation += 1
            return self.snapshot(session_id)

    def undo(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._session(session_id)
            if session.undo_stack:
                session.redo_stack.append(deepcopy(session.data))
                session.data = session.undo_stack.pop()
                session.generation += 1
            return self.snapshot(session_id)

    def redo(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._session(session_id)
            if session.redo_stack:
                session.undo_stack.append(deepcopy(session.data))
                session.data = session.redo_stack.pop()
                session.generation += 1
            return self.snapshot(session_id)

    def save(self, session_id: str, *, overwrite: bool = False) -> dict[str, Any]:
        with self._lock:
            session = self._session(session_id)
            document = self._document(session_id)
            path = self._store.save(document, overwrite=overwrite)
            session.saved_payload = document.serialize()
            return {
                "status": "saved",
                "journeyId": document.id,
                "pathName": path.name,
                "snapshot": self.snapshot(session_id),
            }

    def close(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def _open(self, raw: dict[str, Any], *, saved_payload: bytes | None) -> dict[str, Any]:
        document = JourneyDocument.parse(raw)
        session_id = secrets.token_urlsafe(18)
        with self._lock:
            self._sessions[session_id] = _EditSession(
                session_id=session_id,
                data=dict(document.data),
                saved_payload=saved_payload,
            )
        return self.snapshot(session_id)

    def _session(self, session_id: str) -> _EditSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise ValueError("sessão de autoria de jornada não existe ou expirou")
        return session

    def _document(self, session_id: str) -> JourneyDocument:
        return JourneyDocument.parse(self._session(session_id).data)

    @staticmethod
    def _serialize(data: dict[str, Any]) -> bytes:
        return json.dumps(
            data, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        ).encode("utf-8")

    @staticmethod
    def _theme_dependency_ids(document: JourneyDocument) -> builtins.list[str]:
        themes: set[str] = set()
        for menu in document.data["menus"]:
            appearance = menu.get("appearance", {})
            if appearance.get("mode") == "custom":
                themes.add(str(appearance["themeId"]))
        for stage in document.data["sessionStages"]:
            appearance = stage.get("appearance", {})
            if appearance.get("mode") == "custom":
                themes.add(str(appearance["themeId"]))
        return sorted(themes)

    @staticmethod
    def _menu(data: dict[str, Any], menu_id: str) -> dict[str, Any]:
        for menu in data["menus"]:
            if menu["id"] == menu_id:
                return cast(dict[str, Any], menu)
        raise ValueError(f"menu não existe: {menu_id}")

    def _apply_operation(
        self, data: dict[str, Any], operation: str, payload: dict[str, Any]
    ) -> None:
        if operation == "rename-journey":
            data["name"] = payload["name"]
        elif operation == "add-menu":
            menu = deepcopy(payload["menu"])
            menu_id = str(menu["id"])
            if any(item["id"] == menu_id for item in data["menus"]):
                raise ValueError(f"ID de menu já existe: {menu_id}")
            data["menus"].append(menu)
            data["organization"].append(
                {
                    "id": str(payload.get("organizationId", f"menu-{menu_id}")),
                    "kind": "menu",
                    "label": str(menu["name"]),
                    "parentId": payload.get("parentId"),
                    "menuId": menu_id,
                }
            )
        elif operation == "duplicate-menu":
            source = self._menu(data, str(payload["menuId"]))
            menu = deepcopy(source)
            menu["id"] = str(payload["newId"])
            menu["name"] = str(payload["name"])
            data["menus"].append(menu)
            data["organization"].append(
                {
                    "id": str(payload.get("organizationId", f"menu-{menu['id']}")),
                    "kind": "menu",
                    "label": menu["name"],
                    "parentId": payload.get("parentId"),
                    "menuId": menu["id"],
                }
            )
        elif operation == "rename-menu":
            menu_id = str(payload["menuId"])
            name = str(payload["name"])
            self._menu(data, menu_id)["name"] = name
            for node in data["organization"]:
                if node["kind"] == "menu" and node["menuId"] == menu_id:
                    node["label"] = name
        elif operation == "remove-menu":
            menu_id = str(payload["menuId"])
            if len(data["menus"]) == 1:
                raise ValueError("a jornada precisa manter pelo menos um menu")
            self._menu(data, menu_id)
            menu_nodes = [
                node
                for node in data["organization"]
                if node["kind"] == "menu" and node["menuId"] == menu_id
            ]
            menu_node_ids = {str(node["id"]) for node in menu_nodes}
            replacement_id = payload.get("replacementMenuId")
            replacement_nodes: list[dict[str, Any]] = []
            if replacement_id is not None:
                replacement_id = str(replacement_id)
                if replacement_id == menu_id:
                    raise ValueError("o menu de substituição precisa ser diferente")
                self._menu(data, replacement_id)
                replacement_nodes = [
                    node
                    for node in data["organization"]
                    if node["kind"] == "menu" and node["menuId"] == replacement_id
                ]

            affected_connections = [
                connection
                for connection in data["connections"]
                if any(
                    endpoint.get("kind") == "menu" and endpoint.get("id") == menu_id
                    for endpoint in (connection["from"], connection["to"])
                )
            ]
            affected_children = [
                node for node in data["organization"] if node.get("parentId") in menu_node_ids
            ]
            is_entry = data["entryMenuId"] == menu_id
            if (affected_connections or affected_children or is_entry) and replacement_id is None:
                raise ValueError(
                    "menu referenciado; escolha um destino de substituição para "
                    "preservar conexões e filhos"
                )

            if replacement_id is not None:
                for connection in data["connections"]:
                    for endpoint in (connection["from"], connection["to"]):
                        if endpoint.get("kind") == "menu" and endpoint.get("id") == menu_id:
                            endpoint["id"] = replacement_id
                replacement_parent = str(replacement_nodes[0]["id"]) if replacement_nodes else None
                for child in affected_children:
                    child["parentId"] = replacement_parent
                if is_entry:
                    data["entryMenuId"] = replacement_id

            data["menus"] = [menu for menu in data["menus"] if menu["id"] != menu_id]
            data["organization"] = [
                node
                for node in data["organization"]
                if not (node["kind"] == "menu" and node["menuId"] == menu_id)
            ]
        elif operation == "reorder-menus":
            order = [str(value) for value in payload["menuIds"]]
            current = {str(menu["id"]): menu for menu in data["menus"]}
            if len(order) != len(current) or set(order) != set(current):
                raise ValueError("a ordem precisa conter cada menu exatamente uma vez")
            data["menus"] = [current[menu_id] for menu_id in order]
            by_menu: dict[str, list[dict[str, Any]]] = {}
            for node in data["organization"]:
                if node["kind"] == "menu":
                    by_menu.setdefault(str(node["menuId"]), []).append(node)
            menu_nodes = [node for menu_id in order for node in by_menu.get(menu_id, [])]
            next_nodes: list[dict[str, Any]] = []
            menu_iter = iter(menu_nodes)
            for node in data["organization"]:
                if node["kind"] == "menu":
                    try:
                        next_nodes.append(next(menu_iter))
                    except StopIteration:
                        next_nodes.append(node)
                else:
                    next_nodes.append(node)
            data["organization"] = next_nodes
        elif operation == "set-entry-menu":
            data["entryMenuId"] = str(payload["menuId"])
        elif operation == "set-source":
            menu = self._menu(data, str(payload["menuId"]))
            menu["source"] = {"readModelId": str(payload["readModelId"])}
        elif operation == "add-connection":
            data["connections"].append(deepcopy(payload["connection"]))
        elif operation == "remove-connection":
            connection_id = str(payload["connectionId"])
            before = len(data["connections"])
            data["connections"] = [
                item for item in data["connections"] if item["id"] != connection_id
            ]
            if len(data["connections"]) == before:
                raise ValueError(f"conexão não existe: {connection_id}")
        elif operation in {"set-filters", "set-sort", "set-group-by"}:
            menu = self._menu(data, str(payload["menuId"]))
            key = {
                "set-filters": "filters",
                "set-sort": "sort",
                "set-group-by": "groupBy",
            }[operation]
            menu[key] = deepcopy(payload["values"])
        elif operation == "set-menu-appearance":
            menu = self._menu(data, str(payload["menuId"]))
            appearance = payload.get("appearance")
            if appearance is None:
                menu.pop("appearance", None)
            else:
                menu["appearance"] = deepcopy(appearance)
        elif operation == "set-stage-appearance":
            stage_id = str(payload["stageId"])
            stage = next(
                (item for item in data["sessionStages"] if item["stageId"] == stage_id),
                None,
            )
            appearance = payload.get("appearance")
            if appearance is None:
                data["sessionStages"] = [
                    item for item in data["sessionStages"] if item["stageId"] != stage_id
                ]
            elif stage is None:
                data["sessionStages"].append(
                    {"stageId": stage_id, "appearance": deepcopy(appearance)}
                )
            else:
                stage["appearance"] = deepcopy(appearance)
        else:
            raise ValueError(f"operação de autoria não permitida: {operation}")
