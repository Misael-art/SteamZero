# SPDX-License-Identifier: GPL-3.0-or-later
"""Snapshot observado do ambiente Linux reconciliado pelo daemon user-scoped."""

from __future__ import annotations

import sqlite3


def up(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE session_environment (
          id           TEXT PRIMARY KEY CHECK (id = 'current'),
          observed_at  TEXT NOT NULL,
          digest       TEXT NOT NULL CHECK (length(digest) = 64),
          payload_json TEXT NOT NULL
        )
        """
    )
