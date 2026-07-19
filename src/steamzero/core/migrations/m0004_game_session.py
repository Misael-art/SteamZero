# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Fonte de verdade persistente e exclusiva para sessões de jogo."""

from __future__ import annotations

import sqlite3


def up(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE game_session (
          id              TEXT PRIMARY KEY,
          game_id         TEXT NOT NULL,
          state           TEXT NOT NULL CHECK (
            state IN (
              'idle','launching','running','suspending','suspended',
              'resuming','closing','closed','failed'
            )
          ),
          pid             INTEGER,
          profile_digest  TEXT,
          owner           TEXT NOT NULL,
          started_at      TEXT NOT NULL,
          updated_at      TEXT NOT NULL,
          finished_at     TEXT,
          exit_code       INTEGER,
          failure_code    TEXT,
          metadata_json   TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX idx_game_session_one_active_owner
        ON game_session(owner)
        WHERE state IN (
          'idle','launching','running','suspending','suspended','resuming','closing'
        )
        """
    )
    conn.execute(
        "CREATE INDEX idx_game_session_game_updated ON game_session(game_id, updated_at DESC)"
    )
