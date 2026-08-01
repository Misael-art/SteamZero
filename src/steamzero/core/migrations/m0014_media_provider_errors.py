from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 14


def up(conn: sqlite3.Connection) -> None:
    columns = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(switch_game_media)").fetchall()
    }
    additions = {
        "errors_json": "TEXT NOT NULL DEFAULT '{}'",
    }
    for name, definition in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE switch_game_media ADD COLUMN {name} {definition}")
    conn.execute("PRAGMA user_version = 14")
