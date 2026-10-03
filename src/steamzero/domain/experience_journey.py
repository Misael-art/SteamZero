# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Versioned journey documents, graph diagnostics, metadata filters and context.

This module only resolves declarative experience data. Session operations remain
owned by the session domain and its adapters; menu links cannot start processes.
"""

from __future__ import annotations

import json
import math
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

SCHEMA_V1 = "experience-journey-v1.schema.json"
SCHEMA_V2 = "experience-journey-v2.schema.json"
SCHEMA = SCHEMA_V2
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
_UNSET = object()


def migrate_journey_v1_to_v2(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Upgrade v1 additively for public grouping and selection bindings."""
    upgraded = json.loads(json.dumps(raw, ensure_ascii=False))
    if not isinstance(upgraded, dict):
        raise ValueError("documento de jornada exige objeto raiz")
    if (
        upgraded.get("schemaVersion") != 1
        or upgraded.get("kind") != "steamzero-experience-journey-v1"
    ):
        raise ValueError("a migração exige uma jornada v1")
    upgraded["schemaVersion"] = 2
    upgraded["kind"] = "steamzero-experience-journey-v2"
    for menu in upgraded.get("menus", []):
        menu.setdefault("groupBy", [])
    for connection in upgraded.get("connections", []):
        connection.setdefault("bindings", [])
    return upgraded


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


class JourneyValidationError(ValueError):
    """A journey with blocking diagnostics cannot be persisted or activated."""

    def __init__(self, diagnostics: Sequence[JourneyDiagnostic]) -> None:
        self.diagnostics = tuple(diagnostics)
        super().__init__("; ".join(item.message for item in self.diagnostics))


class PublicFieldUnavailable(ValueError):
    """A filter names a field absent from the selected public read model."""


class JourneyFilterTypeError(ValueError):
    """A declarative filter does not match the published field type."""


def _encoded_size(value: object) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
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
        validated = JourneyDocument.parse(document.serialize())
        validated.ensure_activatable()
        target = self._path(validated.id)
        if target.is_symlink():
            raise ValueError("destino da jornada não pode ser link simbólico")
        fs.write_atomic(target, validated.serialize(), must_not_exist=not overwrite)
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


