# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Versioned journey documents, graph diagnostics, metadata filters and context.

This module only resolves declarative experience data. Session operations remain
owned by the session domain and its adapters; menu links cannot start processes.
"""

from __future__ import annotations

import json
import os
import re
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, TypeAlias
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from steamzero.api import contracts
from steamzero.core import fs

SCHEMA = "experience-journey-v1.schema.json"
MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
MAX_MENUS = 4096
MAX_CONNECTIONS = 16384
MAX_ORGANIZATION_NODES = 8192
MAX_FILTERS_PER_MENU = 64
MAX_NAVIGATION_HISTORY = 512
SESSION_STAGES = frozenset(
    {
        "entryFade",
        "gameplay",
        "pause",
        "saves",
        "bezel",
        "osd",
        "exitFade",
        "loading",
        "empty",
        "error",
        "offline",
    }
)
_INPUT_ONLY = "user-input"
JsonScalar: TypeAlias = str | int | float | bool | None


@dataclass(frozen=True)
class JourneyDiagnostic:
    code: str
    message: str
    subject_id: str = ""
    severity: str = "error"

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "subjectId": self.subject_id,
            "severity": self.severity,
        }


class JourneyBudgetError(ValueError):
    """A document or navigation operation exceeded a published resource cap."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class JourneyRouteError(ValueError):
    """A requested menu transition does not target a declared menu."""


class PublicFieldUnavailable(ValueError):
    """A filter names a field absent from the selected public read model."""


class JourneyFilterTypeError(ValueError):
    """A declarative filter does not match the published field type."""


