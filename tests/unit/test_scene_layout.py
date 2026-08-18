# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato executável de layouts responsivos e repetidores declarativos."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from steamzero.adapters.theme_catalog import ThemeCatalog
from steamzero.domain.scene_layout import (
    DIAG_LAYOUT_LIMIT,
    DIAG_LAYOUT_SOURCE,
    LayoutBounds,
    LayoutKind,
    LayoutRecipeBook,
    resolve_scene_layouts,
)
from steamzero.domain.themes import THEME_DEFAULT_ID

SCHEMA = json.loads(
    Path("src/steamzero/schemas/scene-layout-v1.schema.json").read_text(encoding="utf-8")
)


def _raw_book() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "layouts": {
            "libraryGrid": {
                "source": "library.items",
                "kind": "grid",
                "item": {"width": 120, "height": 64},
                "gap": 12,
                "maxItems": 12,
                "breakpoints": [
                    {"maxWidth": 639, "columns": 2},
                    {"minWidth": 640, "columns": 4},
                ],
                "template": {
                    "kind": "text",
                    "id": "game-title",
                    "properties": {
                        "text": {"binding": "item.title", "fallback": "Sem título"},
                        "color": "#f2f6fb",
                        "fontPixelSize": 16,
                    },
                },
            },
            "recentList": {
                "source": "library.recent",
                "kind": "list",
                "direction": "vertical",
                "item": {"width": 240, "height": 36},
                "gap": 8,
                "maxItems": 4,
                "template": {
                    "kind": "text",
                    "id": "recent-title",
                    "properties": {
                        "text": {"binding": "item.title", "fallback": "Sem título"},
                        "color": "#ffffff",
                        "fontPixelSize": 14,
                    },
                },
            },
        },
    }


def _read_model() -> dict[str, object]:
    return {
        "library": {
            "items": [
                {"title": "Axiom Verge"},
                {"title": "Celeste"},
                {"title": "Hades"},
                {"title": "Tunic"},
                {"title": ""},
            ],
            "recent": [{"title": "Celeste"}, {"title": "Tunic"}],
        }
    }


def test_schema_and_domain_accept_the_same_closed_recipe() -> None:
    raw = _raw_book()
    jsonschema.validate(raw, SCHEMA)
    book = LayoutRecipeBook.from_dict(raw)
    assert set(book.layouts) == {"libraryGrid", "recentList"}


def test_grid_changes_columns_at_breakpoint_and_binds_final_values() -> None:
    book = LayoutRecipeBook.from_dict(_raw_book())
    narrow = resolve_scene_layouts(book, _read_model(), bounds=LayoutBounds(width=600, height=300))
    wide = resolve_scene_layouts(book, _read_model(), bounds=LayoutBounds(width=800, height=300))

    assert narrow.layouts["libraryGrid"].columns == 2
    assert wide.layouts["libraryGrid"].columns == 4
    assert [(item.x, item.y) for item in wide.layouts["libraryGrid"].entries[:5]] == [
        (0.0, 0.0),
        (132.0, 0.0),
        (264.0, 0.0),
        (396.0, 0.0),
        (0.0, 76.0),
    ]
    last = wide.layouts["libraryGrid"].entries[-1]
    assert last.node["text"] == "Sem título"
    assert last.node["id"] == "game-title-4"
    assert last.node["horizontalAlignment"] == "AlignLeft"
    assert last.node["visible"] is True


def test_list_is_declarative_bounded_and_uses_vertical_flow() -> None:
    book = LayoutRecipeBook.from_dict(_raw_book())
    resolved = resolve_scene_layouts(
        book, _read_model(), bounds=LayoutBounds(width=800, height=300)
    )
    layout = resolved.layouts["recentList"]
    assert layout.columns == 1
    assert [(entry.x, entry.y) for entry in layout.entries] == [(0.0, 0.0), (0.0, 44.0)]
    assert all(entry.node["kind"] == "text" for entry in layout.entries)


def test_wheel_applies_offset_converter_from_selected_index() -> None:
    raw = {
        "schemaVersion": 1,
        "layouts": {
            "focusWheel": {
                "source": "library.items",
                "kind": "wheel",
                "item": {"width": 80, "height": 24},
                "gap": 10,
                "selected": 1,
                "template": {
                    "kind": "text",
                    "id": "wheel-title",
                    "properties": {"text": {"binding": "item.title", "fallback": "—"}},
                },
            }
        },
    }
    jsonschema.validate(raw, SCHEMA)
    book = LayoutRecipeBook.from_dict(raw)
    resolved = resolve_scene_layouts(book, _read_model(), bounds=LayoutBounds(width=400, height=80))
    layout = resolved.layouts["focusWheel"]
    assert layout.kind is LayoutKind.WHEEL
    assert [entry.node["text"] for entry in layout.entries[:3]] == [
        "Axiom Verge",
        "Celeste",
        "Hades",
    ]
    assert [round(entry.x, 1) for entry in layout.entries[:3]] == [70.0, 160.0, 250.0]
    assert layout.entries[1].node["scale"] == 1.0
    assert layout.entries[1].node["opacity"] == 1.0
    assert layout.entries[1].node["z"] == 32
    assert layout.entries[0].node["scale"] == 0.92
    assert layout.entries[0].node["opacity"] == 0.82
    assert layout.entries[0].node["z"] == 31
    assert layout.entries[0].node["distance"] == -1
    assert all("binding" not in entry.node for entry in layout.entries)


