# SPDX-License-Identifier: GPL-3.0-or-later
import os
from pathlib import Path

from steamzero.adapters.launcher_session import observe_game_session
from steamzero.core.session_state import SESSION_OWNER
from steamzero.core.state import StateStore


def test_missing_database_is_not_created(tmp_path: Path) -> None:
    database = tmp_path / "missing.db"
    assert observe_game_session(database, "game")["state"] == "unknown"
    assert not database.exists()


def test_observer_follows_owner_and_checks_process_identity(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    pid = os.getpid()
    ticks = int(Path(f"/proc/{pid}/stat").read_text().rpartition(") ")[2].split()[19])
    with StateStore(database) as store:
        store.migrate()
        store.create_game_session(
            {"id": "session-a", "game_id": "game", "owner": SESSION_OWNER, "state": "launching"}
        )
        assert observe_game_session(database, "game")["state"] == "launching"
        store.transition_game_session("session-a", "running", pid=pid, start_ticks=ticks)
        assert observe_game_session(database, "game") == {
            "gameId": "game",
            "sessionId": "session-a",
            "state": "running",
        }
        store.transition_game_session("session-a", "closed")
        assert observe_game_session(database, "game")["state"] == "closed"
        assert observe_game_session(database, "other")["state"] == "unknown"


def test_reused_pid_is_not_a_running_game(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    with StateStore(database) as store:
        store.migrate()
        store.create_game_session(
            {"id": "session-a", "game_id": "game", "owner": SESSION_OWNER, "state": "launching"}
        )
        store.transition_game_session("session-a", "running", pid=os.getpid(), start_ticks=1)
        result = observe_game_session(database, "game")
        assert result["state"] == "unknown"
        assert result["diagnostic"] == "LAUNCHER-SESSION-IDENTITY-001"
