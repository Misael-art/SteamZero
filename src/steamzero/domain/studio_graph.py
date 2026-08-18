# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Árvore e inspector do Theme Studio sobre o scene graph já resolvido.

O Studio não interpreta binding, não carrega QML do pacote e não redesenha a
cena. Ele só organiza os nós finais da Theme Engine para seleção e inspeção,
incluindo o grafo de efeitos allowlisted, os constraints já diagnosticados e um
profiler de orçamento declarado. FPS, frame time e VRAM não são inventados.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

ALLOWED_KINDS = frozenset({"scene", "layout", "surface", "motion", "effect", "timeline", "binding"})
ALLOWED_SEVERITIES = frozenset({"info", "warning", "error"})
_FORBIDDEN = frozenset({"qml", "js", "script", "shader", "python"})
ALLOWED_BINDING_PREFIXES = ("item.", "palette.", "osd.")
DIAG_EFFECT_OMITTED = "THEME-STUDIO-EFFECT-001"
DIAG_EFFECT_COST = "THEME-STUDIO-COST-001"
DIAG_BUDGET = "THEME-STUDIO-BUDGET-001"
DIAG_BINDING = "THEME-STUDIO-BINDING-001"
_COST_UNITS = {"low": 1, "medium": 2, "high": 3}
_FORBIDDEN_BUDGET = frozenset({"fps", "frameTime", "vram", *_FORBIDDEN})
_BUDGET_KEYS = frozenset(
    {
        "effectCost",
        "recipeCost",
        "declaredCost",
        "highCostNodes",
        "omitted",
        "diagnostics",
        "withinBudget",
        "measured",
    }
)


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


def _cost_units(value: object) -> int:
    if isinstance(value, str):
        return _COST_UNITS.get(value, 0)
    return 0


