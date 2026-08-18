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


def test_cover_flow_materializes_overlap_and_rotation() -> None:
    raw = {
        "schemaVersion": 1,
        "layouts": {
            "libraryCover": {
                "source": "library.items",
                "kind": "coverFlow",
                "item": {"width": 80, "height": 24},
                "gap": 0,
                "selected": 1,
                "offset": {
                    "scaleStep": 0.1,
                    "opacityStep": 0.15,
                    "minScale": 0.65,
                    "minOpacity": 0.4,
                    "rotationStep": 28,
                    "maxRotation": 55,
                    "overlap": 0.45,
                },
                "template": {
                    "kind": "text",
                    "id": "cover-title",
                    "properties": {"text": {"binding": "item.title", "fallback": "—"}},
                },
            }
        },
    }
    jsonschema.validate(raw, SCHEMA)
    book = LayoutRecipeBook.from_dict(raw)
    resolved = resolve_scene_layouts(book, _read_model(), bounds=LayoutBounds(width=400, height=80))
    layout = resolved.layouts["libraryCover"]
    assert layout.kind is LayoutKind.COVER_FLOW
    assert [round(entry.x, 1) for entry in layout.entries[:3]] == [124.0, 160.0, 196.0]
    assert layout.entries[1].node["rotationY"] == 0
    assert layout.entries[1].node["scale"] == 1.0
    assert layout.entries[0].node["rotationY"] == -28.0
    assert layout.entries[2].node["rotationY"] == 28.0
    assert layout.entries[0].node["scale"] == 0.9
    assert layout.entries[0].node["opacity"] == 0.85
    assert all("binding" not in entry.node for entry in layout.entries)


def test_carousel_places_items_on_an_ellipse_by_wrapped_distance() -> None:
    raw = {
        "schemaVersion": 1,
        "layouts": {
            "focusCarousel": {
                "source": "library.items",
                "kind": "carousel",
                "item": {"width": 80, "height": 24},
                "maxItems": 3,
                "selected": 1,
                "template": {
                    "kind": "text",
                    "id": "carousel-title",
                    "properties": {"text": {"binding": "item.title", "fallback": "—"}},
                },
            }
        },
    }
    jsonschema.validate(raw, SCHEMA)
    book = LayoutRecipeBook.from_dict(raw)
    resolved = resolve_scene_layouts(book, _read_model(), bounds=LayoutBounds(width=400, height=80))
    layout = resolved.layouts["focusCarousel"]
    assert layout.kind is LayoutKind.CAROUSEL
    assert [entry.node["text"] for entry in layout.entries] == [
        "Axiom Verge",
        "Celeste",
        "Hades",
    ]
    assert [round(entry.x, 1) for entry in layout.entries] == [21.4, 160.0, 298.6]
    assert [round(entry.y, 1) for entry in layout.entries] == [42.0, 0.0, 42.0]
    assert layout.entries[1].node["distance"] == 0
    assert layout.entries[1].node["scale"] == 1.0
    assert layout.entries[0].node["distance"] == -1
    assert layout.entries[0].node["scale"] == 0.92
    assert layout.entries[2].node["distance"] == 1
    assert all("binding" not in entry.node for entry in layout.entries)


def _highlight_book(**highlight: object) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "layouts": {
            "focusWheel": {
                "source": "library.items",
                "kind": "wheel",
                "item": {"width": 80, "height": 24},
                "gap": 10,
                "maxItems": 5,
                "selected": 1,
                "highlight": {
                    "scale": 1.2,
                    "opacity": 1,
                    "outlineWidth": 3,
                    "outlineColor": "#22d3ee",
                    **highlight,
                },
                "template": {
                    "kind": "text",
                    "id": "wheel-title",
                    "properties": {"text": {"binding": "item.title", "fallback": "—"}},
                },
            }
        },
    }


def test_central_highlight_overrides_the_offset_falloff_for_the_selected_item() -> None:
    raw = _highlight_book()
    jsonschema.validate(raw, SCHEMA)
    book = LayoutRecipeBook.from_dict(raw)
    resolved = resolve_scene_layouts(book, _read_model(), bounds=LayoutBounds(width=400, height=80))
    entries = resolved.layouts["focusWheel"].entries
    center = entries[1].node
    assert center["highlighted"] is True
    assert center["adjacent"] is False
    assert center["scale"] == 1.2
    assert center["opacity"] == 1.0
    assert center["outlineWidth"] == 3.0
    assert center["outlineColor"] == "#22d3ee"
    # Sem tratamento declarado, vizinhos e distantes seguem o offset converter.
    assert entries[0].node["highlighted"] is False
    assert entries[0].node["scale"] == 0.92
    assert entries[0].node["outlineWidth"] == 0.0
    assert entries[3].node["adjacent"] is False


