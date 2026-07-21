# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Persistência de cheats no state.db via StateStore.

Implementa a porta interna ``CheatDatabasePort`` definida em domain.switch_cheats.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from steamzero.domain.switch_cheats import (
    CheatDatabasePort,
    CheatType,
    InstalledCheat,
)


class StateStoreCheatsAdapter(CheatDatabasePort):
    """Persiste cheats na tabela switch_cheat."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save_installed_cheat(self, cheat: InstalledCheat) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO switch_cheat
               (id, game_id, title_id, build_id, name, cheat_type,
                source, version, state, install_path, emulator_id,
                code_count, enabled, installed_at, activated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                cheat.id,
                cheat.game_id,
                cheat.title_id,
                cheat.build_id,
                cheat.name,
                cheat.cheat_type.value,
                cheat.source,
                cheat.version,
                cheat.state,
                cheat.install_path,
                cheat.emulator_id,
                cheat.code_count,
                1 if cheat.enabled else 0,
                datetime.now(UTC).isoformat(),
                None,
            ),
        )

    def remove_installed_cheat(self, cheat_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM switch_cheat WHERE id = ?", (cheat_id,))
        return cur.rowcount > 0

    def list_installed(self, game_id: str) -> list[InstalledCheat]:
        rows = self._conn.execute(
            "SELECT * FROM switch_cheat WHERE game_id = ? ORDER BY installed_at DESC",
            (game_id,),
        ).fetchall()
        return [self._row_to_installed(r) for r in rows]

    def update_state(self, cheat_id: str, new_state: str) -> None:
        self._conn.execute(
            "UPDATE switch_cheat SET state = ? WHERE id = ?",
            (new_state, cheat_id),
        )

    def update_enabled(self, cheat_id: str, enabled: bool) -> None:
        self._conn.execute(
            "UPDATE switch_cheat SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, cheat_id),
        )

    def update_location_state(
        self, cheat_id: str, new_state: str, install_path: str, *, enabled: bool
    ) -> None:
        """Atualiza estado, caminho e ativação após uma movimentação confirmada."""
        self._conn.execute(
            "UPDATE switch_cheat SET state = ?, install_path = ?, enabled = ? WHERE id = ?",
            (new_state, install_path, 1 if enabled else 0, cheat_id),
        )

    def get_by_id(self, cheat_id: str) -> InstalledCheat | None:
        row = self._conn.execute("SELECT * FROM switch_cheat WHERE id = ?", (cheat_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_installed(row)

    def _row_to_installed(self, row: sqlite3.Row) -> InstalledCheat:
        return InstalledCheat(
            id=row["id"],
            game_id=row["game_id"],
            title_id=row["title_id"],
            build_id=row["build_id"],
            name=row["name"],
            cheat_type=CheatType(row["cheat_type"]),
            source=row["source"],
            version=row["version"],
            state=row["state"],
            install_path=row["install_path"],
            emulator_id=row["emulator_id"],
            code_count=row["code_count"],
            enabled=bool(row["enabled"]),
        )
