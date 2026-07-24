# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Duração observada e origem da medição por sessão de jogo."""

from __future__ import annotations

import sqlite3


def up(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        ALTER TABLE game_session
        ADD COLUMN played_seconds INTEGER NOT NULL DEFAULT 0
        CHECK (played_seconds >= 0)
        """
    )
    conn.execute(
        """
        ALTER TABLE game_session
        ADD COLUMN duration_source TEXT NOT NULL DEFAULT 'unavailable'
        CHECK (
          duration_source IN (
            'unavailable','observed-monotonic','recovered-wall-clock','legacy-wall-clock'
          )
        )
        """
    )
    conn.execute(
        """
        UPDATE game_session
        SET played_seconds = MAX(
              0,
              CAST((julianday(finished_at) - julianday(started_at)) * 86400 AS INTEGER)
            ),
            duration_source = 'legacy-wall-clock'
        WHERE finished_at IS NOT NULL
          AND state IN ('closed','failed')
        """
    )
    conn.execute(
        """
        CREATE INDEX idx_game_session_recent
        ON game_session(started_at DESC, game_id)
        """
    )
