# SPDX-License-Identifier: GPL-3.0-or-later
"""Persist logical multi-disc sets and their derived descriptor state."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 22


def up(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS multi_disc_set (
          id                 TEXT PRIMARY KEY,
          game_id            TEXT REFERENCES game(id),
          platform_id        TEXT NOT NULL,
          system_id          TEXT NOT NULL,
          normalized_title   TEXT NOT NULL,
          descriptor_path    TEXT,
          descriptor_kind    TEXT,
          descriptor_origin  TEXT CHECK (descriptor_origin IN ('user','generated')),
          descriptor_hash    TEXT,
          confidence         REAL NOT NULL DEFAULT 0.0 CHECK (confidence >= 0 AND confidence <= 1),
          sync_state         TEXT NOT NULL CHECK (
                               sync_state IN ('current','stale','conflict','missing')
                             )
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS multi_disc_disc (
          identity              TEXT PRIMARY KEY,
          set_id                TEXT NOT NULL REFERENCES multi_disc_set(id) ON DELETE CASCADE,
          disc_number           INTEGER NOT NULL CHECK (disc_number >= 1),
          disc_total            INTEGER NOT NULL CHECK (disc_total >= 1),
          format                TEXT NOT NULL,
          current_path          TEXT,
          content_hash          TEXT,
          disc_label            TEXT NOT NULL DEFAULT '',
          disc_role             TEXT,
          archive_path          TEXT,
          member_path           TEXT,
          member_hash           TEXT,
          archive_hash          TEXT,
          source_origin         TEXT NOT NULL DEFAULT 'user' CHECK (
                                  source_origin IN ('user','generated')
                                ),
          accepted_formats_json TEXT NOT NULL,
          conversion_history_json TEXT NOT NULL,
          state                 TEXT NOT NULL CHECK (
                                  state IN ('active','converted','missing','stale','conflict')
                                ),
          UNIQUE(set_id, disc_number)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_multi_disc_disc_set ON multi_disc_disc(set_id)")
    conn.execute("PRAGMA user_version = 22")
