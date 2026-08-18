# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato executável de slots, galeria de saves e OSD da Theme Engine."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from steamzero.adapters.theme_catalog import ThemeCatalog
from steamzero.domain.scene_surfaces import (
    DIAG_SURFACE_ERROR,
    DIAG_SURFACE_PROGRESS,
    DIAG_SURFACE_THUMBNAIL,
    SEMANTIC_SLOTS,
    SurfaceBook,
    resolve_scene_surfaces,
)
from steamzero.domain.theme_editor import ThemeEditorManager
from steamzero.domain.themes import THEME_DEFAULT_ID

SCHEMA = json.loads(
    Path("src/steamzero/schemas/scene-surfaces-v1.schema.json").read_text(encoding="utf-8")
)


def _book() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "slots": {
            "home": {"component": "recentRail"},
            "library": {"component": "libraryGrid"},
            "saveStates": {"component": "saveGallery"},
            "osd": {"component": "quickOsd"},
            "error": {"component": "errorBanner"},
        },
        "components": {
            "recentRail": {"kind": "recentlyPlayed", "source": "library.recent"},
            "libraryGrid": {"kind": "gameGrid", "source": "library.items"},
            "saveGallery": {
                "kind": "saveGallery",
                "source": "saves.slots",
                "maxItems": 4,
            },
            "quickOsd": {
                "kind": "osd",
                "items": ["volume", "mute", "pause", "saveState"],
                "progress": {"binding": "osd.volume", "fallback": 0},
            },
            "errorBanner": {"kind": "errorBanner"},
        },
    }


def _read_model() -> dict[str, object]:
    return {
        "library": {"items": [{"title": "Celeste"}], "recent": [{"title": "Celeste"}]},
        "saves": {
            "slots": [
                {
                    "label": "Auto",
                    "timestamp": "2026-08-17T12:00:00Z",
                    "playtime": "1h 12m",
                    "compatible": True,
                    "hasThumbnail": True,
                },
                {
                    "label": "Slot 2",
                    "timestamp": "",
                    "playtime": "",
                    "compatible": False,
                    "hasThumbnail": False,
                },
            ]
        },
        "osd": {"volume": 0.4, "muted": False, "paused": False},
    }


def test_schema_and_domain_accept_the_same_closed_surface_recipe() -> None:
    raw = _book()
    jsonschema.validate(raw, SCHEMA)
    book = SurfaceBook.from_dict(raw)
    assert set(book.slots) >= {"saveStates", "osd"}
    assert book.components["saveGallery"].kind == "saveGallery"


def test_all_semantic_slots_resolve_and_saves_keep_fallback_without_capture() -> None:
    resolved = resolve_scene_surfaces(_book(), _read_model())
    assert set(resolved.slots) == set(SEMANTIC_SLOTS)
    gallery = resolved.slots["saveStates"]
    assert gallery.kind == "saveGallery"
    assert [entry["title"] for entry in gallery.entries] == ["Auto", "Slot 2"]
    assert gallery.entries[1]["thumbnailFallback"] is True
    assert gallery.entries[0]["compatible"] is True
    assert any(item.code == DIAG_SURFACE_THUMBNAIL for item in resolved.diagnostics)
    assert all("/" not in str(entry) for entry in gallery.entries)


def test_osd_cannot_hide_critical_error_or_fake_success() -> None:
    model = _read_model()
    osd = dict(model["osd"])  # type: ignore[arg-type]
    osd["criticalError"] = {"code": "E-LAUNCH-FAIL", "message": "Falha ao iniciar"}
    osd["success"] = True
    model["osd"] = osd
    resolved = resolve_scene_surfaces(_book(), model)
    bar = resolved.slots["osd"]
    assert bar.critical_visible is True
    assert bar.success is False
    assert bar.progress == 0.4
    assert "volume" in bar.items
    assert any(item.code == DIAG_SURFACE_ERROR for item in resolved.diagnostics)
    assert resolved.slots["error"].kind == "errorBanner"


def _progress_book(**component: object) -> dict[str, object]:
    raw = _book()
    slots = dict(raw["slots"])  # type: ignore[arg-type]
    slots["loading"] = {"component": "downloadBar"}
    raw["slots"] = slots
    components = dict(raw["components"])  # type: ignore[arg-type]
    components["downloadBar"] = {
        "kind": "progressBar",
        "progress": {"binding": "progress.download.ratio", "fallback": 0},
        **component,
    }
    raw["components"] = components
    return raw


def _progress_model(**progress: object) -> dict[str, object]:
    model = _read_model()
    model["progress"] = {"download": {"ratio": 0.375, "current": 3, "total": 8, **progress}}
    return model