def test_missing_or_incompatible_source_degrades_to_safe_empty_layout_with_diagnostic() -> None:
    book = LayoutRecipeBook.from_dict(_raw_book())
    resolved = resolve_scene_layouts(
        book,
        {"library": {"items": "not-a-list", "recent": []}},
        bounds=LayoutBounds(width=800, height=300),
    )
    layout = resolved.layouts["libraryGrid"]
    assert layout.entries == ()
    assert any(
        item.code == DIAG_LAYOUT_SOURCE and item.layout == "libraryGrid"
        for item in resolved.diagnostics
    )


@pytest.mark.parametrize(
    "payload, pattern",
    [
        (
            {
                "source": "library.items",
                "kind": "coverFlow",
                "item": {"width": 1, "height": 1},
                "template": {"kind": "text", "id": "x"},
            },
            "kind",
        ),
        (
            {
                "source": "library.items",
                "kind": "grid",
                "item": {"width": 1, "height": 1},
                "template": {"kind": "text", "id": "x", "qml": "evil.qml"},
            },
            "template",
        ),
        (
            {
                "source": "library.__class__",
                "kind": "grid",
                "item": {"width": 1, "height": 1},
                "template": {"kind": "text", "id": "x"},
            },
            "source",
        ),
        (
            {
                "source": "library.items",
                "kind": "grid",
                "item": {"width": 9000, "height": 1},
                "template": {"kind": "text", "id": "x"},
            },
            "item",
        ),
    ],
)
def test_recipe_refuses_code_paths_unknown_kinds_and_excessive_cost(
    payload: dict[str, object], pattern: str
) -> None:
    with pytest.raises(ValueError, match=pattern):
        LayoutRecipeBook.from_dict({"schemaVersion": 1, "layouts": {"bad": payload}})


def test_schema_refuses_unknown_properties_and_arbitrary_code() -> None:
    raw = _raw_book()
    layout = raw["layouts"]["libraryGrid"]
    assert isinstance(layout, dict)
    layout["script"] = "Qt.quit()"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(raw, SCHEMA)


def test_horizontal_list_and_limit_emit_final_nodes_and_diagnostic() -> None:
    raw = {
        "schemaVersion": 1,
        "layouts": {
            "recentRow": {
                "source": "library.recent",
                "kind": "list",
                "direction": "horizontal",
                "item": {"width": 80, "height": 24},
                "gap": 10,
                "maxItems": 2,
                "template": {
                    "kind": "text",
                    "id": "row-title",
                    "properties": {"text": {"binding": "item.title", "fallback": "—"}},
                },
            }
        },
    }
    book = LayoutRecipeBook.from_dict(raw)
    resolved = resolve_scene_layouts(
        book,
        {
            "library": {
                "recent": [{"title": "Axiom Verge"}, {"title": "Celeste"}, {"title": "Hades"}]
            }
        },
        bounds=LayoutBounds(width=400, height=80),
    )
    layout = resolved.layouts["recentRow"]
    assert layout.kind is LayoutKind.LIST
    assert [(entry.x, entry.y, entry.node["text"]) for entry in layout.entries] == [
        (0.0, 0.0, "Axiom Verge"),
        (90.0, 0.0, "Celeste"),
    ]
    assert all("binding" not in entry.node for entry in layout.entries)
    assert any(
        item.code == DIAG_LAYOUT_LIMIT and item.layout == "recentRow"
        for item in resolved.diagnostics
    )


def test_invalid_scene_layouts_fall_back_to_builtin_and_keep_accessibility(
    tmp_path: Path,
) -> None:
    theme_dir = tmp_path / "org.test.bad-layout"
    theme_dir.mkdir()
    (theme_dir / "theme.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "kind": "steamzero-theme-v1",
                "id": "org.test.bad-layout",
                "name": "Bad Layout",
                "version": "1.0.0",
                "author": "Tester",
                "license": "MIT",
                "compatibility": {"themeApi": 1},
                "sceneLayouts": {
                    "schemaVersion": 1,
                    "layouts": {
                        "bad": {
                            "source": "library.items",
                            "kind": "coverFlow",
                            "item": {"width": 10, "height": 10},
                            "template": {"kind": "text", "id": "x"},
                        }
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    catalog = ThemeCatalog(user_themes_dir=tmp_path)
    entries = {entry["id"]: entry for entry in catalog.list_catalog()}
    assert entries["org.test.bad-layout"]["state"] == "invalid"
    resolved = catalog.resolve(
        "org.test.bad-layout",
        high_contrast=True,
        reduced_motion=True,
    )
    assert resolved.id == THEME_DEFAULT_ID
    assert resolved.high_contrast is True
    assert resolved.reduced_motion is True
    assert resolved.color.background == "#000000"
    assert resolved.motion.durationNormal == 0
    assert resolved.scene_layouts is None