def _encoded_size(value: object) -> int:
    return len(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


class JourneyStore:
    """Atomic local persistence and document-only export/import as a copy."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, journey_id: str) -> Path:
        if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)+", journey_id):
            raise ValueError("ID de jornada inválido")
        return self.root / f"{journey_id}.journey.json"

    def save(self, document: JourneyDocument, *, overwrite: bool = False) -> Path:
        if self.root.is_symlink():
            raise ValueError("diretório das jornadas não pode ser link simbólico")
        target = self._path(document.id)
        if target.is_symlink():
            raise ValueError("destino da jornada não pode ser link simbólico")
        fs.write_atomic(target, document.serialize(), must_not_exist=not overwrite)
        return target

    def load(self, journey_id: str) -> JourneyDocument:
        path = self._path(journey_id)
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except OSError as exc:
            if path.is_symlink():
                raise ValueError("documento da jornada não pode ser link simbólico") from exc
            raise
        with os.fdopen(descriptor, "rb") as stream:
            if os.fstat(stream.fileno()).st_size > MAX_DOCUMENT_BYTES:
                raise JourneyBudgetError(
                    "JOURNEY-BUDGET-DOCUMENT",
                    f"documento excede {MAX_DOCUMENT_BYTES} bytes UTF-8",
                )
            payload = stream.read(MAX_DOCUMENT_BYTES + 1)
        if len(payload) > MAX_DOCUMENT_BYTES:
            raise JourneyBudgetError(
                "JOURNEY-BUDGET-DOCUMENT",
                f"documento excede {MAX_DOCUMENT_BYTES} bytes UTF-8",
            )
        return JourneyDocument.parse(payload)

    @staticmethod
    def export_copy(document: JourneyDocument) -> bytes:
        """Export the journey sidecar; referenced themes remain explicit dependencies."""
        buffer = BytesIO()
        with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("experience.json", document.serialize())
        return buffer.getvalue()

    @staticmethod
    def import_copy(bundle: bytes, *, copy_id: str, copy_name: str) -> JourneyDocument:
        if len(bundle) > MAX_DOCUMENT_BYTES + 65536:
            raise JourneyBudgetError(
                "JOURNEY-BUDGET-ARCHIVE",
                "pacote de jornada excede o limite compactado publicado",
            )
        try:
            with ZipFile(BytesIO(bundle), mode="r") as archive:
                entries = archive.infolist()
                if len(entries) != 1 or entries[0].filename != "experience.json":
                    raise ValueError("pacote deve conter somente experience.json")
                if entries[0].file_size > MAX_DOCUMENT_BYTES:
                    raise JourneyBudgetError(
                        "JOURNEY-BUDGET-DOCUMENT",
                        f"documento excede {MAX_DOCUMENT_BYTES} bytes UTF-8",
                    )
                raw = json.loads(archive.read(entries[0]).decode("utf-8"))
        except BadZipFile as exc:
            raise ValueError("pacote de jornada inválido") from exc
        if not isinstance(raw, dict):
            raise ValueError("documento de jornada exige objeto raiz")
        raw["id"] = copy_id
        raw["name"] = copy_name
        return JourneyDocument.parse(raw)


@dataclass(frozen=True)
class JourneyDocument:
    """A schema-validated, round-trippable journey document."""

    data: Mapping[str, Any]

    @classmethod
    def parse(cls, payload: Mapping[str, Any] | str | bytes) -> JourneyDocument:
        if isinstance(payload, bytes):
            if len(payload) > MAX_DOCUMENT_BYTES:
                raise JourneyBudgetError(
                    "JOURNEY-BUDGET-DOCUMENT",
                    f"documento excede {MAX_DOCUMENT_BYTES} bytes UTF-8",
                )
            try:
                raw = json.loads(payload.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("documento de jornada não é JSON UTF-8 válido") from exc
        elif isinstance(payload, str):
            encoded = payload.encode("utf-8")
            if len(encoded) > MAX_DOCUMENT_BYTES:
                raise JourneyBudgetError(
                    "JOURNEY-BUDGET-DOCUMENT",
                    f"documento excede {MAX_DOCUMENT_BYTES} bytes UTF-8",
                )
            try:
                raw = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ValueError("documento de jornada não é JSON válido") from exc
        else:
            raw = dict(payload)
            if _encoded_size(raw) > MAX_DOCUMENT_BYTES:
                raise JourneyBudgetError(
                    "JOURNEY-BUDGET-DOCUMENT",
                    f"documento excede {MAX_DOCUMENT_BYTES} bytes UTF-8",
                )
        if not isinstance(raw, dict):
            raise ValueError("documento de jornada exige objeto raiz")
        contracts.validate(raw, SCHEMA)
        document = cls(data=json.loads(json.dumps(raw, ensure_ascii=False)))
        document.serialize()
        budget_errors = [
            issue
            for issue in document.diagnostics()
            if issue.code.startswith("JOURNEY-BUDGET-") and issue.severity == "error"
        ]
        if budget_errors:
            raise JourneyBudgetError(budget_errors[0].code, budget_errors[0].message)
        return document

    @property
    def id(self) -> str:
        return str(self.data["id"])

    @property
    def entry_menu_id(self) -> str:
        return str(self.data["entryMenuId"])

    @property
    def menus(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.data["menus"])

    @property
    def menu_ids(self) -> frozenset[str]:
        return frozenset(str(menu["id"]) for menu in self.menus)

    def serialize(self) -> bytes:
        raw = json.dumps(self.data, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        if len(raw) > MAX_DOCUMENT_BYTES:
            raise JourneyBudgetError(
                "JOURNEY-BUDGET-DOCUMENT",
                f"documento serializado excede {MAX_DOCUMENT_BYTES} bytes UTF-8",
            )
        return raw

    def diagnostics(
        self,
        published_read_models: Mapping[str, Iterable[str]] | None = None,
    ) -> tuple[JourneyDiagnostic, ...]:
        return validate_journey(self.data, published_read_models=published_read_models)


def _unique_ids(
    items: Sequence[Mapping[str, Any]], key: str, label: str
) -> list[JourneyDiagnostic]:
    seen: set[str] = set()
    duplicate: set[str] = set()
    for item in items:
        value = str(item.get(key, ""))
        if value in seen:
            duplicate.add(value)
        seen.add(value)
    return [
        JourneyDiagnostic(f"JOURNEY-ID-DUPLICATE-{label}", f"ID duplicado: {value}", value)
        for value in sorted(duplicate)
    ]


def _endpoint_id(endpoint: Mapping[str, Any]) -> str | None:
    kind = endpoint.get("kind")
    if kind == "history":
        return None
    return f"{kind}:{endpoint.get('id', '')}"


def _automatic_cycle(connections: Sequence[Mapping[str, Any]]) -> bool:
    adjacency: dict[str, set[str]] = {}
    indegree: dict[str, int] = {}
    for connection in connections:
        if connection.get("when") == _INPUT_ONLY:
            continue
        source = connection.get("from")
        target = connection.get("to")
        if not isinstance(source, Mapping) or not isinstance(target, Mapping):
            continue
        source_id, target_id = _endpoint_id(source), _endpoint_id(target)
        if source_id is None or target_id is None:
            continue
        adjacency.setdefault(source_id, set())
        adjacency.setdefault(target_id, set())
        if target_id not in adjacency[source_id]:
            adjacency[source_id].add(target_id)
            indegree[target_id] = indegree.get(target_id, 0) + 1
        indegree.setdefault(source_id, indegree.get(source_id, 0))
    queue = deque(node for node in adjacency if indegree.get(node, 0) == 0)
    visited = 0
    while queue:
        current = queue.popleft()
        visited += 1
        for target in adjacency[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    return visited != len(adjacency)


def _organization_cycle(nodes: Sequence[Mapping[str, Any]]) -> bool:
    parents = {str(node.get("id", "")): node.get("parentId") for node in nodes}
    state: dict[str, int] = {}
    for start in parents:
        if state.get(start) == 2:
            continue
        chain: list[str] = []
        current: str | None = start
        while current is not None and current in parents and state.get(current, 0) == 0:
            state[current] = 1
            chain.append(current)
            parent = parents[current]
            current = str(parent) if parent is not None else None
        if current is not None and state.get(current) == 1:
            return True
        for node_id in chain:
            state[node_id] = 2
    return False


def _field_definitions(fields: Iterable[str] | Mapping[str, str]) -> dict[str, str]:
    if isinstance(fields, Mapping):
        return {str(field_id): str(field_type) for field_id, field_type in fields.items()}
    return {str(field_id): "any" for field_id in fields}


def _value_matches_type(value: object, field_type: str) -> bool:
    if value is None or field_type == "any":
        return True
    if field_type == "string":
        return isinstance(value, str)
    if field_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if field_type == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if field_type == "boolean":
        return isinstance(value, bool)
    if field_type == "string[]":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    return False


def _filter_type_error(item_filter: Mapping[str, Any], field_type: str) -> str:
    operator = str(item_filter.get("operator", ""))
    value = item_filter.get("value")
    if operator in {"isKnown", "isUnknown"}:
        return ""
    if operator in {"greaterThanOrEqual", "lessThanOrEqual"} and field_type not in {
        "integer",
        "number",
        "any",
    }:
        return f"operador {operator} exige campo numérico, mas {field_type} foi publicado"
    if operator == "contains":
        if field_type not in {"string", "string[]", "any"}:
            return f"operador contains não é compatível com o tipo {field_type}"
        if field_type in {"string", "string[]"} and not isinstance(value, str):
            return "contains exige texto, mas o valor fornecido não é texto"
        return ""
    if operator == "oneOf":
        if not isinstance(value, list) or not all(
            _value_matches_type(item, field_type) for item in value
        ):
            return f"os valores de oneOf não correspondem ao tipo publicado {field_type}"
    elif not _value_matches_type(value, field_type):
        return f"o valor do filtro não corresponde ao tipo publicado {field_type}"
    return ""


def validate_journey(
    raw: Mapping[str, Any],
    *,
    published_read_models: Mapping[str, Iterable[str] | Mapping[str, str]] | None = None,
) -> tuple[JourneyDiagnostic, ...]:
    """Report graph, source and resource problems without executing document code."""
    menus = raw.get("menus", [])
    connections = raw.get("connections", [])
    organization = raw.get("organization", [])
    session_stages = raw.get("sessionStages", [])
    if not all(
        isinstance(value, list) for value in (menus, connections, organization, session_stages)
    ):
        return (JourneyDiagnostic("JOURNEY-SHAPE-LIST", "coleções da jornada devem ser listas"),)

    issues: list[JourneyDiagnostic] = []
    if len(menus) > MAX_MENUS:
        issues.append(
            JourneyDiagnostic(
                "JOURNEY-BUDGET-MENUS",
                f"limite de recurso: até {MAX_MENUS} menus por documento",
            )
        )
    if len(connections) > MAX_CONNECTIONS:
        issues.append(
            JourneyDiagnostic(
                "JOURNEY-BUDGET-CONNECTIONS",
                f"limite de recurso: até {MAX_CONNECTIONS} conexões por documento",
            )
        )
    if len(organization) > MAX_ORGANIZATION_NODES:
        issues.append(
            JourneyDiagnostic(
                "JOURNEY-BUDGET-ORGANIZATION",
                f"limite de recurso: até {MAX_ORGANIZATION_NODES} itens organizacionais",
            )
        )
    issues.extend(_unique_ids(menus, "id", "MENU"))
    issues.extend(_unique_ids(connections, "id", "CONNECTION"))
    issues.extend(_unique_ids(organization, "id", "ORGANIZATION"))
    issues.extend(_unique_ids(session_stages, "stageId", "STAGE"))
    for menu in menus:
        if len(menu.get("filters", [])) > MAX_FILTERS_PER_MENU:
            issues.append(
                JourneyDiagnostic(
                    "JOURNEY-BUDGET-FILTERS",
                    f"limite de recurso: até {MAX_FILTERS_PER_MENU} filtros por menu",
                    str(menu.get("id", "")),
                )
            )

    menu_ids = {str(menu.get("id", "")) for menu in menus}
    if raw.get("entryMenuId") not in menu_ids:
        issues.append(
            JourneyDiagnostic(
                "JOURNEY-ENTRY-MISSING",
                "menu de entrada não existe; escolha ou recrie um destino",
                str(raw.get("entryMenuId", "")),
            )
        )

    for connection in connections:
        connection_id = str(connection.get("id", ""))
        for side in ("from", "to"):
            endpoint = connection.get(side)
            if not isinstance(endpoint, Mapping):
                continue
            kind, target_id = endpoint.get("kind"), str(endpoint.get("id", ""))
            exists = kind == "menu" and target_id in menu_ids
            exists = exists or (kind == "stage" and target_id in SESSION_STAGES)
            exists = exists or kind == "history"
            if not exists:
                issues.append(
                    JourneyDiagnostic(
                        "JOURNEY-REFERENCE-MISSING",
                        f"destino {kind}:{target_id} não existe; reconecte a ação",
                        connection_id,
                    )
                )
    if _automatic_cycle(connections):
        issues.append(
            JourneyDiagnostic(
                "JOURNEY-AUTOMATIC-CYCLE",
                "ciclo automático pode não terminar; adicione uma saída ou torne a ação manual",
            )
        )

    organization_ids = {str(node.get("id", "")) for node in organization}
    for node in organization:
        node_id = str(node.get("id", ""))
        parent_id = node.get("parentId")
        if parent_id is not None and str(parent_id) not in organization_ids:
            issues.append(
                JourneyDiagnostic(
                    "JOURNEY-ORGANIZATION-PARENT-MISSING",
                    "grupo organizacional não existe; mova o item para um grupo válido",
                    node_id,
                )
            )
        if node.get("kind") == "menu" and str(node.get("menuId", "")) not in menu_ids:
            issues.append(
                JourneyDiagnostic(
                    "JOURNEY-ORGANIZATION-MENU-MISSING",
                    "menu da árvore não existe; escolha um menu válido",
                    node_id,
                )
            )
    if _organization_cycle(organization):
        issues.append(
            JourneyDiagnostic(
                "JOURNEY-ORGANIZATION-CYCLE",
                "a árvore organizacional contém um ciclo; reorganize os grupos",
            )
        )

    if published_read_models is not None:
        for menu in menus:
            menu_id = str(menu.get("id", ""))
            source = menu.get("source", {})
            read_model_id = str(source.get("readModelId", ""))
            available = published_read_models.get(read_model_id)
            if available is None:
                issues.append(
                    JourneyDiagnostic(
                        "JOURNEY-READ-MODEL-UNAVAILABLE",
                        f"fonte pública {read_model_id} indisponível; escolha uma fonte publicada",
                        menu_id,
                        "warning",
                    )
                )
                continue
            fields = _field_definitions(available)
            for item_filter in menu.get("filters", []):
                field_id = str(item_filter.get("fieldId", ""))
                if field_id not in fields:
                    issues.append(
                        JourneyDiagnostic(
                            "JOURNEY-FIELD-UNAVAILABLE",
                            f"campo publicado {field_id} não existe nessa fonte; "
                            "remova ou substitua o filtro",
                            menu_id,
                            "warning",
                        )
                    )
                else:
                    reason = _filter_type_error(item_filter, fields[field_id])
                    if reason:
                        issues.append(
                            JourneyDiagnostic(
                                "JOURNEY-FILTER-TYPE",
                                f"{field_id}: {reason}; ajuste o filtro",
                                menu_id,
                                "warning",
                            )
                        )
            for sort in menu.get("sort", []):
                field_id = str(sort.get("fieldId", ""))
                if field_id not in fields:
                    issues.append(
                        JourneyDiagnostic(
                            "JOURNEY-SORT-FIELD-UNAVAILABLE",
                            f"campo publicado {field_id} não existe nessa fonte; "
                            "escolha outro campo",
                            menu_id,
                            "warning",
                        )
                    )
    return tuple(issues)


def _matches_filter(
    record_value: object,
    operator: str,
    expected: object,
) -> bool:
    if operator == "isKnown":
        return record_value is not None
    if operator == "isUnknown":
        return record_value is None
    if record_value is None:
        return False
    if operator == "equals":
        return record_value == expected
    if operator == "notEquals":
        return record_value != expected
    if operator == "oneOf":
        return isinstance(expected, list) and record_value in expected
    if operator == "contains":
        if isinstance(record_value, str) and isinstance(expected, str):
            return expected.casefold() in record_value.casefold()
        if isinstance(record_value, list | tuple | set):
            return expected in record_value
        return False
    if operator == "greaterThanOrEqual":
        return (
            isinstance(record_value, int | float)
            and not isinstance(record_value, bool)
            and isinstance(expected, int | float)
            and not isinstance(expected, bool)
            and record_value >= expected
        )
    if operator == "lessThanOrEqual":
        return (
            isinstance(record_value, int | float)
            and not isinstance(record_value, bool)
            and isinstance(expected, int | float)
            and not isinstance(expected, bool)
            and record_value <= expected
        )
    return False


def filter_public_records(
    rows: Iterable[Mapping[str, Any]],
    filters: Sequence[Mapping[str, Any]],
    *,
    published_field_ids: Iterable[str] | Mapping[str, str],
) -> list[Mapping[str, Any]]:
    """Apply declarative AND filters to a published, already-projected read model."""
    fields = _field_definitions(published_field_ids)
    allowed = frozenset(fields)
    missing = sorted({str(item.get("fieldId", "")) for item in filters} - allowed)
    if missing:
        raise PublicFieldUnavailable(
            "campo(s) não publicado(s) para esta fonte: " + ", ".join(missing)
        )
    for item_filter in filters:
        field_id = str(item_filter["fieldId"])
        reason = _filter_type_error(item_filter, fields[field_id])
        if reason:
            raise JourneyFilterTypeError(f"{field_id}: {reason}")
    return [
        row
        for row in rows
        if all(
            _matches_filter(
                row.get(str(item["fieldId"])),
                str(item["operator"]),
                item.get("value"),
            )
            for item in filters
        )
    ]


@dataclass(frozen=True)
class PublicQueryResult:
    source_state: str
    result_state: str
    rows: tuple[Mapping[str, Any], ...]
    total_count: int
    result_count: int
    unknown_value_counts: Mapping[str, int]
    recovery_action: str
    diagnostic_code: str = ""
    diagnostic_message: str = ""


def query_public_records(
    rows: Iterable[Mapping[str, Any]] | None,
    filters: Sequence[Mapping[str, Any]],
    *,
    published_fields: Iterable[str] | Mapping[str, str],
) -> PublicQueryResult:
    """Return explicit empty/source/error states for a public menu query."""
    if rows is None:
        return PublicQueryResult(
            source_state="unavailable",
            result_state="source-unavailable",
            rows=(),
            total_count=0,
            result_count=0,
            unknown_value_counts={},
            recovery_action="retry-source",
            diagnostic_code="JOURNEY-READ-MODEL-UNAVAILABLE",
            diagnostic_message=(
                "A fonte de dados não respondeu; tente novamente ou escolha outra fonte."
            ),
        )
    records = tuple(rows)
    field_types = _field_definitions(published_fields)
    unknown_counts = {
        field_id: sum(1 for row in records if row.get(field_id) is None) for field_id in field_types
    }
    try:
        result_rows = filter_public_records(
            records,
            filters,
            published_field_ids=field_types,
        )
    except PublicFieldUnavailable as exc:
        return PublicQueryResult(
            source_state="available",
            result_state="invalid-filter",
            rows=(),
            total_count=len(records),
            result_count=0,
            unknown_value_counts=unknown_counts,
            recovery_action="replace-filter",
            diagnostic_code="JOURNEY-FIELD-UNAVAILABLE",
            diagnostic_message=str(exc),
        )
    except JourneyFilterTypeError as exc:
        return PublicQueryResult(
            source_state="available",
            result_state="invalid-filter",
            rows=(),
            total_count=len(records),
            result_count=0,
            unknown_value_counts=unknown_counts,
            recovery_action="adjust-filter-type",
            diagnostic_code="JOURNEY-FILTER-TYPE",
            diagnostic_message=str(exc),
        )
    return PublicQueryResult(
        source_state="available",
        result_state="results" if result_rows else "zero-results",
        rows=tuple(result_rows),
        total_count=len(records),
        result_count=len(result_rows),
        unknown_value_counts=unknown_counts,
        recovery_action="" if result_rows else "clear-filters",
    )


@dataclass(frozen=True)
class JourneyNavigationContext:
    menu_id: str
    selected_item_id: str | None = None
    filters: tuple[tuple[str, JsonScalar], ...] = ()
    scroll_position: float = 0.0
    focus_id: str | None = None


@dataclass(frozen=True)
class JourneyReturnContext:
    context: JourneyNavigationContext
    generation: int


class JourneyNavigator:
    """Menu context stack; visual navigation does not run session operations."""

    def __init__(self, document: JourneyDocument) -> None:
        if document.entry_menu_id not in document.menu_ids:
            raise JourneyRouteError("menu de entrada não existe")
        self._document = document
        self._menu_ids = document.menu_ids
        self._contexts = [JourneyNavigationContext(document.entry_menu_id)]
        self._history: list[JourneyNavigationContext] = []
        self._generation = 0

    @property
    def context(self) -> JourneyNavigationContext:
        return self._contexts[-1]

    @property
    def generation(self) -> int:
        return self._generation

    def update_context(
        self,
        *,
        selected_item_id: str | None = None,
        filters: Mapping[str, JsonScalar] | None = None,
        scroll_position: float = 0.0,
        focus_id: str | None = None,
    ) -> JourneyNavigationContext:
        if scroll_position < 0:
            raise ValueError("scroll_position não pode ser negativa")
        current = JourneyNavigationContext(
            menu_id=self.context.menu_id,
            selected_item_id=selected_item_id,
            filters=tuple(sorted((filters or {}).items())),
            scroll_position=scroll_position,
            focus_id=focus_id,
        )
        if current != self.context:
            self._contexts[-1] = current
            self._generation += 1
        return current

    def navigate(
        self,
        target_menu_id: str,
        *,
        filters: Mapping[str, JsonScalar] | None = None,
    ) -> JourneyNavigationContext:
        if target_menu_id not in self._menu_ids:
            raise JourneyRouteError(f"menu de destino não existe: {target_menu_id}")
        if len(self._history) >= MAX_NAVIGATION_HISTORY:
            raise JourneyBudgetError(
                "JOURNEY-BUDGET-HISTORY",
                f"histórico atingiu {MAX_NAVIGATION_HISTORY} etapas; volte ou reinicie a navegação",
            )
        self._history.append(self.context)
        next_context = JourneyNavigationContext(
            menu_id=target_menu_id,
            filters=tuple(
                sorted((filters if filters is not None else dict(self.context.filters)).items())
            ),
        )
        self._contexts.append(next_context)
        self._generation += 1
        return next_context

    def back(self) -> JourneyNavigationContext | None:
        if not self._history:
            return None
        self._contexts.pop()
        restored = self._history.pop()
        self._contexts[-1] = restored
        self._generation += 1
        return restored

    def capture_return_context(self) -> JourneyReturnContext:
        return JourneyReturnContext(self.context, self._generation)

    def restore_return_context(self, saved: JourneyReturnContext) -> bool:
        """Ignore a late response after the user has navigated to a newer route."""
        if saved.generation != self._generation or saved.context.menu_id not in self._menu_ids:
            return False
        self._contexts[-1] = saved.context
        self._generation += 1
        return True

    def accepts_response(self, generation: int) -> bool:
        return generation == self._generation


def resolve_theme_coverage(
    document: JourneyDocument,
    *,
    used_stages: Iterable[str],
    themes: Mapping[str, Mapping[str, Any]],
    aura_version: str,
    required_theme_capabilities: Mapping[str, Iterable[str]] | None = None,
    adapter_capabilities: Iterable[str] | None = None,
    operation_requirements: Mapping[str, Iterable[str]] | None = None,
) -> list[dict[str, Any]]:
    """Resolve per-menu/per-stage appearance separately from adapter operations.

    ``used_stages`` accepts session stage IDs and ``menu:<id>`` identifiers. An
    omitted assignment and an explicit AURA choice remain distinguishable.
    """
    menu_appearance = {f"menu:{menu['id']}": menu.get("appearance") for menu in document.menus}
    stage_appearance = {
        str(stage["stageId"]): stage.get("appearance") for stage in document.data["sessionStages"]
    }
    required_theme_capabilities = required_theme_capabilities or {}
    operation_requirements = operation_requirements or {}
    adapter_caps = None if adapter_capabilities is None else frozenset(adapter_capabilities)
    results: list[dict[str, Any]] = []
    for stage_id in dict.fromkeys(str(value) for value in used_stages):
        if stage_id.startswith("menu:"):
            assignment = menu_appearance.get(stage_id)
            known_stage = stage_id[5:] in document.menu_ids
        else:
            assignment = stage_appearance.get(stage_id)
            known_stage = stage_id in SESSION_STAGES
        if not known_stage:
            results.append(
                {
                    "stageId": stage_id,
                    "appearance": "missing-reference",
                    "sourceThemeId": "org.steamzero.default",
                    "sourceVersion": aura_version,
                    "declaredThemeId": None,
                    "declaredThemeVersion": None,
                    "reason": "stage-reference-missing",
                    "missingThemeCapabilities": [],
                }
            )
            continue

        appearance_state = "inherited"
        reason = "not-customized"
        source_id = "org.steamzero.default"
        source_version = aura_version
        declared_theme_id: str | None = None
        declared_theme_version: str | None = None
        missing_theme_caps: list[str] = []
        if isinstance(assignment, Mapping) and assignment.get("mode") == "inherit-aura":
            reason = "explicit-choice"
        elif isinstance(assignment, Mapping) and assignment.get("mode") == "custom":
            theme_id = str(assignment.get("themeId", ""))
            declared_theme_id = theme_id
            theme = themes.get(theme_id)
            if theme is None:
                appearance_state = "missing-reference"
                reason = "theme-reference-missing"
            else:
                declared_theme_version = str(theme.get("version", "unknown"))
                theme_caps = frozenset(theme.get("capabilities", ()))
                missing_theme_caps = sorted(
                    set(required_theme_capabilities.get(stage_id, ())) - theme_caps
                )
                if missing_theme_caps:
                    appearance_state = "incompatible"
                    reason = "theme-capability-unavailable"
                else:
                    appearance_state = "custom"
                    source_id = theme_id
                    source_version = declared_theme_version

        needed_operations = frozenset(operation_requirements.get(stage_id, ()))
        if not needed_operations:
            operation_state = "not-required"
            missing_operations: list[str] = []
        elif adapter_caps is None:
            operation_state = "unknown"
            missing_operations = []
        else:
            missing_operations = sorted(needed_operations - adapter_caps)
            operation_state = "unavailable" if missing_operations else "available"

        results.append(
            {
                "stageId": stage_id,
                "appearance": appearance_state,
                "sourceThemeId": source_id,
                "sourceVersion": source_version,
                "declaredThemeId": declared_theme_id,
                "declaredThemeVersion": declared_theme_version,
                "reason": reason,
                "missingThemeCapabilities": missing_theme_caps,
                "operationCapability": operation_state,
                "missingOperationCapabilities": missing_operations,
            }
        )
    return results


def summarize_theme_coverage(coverage: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build the pre-apply summary without hiding degraded or missing stages."""
    aura_stages = [
        str(item.get("stageId", ""))
        for item in coverage
        if item.get("sourceThemeId") == "org.steamzero.default"
    ]
    inherited = [
        str(item.get("stageId", "")) for item in coverage if item.get("appearance") == "inherited"
    ]
    missing = [
        str(item.get("stageId", ""))
        for item in coverage
        if item.get("appearance") == "missing-reference"
    ]
    incompatible = [
        str(item.get("stageId", ""))
        for item in coverage
        if item.get("appearance") == "incompatible"
    ]
    unavailable_operations = [
        str(item.get("stageId", ""))
        for item in coverage
        if item.get("operationCapability") == "unavailable"
    ]
    return {
        "auraDefaultCount": len(inherited),
        "auraDefaultStages": inherited,
        "auraFallbackCount": len(aura_stages),
        "auraFallbackStages": aura_stages,
        "inheritedStages": inherited,
        "missingReferenceStages": missing,
        "incompatibleStages": incompatible,
        "unavailableOperationStages": unavailable_operations,
        "requiresPreApplyConfirmation": bool(aura_stages),
        "label": (
            f"Tema misto · {len(inherited)} etapas usam AURA padrão"
            if inherited
            else f"Tema com avisos · fallback AURA em {len(aura_stages)} etapas"
            if aura_stages
            else "Tema personalizado em todas as etapas usadas"
        ),
    }
