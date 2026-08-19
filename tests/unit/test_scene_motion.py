# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato executável de estados nativos, transições e timeline."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from steamzero.adapters.theme_catalog import ThemeCatalog
from steamzero.domain.scene_motion import (
    DIAG_MOTION_PRESENCE,
    DIAG_MOTION_REDUCED,
    NATIVE_STATES,
    MotionBook,
    resolve_scene_motion,
)
from steamzero.domain.theme_editor import ThemeEditorManager

SCHEMA = json.loads(
    Path("src/steamzero/schemas/scene-motion-v1.schema.json").read_text(encoding="utf-8")
)


def _book() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "states": {
            "normal": {"opacity": 1, "scale": 1},
            "focused": {"opacity": 1, "scale": 1.06},
            "selected": {"opacity": 1, "scale": 1.04},
            "pressed": {"opacity": 0.92, "scale": 0.98},
            "disabled": {"opacity": 0.45},
        },
        "transitions": [
            {
                "id": "focusIn",
                "from": "normal",
                "to": "focused",
                "duration": 180,
                "easing": "cubicOut",
                "essential": False,
            },
            {
                "id": "errorFlash",
                "from": "normal",
                "to": "error",
                "duration": 90,
                "easing": "linear",
                "essential": True,
            },
        ],
        "timelines": {
            "previewFocus": {
                "kind": "sequence",
                "repeat": 0,
                "clips": [
                    {"state": "normal", "duration": 0},
                    {"transition": "focusIn"},
                    {"state": "focused", "duration": 80},
                ],
            }
        },
    }


def test_schema_and_domain_accept_the_same_closed_motion_recipe() -> None:
    raw = _book()
    jsonschema.validate(raw, SCHEMA)
    book = MotionBook.from_dict(raw)
    assert set(book.states) >= {"normal", "focused"}
    assert "focusIn" in book.transitions


def test_native_states_fill_defaults_and_snapshots_are_scalars() -> None:
    resolved = resolve_scene_motion(_book())
    assert set(resolved.states) == set(NATIVE_STATES)
    focused = resolved.states["focused"]
    assert focused.opacity == 1.0
    assert focused.scale == 1.06
    assert focused.translate_x == 0.0
    assert "easing" not in focused.to_dict()


def test_reduced_motion_zeros_non_essential_and_keeps_error_flash() -> None:
    full = resolve_scene_motion(_book())
    reduced = resolve_scene_motion(_book(), reduced_motion=True)
    assert full.transitions["focusIn"].duration == 180
    assert reduced.transitions["focusIn"].duration == 0
    assert reduced.transitions["errorFlash"].duration == 90
    assert any(item.code == DIAG_MOTION_REDUCED for item in reduced.diagnostics)
    preview = reduced.timelines["previewFocus"]
    assert preview.total_duration == 80
    assert preview.steps[-1].state == "focused"


def test_timeline_materializes_sequence_without_package_code() -> None:
    resolved = resolve_scene_motion(_book())
    timeline = resolved.timelines["previewFocus"]
    assert timeline.kind == "sequence"
    assert [step.state for step in timeline.steps] == ["normal", "focused", "focused"]
    assert timeline.total_duration == 260
    assert all("script" not in step.to_dict() for step in timeline.steps)


def _presence_book(**presence: object) -> dict[str, object]:
    raw = _book()
    raw["presence"] = {
        "source": "interaction.state",
        "fadeDuration": 200,
        "layers": {
            "chrome": {"idle": 0.2, "navigating": 1, "focused": 1, "menuOpen": 0.5},
            "osd": {"idle": 0, "navigating": 0.8, "focused": 1, "menuOpen": 1},
        },
        **presence,
    }
    return raw