def _mapping_list(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


@dataclass(frozen=True)
class StudioBudget:
    effect_cost: int = 0
    recipe_cost: int = 0
    high_cost_nodes: int = 0
    omitted: int = 0
    diagnostics: int = 0
    within_budget: bool = True
    measured: bool = False

    def __post_init__(self) -> None:
        for name, value in (
            ("effectCost", self.effect_cost),
            ("recipeCost", self.recipe_cost),
            ("highCostNodes", self.high_cost_nodes),
            ("omitted", self.omitted),
            ("diagnostics", self.diagnostics),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"studio budget.{name} inválido")
        if self.measured:
            raise ValueError("studio budget não aceita medição física")

    @property
    def declared_cost(self) -> int:
        return self.effect_cost + self.recipe_cost

    def to_dict(self) -> dict[str, int | bool]:
        return {
            "effectCost": self.effect_cost,
            "recipeCost": self.recipe_cost,
            "declaredCost": self.declared_cost,
            "highCostNodes": self.high_cost_nodes,
            "omitted": self.omitted,
            "diagnostics": self.diagnostics,
            "withinBudget": self.within_budget,
            "measured": False,
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> StudioBudget:
        unknown = set(raw) - _BUDGET_KEYS
        forbidden = set(raw) & _FORBIDDEN_BUDGET
        if unknown or forbidden:
            raise ValueError(f"studio budget inválido: {sorted(unknown | forbidden)}")
        budget = cls(
            effect_cost=int(raw.get("effectCost", 0) or 0),
            recipe_cost=int(raw.get("recipeCost", 0) or 0),
            high_cost_nodes=int(raw.get("highCostNodes", 0) or 0),
            omitted=int(raw.get("omitted", 0) or 0),
            diagnostics=int(raw.get("diagnostics", 0) or 0),
            within_budget=raw.get("withinBudget", True) is not False,
            measured=raw.get("measured", False) is True,
        )
        declared = raw.get("declaredCost")
        if declared is not None and int(declared) != budget.declared_cost:
            raise ValueError("studio budget.declaredCost inconsistente")
        return budget


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
    budget: StudioBudget = StudioBudget()

    def __post_init__(self) -> None:
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("studio graph tem ids duplicados")
        if self.selected_id not in set(ids):
            raise ValueError("studio selectedId ausente")

    def select(self, node_id: str) -> StudioNode | None:
        return next((node for node in self.nodes if node.id == node_id), None)

    def to_qml_object(self) -> dict[str, Any]:
        return {
            "selectedId": self.selected_id,
            "nodes": [node.to_dict() for node in self.nodes],
            "budget": self.budget.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> StudioGraph:
        if set(raw) - {"selectedId", "nodes", "budget"}:
            raise ValueError("studio graph inválido")
        nodes = raw.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            raise ValueError("studio graph.nodes exige lista")
        parsed = tuple(StudioNode.from_dict(node) for node in nodes if isinstance(node, Mapping))
        if len(parsed) != len(nodes):
            raise ValueError("studio node exige objeto")
        budget_raw = raw.get("budget", {})
        if budget_raw is None:
            budget_raw = {}
        if not isinstance(budget_raw, Mapping):
            raise ValueError("studio graph.budget exige objeto")
        return cls(
            nodes=parsed,
            selected_id=str(raw.get("selectedId", "scene")),
            budget=StudioBudget.from_dict(budget_raw),
        )


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
        if not isinstance(slot, Mapping) or name not in {"saveStates", "osd", "error", "loading"}:
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
                    "style": slot.get("style"),
                    "filledSegments": slot.get("filledSegments"),
                    "label": slot.get("label"),
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


def build_studio_budget(preview: Mapping[str, Any]) -> StudioBudget:
    """Soma custos já declarados. Não mede FPS, frame time nem VRAM."""
    effect_cost = 0
    recipe_cost = 0
    high_cost_nodes = 0
    effects = preview.get("effects")
    if isinstance(effects, Mapping):
        for entries in effects.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, Mapping):
                    continue
                effect_cost += _cost_units(entry.get("cost"))
                if entry.get("cost") == "high":
                    high_cost_nodes += 1
    recipes = preview.get("assetRecipes")
    if isinstance(recipes, Mapping):
        for recipe in recipes.values():
            if not isinstance(recipe, Mapping):
                continue
            for node in _mapping_list(recipe.get("nodes")):
                recipe_cost += _cost_units(node.get("cost"))
                if node.get("cost") == "high":
                    high_cost_nodes += 1
    effect_diags = _mapping_list(preview.get("effectDiagnostics"))
    recipe_diags = _mapping_list(preview.get("assetRecipeDiagnostics"))
    layout_preview = preview.get("sceneLayoutPreview")
    surface_preview = preview.get("sceneSurfacePreview")
    motion_preview = preview.get("sceneMotionPreview")
    extra_diags = (
        _mapping_list(
            layout_preview.get("diagnostics") if isinstance(layout_preview, Mapping) else None
        )
        + _mapping_list(
            surface_preview.get("diagnostics") if isinstance(surface_preview, Mapping) else None
        )
        + _mapping_list(
            motion_preview.get("diagnostics") if isinstance(motion_preview, Mapping) else None
        )
    )
    over_budget = any(
        "orçamento excedido" in str(item.get("reason") or "") for item in recipe_diags
    )
    return StudioBudget(
        effect_cost=effect_cost,
        recipe_cost=recipe_cost,
        high_cost_nodes=high_cost_nodes,
        omitted=len(effect_diags) + len(recipe_diags),
        diagnostics=len(effect_diags) + len(recipe_diags) + len(extra_diags),
        within_budget=not over_budget,
        measured=False,
    )


def _binding_path_status(path: object) -> tuple[str, tuple[StudioConstraint, ...]]:
    if not isinstance(path, str) or not path:
        return "", (
            StudioConstraint(
                code=DIAG_BINDING,
                reason="caminho de binding ausente",
                severity="warning",
            ),
        )
    lowered = path.casefold()
    if any(token in lowered for token in _FORBIDDEN) or not path.startswith(
        ALLOWED_BINDING_PREFIXES
    ):
        return "", (
            StudioConstraint(
                code=DIAG_BINDING,
                reason="caminho de binding não allowlisted",
                severity="warning",
            ),
        )
    return path, ()


def _scalar_or_none(value: object) -> str | int | float | bool | None:
    if value is None or isinstance(value, str | int | float | bool):
        if isinstance(value, float) and value != value:
            return None
        return value
    return None


def _first_entry_field(preview: Mapping[str, Any], layout_name: str, field: str) -> object:
    layouts = preview.get("sceneLayoutPreview")
    if not isinstance(layouts, Mapping):
        return None
    declared = layouts.get("layouts")
    if not isinstance(declared, Mapping):
        return None
    layout = declared.get(layout_name)
    if not isinstance(layout, Mapping):
        return None
    entries = layout.get("entries")
    if not isinstance(entries, list) or not entries or not isinstance(entries[0], Mapping):
        return None
    return entries[0].get(field)


def _glass_resolved_tint(preview: Mapping[str, Any], panel_name: str) -> object:
    glass = preview.get("glassPreview")
    if not isinstance(glass, Mapping):
        return None
    panels = glass.get("panels")
    if not isinstance(panels, Mapping):
        return None
    panel = panels.get(panel_name)
    if not isinstance(panel, Mapping):
        return None
    return panel.get("tint")


def _surface_resolved_progress(preview: Mapping[str, Any], component: str) -> object:
    surfaces = preview.get("sceneSurfacePreview")
    if not isinstance(surfaces, Mapping):
        return None
    slots = surfaces.get("slots")
    if not isinstance(slots, Mapping):
        return None
    for slot in slots.values():
        if not isinstance(slot, Mapping):
            continue
        if slot.get("kind") == "osd" or slot.get("slot") == "osd":
            return slot.get("progress")
    del component
    return None


def _append_binding(
    nodes: list[StudioNode],
    children: list[str],
    *,
    node_id: str,
    label: str,
    source: str,
    field: str,
    declared: Mapping[str, Any],
    resolved: object,
) -> None:
    path, constraints = _binding_path_status(declared.get("binding"))
    fallback = _scalar_or_none(declared.get("fallback"))
    sample = _scalar_or_none(resolved)
    used_fallback = path != "" and (sample is None or sample == fallback)
    children.append(node_id)
    nodes.append(
        StudioNode(
            id=node_id,
            kind="binding",
            label=label,
            parent="scene",
            properties={
                "path": path,
                "field": field,
                "source": source,
                "fallback": fallback,
                "resolved": sample,
                "usedFallback": used_fallback,
            },
            constraints=constraints,
        )
    )


def _binding_nodes(preview: Mapping[str, Any], children: list[str]) -> list[StudioNode]:
    nodes: list[StudioNode] = []
    layouts = preview.get("sceneLayouts")
    if isinstance(layouts, Mapping):
        declared = layouts.get("layouts")
        if isinstance(declared, Mapping):
            for name, layout in declared.items():
                if not isinstance(name, str) or not isinstance(layout, Mapping):
                    continue
                template = layout.get("template")
                if not isinstance(template, Mapping):
                    continue
                properties = template.get("properties")
                if not isinstance(properties, Mapping):
                    continue
                for field, value in properties.items():
                    if not isinstance(field, str) or not isinstance(value, Mapping):
                        continue
                    if "binding" not in value:
                        continue
                    _append_binding(
                        nodes,
                        children,
                        node_id=f"binding.layout.{name}.{field}",
                        label=f"{name}.{field}",
                        source="layout",
                        field=field,
                        declared=value,
                        resolved=_first_entry_field(preview, name, field),
                    )
    glass = preview.get("glass")
    if isinstance(glass, Mapping):
        panels = glass.get("panels")
        if isinstance(panels, Mapping):
            for name, panel in panels.items():
                if not isinstance(name, str) or not isinstance(panel, Mapping):
                    continue
                tint = panel.get("tint")
                if not isinstance(tint, Mapping) or "binding" not in tint:
                    continue
                _append_binding(
                    nodes,
                    children,
                    node_id=f"binding.glass.{name}.tint",
                    label=f"{name}.tint",
                    source="glass",
                    field="tint",
                    declared=tint,
                    resolved=_glass_resolved_tint(preview, name),
                )
    surfaces = preview.get("sceneSurfaces")
    if isinstance(surfaces, Mapping):
        components = surfaces.get("components")
        if isinstance(components, Mapping):
            for name, component in components.items():
                if not isinstance(name, str) or not isinstance(component, Mapping):
                    continue
                progress = component.get("progress")
                if not isinstance(progress, Mapping) or "binding" not in progress:
                    continue
                _append_binding(
                    nodes,
                    children,
                    node_id=f"binding.surface.{name}.progress",
                    label=f"{name}.progress",
                    source="surface",
                    field="progress",
                    declared=progress,
                    resolved=_surface_resolved_progress(preview, name),
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
    nodes.extend(_binding_nodes(preview, children))
    budget = build_studio_budget(preview)
    budget_constraints: tuple[StudioConstraint, ...] = ()
    if not budget.within_budget:
        budget_constraints = (
            StudioConstraint(
                code=DIAG_BUDGET,
                reason="receita acima do orçamento declarado do tier",
                severity="warning",
            ),
        )
    nodes.insert(
        0,
        StudioNode(
            id="scene",
            kind="scene",
            label="Cena",
            properties={
                "children": len(children),
                "declaredCost": budget.declared_cost,
                "withinBudget": budget.within_budget,
            },
            children=tuple(children),
            constraints=budget_constraints,
        ),
    )
    return StudioGraph(nodes=tuple(nodes), selected_id="scene", budget=budget)
