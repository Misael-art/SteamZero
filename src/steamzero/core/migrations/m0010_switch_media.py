from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 10


def up(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS switch_game_media (
            game_id TEXT PRIMARY KEY,
            title_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            media_source TEXT NOT NULL DEFAULT 'fallback',
            media_kind TEXT NOT NULL DEFAULT 'icon',
            media_path TEXT,
            previous_media_path TEXT,
            developer TEXT,
            version TEXT,
            languages TEXT NOT NULL DEFAULT '',
            metadata_state TEXT NOT NULL DEFAULT 'unavailable',
            reason TEXT NOT NULL DEFAULT '',
            checked_at TEXT NOT NULL DEFAULT '',
            selected_candidate_idx INTEGER NOT NULL DEFAULT -1,
            candidate_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
        """
    )
    conn.execute("PRAGMA user_version = 10")
