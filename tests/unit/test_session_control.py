# SPDX-License-Identifier: GPL-3.0-or-later
"""Provas do canal de controle pertencente ao processo da sessão."""

from __future__ import annotations

import os
import signal
from pathlib import Path
from typing import Any, cast

import pytest

from steamzero.adapters.launcher_session import observe_game_session
from steamzero.adapters.session_control import (
    SessionControlOwner,
    SessionControlServer,
    control_path,
    resolve_remote_session_control,
)
from steamzero.adapters.session_overlay import SessionOverlayAdapter
from steamzero.core.session_state import SESSION_OWNER
from steamzero.core.state import StateStore


def _start_ticks(pid: int) -> int:
    fields = Path(f"/proc/{pid}/stat").read_text().rpartition(") ")[2].split()
    return int(fields[19])


def _seed_session(database: Path) -> tuple[str, str]:
    session_id, game_id = "session-control-1", "game-control-1"
    with StateStore(database) as store:
        store.migrate()
        store.create_game_session(
            {
                "id": session_id,
                "game_id": game_id,
                "owner": SESSION_OWNER,
                "state": "launching",
            }
        )
        store.transition_game_session(
            session_id,
            "running",
            pid=os.getpid(),
            start_ticks=_start_ticks(os.getpid()),
        )
    return session_id, game_id


class _PeripheralControl:
    def list_peripherals(self) -> dict[str, object]:
        return {
            "state": "ready",
            "selectedBezel": "aura-default",
            "bezels": [
                {
                    "id": "aura-default",
                    "label": "AURA Cinema",
                    "assetUrl": "asset://bezels/aura-bezel.svg",
                    "available": True,
                    "selected": True,
                }
            ],
            "fade": {"phase": "idle", "progress": 0.0, "durationMs": 180},
        }


def test_remote_control_uses_owner_transitions_and_never_signals_from_ui(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    session_id, game_id = _seed_session(database)
    observed_signals: list[tuple[int, int]] = []
    owner = SessionControlOwner(
        session_id,
        game_id,
        os.getpid(),
        _start_ticks(os.getpid()),
        store_factory=lambda: StateStore(database),
        read_start_ticks=_start_ticks,
        signal_process=lambda pid, signum: observed_signals.append((pid, signum)),
    )
    socket_root = tmp_path.parent
    server = SessionControlServer(owner, control_path(session_id, root=socket_root))
    server.start()
    try:

        def observe(requested: str) -> dict[str, object]:
            return observe_game_session(database, requested)

        remote = resolve_remote_session_control(
            session_id, game_id, observe=observe, root=socket_root
        )
        assert remote is not None
        overlay = SessionOverlayAdapter(
            observe,
            lambda _session, _game: cast(Any, remote),
        )

        paused = overlay.dispatch(game_id, session_id, "pause")
        resumed = overlay.dispatch(game_id, session_id, "pause")

        assert paused.accepted is True
        assert paused.state == "suspended"
        assert resumed.accepted is True
        assert resumed.state == "running"
        assert observed_signals == [
            (os.getpid(), signal.SIGSTOP),
            (os.getpid(), signal.SIGCONT),
        ]
    finally:
        server.close()
    assert not server.path.exists()


def test_control_channel_rejects_stale_identity_without_transition(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    session_id, game_id = _seed_session(database)
    owner = SessionControlOwner(
        session_id,
        game_id,
        os.getpid(),
        _start_ticks(os.getpid()),
        store_factory=lambda: StateStore(database),
        read_start_ticks=_start_ticks,
        signal_process=lambda _pid, _signum: None,
    )
    socket_root = tmp_path.parent
    server = SessionControlServer(owner, control_path(session_id, root=socket_root))
    server.start()
    try:

        def observe(requested: str) -> dict[str, object]:
            return observe_game_session(database, requested)

        remote = resolve_remote_session_control(
            session_id, "other-game", observe=observe, root=socket_root
        )
        assert remote is not None
        with pytest.raises(RuntimeError, match="recusou"):
            remote.suspend()
        with StateStore(database) as store:
            row = store.get_game_session(session_id)
            assert row is not None
            assert row["state"] == "running"
    finally:
        server.close()


def test_control_path_does_not_accept_path_injection() -> None:
    try:
        control_path("../outside")
    except ValueError as exc:
        assert "sessionId" in str(exc)
    else:
        raise AssertionError("session id inválido foi aceito")


def test_remote_control_projects_complete_session_peripherals(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    session_id, game_id = _seed_session(database)
    owner = SessionControlOwner(
        session_id,
        game_id,
        os.getpid(),
        _start_ticks(os.getpid()),
        store_factory=lambda: StateStore(database),
        read_start_ticks=_start_ticks,
        signal_process=lambda _pid, _signum: None,
        peripheral_control=cast(Any, _PeripheralControl()),
    )
    socket_root = tmp_path.parent
    server = SessionControlServer(owner, control_path(session_id, root=socket_root))
    server.start()
    try:
        remote = resolve_remote_session_control(
            session_id,
            game_id,
            observe=lambda requested: observe_game_session(database, requested),
            root=socket_root,
        )
        assert remote is not None
        data = remote.list_peripherals()
        assert data["selectedBezel"] == "aura-default"
        assert data["bezels"][0]["assetUrl"] == "asset://bezels/aura-bezel.svg"
    finally:
        server.close()