@dataclass(frozen=True, init=False)
class JourneyDocument:
    """A schema-validated document backed by an immutable canonical snapshot.

    ``data`` intentionally returns a fresh decoded mapping. Callers can inspect
    and edit that snapshot, but cannot mutate the bytes this validated value
    will persist or activate.
    """

    _serialized: bytes

    @classmethod
    def _from_serialized(cls, serialized: bytes) -> JourneyDocument:
        document = object.__new__(cls)
        object.__setattr__(document, "_serialized", serialized)
        return document

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
            try:
                input_size = _encoded_size(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError("documento de jornada contém valores não JSON") from exc
            if input_size > MAX_DOCUMENT_BYTES:
                raise JourneyBudgetError(
                    "JOURNEY-BUDGET-DOCUMENT",
                    f"documento excede {MAX_DOCUMENT_BYTES} bytes UTF-8",
                )
        if not isinstance(raw, dict):
            raise ValueError("documento de jornada exige objeto raiz")
        try:
            snapshot = json.loads(json.dumps(raw, ensure_ascii=False, allow_nan=False))
        except (TypeError, ValueError) as exc:
            raise ValueError("documento de jornada contém valores não JSON") from exc
        if not isinstance(snapshot, dict):
            raise ValueError("documento de jornada exige objeto raiz")
        if snapshot.get("schemaVersion") == 1:
            contracts.validate(snapshot, SCHEMA_V1)
            snapshot = migrate_journey_v1_to_v2(snapshot)
        contracts.validate(snapshot, SCHEMA)
        serialized = json.dumps(
            snapshot, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False
        ).encode("utf-8")
        if len(serialized) > MAX_DOCUMENT_BYTES:
            raise JourneyBudgetError(
                "JOURNEY-BUDGET-DOCUMENT",
                f"documento serializado excede {MAX_DOCUMENT_BYTES} bytes UTF-8",
            )
        document = cls._from_serialized(serialized)
        budget_errors = [
            issue
            for issue in document.diagnostics()
            if issue.code.startswith("JOURNEY-BUDGET-") and issue.severity == "error"
        ]
        if budget_errors:
            raise JourneyBudgetError(budget_errors[0].code, budget_errors[0].message)
        return document

    @property
    def data(self) -> Mapping[str, Any]:
        value = json.loads(self._serialized.decode("utf-8"))
        if not isinstance(value, dict):  # Defensive; the schema requires an object.
            raise ValueError("documento de jornada exige objeto raiz")
        return value

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
        return self._serialized

    def diagnostics(
        self,
        published_read_models: Mapping[str, Iterable[str] | Mapping[str, str]] | None = None,
        *,
        strict_published_fields: bool = False,
    ) -> tuple[JourneyDiagnostic, ...]:
        return validate_journey(
            self.data,
            published_read_models=published_read_models,
            strict_published_fields=strict_published_fields,
        )

    def ensure_activatable(
        self,
        published_read_models: Mapping[str, Iterable[str] | Mapping[str, str]] | None = None,
        *,
        strict_published_fields: bool = True,
    ) -> None:
        blocking = tuple(
            issue
            for issue in self.diagnostics(
                published_read_models,
                strict_published_fields=strict_published_fields,
            )
            if issue.severity == "error"
        )
        if blocking:
            raise JourneyValidationError(blocking)


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


_STAGE_SCENE_SLOTS: dict[str, tuple[str, str]] = {
    "gameplay": ("gameDetail", "gameDetail"),
    "pause": ("quickMenu", "osd"),
    "saves": ("saveStates", "saveGallery"),
    "osd": ("osd", "osd"),
    "loading": ("loading", "loadingState"),
    "empty": ("empty", "emptyState"),
    "error": ("error", "errorBanner"),
    "offline": ("offline", "offlineState"),
}


def _missing_scene_elements(stage_id: str, theme: Mapping[str, Any]) -> list[str]:
    surfaces = theme.get("sceneSurfaces")
    slots = surfaces.get("slots", {}) if isinstance(surfaces, Mapping) else {}
    components = surfaces.get("components", {}) if isinstance(surfaces, Mapping) else {}
    missing: list[str] = []
    if stage_id.startswith("menu:"):
        required_slots = [("library", {"gameGrid", "recentlyPlayed"})]
    elif stage_id in _STAGE_SCENE_SLOTS:
        slot_id, component_kind = _STAGE_SCENE_SLOTS[stage_id]
        required_slots = [(slot_id, {component_kind})]
    elif stage_id == "bezel":
        # The current scene-surfaces contract has no bezel element kind or slot.
        return ["sceneSurfaces.slot:bezel"]
    else:
        required_slots = []

    for slot_id, allowed_kinds in required_slots:
        slot = slots.get(slot_id) if isinstance(slots, Mapping) else None
        if not isinstance(slot, Mapping):
            missing.append(f"sceneSurfaces.slot:{slot_id}")
            continue
        component_id = str(slot.get("component", ""))
        component = components.get(component_id) if isinstance(components, Mapping) else None
        if not isinstance(component, Mapping):
            missing.append(f"sceneSurfaces.component:{component_id}")
            continue
        kind = str(component.get("kind", ""))
        if kind not in allowed_kinds:
            missing.append(f"sceneSurfaces.component:{component_id}.kind={kind}")
        if stage_id == "pause" and "pause" not in component.get("items", []):
            missing.append(f"sceneSurfaces.component:{component_id}.items.pause")

    if stage_id in {"entryFade", "exitFade"}:
        motion = theme.get("sceneMotion")
        transitions = motion.get("transitions", []) if isinstance(motion, Mapping) else []
        if not any(
            isinstance(item, Mapping) and item.get("id") == stage_id for item in transitions
        ):
            missing.append(f"sceneMotion.transition:{stage_id}")
    return missing


def _provided_scene_elements(theme: Mapping[str, Any]) -> list[str]:
    surfaces = theme.get("sceneSurfaces")
    if not isinstance(surfaces, Mapping):
        return []
    slots = surfaces.get("slots", {})
    components = surfaces.get("components", {})
    if not isinstance(slots, Mapping) or not isinstance(components, Mapping):
        return []
    provided: list[str] = []
    for slot_id, slot in sorted(slots.items(), key=lambda item: str(item[0])):
        if not isinstance(slot, Mapping):
            continue
        component_id = str(slot.get("component", ""))
        component = components.get(component_id)
        if isinstance(component, Mapping):
            kind = str(component.get("kind", "unknown"))
            provided.append(f"{slot_id}:{component_id}:{kind}")
    return provided


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
        return (
            isinstance(value, int | float)
            and not isinstance(value, bool)
            and (not isinstance(value, float) or math.isfinite(value))
        )
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
    if operator in {"greaterThanOrEqual", "lessThanOrEqual"}:
        if value is None:
            return (
                f"operador {operator} exige valor numérico conhecido; null não é permitido. "
                "Use isKnown ou isUnknown para tratar valores desconhecidos"
            )
        if field_type not in {"integer", "number", "any"}:
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
    strict_published_fields: bool = False,
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
    expected_actions = {
        "select": "navigate",
        "back": "back",
        "play": "launch",
        "pause": "pause",
        "resume": "resume",
        "open-saves": "open-saves",
        "save": "save",
        "load": "load",
        "exit": "exit",
        "retry": "retry",
    }
    route_keys: set[tuple[str, str, str]] = set()
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
        source_endpoint = connection.get("from", {})
        event = str(connection.get("event", ""))
        when = str(connection.get("when", ""))
        route_key = (
            json.dumps(source_endpoint, ensure_ascii=False, sort_keys=True),
            event,
            when,
        )
        if route_key in route_keys:
            issues.append(
                JourneyDiagnostic(
                    "JOURNEY-CONNECTION-AMBIGUOUS",
                    "mais de uma conexão atende ao mesmo evento; remova ou altere uma delas",
                    connection_id,
                )
            )
        route_keys.add(route_key)
        if expected_actions.get(event) != connection.get("action"):
            issues.append(
                JourneyDiagnostic(
                    "JOURNEY-EVENT-ACTION-MISMATCH",
                    f"evento {event} exige a ação semântica {expected_actions.get(event)}",
                    connection_id,
                )
            )
        bindings = connection.get("bindings", [])
        if bindings and (
            source_endpoint.get("kind") != "menu"
            or connection.get("to", {}).get("kind") != "menu"
            or connection.get("action") != "navigate"
        ):
            issues.append(
                JourneyDiagnostic(
                    "JOURNEY-BINDING-ENDPOINT",
                    "vínculos de seleção só podem ligar dois menus em uma ação navigate",
                    connection_id,
                )
            )
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
        published_field_severity = "error" if strict_published_fields else "warning"
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
                        published_field_severity,
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
                            published_field_severity,
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
                                published_field_severity,
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
                            published_field_severity,
                        )
                    )
            for field_id in menu.get("groupBy", []):
                if str(field_id) not in fields:
                    issues.append(
                        JourneyDiagnostic(
                            "JOURNEY-GROUP-FIELD-UNAVAILABLE",
                            f"campo publicado {field_id} não existe nessa fonte; "
                            "escolha outro campo de agrupamento",
                            menu_id,
                            published_field_severity,
                        )
                    )
        menu_lookup = {str(menu.get("id", "")): menu for menu in menus}
        for connection in connections:
            bindings = connection.get("bindings", [])
            source_endpoint = connection.get("from", {})
            target_endpoint = connection.get("to", {})
            if (
                not bindings
                or source_endpoint.get("kind") != "menu"
                or target_endpoint.get("kind") != "menu"
            ):
                continue
            source_menu = menu_lookup.get(str(source_endpoint.get("id", "")))
            target_menu = menu_lookup.get(str(target_endpoint.get("id", "")))
            if source_menu is None or target_menu is None:
                continue
            source_model = published_read_models.get(
                str(source_menu.get("source", {}).get("readModelId", ""))
            )
            target_model = published_read_models.get(
                str(target_menu.get("source", {}).get("readModelId", ""))
            )
            source_fields = _field_definitions(source_model or {})
            target_fields = _field_definitions(target_model or {})
            for binding in bindings:
                source_field = str(binding.get("sourceFieldId", ""))
                target_field = str(binding.get("targetFieldId", ""))
                if source_field not in source_fields or target_field not in target_fields:
                    issues.append(
                        JourneyDiagnostic(
                            "JOURNEY-BINDING-FIELD-UNAVAILABLE",
                            f"vínculo {source_field} → {target_field} usa campo não publicado",
                            str(connection.get("id", "")),
                            published_field_severity,
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
    groups: tuple[Mapping[str, Any], ...] = ()


def _sortable_value(value: object) -> tuple[object, ...]:
    if isinstance(value, bool):
        return (0, int(value))
    if isinstance(value, int | float):
        return (1, float(value))
    if isinstance(value, str):
        return (2, value.casefold(), value)
    if isinstance(value, list | tuple):
        return (3, tuple(str(item).casefold() for item in value))
    return (4, json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def _sort_public_records(
    rows: Sequence[Mapping[str, Any]],
    sort: Sequence[Mapping[str, Any]],
    fields: Mapping[str, str],
) -> list[Mapping[str, Any]]:
    missing = sorted({str(item.get("fieldId", "")) for item in sort} - set(fields))
    if missing:
        raise PublicFieldUnavailable(
            "campo(s) de ordenação não publicado(s): " + ", ".join(missing)
        )
    ordered = list(rows)
    for item in reversed(sort):
        field_id = str(item["fieldId"])
        known = [row for row in ordered if row.get(field_id) is not None]
        unknown = [row for row in ordered if row.get(field_id) is None]
        known.sort(
            key=lambda row: _sortable_value(row.get(field_id)),
            reverse=str(item.get("direction", "ascending")) == "descending",
        )
        ordered = known + unknown
    return ordered


def _group_public_records(
    rows: Sequence[Mapping[str, Any]],
    group_by: Sequence[str],
    fields: Mapping[str, str],
) -> tuple[Mapping[str, Any], ...]:
    missing = sorted(set(group_by) - set(fields))
    if missing:
        raise PublicFieldUnavailable(
            "campo(s) de agrupamento não publicado(s): " + ", ".join(missing)
        )
    buckets: dict[bytes, tuple[dict[str, Any], list[Mapping[str, Any]]]] = {}
    for row in rows:
        key = {field_id: row.get(field_id) for field_id in group_by}
        token = json.dumps(key, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        if token not in buckets:
            buckets[token] = (key, [])
        buckets[token][1].append(row)
    return tuple(
        {"values": values, "count": len(group_rows), "rows": tuple(group_rows)}
        for values, group_rows in buckets.values()
    )


def query_public_records(
    rows: Iterable[Mapping[str, Any]] | None,
    filters: Sequence[Mapping[str, Any]],
    *,
    published_fields: Iterable[str] | Mapping[str, str],
    sort: Sequence[Mapping[str, Any]] = (),
    group_by: Sequence[str] = (),
) -> PublicQueryResult:
    """Filter, order and group only fields in a published read model.

    Menu filters run before context bindings; callers pass both as AND clauses,
    so a selected value can narrow a menu but cannot relax its authored filter.
    """
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
        result_rows = _sort_public_records(result_rows, sort, field_types)
        groups = _group_public_records(result_rows, group_by, field_types)
    except PublicFieldUnavailable as exc:
        message = str(exc)
        is_grouping = "agrupamento" in message
        is_sort = "ordenação" in message
        return PublicQueryResult(
            source_state="available",
            result_state="invalid-filter",
            rows=(),
            total_count=len(records),
            result_count=0,
            unknown_value_counts=unknown_counts,
            recovery_action=(
                "replace-grouping"
                if is_grouping
                else "replace-sort"
                if is_sort
                else "replace-filter"
            ),
            diagnostic_code=(
                "JOURNEY-GROUP-FIELD-UNAVAILABLE"
                if is_grouping
                else "JOURNEY-SORT-FIELD-UNAVAILABLE"
                if is_sort
                else "JOURNEY-FIELD-UNAVAILABLE"
            ),
            diagnostic_message=message,
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
        groups=groups,
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

    def __init__(
        self,
        document: JourneyDocument,
        *,
        published_read_models: Mapping[str, Iterable[str] | Mapping[str, str]] | None = None,
    ) -> None:
        document.ensure_activatable(published_read_models)
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
        selected_item_id: str | None | object = _UNSET,
        filters: Mapping[str, JsonScalar] | None | object = _UNSET,
        scroll_position: float | object = _UNSET,
        focus_id: str | None | object = _UNSET,
    ) -> JourneyNavigationContext:
        previous = self.context
        if scroll_position is _UNSET:
            next_scroll_position = previous.scroll_position
        elif (
            isinstance(scroll_position, bool)
            or not isinstance(scroll_position, int | float)
            or not math.isfinite(scroll_position)
            or scroll_position < 0
        ):
            raise ValueError("scroll_position não pode ser negativa")
        else:
            next_scroll_position = float(scroll_position)

        if selected_item_id is _UNSET:
            next_selected_item_id = previous.selected_item_id
        elif selected_item_id is None or isinstance(selected_item_id, str):
            next_selected_item_id = selected_item_id
        else:
            raise ValueError("selected_item_id deve ser string ou None")

        if focus_id is _UNSET:
            next_focus_id = previous.focus_id
        elif focus_id is None or isinstance(focus_id, str):
            next_focus_id = focus_id
        else:
            raise ValueError("focus_id deve ser string ou None")

        if filters is _UNSET:
            next_filters = previous.filters
        elif filters is None:
            next_filters = ()
        elif isinstance(filters, Mapping):
            if any(
                not isinstance(field_id, str)
                or not field_id
                or not (
                    value is None
                    or isinstance(value, str | int | bool)
                    or (isinstance(value, float) and math.isfinite(value))
                )
                for field_id, value in filters.items()
            ):
                raise ValueError("filters devem conter campos públicos com valores escalares")
            next_filters = tuple(sorted(filters.items()))
        else:
            raise ValueError("filters deve ser um mapa de campos públicos")

        current = JourneyNavigationContext(
            menu_id=self.context.menu_id,
            selected_item_id=next_selected_item_id,
            filters=next_filters,
            scroll_position=next_scroll_position,
            focus_id=next_focus_id,
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


@dataclass(frozen=True)
class JourneyExecutionResult:
    """A resolved route or a semantic operation request for a real adapter."""

    state: str
    connection_id: str = ""
    action: str = ""
    target: Mapping[str, str] | None = None
    context: JourneyNavigationContext | None = None
    query: PublicQueryResult | None = None
    return_context: JourneyReturnContext | None = None
    diagnostic_code: str = ""
    diagnostic_message: str = ""
    recovery_action: str = ""


class JourneyExecutor:
    """Execute declared menu routes and return allowlisted session intent.

    This class never launches or controls a process. Session actions are
    returned to the owning adapter; menu filtering receives only caller-provided
    public read models and published field definitions.
    """

    def __init__(
        self,
        document: JourneyDocument,
        navigator: JourneyNavigator | None = None,
        *,
        published_read_models: Mapping[str, Iterable[str] | Mapping[str, str]] | None = None,
    ) -> None:
        document.ensure_activatable(published_read_models)
        self.document = document
        self.navigator = navigator or JourneyNavigator(
            document,
            published_read_models=published_read_models,
        )
        self._menus = {str(menu["id"]): menu for menu in document.menus}

    def execute(
        self,
        event: str,
        *,
        when: str = _INPUT_ONLY,
        source_endpoint: Mapping[str, str] | None = None,
        selected_record: Mapping[str, Any] | None = None,
        selected_item_id: str | None | object = _UNSET,
        filters: Mapping[str, JsonScalar] | None | object = _UNSET,
        scroll_position: float | object = _UNSET,
        focus_id: str | None | object = _UNSET,
        read_models: Mapping[str, Sequence[Mapping[str, Any]] | None] | None = None,
        published_read_models: Mapping[str, Iterable[str] | Mapping[str, str]] | None = None,
        pending_return: JourneyReturnContext | None = None,
    ) -> JourneyExecutionResult:
        source = dict(source_endpoint or {"kind": "menu", "id": self.navigator.context.menu_id})
        candidates = [
            item
            for item in self.document.data["connections"]
            if item["from"] == source and item["event"] == event and item["when"] == when
        ]
        if not candidates:
            return JourneyExecutionResult(
                "unmatched",
                diagnostic_code="JOURNEY-CONNECTION-NOT-FOUND",
                diagnostic_message="Nenhuma conexão atende a este evento e resultado.",
                recovery_action="stay-current",
            )
        if len(candidates) != 1:
            return JourneyExecutionResult(
                "invalid",
                diagnostic_code="JOURNEY-CONNECTION-AMBIGUOUS",
                diagnostic_message="Mais de uma conexão atende ao mesmo evento; ajuste o mapa.",
                recovery_action="edit-connections",
            )
        connection = candidates[0]
        action = str(connection["action"])
        target = connection["to"]
        restored_pending_return = False

        if source.get("kind") == "stage" and pending_return is not None:
            if not self.navigator.restore_return_context(pending_return):
                return JourneyExecutionResult(
                    "stale-response",
                    connection_id=str(connection["id"]),
                    action=action,
                    diagnostic_code="JOURNEY-RESPONSE-STALE",
                    diagnostic_message="A resposta chegou após uma navegação mais recente.",
                    recovery_action="keep-current-route",
                )
            restored_pending_return = True

        has_context_update = (
            selected_item_id is not _UNSET
            or filters is not _UNSET
            or scroll_position is not _UNSET
            or focus_id is not _UNSET
        )
        if (
            has_context_update
            and source.get("kind") == "menu"
            and str(source.get("id")) == self.navigator.context.menu_id
        ):
            context_update: dict[str, Any] = {}
            if selected_item_id is not _UNSET:
                context_update["selected_item_id"] = selected_item_id
            if filters is not _UNSET:
                context_update["filters"] = filters
            if scroll_position is not _UNSET:
                context_update["scroll_position"] = scroll_position
            if focus_id is not _UNSET:
                context_update["focus_id"] = focus_id
            self.navigator.update_context(**context_update)

        if action in {"launch", "pause", "resume", "open-saves", "save", "load", "exit", "retry"}:
            return JourneyExecutionResult(
                "operation-request",
                connection_id=str(connection["id"]),
                action=action,
                target=target,
                context=self.navigator.context,
                return_context=self.navigator.capture_return_context(),
            )

        if action == "back" and target.get("kind") == "history":
            restored = self.navigator.context if restored_pending_return else self.navigator.back()
            if restored is None and pending_return is not None:
                if not self.navigator.restore_return_context(pending_return):
                    return JourneyExecutionResult(
                        "stale-response",
                        connection_id=str(connection["id"]),
                        action=action,
                        diagnostic_code="JOURNEY-RESPONSE-STALE",
                        diagnostic_message="A resposta chegou após uma navegação mais recente.",
                        recovery_action="keep-current-route",
                    )
                restored = self.navigator.context
            if restored is None:
                return JourneyExecutionResult(
                    "recovery-required",
                    connection_id=str(connection["id"]),
                    action=action,
                    diagnostic_code="JOURNEY-HISTORY-EMPTY",
                    diagnostic_message="Não há menu de origem para restaurar.",
                    recovery_action="open-entry-menu",
                )
            return JourneyExecutionResult(
                "navigated",
                connection_id=str(connection["id"]),
                action=action,
                target=target,
                context=restored,
            )

        if target.get("kind") != "menu":
            return JourneyExecutionResult(
                "stage-resolved",
                connection_id=str(connection["id"]),
                action=action,
                target=target,
                context=self.navigator.context,
            )

        target_menu_id = str(target["id"])
        target_menu = self._menus[target_menu_id]
        context_filters: dict[str, JsonScalar] = {}
        binding_filters: list[dict[str, Any]] = []
        source_menu = self._menus.get(str(source.get("id", "")))
        source_fields = {}
        target_read_model_id = str(target_menu["source"]["readModelId"])
        target_fields = None
        if published_read_models is not None:
            if source_menu is not None:
                source_fields = _field_definitions(
                    published_read_models.get(str(source_menu["source"]["readModelId"]), {})
                )
            target_fields = published_read_models.get(target_read_model_id)

        for binding in connection.get("bindings", []):
            source_field = str(binding["sourceFieldId"])
            target_field = str(binding["targetFieldId"])
            if (
                selected_record is None
                or source_field not in source_fields
                or target_fields is None
                or target_field not in _field_definitions(target_fields)
            ):
                return JourneyExecutionResult(
                    "invalid-binding",
                    connection_id=str(connection["id"]),
                    action=action,
                    diagnostic_code="JOURNEY-BINDING-FIELD-UNAVAILABLE",
                    diagnostic_message=(
                        f"O vínculo {source_field} → {target_field} precisa de campos "
                        "publicados e de um item selecionado."
                    ),
                    recovery_action="choose-public-fields",
                )
            value = selected_record.get(source_field)
            target_type = _field_definitions(target_fields)[target_field]
            if value is None:
                return JourneyExecutionResult(
                    "invalid-binding",
                    connection_id=str(connection["id"]),
                    action=action,
                    diagnostic_code="JOURNEY-BINDING-SOURCE-UNKNOWN",
                    diagnostic_message=(
                        f"O campo selecionado {source_field} é desconhecido; "
                        "escolha um valor conhecido ou filtre desconhecidos explicitamente."
                    ),
                    recovery_action="select-known-value",
                )
            if (
                not isinstance(value, str | int | float | bool)
                or (isinstance(value, float) and not math.isfinite(value))
                or not _value_matches_type(value, source_fields[source_field])
                or not _value_matches_type(value, target_type)
            ):
                return JourneyExecutionResult(
                    "invalid-binding",
                    connection_id=str(connection["id"]),
                    action=action,
                    diagnostic_code="JOURNEY-BINDING-TYPE",
                    diagnostic_message=(
                        f"O vínculo {source_field} → {target_field} não é compatível "
                        "com os tipos publicados."
                    ),
                    recovery_action="choose-compatible-fields",
                )
            context_filters[target_field] = value
            binding_filters.append({"fieldId": target_field, "operator": "equals", "value": value})

        read_model_rows = (read_models or {}).get(target_read_model_id)
        field_definitions = _field_definitions(target_fields) if target_fields is not None else {}
        query = query_public_records(
            read_model_rows,
            [*target_menu["filters"], *binding_filters],
            published_fields=field_definitions,
            sort=target_menu["sort"],
            group_by=target_menu.get("groupBy", []),
        )
        context = self.navigator.navigate(target_menu_id, filters=context_filters)
        return JourneyExecutionResult(
            "navigated",
            connection_id=str(connection["id"]),
            action=action,
            target=target,
            context=context,
            query=query,
        )


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
                    "missingSceneElements": [],
                    "providedSceneElements": [],
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
        missing_scene_elements: list[str] = []
        provided_scene_elements: list[str] = []
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
                provided_scene_elements = _provided_scene_elements(theme)
                missing_theme_caps = sorted(
                    set(required_theme_capabilities.get(stage_id, ())) - theme_caps
                )
                missing_scene_elements = _missing_scene_elements(stage_id, theme)
                if missing_theme_caps or missing_scene_elements:
                    appearance_state = "incompatible"
                    reason = (
                        "theme-capability-unavailable"
                        if missing_theme_caps
                        else "scene-element-unavailable"
                    )
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
                "missingSceneElements": missing_scene_elements,
                "providedSceneElements": provided_scene_elements,
                "operationCapability": operation_state,
                "missingOperationCapabilities": missing_operations,
            }
        )
    return results


def summarize_theme_coverage(coverage: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build the pre-apply summary without hiding degraded or missing stages."""
    aura_effective_stages = [
        str(item.get("stageId", ""))
        for item in coverage
        if item.get("sourceThemeId") == "org.steamzero.default"
    ]
    inherited = [
        str(item.get("stageId", ""))
        for item in coverage
        if item.get("appearance") == "inherited" and item.get("reason") == "not-customized"
    ]
    explicit_aura = [
        str(item.get("stageId", ""))
        for item in coverage
        if item.get("appearance") == "inherited" and item.get("reason") == "explicit-choice"
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
    fallback = list(dict.fromkeys([*missing, *incompatible]))
    missing_scene_elements = [
        str(item.get("stageId", "")) for item in coverage if item.get("missingSceneElements")
    ]
    unavailable_operations = [
        str(item.get("stageId", ""))
        for item in coverage
        if item.get("operationCapability") == "unavailable"
    ]
    return {
        "auraDefaultCount": len(inherited),
        "auraDefaultStages": inherited,
        "auraExplicitCount": len(explicit_aura),
        "auraExplicitStages": explicit_aura,
        "auraFallbackCount": len(fallback),
        "auraFallbackStages": fallback,
        "auraEffectiveCount": len(aura_effective_stages),
        "auraEffectiveStages": aura_effective_stages,
        "inheritedStages": inherited,
        "missingReferenceStages": missing,
        "incompatibleStages": incompatible,
        "missingSceneElementStages": missing_scene_elements,
        "unavailableOperationStages": unavailable_operations,
        "requiresPreApplyConfirmation": bool(aura_effective_stages),
        "label": (
            f"Tema misto · AURA efetivo em {len(aura_effective_stages)} etapas "
            f"({len(inherited)} herdadas, {len(explicit_aura)} escolhidas, "
            f"{len(fallback)} em fallback)"
            if aura_effective_stages
            else "Tema personalizado em todas as etapas usadas"
        ),
    }
