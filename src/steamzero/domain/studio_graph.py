# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Árvore e inspector do Theme Studio sobre o scene graph já resolvido.

O Studio não interpreta binding, não carrega QML do pacote e não redesenha a
cena. Ele só organiza os nós finais da Theme Engine para seleção e inspeção,
incluindo o grafo de efeitos allowlisted e os constraints já diagnosticados.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

ALLOWED_KINDS = frozenset({"scene", "layout", "surface", "motion", "effect", "timeline"})
ALLOWED_SEVERITIES = frozenset({"info", "warning", "error"})
_FORBIDDEN = frozenset({"qml", "js", "script", "shader", "python"})
DIAG_EFFECT_OMITTED = "THEME-STUDIO-EFFECT-001"
DIAG_EFFECT_COST = "THEME-STUDIO-COST-001"


def _scalars(raw: Mapping[str, Any]) -> dict[str, str | int | float | bool | None]:
    values: dict[str, str | int | float | bool | None] = {}
    for key, value in raw.items():
        if key in _FORBIDDEN:
            raise ValueError(f"propriedade de grafo não permitida: {key}")
        if value is None or isinstance(value, str | int | float | bool):
            if isinstance(value, float) and value != value:
                continue
            values[str(key)] = value
    return values


@dataclass(frozen=True)
class StudioConstraint:
    code: str
    reason: str
    severity: str = "warning"

    def __post_init__(self) -> None:
        if not self.code or "/" in self.code or " " in self.code:
            raise ValueError("studio constraint code inválido")
        if self.severity not in ALLOWED_SEVERITIES:
            raise ValueError(f"studio constraint severity desconhecida: {self.severity}")
        if not self.reason or any(token in self.reason.casefold() for token in _FORBIDDEN):
            raise ValueError("studio constraint reason inválido")

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "reason": self.reason, "severity": self.severity}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> StudioConstraint:
        unknown = set(raw) - {"code", "reason", "severity"}
        if unknown:
            raise ValueError(f"studio constraint inválido: {sorted(unknown)}")
        return cls(
            code=str(raw.get("code", "")),
            reason=str(raw.get("reason", "")),
            severity=str(raw.get("severity", "warning")),
        )


