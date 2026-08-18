# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato do canvas/árvore/inspector do Theme Studio sobre o scene graph."""

from __future__ import annotations

import pytest

from steamzero.domain.studio_graph import StudioGraph
from steamzero.domain.theme_editor import ThemeEditorManager


def test_builtin_preview_exposes_a_selectable_scene_tree() -> None:
    preview = ThemeEditorManager().load("org.steamzero.asset-recipes-demo")["preview"]
    assert isinstance(preview, dict)
    graph = preview["studioGraph"]
    assert isinstance(graph, dict)
    ids = {node["id"] for node in graph["nodes"]}
    assert "scene" in ids
    assert "layout.previewTitles" in ids
    assert "surface.saveStates" in ids
    assert "motion.focusIn" in ids
    selected = next(node for node in graph["nodes"] if node["id"] == graph["selectedId"])
    assert selected["kind"] == "scene"
    assert all(isinstance(node["properties"], dict) for node in graph["nodes"])
    assert all("qml" not in node for node in graph["nodes"])


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


def test_graph_refuses_code_bearing_nodes() -> None:
    with pytest.raises(ValueError, match=r"qml|inválid"):
        StudioGraph.from_dict(
            {
                "selectedId": "scene",
                "nodes": [{"id": "scene", "kind": "scene", "label": "Cena", "qml": "evil.qml"}],
            }
        )