def test_transparency_follows_the_declared_interaction_state() -> None:
    raw = _presence_book()
    jsonschema.validate(raw, SCHEMA)
    idle = resolve_scene_motion(raw, interaction_state="idle")
    assert idle.presence["chrome"].opacity == 0.2
    assert idle.presence["chrome"].state == "idle"
    assert idle.presence["chrome"].fade_duration == 200
    assert idle.presence["osd"].opacity == 0.0

    menu = resolve_scene_motion(raw, interaction_state="menuOpen")
    assert menu.presence["chrome"].opacity == 0.5
    assert menu.presence["osd"].opacity == 1.0
    assert menu.to_qml_object()["presence"]["chrome"]["opacity"] == 0.5


def test_unknown_interaction_state_falls_back_to_full_opacity_with_diagnostic() -> None:
    raw = _presence_book()
    resolved = resolve_scene_motion(raw, interaction_state="screensaver")
    assert resolved.presence["chrome"].opacity == 1.0
    assert resolved.presence["chrome"].state == "unknown"
    assert any(item.code == DIAG_MOTION_PRESENCE for item in resolved.diagnostics)

    missing = resolve_scene_motion(raw)
    assert missing.presence["chrome"].opacity == 1.0
    assert any(item.code == DIAG_MOTION_PRESENCE for item in missing.diagnostics)


def test_reduced_motion_cuts_the_transparency_fade_without_losing_the_value() -> None:
    raw = _presence_book()
    resolved = resolve_scene_motion(raw, interaction_state="idle", reduced_motion=True)
    assert resolved.presence["chrome"].opacity == 0.2
    assert resolved.presence["chrome"].fade_duration == 0
    assert any(item.code == DIAG_MOTION_REDUCED for item in resolved.diagnostics)


def test_presence_recipe_refuses_unknown_states_sources_and_limits() -> None:
    for override, message in (
        ({"source": "os.environ"}, "source"),
        ({"layers": {"chrome": {"screensaver": 0.5}}}, "estado"),
        ({"layers": {"chrome": {"idle": 4}}}, "opacity"),
        ({"fadeDuration": 9000}, "fadeDuration"),
    ):
        with pytest.raises(ValueError, match=message):
            MotionBook.from_dict(_presence_book(**override))


def test_recipe_refuses_unknown_state_easing_code_and_excessive_duration() -> None:
    with pytest.raises(ValueError, match="estado"):
        MotionBook.from_dict(
            {
                "schemaVersion": 1,
                "states": {"hovering": {"opacity": 1}},
                "transitions": [],
                "timelines": {},
            }
        )
    with pytest.raises(ValueError, match="easing"):
        MotionBook.from_dict(
            {
                "schemaVersion": 1,
                "states": {"normal": {}},
                "transitions": [
                    {
                        "id": "bad",
                        "from": "normal",
                        "to": "focused",
                        "duration": 10,
                        "easing": "Math.sin",
                    }
                ],
                "timelines": {},
            }
        )
    with pytest.raises(ValueError, match="duration"):
        MotionBook.from_dict(
            {
                "schemaVersion": 1,
                "states": {"normal": {}},
                "transitions": [
                    {
                        "id": "long",
                        "from": "normal",
                        "to": "focused",
                        "duration": 9000,
                        "easing": "linear",
                    }
                ],
                "timelines": {},
            }
        )
    raw = _book()
    raw["script"] = "Qt.quit()"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(raw, SCHEMA)


def test_builtin_preview_consumes_resolved_motion_and_keeps_accessibility() -> None:
    preview = ThemeEditorManager().load("org.steamzero.asset-recipes-demo")["preview"]
    assert isinstance(preview, dict)
    motion = preview["sceneMotionPreview"]
    assert motion["states"]["focused"]["scale"] == 1.06
    assert motion["transitions"]["focusIn"]["duration"] == 180
    assert motion["timelines"]["previewFocus"]["steps"][-1]["state"] == "focused"
    accessible = ThemeCatalog().resolve(
        "org.steamzero.asset-recipes-demo",
        high_contrast=True,
        reduced_motion=True,
    )
    assert accessible.scene_motion is not None
    assert accessible.high_contrast is True
    assert accessible.reduced_motion is True
    assert accessible.color.background == "#000000"
    assert accessible.motion.durationNormal == 0
