# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors

from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from steamzero.domain.save_states import (
    resolve_save_state_gallery,
    unavailable_gallery,
)

ROOT = Path(__file__).parents[2]
SCHEMA = json.loads(
    (ROOT / "src/steamzero/schemas/session-save-state-v1.schema.json").read_text(encoding="utf-8")
)


def test_gallery_is_bounded_and_never_publishes_a_private_thumbnail_path() -> None:
    gallery = resolve_save_state_gallery(
        {
            "entries": [
                {
                    "slot": 3,
                    "timestamp": "2026-09-13T20:00:00Z",
                    "playtimeSeconds": 3600,
                    "thumbnail": "/home/player/.config/retroarch/states/slot3.png",
                    "compatibility": "native",
                    "backupAvailable": True,
                }
            ]
            * 40
        },
        save_available=True,
        load_available=True,
    )

    payload = gallery.to_dict()
    jsonschema.validate(payload, SCHEMA)
    assert len(gallery.entries) == 32
    assert payload["entries"][0]["thumbnailUrl"] == ""
    assert payload["entries"][0]["thumbnailFallback"] is True
    assert "/home/player" not in json.dumps(payload)
    assert payload["entries"][0]["backupAvailable"] is True


def test_gallery_accepts_only_allowlisted_thumbnail_urls_and_exposes_empty_state() -> None:
    gallery = resolve_save_state_gallery(
        {
            "entries": [
                {
                    "slot": 1,
                    "timestamp": "2026-09-13T20:00:00Z",
                    "playtimeSeconds": 90,
                    "thumbnailUrl": "asset://save-states/slot-1.png",
                    "compatibility": "emulated",
                }
            ]
        },
        save_available=True,
        load_available=True,
    )
    assert gallery.state == "ready"
    assert gallery.load_available is True
    assert gallery.entries[0].thumbnail_url == "asset://save-states/slot-1.png"

    empty = resolve_save_state_gallery({"entries": []}, save_available=True, load_available=True)
    assert empty.state == "empty"
    assert empty.save_available is True
    assert empty.load_available is False
    jsonschema.validate(empty.to_dict(), SCHEMA)


def test_unavailable_gallery_is_explicit_and_schema_valid() -> None:
    gallery = unavailable_gallery("Adapter ausente")
    payload = gallery.to_dict()
    jsonschema.validate(payload, SCHEMA)
    assert payload == {
        "schemaVersion": 1,
        "state": "unavailable",
        "available": False,
        "saveAvailable": False,
        "loadAvailable": False,
        "reason": "Adapter ausente",
        "entries": [],
    }