def test_adjacent_treatment_applies_only_to_the_immediate_neighbours() -> None:
    raw = _highlight_book(
        adjacent={"scale": 0.9, "opacity": 0.6, "outlineWidth": 1, "outlineColor": "#334155"}
    )
    jsonschema.validate(raw, SCHEMA)
    book = LayoutRecipeBook.from_dict(raw)
    entries = (
        resolve_scene_layouts(book, _read_model(), bounds=LayoutBounds(width=400, height=80))
        .layouts["focusWheel"]
        .entries
    )
    assert [entry.node["adjacent"] for entry in entries] == [True, False, True, False, False]
    assert entries[0].node["scale"] == 0.9
    assert entries[0].node["opacity"] == 0.6
    assert entries[0].node["outlineWidth"] == 1.0
    assert entries[0].node["outlineColor"] == "#334155"
    assert entries[2].node["scale"] == 0.9
    # Distância 2 continua no falloff do offset, sem contorno.
    assert entries[3].node["scale"] == 0.84
    assert entries[3].node["outlineWidth"] == 0.0


def test_highlight_refuses_layouts_without_a_centre_and_unsafe_limits() -> None:
    for override, message in (
        ({"outlineWidth": 32}, "outlineWidth"),
        ({"outlineColor": "rgba(0,0,0,1)"}, "outlineColor"),
        ({"scale": 4}, "scale"),
    ):
        with pytest.raises(ValueError, match=message):
            LayoutRecipeBook.from_dict(_highlight_book(**override))
    with pytest.raises(ValueError, match="highlight"):
        LayoutRecipeBook.from_dict(
            {
                "schemaVersion": 1,
                "layouts": {
                    "plainGrid": {
                        "source": "library.items",
                        "kind": "grid",
                        "item": {"width": 80, "height": 24},
                        "highlight": {"scale": 1.2},
                        "template": {"kind": "text", "id": "x"},
                    }
                },
            }
        )


def test_flow_wraps_by_bounds_and_reports_computed_columns() -> None:
    raw = {
        "schemaVersion": 1,
        "layouts": {
            "shelfFlow": {
                "source": "library.items",
                "kind": "flow",
                "item": {"width": 80, "height": 24},
                "gap": 10,
                "maxItems": 5,
                "template": {
                    "kind": "text",
                    "id": "flow-title",
                    "properties": {"text": {"binding": "item.title", "fallback": "—"}},
                },
            }
        },
    }
    jsonschema.validate(raw, SCHEMA)
    book = LayoutRecipeBook.from_dict(raw)
    resolved = resolve_scene_layouts(
        book, _read_model(), bounds=LayoutBounds(width=400, height=300)
    )
    layout = resolved.layouts["shelfFlow"]
    assert layout.kind is LayoutKind.FLOW
    assert layout.columns == 4
    assert [(entry.x, entry.y) for entry in layout.entries] == [
        (0.0, 0.0),
        (90.0, 0.0),
        (180.0, 0.0),
        (270.0, 0.0),
        (0.0, 34.0),
    ]
    assert resolved.diagnostics == ()
    assert all("binding" not in entry.node for entry in layout.entries)

    narrow = resolve_scene_layouts(book, _read_model(), bounds=LayoutBounds(width=200, height=300))
    assert narrow.layouts["shelfFlow"].columns == 2
    assert [(entry.x, entry.y) for entry in narrow.layouts["shelfFlow"].entries][:3] == [
        (0.0, 0.0),
        (90.0, 0.0),
        (0.0, 34.0),
    ]


def test_vertical_flow_wraps_by_bounds_height() -> None:
    raw = {
        "schemaVersion": 1,
        "layouts": {
            "columnFlow": {
                "source": "library.items",
                "kind": "flow",
                "direction": "vertical",
                "item": {"width": 80, "height": 24},
                "gap": 10,
                "maxItems": 5,
                "template": {"kind": "text", "id": "flow-title"},
            }
        },
    }
    jsonschema.validate(raw, SCHEMA)
    book = LayoutRecipeBook.from_dict(raw)
    resolved = resolve_scene_layouts(book, _read_model(), bounds=LayoutBounds(width=400, height=80))
    layout = resolved.layouts["columnFlow"]
    assert layout.columns == 3
    assert [(entry.x, entry.y) for entry in layout.entries] == [
        (0.0, 0.0),
        (0.0, 34.0),
        (90.0, 0.0),
        (90.0, 34.0),
        (180.0, 0.0),
    ]


