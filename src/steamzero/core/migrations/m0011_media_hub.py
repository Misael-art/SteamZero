from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 11


def up(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS media_masters (
            master_id TEXT PRIMARY KEY,
            game_id TEXT NOT NULL,
            title_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            file_size INTEGER NOT NULL DEFAULT 0,
            mime_type TEXT NOT NULL DEFAULT 'image/png',
            provenance_provider TEXT NOT NULL DEFAULT '',
            provenance_url TEXT NOT NULL DEFAULT '',
            provenance_license TEXT NOT NULL DEFAULT '',
            provenance_attribution TEXT NOT NULL DEFAULT '',
            provenance_downloaded_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS media_optimized (
            optimized_id TEXT PRIMARY KEY,
            master_id TEXT NOT NULL,
            game_id TEXT NOT NULL,
            profile TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            file_size INTEGER NOT NULL DEFAULT 0,
            master_sha256 TEXT NOT NULL,
            tool_used TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            FOREIGN KEY (master_id) REFERENCES media_masters(master_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS media_views_steam (
            view_id TEXT PRIMARY KEY,
            game_id TEXT NOT NULL,
            steam_user_id TEXT NOT NULL,
            steam_appid INTEGER NOT NULL,
            kind TEXT NOT NULL,
            source_optimized_id TEXT,
            view_path TEXT NOT NULL,
            link_type TEXT NOT NULL DEFAULT 'symlink',
            sha256 TEXT NOT NULL,
            operation TEXT NOT NULL DEFAULT 'create',
            schema_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_masters_game ON media_masters(game_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_masters_sha ON media_masters(sha256)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_optimized_game ON media_optimized(game_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_views_steam_game ON media_views_steam(game_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_media_views_steam_user ON media_views_steam(steam_user_id)"
    )
    conn.execute("PRAGMA user_version = 11")
