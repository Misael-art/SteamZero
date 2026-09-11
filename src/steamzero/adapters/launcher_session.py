# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only observation of the canonical game lifecycle, not a second manager."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from steamzero.core.session_state import SESSION_OWNER, SESSION_STATES, normalize_session_state


def observe_game_session(database: Path, game_id: str) -> dict[str, Any]:
    """Never create/migrate a database or infer a running game from spawn alone.

    Running rows require matching Linux process start time to reject PID reuse.
    A missing process is unknown until the lifecycle owner records its result.
    """
    unknown = {"gameId": game_id, "state": "unknown", "sessionId": None}
    try:
        connection = sqlite3.connect(
            database.absolute().as_uri() + "?mode=ro", uri=True, timeout=0.2
        )
        try:
            row = connection.execute(
                "SELECT id,state,pid,start_ticks FROM game_session "
                "WHERE game_id=? AND owner=? ORDER BY updated_at DESC,id DESC LIMIT 1",
                (game_id, SESSION_OWNER),
            ).fetchone()
        finally:
            connection.close()
    except (sqlite3.Error, OSError, ValueError):
        return {**unknown, "diagnostic": "LAUNCHER-SESSION-UNAVAILABLE-001"}
    if row is None:
        return {**unknown, "diagnostic": "LAUNCHER-SESSION-NOT-OBSERVED-001"}
    session_id, raw_state, pid, ticks = row
    state = normalize_session_state(raw_state)
    result = {
        "gameId": game_id,
        "sessionId": session_id,
        "state": state if state in SESSION_STATES else "unknown",
    }
    if state in {"running", "suspended", "suspending", "resuming", "closing"}:
        if not isinstance(pid, int) or pid <= 1 or not isinstance(ticks, int):
            return {**result, "state": "unknown", "diagnostic": "LAUNCHER-SESSION-IDENTITY-001"}
        try:
            fields = Path(f"/proc/{pid}/stat").read_text().rpartition(") ")[2].split()
            matches = int(fields[19]) == ticks and fields[0] not in {"Z", "X"}
        except (OSError, ValueError, IndexError):
            matches = False
        if not matches:
            return {**result, "state": "unknown", "diagnostic": "LAUNCHER-SESSION-IDENTITY-001"}
    return result