def _constraint_tuple(raw: object) -> tuple[StudioConstraint, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("studio node.constraints exige lista")
    parsed = tuple(StudioConstraint.from_dict(item) for item in raw if isinstance(item, Mapping))
    if len(parsed) != len(raw):
        raise ValueError("studio constraint exige objeto")
    return parsed


def _constraints_from(
    items: object,
    *,
    match_key: str,
    match_value: str,
    default_code: str,
    severity: str,
) -> tuple[StudioConstraint, ...]:
    if not isinstance(items, list):
        return ()
    found: list[StudioConstraint] = []
    for item in items:
        if not isinstance(item, Mapping) or item.get(match_key) != match_value:
            continue
        found.append(
            StudioConstraint(
                code=str(item.get("code") or default_code),
                reason=str(item.get("reason") or "constraint diagnosticado"),
                severity=severity,
            )
        )
    return tuple(found)


def _reason_constraints(
    items: object,
    token: str,
    *,
    default_code: str,
    severity: str = "warning",
) -> tuple[StudioConstraint, ...]:
    if not isinstance(items, list) or not token:
        return ()
    found: list[StudioConstraint] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        reason = str(item.get("reason") or "")
        if f"'{token}'" not in reason and f": {token}" not in reason:
            continue
        found.append(
            StudioConstraint(
                code=str(item.get("code") or default_code),
                reason=reason or "constraint diagnosticado",
                severity=severity,
            )
        )
    return tuple(found)


def _code_constraints(
    items: object,
    code: str,
    *,
    severity: str = "warning",
) -> tuple[StudioConstraint, ...]:
    if not isinstance(items, list) or not code:
        return ()
    found: list[StudioConstraint] = []
    for item in items:
        if not isinstance(item, Mapping) or item.get("code") != code:
            continue
        found.append(
            StudioConstraint(
                code=code,
                reason=str(item.get("reason") or "constraint diagnosticado"),
                severity=severity,
            )
        )
    return tuple(found)


@dataclass(frozen=True)
class StudioNode:
    id: str
    kind: str
    label: str
    properties: Mapping[str, str | int | float | bool | None]
    parent: str | None = None
    children: tuple[str, ...] = ()
    constraints: tuple[StudioConstraint, ...] = ()

    def __post_init__(self) -> None:
        if not self.id or "/" in self.id or " " in self.id:
            raise ValueError("studio node id inválido")
        if self.kind not in ALLOWED_KINDS:
            raise ValueError(f"studio node kind desconhecido: {self.kind}")
        forbidden = set(self.properties) & _FORBIDDEN
        if forbidden:
            raise ValueError(f"propriedade de grafo não permitida: {sorted(forbidden)}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "parent": self.parent,
            "children": list(self.children),
            "properties": dict(self.properties),
            "constraints": [item.to_dict() for item in self.constraints],
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> StudioNode:
        unknown = set(raw) - {
            "id",
            "kind",
            "label",
            "parent",
            "children",
            "properties",
            "constraints",
        }
        if unknown:
            raise ValueError(f"studio node inválido: {sorted(unknown)}")
        properties = raw.get("properties", {})
        if not isinstance(properties, Mapping):
            raise ValueError("studio node.properties exige objeto")
        children = raw.get("children", [])
        if not isinstance(children, list) or not all(isinstance(item, str) for item in children):
            raise ValueError("studio node.children inválidos")
        return cls(
            id=str(raw.get("id", "")),
            kind=str(raw.get("kind", "")),
            label=str(raw.get("label", "")),
            properties=_scalars(properties),
            parent=str(raw["parent"]) if raw.get("parent") is not None else None,
            children=tuple(children),
            constraints=_constraint_tuple(raw.get("constraints")),
        )


@dataclass(frozen=True)
class StudioGraph:
    nodes: tuple[StudioNode, ...]
    selected_id: str = "scene"

    def __post_init__(self) -> None:
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("studio graph tem ids duplicados")
        if self.selected_id not in set(ids):
            raise ValueError("studio selectedId ausente")

    def select(self, node_id: str) -> StudioNode | None:
        return next((node for node in self.nodes if node.id == node_id), None)

    def to_qml_object(self) -> dict[str, Any]:
        return {"selectedId": self.selected_id, "nodes": [node.to_dict() for node in self.nodes]}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> StudioGraph:
        if set(raw) - {"selectedId", "nodes"}:
            raise ValueError("studio graph inválido")
        nodes = raw.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            raise ValueError("studio graph.nodes exige lista")
        parsed = tuple(StudioNode.from_dict(node) for node in nodes if isinstance(node, Mapping))
        if len(parsed) != len(nodes):
            raise ValueError("studio node exige objeto")
        return cls(nodes=parsed, selected_id=str(raw.get("selectedId", "scene")))


def _layout_nodes(preview: Mapping[str, Any], children: list[str]) -> list[StudioNode]:
    layouts = preview.get("sceneLayoutPreview")
    if not isinstance(layouts, Mapping):
        return []
    declared = layouts.get("layouts")
    if not isinstance(declared, Mapping):
        return []
    nodes: list[StudioNode] = []
    diagnostics = layouts.get("diagnostics")
    for name, layout in declared.items():
        if not isinstance(layout, Mapping):
            continue
        node_id = f"layout.{name}"
        children.append(node_id)
        entries = layout.get("entries")
        count = len(entries) if isinstance(entries, list) else 0
        nodes.append(
            StudioNode(
                id=node_id,
                kind="layout",
                label=str(name),
                parent="scene",
                properties={
                    "kind": layout.get("kind"),
                    "columns": layout.get("columns"),
                    "entries": count,
                },
                constraints=_constraints_from(
                    diagnostics,
                    match_key="layout",
                    match_value=str(name),
                    default_code="THEME-LAYOUT-SOURCE-001",
                    severity="warning",
                ),
            )
        )
    return nodes


def _surface_nodes(preview: Mapping[str, Any], children: list[str]) -> list[StudioNode]:
    surfaces = preview.get("sceneSurfacePreview")
    if not isinstance(surfaces, Mapping):
        return []
    slots = surfaces.get("slots")
    if not isinstance(slots, Mapping):
        return []
    nodes: list[StudioNode] = []
    diagnostics = surfaces.get("diagnostics")
    for name, slot in slots.items():
        if not isinstance(slot, Mapping) or name not in {"saveStates", "osd", "error"}:
            continue
        node_id = f"surface.{name}"
        children.append(node_id)
        entries = slot.get("entries")
        severity = "error" if slot.get("criticalVisible") else "warning"
        nodes.append(
            StudioNode(
                id=node_id,
                kind="surface",
                label=str(name),
                parent="scene",
                properties={
                    "kind": slot.get("kind"),
                    "entries": len(entries) if isinstance(entries, list) else 0,
                    "criticalVisible": slot.get("criticalVisible"),
                },
                constraints=_constraints_from(
                    diagnostics,
                    match_key="slot",
                    match_value=str(name),
                    default_code="THEME-SURFACE-SOURCE-001",
                    severity=severity,
                ),
            )
        )
    return nodes


def _motion_nodes(preview: Mapping[str, Any], children: list[str]) -> list[StudioNode]:
    motion = preview.get("sceneMotionPreview")
    if not isinstance(motion, Mapping):
        return []
    transitions = motion.get("transitions")
    if not isinstance(transitions, Mapping):
        return []
    diagnostics = motion.get("diagnostics")
    nodes: list[StudioNode] = []
    for name, transition in transitions.items():
        if not isinstance(transition, Mapping):
            continue
        node_id = f"motion.{name}"
        children.append(node_id)
        nodes.append(
            StudioNode(
                id=node_id,
                kind="motion",
                label=str(name),
                parent="scene",
                properties={
                    "from": transition.get("from"),
                    "to": transition.get("to"),
                    "duration": transition.get("duration"),
                    "easing": transition.get("easing"),
                },
                constraints=_reason_constraints(
                    diagnostics,
                    str(name),
                    default_code="THEME-MOTION-REDUCED-001",
                ),
            )
        )
    return nodes


def _timeline_nodes(preview: Mapping[str, Any], children: list[str]) -> list[StudioNode]:
    motion = preview.get("sceneMotionPreview")
    if not isinstance(motion, Mapping):
        return []
    timelines = motion.get("timelines")
    if not isinstance(timelines, Mapping):
        return []
    diagnostics = motion.get("diagnostics")
    nodes: list[StudioNode] = []
    for name, timeline in timelines.items():
        if not isinstance(name, str) or not isinstance(timeline, Mapping):
            continue
        timeline_id = f"timeline.{name}"
        steps = timeline.get("steps")
        step_entries = steps if isinstance(steps, list) else []
        child_ids: list[str] = []
        for index, step in enumerate(step_entries):
            if not isinstance(step, Mapping):
                continue
            node_id = f"{timeline_id}.{index}"
            child_ids.append(node_id)
            nodes.append(
                StudioNode(
                    id=node_id,
                    kind="timeline",
                    label=str(step.get("state") or name),
                    parent=timeline_id,
                    properties={
                        "state": step.get("state"),
                        "duration": step.get("duration"),
                        "easing": step.get("easing"),
                    },
                )
            )
        children.append(timeline_id)
        nodes.insert(
            len(nodes) - len(child_ids),
            StudioNode(
                id=timeline_id,
                kind="timeline",
                label=str(name),
                parent="scene",
                children=tuple(child_ids),
                properties={
                    "kind": timeline.get("kind"),
                    "repeat": timeline.get("repeat"),
                    "totalDuration": timeline.get("totalDuration"),
                    "steps": len(child_ids),
                },
                constraints=_code_constraints(diagnostics, "THEME-MOTION-CLIP-002"),
            ),
        )
    return nodes


def _effect_nodes(preview: Mapping[str, Any], children: list[str]) -> list[StudioNode]:
    effects = preview.get("effects")
    if not isinstance(effects, Mapping):
        return []
    omitted = preview.get("effectDiagnostics")
    nodes: list[StudioNode] = []
    for name, entries in effects.items():
        if not isinstance(name, str) or not isinstance(entries, list):
            continue
        stack_id = f"effect.{name}"
        child_ids: list[str] = []
        for index, entry in enumerate(entries):
            if not isinstance(entry, Mapping):
                continue
            node_id = f"{stack_id}.{index}"
            child_ids.append(node_id)
            properties: dict[str, str | int | float | bool | None] = {
                "type": entry.get("type") if isinstance(entry.get("type"), str) else None,
                "cost": entry.get("cost") if isinstance(entry.get("cost"), str) else None,
                "capability": (
                    entry.get("capability") if isinstance(entry.get("capability"), str) else None
                ),
            }
            parameters = entry.get("parameters")
            if isinstance(parameters, Mapping):
                for key, value in parameters.items():
                    if key in properties or key in _FORBIDDEN:
                        continue
                    if value is None or isinstance(value, str | int | float | bool):
                        if isinstance(value, float) and value != value:
                            continue
                        properties[str(key)] = value
            cost_constraints: tuple[StudioConstraint, ...] = ()
            if properties.get("cost") == "high":
                cost_constraints = (
                    StudioConstraint(
                        code=DIAG_EFFECT_COST,
                        reason="efeito de custo alto; o inspector só observa, não executa",
                        severity="info",
                    ),
                )
            nodes.append(
                StudioNode(
                    id=node_id,
                    kind="effect",
                    label=str(properties.get("type") or name),
                    parent=stack_id,
                    properties=properties,
                    constraints=cost_constraints,
                )
            )
        children.append(stack_id)
        nodes.insert(
            len(nodes) - len(child_ids),
            StudioNode(
                id=stack_id,
                kind="effect",
                label=str(name),
                parent="scene",
                children=tuple(child_ids),
                properties={
                    "stack": name,
                    "nodes": len(child_ids),
                    "omitted": (
                        len(
                            [
                                item
                                for item in omitted
                                if isinstance(item, Mapping) and item.get("stack") == name
                            ]
                        )
                        if isinstance(omitted, list)
                        else 0
                    ),
                },
                constraints=_constraints_from(
                    omitted,
                    match_key="stack",
                    match_value=name,
                    default_code=DIAG_EFFECT_OMITTED,
                    severity="warning",
                ),
            ),
        )
    return nodes


def build_studio_graph(preview: Mapping[str, Any]) -> StudioGraph:
    """Monta a árvore a partir do preview já materializado pela engine."""
    children: list[str] = []
    nodes: list[StudioNode] = []
    nodes.extend(_layout_nodes(preview, children))
    nodes.extend(_surface_nodes(preview, children))
    nodes.extend(_motion_nodes(preview, children))
    nodes.extend(_timeline_nodes(preview, children))
    nodes.extend(_effect_nodes(preview, children))
    nodes.insert(
        0,
        StudioNode(
            id="scene",
            kind="scene",
            label="Cena",
            properties={"children": len(children)},
            children=tuple(children),
        ),
    )
    return StudioGraph(nodes=tuple(nodes), selected_id="scene")
