from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 21


def up(conn: sqlite3.Connection) -> None:
    columns = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(switch_game_media)").fetchall()
    }
    if "platform_id" not in columns:
        # Dados anteriores foram escritos pelo fluxo Switch-only; preservar
        # essa proveniência é diferente de inventar Switch numa nova entrada.
        conn.execute(
            "ALTER TABLE switch_game_media ADD COLUMN platform_id TEXT NOT NULL DEFAULT 'switch'"
        )
    conn.execute("PRAGMA user_version = 21")
