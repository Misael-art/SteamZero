# SPDX-License-Identifier: GPL-3.0-or-later
"""Contrato feat-playtime-v1, agregação, paginação e entradas hostis."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from steamzero.api import contracts
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain.playtime import PlaytimeCatalog


def _store(path: Path) -> StateStore:
    store = StateStore(path)
    store.migrate()
    return store


def _session(
    store: StateStore,
    *,
    session_id: str,
    game_id: str,
    started_at: str,
    source: str,
    title: str,
    seconds: int,
    failure_code: str | None = None,
) -> None:
    store.create_game_session(
        {
            "id": session_id,
            "game_id": game_id,
            "state": "launching",
            "owner": "steamzero-game-session",
            "started_at": started_at,
            "metadata_json": json.dumps({"source": source, "title": title}),
        }
    )
    store.transition_game_session(session_id, "running")
    store.transition_game_session(
        session_id,
        "failed" if failure_code else "closed",
        finished_at=started_at,
        failure_code=failure_code,
        played_seconds=seconds,
        duration_source="observed-monotonic",
    )


def test_catalog_aggregates_recent_games_and_interrupted_state(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    with _store(path) as store:
        _session(
            store,
            session_id="S1",
            game_id="10",
            started_at="2026-07-23T10:00:00+00:00",
            source="steam",
            title="Portal",
            seconds=600,
        )
        _session(
            store,
            session_id="S2",
            game_id="10",
            started_at="2026-07-23T11:00:00+00:00",
            source="steam",
            title="Portal",
            seconds=300,
            failure_code="E-SESSION-INTERRUPTED",
        )
        _session(
            store,
            session_id="S3",
            game_id="emu-a",
            started_at="2026-07-23T09:00:00+00:00",
            source="emulation",
            title="Jogo Retro",
            seconds=120,
        )

    payload = PlaytimeCatalog(lambda: StateStore(path)).list(limit=20)

    contracts.validate(payload, "feat-playtime-v1.schema.json")
    assert payload["totalPlayedSeconds"] == 1020
    assert [game["gameId"] for game in payload["games"]] == ["10", "emu-a"]
    portal = payload["games"][0]
    assert portal["playedSeconds"] == 900
    assert portal["sessionCount"] == 2
    assert portal["continueState"] == "interrupted"
    assert portal["action"]["kind"] == "steam-continue"


def test_catalog_uses_opaque_keyset_cursor_and_point_lookup(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    with _store(path) as store:
        for index in range(3):
            _session(
                store,
                session_id=f"S{index}",
                game_id=f"game-{index}",
                started_at=f"2026-07-23T0{index}:00:00+00:00",
                source="emulation",
                title=f"Game {index}",
                seconds=index + 1,
            )
    catalog = PlaytimeCatalog(lambda: StateStore(path))

    first = catalog.list(limit=2)
    second = catalog.list(limit=2, cursor=first["page"]["nextCursor"])

    assert first["page"]["hasMore"] is True
    assert [game["gameId"] for game in first["games"]] == ["game-2", "game-1"]
    assert [game["gameId"] for game in second["games"]] == ["game-0"]
    assert catalog.get("game-0")["game"]["title"] == "Game 0"


def test_active_and_legacy_sessions_do_not_claim_safe_relaunch(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    with _store(path) as store:
        store.create_game_session(
            {
                "id": "ACTIVE",
                "game_id": "legacy",
                "state": "launching",
                "owner": "steamzero-game-session",
                "metadata_json": "{}",
            }
        )
    game = PlaytimeCatalog(lambda: StateStore(path)).get("legacy")["game"]
    assert game["continueState"] == "in-progress"
    assert game["source"] == "unknown"
    assert game["action"]["enabled"] is False


@settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(st.text(max_size=1100))
def test_cursor_fuzz_is_valid_page_or_typed_error(tmp_path: Path, cursor: str) -> None:
    catalog = PlaytimeCatalog(lambda: StateStore(tmp_path / "state.db"))
    try:
        result = catalog.list(cursor=cursor)
    except SteamZeroError as exc:
        assert exc.code == "E-API-SCHEMA"
    else:
        contracts.validate(result, "feat-playtime-v1.schema.json")


@pytest.mark.parametrize("limit", [0, 101, True, "20"])
def test_limit_is_closed_and_bounded(tmp_path: Path, limit: object) -> None:
    with pytest.raises(SteamZeroError, match="limit"):
        PlaytimeCatalog(lambda: StateStore(tmp_path / "state.db")).list(limit=limit)  # type: ignore[arg-type]
