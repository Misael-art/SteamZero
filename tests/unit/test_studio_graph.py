# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato do canvas/árvore/inspector do Theme Studio sobre o scene graph."""

from __future__ import annotations

import pytest

from steamzero.domain.studio_graph import (
    DIAG_BINDING,
    DIAG_BUDGET,
    DIAG_EFFECT_COST,
    DIAG_EFFECT_OMITTED,
    StudioBudget,
    StudioGraph,
    build_studio_graph,
)
from steamzero.domain.theme_editor import ThemeEditorManager


def test_builtin_preview_exposes_a_selectable_scene_tree() -> None:
    preview = ThemeEditorManager().load("org.steamzero.asset-recipes-demo")["preview"]
    assert isinstance(preview, dict)
    graph = preview["studioGraph"]
    assert isinstance(graph, dict)
    ids = {node["id"] for node in graph["nodes"]}
    assert "scene" in ids
    assert "layout.previewTitles" in ids
    assert "layout.previewWheel" in ids
    assert "layout.previewCoverFlow" in ids
    assert "surface.saveStates" in ids
    assert "motion.focusIn" in ids
    assert "timeline.previewFocus" in ids
    assert "timeline.previewFocus.1" in ids
    assert "effect.focusedCover" in ids
    assert "effect.focusedCover.0" in ids
    assert "binding.layout.previewTitles.text" in ids
    assert "binding.glass.previewCard.tint" in ids
    selected = next(node for node in graph["nodes"] if node["id"] == graph["selectedId"])
    assert selected["kind"] == "scene"
    assert all(isinstance(node["properties"], dict) for node in graph["nodes"])
    assert all(isinstance(node.get("constraints"), list) for node in graph["nodes"])
    assert all("qml" not in node for node in graph["nodes"])
    budget = graph["budget"]
    assert isinstance(budget, dict)
    assert budget["measured"] is False
    assert "fps" not in budget
    assert "vram" not in budget
    assert budget["declaredCost"] == budget["effectCost"] + budget["recipeCost"]
    assert budget["declaredCost"] > 0
    assert budget["withinBudget"] is True


def test_selecting_a_layout_node_exposes_only_scalar_inspector_fields() -> None:
    preview = ThemeEditorManager().load("org.steamzero.asset-recipes-demo")["preview"]
    assert isinstance(preview, dict)
    graph = StudioGraph.from_dict(preview["studioGraph"])
    selected = graph.select("layout.previewTitles")
    assert selected is not None
    assert selected.kind == "layout"
    assert selected.properties["kind"] == "grid"
    assert selected.properties["columns"] == 4
    assert "binding" not in selected.properties
    assert graph.select("evil.qml") is None


def test_effect_diagnostics_become_inspector_constraints() -> None:
    graph = build_studio_graph(
        {
            "effects": {
                "focusedCover": [
                    {
                        "type": "glow",
                        "parameters": {"strength": 0.12, "blur": 12},
                        "capability": "graphics.effect.glow",
                        "cost": "high",
                    }
                ]
            },
            "effectDiagnostics": [
                {
                    "stack": "focusedCover",
                    "effect": "blur",
                    "reason": "omitido no tier economy",
                    "fallback": "omit",
                }
            ],
            "sceneLayoutPreview": {
                "layouts": {
                    "previewTitles": {"kind": "grid", "columns": 4, "entries": []},
                },
                "diagnostics": [
                    {
                        "code": "THEME-LAYOUT-SOURCE-001",
                        "layout": "previewTitles",
                        "reason": "fonte vazia",
                        "fallback": "empty",
                    }
                ],
            },
        }
    )
    stack = graph.select("effect.focusedCover")
    assert stack is not None
    assert stack.kind == "effect"
    assert stack.properties["omitted"] == 1
    assert stack.constraints[0].code == DIAG_EFFECT_OMITTED
    glow = graph.select("effect.focusedCover.0")
    assert glow is not None
    assert glow.properties["type"] == "glow"
    assert glow.properties["strength"] == 0.12
    assert glow.constraints[0].code == DIAG_EFFECT_COST
    layout = graph.select("layout.previewTitles")
    assert layout is not None
    assert layout.constraints[0].code == "THEME-LAYOUT-SOURCE-001"
    assert graph.select("evil.shader") is None


def test_resolved_timeline_is_inspectable_without_running_motion() -> None:
    preview = ThemeEditorManager().load("org.steamzero.asset-recipes-demo")["preview"]
    assert isinstance(preview, dict)
    graph = StudioGraph.from_dict(preview["studioGraph"])
    timeline = graph.select("timeline.previewFocus")
    assert timeline is not None
    assert timeline.kind == "timeline"
    assert timeline.properties["kind"] == "sequence"
    assert timeline.properties["steps"] == 3
    assert timeline.properties["totalDuration"] == 260
    step = graph.select("timeline.previewFocus.1")
    assert step is not None
    assert step.properties["state"] == "focused"
    assert step.properties["duration"] == 180
    assert step.properties["easing"] == "cubicOut"


