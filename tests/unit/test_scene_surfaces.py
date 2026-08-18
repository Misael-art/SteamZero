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
