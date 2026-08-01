from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 15


def up(conn: sqlite3.Connection) -> None:
    columns = {
        str(row[1])
        for row in conn.execute("PRAGMA table_info(scraping_provider_status)").fetchall()
    }
    additions = {
        "last_error_code": "TEXT",
        "last_error_category": "TEXT",
        "state": "TEXT NOT NULL DEFAULT 'active'",
    }
    for name, definition in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE scraping_provider_status ADD COLUMN {name} {definition}")
    conn.execute("PRAGMA user_version = 15")
