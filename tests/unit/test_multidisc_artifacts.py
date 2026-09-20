# SPDX-License-Identifier: GPL-3.0-or-later
"""Owned descriptor projection and State Store persistence tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain.multidisc import DiscRecord, MultiDiscSet
from steamzero.domain.multidisc_artifacts import (
    OWNERSHIP_MARKER,
    descriptor_projection,
    plan_descriptor_update,
    render_descriptor,
)


def _set(tmp_path: Path) -> MultiDiscSet:
    first = tmp_path / "Game (Disc 1).chd"
    second = tmp_path / "Game (Disc 2).chd"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    descriptor = tmp_path / "Game.m3u"
    return MultiDiscSet(
        set_id="playstation:psx:game",
        platform_id="playstation",
        system_id="psx",
        normalized_title="game",
        descriptor_path=descriptor,
        discs=(
            DiscRecord("playstation:psx:game", 1, 2, "chd", first, "h1", ("chd",), "active"),
            DiscRecord("playstation:psx:game", 2, 2, "chd", second, "h2", ("chd",), "active"),
        ),
    )


def test_descriptor_is_deterministic_and_uses_relative_active_paths(tmp_path: Path) -> None:
    logical_set = _set(tmp_path)
    content = render_descriptor(logical_set)
    assert content == (
        f"{OWNERSHIP_MARKER}\n"
        "# SteamZero-MultiDisc-Set: playstation:psx:game\n"
        "# SteamZero-MultiDisc-Disc: playstation:psx:game:disc-1\n"
        "Game (Disc 1).chd\n"
        "# SteamZero-MultiDisc-Disc: playstation:psx:game:disc-2\n"
        "Game (Disc 2).chd\n"
    )
    projection = descriptor_projection(logical_set)
    assert projection.state == "missing"
    assert len(projection.content_hash) == 64


def test_user_playlist_is_conflict_and_never_plannable(tmp_path: Path) -> None:
    logical_set = _set(tmp_path)
    assert logical_set.descriptor_path is not None
    logical_set.descriptor_path.write_text("Game (Disc 1).chd\n", encoding="utf-8")
    with pytest.raises(SteamZeroError, match="ownership"):
        plan_descriptor_update(logical_set)


def test_generated_playlist_is_stale_when_a_disc_changes(tmp_path: Path) -> None:
    logical_set = _set(tmp_path)
    assert logical_set.descriptor_path is not None
    logical_set.descriptor_path.write_text(render_descriptor(logical_set), encoding="utf-8")
    assert descriptor_projection(logical_set).state == "current"
    converted_path = tmp_path / "Game (Disc 2).img"
    converted_path.write_bytes(b"new-two")
    changed = MultiDiscSet(
        **{
            **logical_set.__dict__,
            "discs": (
                *logical_set.discs[:1],
                DiscRecord(
                    "playstation:psx:game",
                    2,
                    2,
                    "img",
                    converted_path,
                    "new-h2",
                    ("img",),
                    "converted",
                ),
            ),
        }
    )
    assert descriptor_projection(changed).state == "stale"


def test_descriptor_refuses_format_not_accepted_by_adapter(tmp_path: Path) -> None:
    logical_set = _set(tmp_path)
    changed = MultiDiscSet(
        **{
            **logical_set.__dict__,
            "discs": (
                *logical_set.discs[:1],
                DiscRecord(
                    "playstation:psx:game",
                    2,
                    2,
                    "img",
                    logical_set.discs[1].path,
                    "h2",
                    ("chd",),
                    "converted",
                ),
            ),
        }
    )
    with pytest.raises(SteamZeroError, match="formato não aceito"):
        render_descriptor(changed)


def test_state_store_persists_set_disc_identity_and_history(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    with StateStore(db) as store:
        assert store.migrate() == 22
        store.save_multidisc_set(
            {
                "id": "set-1",
                "game_id": None,
                "platform_id": "playstation",
                "system_id": "psx",
                "normalized_title": "game",
                "descriptor_path": "Game.m3u",
                "descriptor_kind": "m3u",
                "descriptor_origin": "generated",
                "descriptor_hash": "a" * 64,
                "confidence": 1.0,
                "sync_state": "current",
            }
        )
        store.save_multidisc_disc(
            {
                "identity": "set-1:disc-1",
                "set_id": "set-1",
                "disc_number": 1,
                "disc_total": 2,
                "format": "chd",
                "current_path": "Game (Disc 1).chd",
                "content_hash": "b" * 64,
                "accepted_formats_json": json.dumps(["chd"]),
                "conversion_history_json": json.dumps([{"fromFormat": "img", "toFormat": "chd"}]),
                "state": "converted",
            }
        )
        assert store.get_multidisc_set("set-1")["descriptor_hash"] == "a" * 64  # type: ignore[index]
        assert store.list_multidisc_discs("set-1")[0]["state"] == "converted"
