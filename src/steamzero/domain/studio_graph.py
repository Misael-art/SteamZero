# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Árvore e inspector do Theme Studio sobre o scene graph já resolvido.

O Studio não interpreta binding, não carrega QML do pacote e não redesenha a
cena. Ele só organiza os nós finais da Theme Engine para seleção e inspeção.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

ALLOWED_KINDS = frozenset({"scene", "layout", "surface", "motion", "effect"})
_FORBIDDEN = frozenset({"qml", "js", "script", "shader", "python"})


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
class StudioNode:
    id: str
    kind: str
    label: str
    properties: Mapping[str, str | int | float | bool | None]
    parent: str | None = None
    children: tuple[str, ...] = ()

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
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> StudioNode:
        unknown = set(raw) - {"id", "kind", "label", "parent", "children", "properties"}
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


def build_studio_graph(preview: Mapping[str, Any]) -> StudioGraph:
    """Monta a árvore a partir do preview já materializado pela engine."""
    children: list[str] = []
    nodes: list[StudioNode] = []
    layouts = preview.get("sceneLayoutPreview")
    if isinstance(layouts, Mapping):
        declared = layouts.get("layouts")
        if isinstance(declared, Mapping):
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
                    )
                )
    surfaces = preview.get("sceneSurfacePreview")
    if isinstance(surfaces, Mapping):
        slots = surfaces.get("slots")
        if isinstance(slots, Mapping):
            for name, slot in slots.items():
                if not isinstance(slot, Mapping) or name not in {"saveStates", "osd", "error"}:
                    continue
                node_id = f"surface.{name}"
                children.append(node_id)
                entries = slot.get("entries")
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
                    )
                )
    motion = preview.get("sceneMotionPreview")
    if isinstance(motion, Mapping):
        transitions = motion.get("transitions")
        if isinstance(transitions, Mapping):
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
                    )
                )
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