def test_flow_degrades_to_a_single_track_with_diagnostic_when_item_exceeds_bounds() -> None:
    raw = {
        "schemaVersion": 1,
        "layouts": {
            "tooWide": {
                "source": "library.recent",
                "kind": "flow",
                "item": {"width": 240, "height": 36},
                "gap": 8,
                "template": {"kind": "text", "id": "flow-title"},
            }
        },
    }
    jsonschema.validate(raw, SCHEMA)
    book = LayoutRecipeBook.from_dict(raw)
    resolved = resolve_scene_layouts(
        book, _read_model(), bounds=LayoutBounds(width=100, height=300)
    )
    layout = resolved.layouts["tooWide"]
    assert layout.columns == 1
    assert [(entry.x, entry.y) for entry in layout.entries] == [(0.0, 0.0), (0.0, 44.0)]
    assert any(
        item.code == DIAG_LAYOUT_LIMIT
        and item.layout == "tooWide"
        and item.fallback == "singleTrack"
        for item in resolved.diagnostics
    )


def test_flow_refuses_declared_columns_and_breakpoints() -> None:
    for extra in ({"columns": 3}, {"breakpoints": [{"columns": 2}]}):
        with pytest.raises(ValueError, match="flow"):
            LayoutRecipeBook.from_dict(
                {
                    "schemaVersion": 1,
                    "layouts": {
                        "bad": {
                            "source": "library.items",
                            "kind": "flow",
                            "item": {"width": 80, "height": 24},
                            "template": {"kind": "text", "id": "x"},
                            **extra,
                        }
                    },
                }
            )


def test_stack_overlaps_items_by_gap_and_materializes_depth() -> None:
    raw = {
        "schemaVersion": 1,
        "layouts": {
            "focusStack": {
                "source": "library.items",
                "kind": "stack",
                "item": {"width": 80, "height": 24},
                "gap": 12,
                "maxItems": 3,
                "selected": 1,
                "template": {
                    "kind": "text",
                    "id": "stack-title",
                    "properties": {"text": {"binding": "item.title", "fallback": "—"}},
                },
            }
        },
    }
    jsonschema.validate(raw, SCHEMA)
    book = LayoutRecipeBook.from_dict(raw)
    resolved = resolve_scene_layouts(book, _read_model(), bounds=LayoutBounds(width=400, height=80))
    layout = resolved.layouts["focusStack"]
    assert layout.kind is LayoutKind.STACK
    assert [(entry.x, entry.y) for entry in layout.entries] == [
        (160.0, 16.0),
        (160.0, 28.0),
        (160.0, 40.0),
    ]
    assert [entry.node["z"] for entry in layout.entries] == [31, 32, 31]
    assert [entry.node["scale"] for entry in layout.entries] == [0.92, 1.0, 0.92]
    assert [entry.node["opacity"] for entry in layout.entries] == [0.82, 1.0, 0.82]
    assert [entry.node["distance"] for entry in layout.entries] == [-1, 0, 1]
    assert all("binding" not in entry.node for entry in layout.entries)


def test_horizontal_stack_peeks_on_the_x_axis_only() -> None:
    raw = {
        "schemaVersion": 1,
        "layouts": {
            "sideStack": {
                "source": "library.items",
                "kind": "stack",
                "direction": "horizontal",
                "item": {"width": 80, "height": 24},
                "gap": 12,
                "maxItems": 3,
                "selected": 1,
                "template": {"kind": "text", "id": "stack-title"},
            }
        },
    }
    jsonschema.validate(raw, SCHEMA)
    book = LayoutRecipeBook.from_dict(raw)
    resolved = resolve_scene_layouts(book, _read_model(), bounds=LayoutBounds(width=400, height=80))
    layout = resolved.layouts["sideStack"]
    assert [(entry.x, entry.y) for entry in layout.entries] == [
        (148.0, 28.0),
        (160.0, 28.0),
        (172.0, 28.0),
    ]


def test_stack_refuses_breakpoints() -> None:
    with pytest.raises(ValueError, match="stack"):
        LayoutRecipeBook.from_dict(
            {
                "schemaVersion": 1,
                "layouts": {
                    "bad": {
                        "source": "library.items",
                        "kind": "stack",
                        "item": {"width": 80, "height": 24},
                        "template": {"kind": "text", "id": "x"},
                        "breakpoints": [{"columns": 2}],
                    }
                },
            }
        )


def test_cover_flow_refuses_vertical_direction() -> None:
    with pytest.raises(ValueError, match="horizontal"):
        LayoutRecipeBook.from_dict(
            {
                "schemaVersion": 1,
                "layouts": {
                    "bad": {
                        "source": "library.items",
                        "kind": "coverFlow",
                        "direction": "vertical",
                        "item": {"width": 80, "height": 24},
                        "template": {"kind": "text", "id": "x"},
                    }
                },
            }
        )


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
                "kind": "mosaic",
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
                            "kind": "mosaic",
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
