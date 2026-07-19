# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Amplia perfis para escopos Steam e observação do launcher M11."""

from __future__ import annotations

import sqlite3

_STATEMENTS = (
    "ALTER TABLE profile RENAME TO profile_v2",
    """
    CREATE TABLE profile (
      id            TEXT PRIMARY KEY,
      scope         TEXT NOT NULL CHECK (
        scope IN (
          'game','platform','device','mode','desktop-experience',
          'global','portable','dock'
        )
      ),
      kind          TEXT NOT NULL CHECK (
        kind IN (
          'performance','controls','display','desktop-plan','desktop-current',
          'desktop-override','desktop-recovery','desktop-observation',
          'performance-runtime'
        )
      ),
      payload_json  TEXT,
      priority      INTEGER,
      profile_owner TEXT
    )
    """,
    """
    INSERT INTO profile (id,scope,kind,payload_json,priority,profile_owner)
    SELECT id,scope,kind,payload_json,priority,profile_owner FROM profile_v2
    """,
    "DROP TABLE profile_v2",
)


def up(conn: sqlite3.Connection) -> None:
    for statement in _STATEMENTS:
        conn.execute(statement.strip())