def test_progress_bar_materializes_value_segments_and_counter_label() -> None:
    raw = _progress_book(
        style="segmented",
        segments=8,
        counter={
            "current": "progress.download.current",
            "total": "progress.download.total",
            "format": "{current}/{total}",
        },
    )
    jsonschema.validate(raw, SCHEMA)
    resolved = resolve_scene_surfaces(raw, _progress_model())
    bar = resolved.slots["loading"]
    assert bar.kind == "progressBar"
    assert bar.progress == 0.375
    assert bar.style == "segmented"
    assert bar.segments == 8
    assert bar.filled_segments == 3
    assert bar.sweep == 0.0
    assert bar.label == "3/8"
    assert not any(item.code == DIAG_SURFACE_PROGRESS for item in resolved.diagnostics)
    assert bar.to_dict()["filledSegments"] == 3


def test_circular_progress_materializes_the_sweep_angle() -> None:
    raw = _progress_book(style="circular")
    jsonschema.validate(raw, SCHEMA)
    bar = resolve_scene_surfaces(raw, _progress_model()).slots["loading"]
    assert bar.style == "circular"
    assert bar.sweep == 135.0
    assert bar.segments == 0
    assert bar.filled_segments == 0


def test_dotted_progress_clamps_filled_dots_to_the_declared_segments() -> None:
    raw = _progress_book(style="dotted", segments=4)
    jsonschema.validate(raw, SCHEMA)
    bar = resolve_scene_surfaces(raw, _progress_model(ratio=2.5)).slots["loading"]
    assert bar.style == "dotted"
    assert bar.progress == 1.0
    assert bar.filled_segments == 4


def test_progress_counter_without_source_keeps_the_bar_and_reports_a_diagnostic() -> None:
    raw = _progress_book(
        counter={
            "current": "progress.download.current",
            "total": "progress.download.total",
        }
    )
    jsonschema.validate(raw, SCHEMA)
    model = _read_model()
    model["progress"] = {"download": {"ratio": 0.5}}
    resolved = resolve_scene_surfaces(raw, model)
    bar = resolved.slots["loading"]
    assert bar.kind == "progressBar"
    assert bar.progress == 0.5
    assert bar.label == ""
    assert any(
        item.code == DIAG_SURFACE_PROGRESS and item.slot == "loading"
        for item in resolved.diagnostics
    )


def test_progress_recipe_refuses_unsafe_styles_limits_and_formats() -> None:
    for component, message in (
        ({"style": "hologram"}, "style"),
        ({"style": "segmented", "segments": 64}, "segments"),
        ({"style": "linear", "segments": 4}, "segments"),
        (
            {
                "counter": {
                    "current": "progress.download.current",
                    "total": "progress.download.total",
                    "format": "{current} de {secret}",
                }
            },
            "format",
        ),
        (
            {"counter": {"current": "saves.slots", "total": "progress.download.total"}},
            "counter",
        ),
    ):
        with pytest.raises(ValueError, match=message):
            SurfaceBook.from_dict(_progress_book(**component))


def test_recipe_refuses_unknown_slot_code_paths_and_private_sources() -> None:
    with pytest.raises(ValueError, match="slot"):
        SurfaceBook.from_dict(
            {
                "schemaVersion": 1,
                "slots": {"bigPicture": {"component": "libraryGrid"}},
                "components": {"libraryGrid": {"kind": "gameGrid", "source": "library.items"}},
            }
        )
    with pytest.raises(ValueError, match=r"kind|source"):
        SurfaceBook.from_dict(
            {
                "schemaVersion": 1,
                "slots": {"osd": {"component": "evil"}},
                "components": {
                    "evil": {"kind": "osd", "source": "saves.__class__", "items": ["volume"]}
                },
            }
        )
    raw = _book()
    raw["script"] = "Qt.quit()"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(raw, SCHEMA)


def test_builtin_preview_consumes_surfaces_without_promoting_launcher() -> None:
    preview = ThemeEditorManager().load("org.steamzero.asset-recipes-demo")["preview"]
    assert isinstance(preview, dict)
    surfaces = preview["sceneSurfacePreview"]
    assert surfaces["slots"]["saveStates"]["kind"] == "saveGallery"
    assert surfaces["slots"]["osd"]["criticalVisible"] is False
    assert surfaces["slots"]["osd"]["items"][0] == "volume"
    accessible = ThemeCatalog().resolve(
        "org.steamzero.asset-recipes-demo",
        high_contrast=True,
        reduced_motion=True,
    )
    assert accessible.scene_surfaces is not None
    assert accessible.reduced_motion is True
    assert accessible.high_contrast is True
    fallback = ThemeCatalog().resolve("org.missing.surfaces")
    assert fallback.id == THEME_DEFAULT_ID
    assert fallback.scene_surfaces is None