def test_reduced_motion_diagnostics_attach_to_transition_nodes() -> None:
    graph = build_studio_graph(
        {
            "sceneMotionPreview": {
                "transitions": {
                    "focusIn": {
                        "from": "normal",
                        "to": "focused",
                        "duration": 0,
                        "easing": "cubicOut",
                    }
                },
                "timelines": {
                    "previewFocus": {
                        "kind": "sequence",
                        "repeat": 0,
                        "totalDuration": 80,
                        "steps": [
                            {"state": "normal", "duration": 0, "easing": "linear"},
                            {"state": "focused", "duration": 0, "easing": "cubicOut"},
                            {"state": "focused", "duration": 80, "easing": "linear"},
                        ],
                    }
                },
                "diagnostics": [
                    {
                        "code": "THEME-MOTION-REDUCED-001",
                        "reason": "transição 'focusIn' zerada com reduced motion",
                        "fallback": "cut",
                    },
                    {
                        "code": "THEME-MOTION-CLIP-002",
                        "reason": "clip referencia transition ausente: missingFlash",
                        "fallback": "cut",
                    },
                ],
            }
        }
    )
    motion = graph.select("motion.focusIn")
    assert motion is not None
    assert motion.constraints[0].code == "THEME-MOTION-REDUCED-001"
    timeline = graph.select("timeline.previewFocus")
    assert timeline is not None
    assert timeline.properties["totalDuration"] == 80
    assert timeline.constraints[0].code == "THEME-MOTION-CLIP-002"
    assert graph.select("evil.js") is None


def test_declared_budget_does_not_invent_physical_metrics() -> None:
    graph = build_studio_graph(
        {
            "effects": {
                "focusedCover": [
                    {
                        "type": "glow",
                        "parameters": {"strength": 0.12},
                        "capability": "graphics.effect.glow",
                        "cost": "high",
                    }
                ]
            },
            "assetRecipes": {
                "outlineThin": {
                    "nodes": [
                        {
                            "type": "outline",
                            "parameters": {"width": 2},
                            "cost": "medium",
                        }
                    ]
                }
            },
            "assetRecipeDiagnostics": [
                {
                    "recipe": "outlinedGlow",
                    "node": "recipe",
                    "reason": "orçamento excedido no tier economy: 6 > 5",
                    "fallback": "source",
                }
            ],
        }
    )
    assert graph.budget.effect_cost == 3
    assert graph.budget.recipe_cost == 2
    assert graph.budget.declared_cost == 5
    assert graph.budget.high_cost_nodes == 1
    assert graph.budget.within_budget is False
    assert graph.budget.measured is False
    scene = graph.select("scene")
    assert scene is not None
    assert scene.constraints[0].code == DIAG_BUDGET
    with pytest.raises(ValueError, match="inválid"):
        StudioBudget.from_dict({"effectCost": 1, "fps": 60})
    with pytest.raises(ValueError, match="medição física"):
        StudioBudget.from_dict({"effectCost": 1, "measured": True})


def test_assisted_bindings_expose_allowlisted_paths_without_eval() -> None:
    preview = ThemeEditorManager().load("org.steamzero.asset-recipes-demo")["preview"]
    assert isinstance(preview, dict)
    graph = StudioGraph.from_dict(preview["studioGraph"])
    text = graph.select("binding.layout.previewTitles.text")
    assert text is not None
    assert text.kind == "binding"
    assert text.properties["path"] == "item.title"
    assert text.properties["resolved"] == "Axiom Verge"
    assert text.properties["usedFallback"] is False
    tint = graph.select("binding.glass.previewCard.tint")
    assert tint is not None
    assert tint.properties["path"] == "palette.accent"
    assert isinstance(tint.properties["resolved"], str)
    progress = graph.select("binding.surface.quickOsd.progress")
    assert progress is not None
    assert progress.properties["path"] == "osd.volume"
    assert progress.properties["resolved"] == 0.4


def test_forbidden_binding_paths_become_constraints() -> None:
    graph = build_studio_graph(
        {
            "sceneLayouts": {
                "layouts": {
                    "previewTitles": {
                        "template": {
                            "properties": {
                                "text": {
                                    "binding": "evil.qml",
                                    "fallback": "x",
                                }
                            }
                        }
                    }
                }
            }
        }
    )
    node = graph.select("binding.layout.previewTitles.text")
    assert node is not None
    assert node.properties["path"] == ""
    assert node.constraints[0].code == DIAG_BINDING
    assert graph.select("eval.python") is None


def test_graph_refuses_code_bearing_nodes() -> None:
    with pytest.raises(ValueError, match=r"qml|inválid"):
        StudioGraph.from_dict(
            {
                "selectedId": "scene",
                "nodes": [{"id": "scene", "kind": "scene", "label": "Cena", "qml": "evil.qml"}],
            }
        )
