# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato executável de panels, cards, modals e drawers semânticos."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from steamzero.domain.scene_containers import (
    CRITICAL_ERROR_Z,
    DIAG_CONTAINER_FIT,
    ContainerBook,
    ContainerBounds,
    resolve_scene_containers,
)
from steamzero.domain.theme_editor import ThemeEditorManager

SCHEMA = json.loads(
    Path("src/steamzero/schemas/scene-containers-v1.schema.json").read_text(encoding="utf-8")
)


def _book(**containers: object) -> dict[str, object]:
    declared: dict[str, object] = {
        "detailPanel": {
            "kind": "panel",
            "anchor": "right",
            "size": 0.4,
            "padding": 16,
            "radius": 12,
            "elevation": 2,
        },
        "gameCard": {
            "kind": "card",
            "anchor": "center",
            "width": 320,
            "height": 180,
            "padding": 12,
            "radius": 16,
        },
        "confirmModal": {
            "kind": "modal",
            "width": 420,
            "height": 220,
            "scrimOpacity": 0.6,
            "radius": 16,
        },
        "quickDrawer": {"kind": "drawer", "anchor": "bottom", "size": 0.35, "radius": 20},
    }
    declared.update(containers)
    return {"schemaVersion": 1, "containers": declared}


def _bounds() -> ContainerBounds:
    return ContainerBounds(width=1280, height=800)


def test_schema_and_domain_accept_the_same_closed_container_recipe() -> None:
    raw = _book()
    jsonschema.validate(raw, SCHEMA)
    book = ContainerBook.from_dict(raw)
    assert set(book.containers) == {"detailPanel", "gameCard", "confirmModal", "quickDrawer"}


def test_anchored_panel_and_drawer_resolve_geometry_from_the_bounds() -> None:
    resolved = resolve_scene_containers(_book(), bounds=_bounds())
    panel = resolved.containers["detailPanel"]
    assert (panel.x, panel.y, panel.width, panel.height) == (768.0, 0.0, 512.0, 800.0)
    assert panel.padding == 16.0
    assert panel.scrim == 0.0
    assert panel.blocks_input is False

    drawer = resolved.containers["quickDrawer"]
    assert (drawer.x, drawer.y, drawer.width, drawer.height) == (0.0, 520.0, 1280.0, 280.0)


def test_centred_card_uses_declared_size_and_stays_inside_the_bounds() -> None:
    resolved = resolve_scene_containers(_book(), bounds=_bounds())
    card = resolved.containers["gameCard"]
    assert (card.x, card.y, card.width, card.height) == (480.0, 310.0, 320.0, 180.0)
    assert not resolved.diagnostics

    narrow = resolve_scene_containers(_book(), bounds=ContainerBounds(width=240, height=160))
    clamped = narrow.containers["gameCard"]
    assert clamped.width == 240.0
    assert clamped.height == 160.0
    assert clamped.x == 0.0 and clamped.y == 0.0
    assert any(
        item.code == DIAG_CONTAINER_FIT and item.container == "gameCard"
        for item in narrow.diagnostics
    )


def test_modal_materializes_scrim_blocks_input_and_never_covers_a_critical_error() -> None:
    resolved = resolve_scene_containers(_book(), bounds=_bounds())
    modal = resolved.containers["confirmModal"]
    assert modal.scrim == 0.6
    assert modal.blocks_input is True
    assert modal.z < CRITICAL_ERROR_Z
    assert modal.scrim_z < modal.z
    assert resolved.critical_error_z == CRITICAL_ERROR_Z
    assert resolved.to_qml_object()["containers"]["confirmModal"]["blocksInput"] is True
    # Panel e card ficam abaixo do modal; a pilha é materializada, não deduzida no QML.
    assert resolved.containers["detailPanel"].z < modal.scrim_z


def test_container_recipe_refuses_unknown_kinds_anchors_and_unsafe_limits() -> None:
    for override, message in (
        ({"gameCard": {"kind": "hologram"}}, "kind"),
        ({"gameCard": {"kind": "card", "anchor": "diagonal"}}, "anchor"),
        ({"gameCard": {"kind": "card", "anchor": "center", "size": 4}}, "size"),
        (
            {
                "gameCard": {
                    "kind": "card",
                    "anchor": "center",
                    "width": 200,
                    "height": 120,
                    "scrimOpacity": 0.5,
                }
            },
            "scrim",
        ),
        (
            {
                "gameCard": {
                    "kind": "card",
                    "anchor": "center",
                    "width": 200,
                    "height": 120,
                    "elevation": 9,
                }
            },
            "elevation",
        ),
        ({"detailPanel": {"kind": "panel", "anchor": "center", "size": 0.4}}, "borda"),
    ):
        with pytest.raises(ValueError, match=message):
            ContainerBook.from_dict(_book(**override))


def test_builtin_preview_exposes_resolved_containers_without_promoting_launcher() -> None:
    preview = ThemeEditorManager().load("org.steamzero.asset-recipes-demo")["preview"]
    assert isinstance(preview, dict)
    containers = preview["sceneContainerPreview"]
    assert isinstance(containers, dict)
    assert containers["containers"]["previewModal"]["blocksInput"] is True
    assert containers["criticalErrorZ"] == CRITICAL_ERROR_Z
    assert "qml" not in json.dumps(containers).lower()
