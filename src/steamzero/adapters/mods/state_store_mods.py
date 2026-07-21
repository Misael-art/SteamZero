# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Persistência de mods no state.db via StateStore.

Implementa a porta interna ``ModDatabasePort`` definida em domain.switch_mods.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from steamzero.domain.switch_mods import GameBuildId, InstalledMod, ModDatabasePort, ModType


class StateStoreModsAdapter(ModDatabasePort):
    """Persiste mods e Build IDs nas tabelas switch_mod / switch_game_build_id."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # --- InstalledMod --------------------------------------------------------

    def save_installed_mod(self, mod: InstalledMod) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO switch_mod
               (id, game_id, catalog_id, title_id, build_id, name, mod_type,
                source, version, state, install_path, emulator_id, installed_at, activated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                mod.id,
                mod.game_id,
                mod.catalog_id,
                mod.title_id,
                mod.build_id,
                mod.name,
                mod.mod_type.value,
                mod.source,
                mod.version,
                mod.state,
                mod.install_path,
                mod.emulator_id,
                datetime.now(UTC).isoformat(),
                None,
            ),
        )

    def remove_installed_mod(self, mod_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM switch_mod WHERE id = ?", (mod_id,))
        return cur.rowcount > 0

    def list_installed(self, game_id: str) -> list[InstalledMod]:
        rows = self._conn.execute(
            "SELECT * FROM switch_mod WHERE game_id = ? ORDER BY installed_at DESC",
            (game_id,),
        ).fetchall()
        return [self._row_to_installed(r) for r in rows]

    def update_state(self, mod_id: str, new_state: str) -> None:
        now = datetime.now(UTC).isoformat()
        if new_state == "active":
            self._conn.execute(
                "UPDATE switch_mod SET state = ?, activated_at = ? WHERE id = ?",
                (new_state, now, mod_id),
            )
        else:
            self._conn.execute(
                "UPDATE switch_mod SET state = ? WHERE id = ?",
                (new_state, mod_id),
            )

    def update_location_state(self, mod_id: str, new_state: str, install_path: str) -> None:
        """Atualiza estado e localização após uma movimentação confirmada."""
        self._conn.execute(
            "UPDATE switch_mod SET state = ?, install_path = ? WHERE id = ?",
            (new_state, install_path, mod_id),
        )

    def get_by_id(self, mod_id: str) -> InstalledMod | None:
        row = self._conn.execute("SELECT * FROM switch_mod WHERE id = ?", (mod_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_installed(row)

    # --- GameBuildId ---------------------------------------------------------

    def save_build_id(self, entry: GameBuildId) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO switch_game_build_id
               (game_id, title_id, build_id, detected_from, detected_at)
               VALUES (?,?,?,?,?)""",
            (entry.game_id, entry.title_id, entry.build_id, entry.detected_from, entry.detected_at),
        )

    def list_build_ids(self, game_id: str) -> list[GameBuildId]:
        rows = self._conn.execute(
            "SELECT * FROM switch_game_build_id WHERE game_id = ? ORDER BY detected_at DESC",
            (game_id,),
        ).fetchall()
        return [self._row_to_build_id(r) for r in rows]

    # --- helpers -------------------------------------------------------------

    def _row_to_installed(self, row: sqlite3.Row) -> InstalledMod:
        return InstalledMod(
            id=row["id"],
            game_id=row["game_id"],
            catalog_id=row["catalog_id"],
            title_id=row["title_id"],
            build_id=row["build_id"],
            name=row["name"],
            mod_type=ModType(row["mod_type"]),
            source=row["source"],
            version=row["version"],
            state=row["state"],
            install_path=row["install_path"],
            emulator_id=row["emulator_id"],
        )

    def _row_to_build_id(self, row: sqlite3.Row) -> GameBuildId:
        return GameBuildId(
            game_id=row["game_id"],
            title_id=row["title_id"],
            build_id=row["build_id"],
            detected_from=row["detected_from"],
            detected_at=row["detected_at"],
        )
