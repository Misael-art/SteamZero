# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Persistência de mods no state.db via StateStore.

Implementa a porta interna ``ModDatabasePort`` definida em domain.switch_mods.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime

from steamzero.domain.switch_mods import GameBuildId, InstalledMod, ModDatabasePort, ModType
from steamzero.ports import ModCandidate, ModIdentity


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

    # --- Remote catalog ------------------------------------------------------

    def replace_catalog(
        self, title_id: str, candidates: list[ModCandidate]
    ) -> list[str]:
        """Substitui atomicamente o recorte de um Title ID e devolve IDs estáveis."""
        now = datetime.now(UTC).isoformat()
        self._conn.execute("DELETE FROM switch_mod_catalog WHERE title_id = ?", (title_id,))
        identifiers: list[str] = []
        for candidate in candidates:
            identifier = self._catalog_id(candidate)
            identifiers.append(identifier)
            identity = candidate.identity
            self._conn.execute(
                """INSERT INTO switch_mod_catalog
                   (id, title_id, build_id, name, mod_type, source, source_url,
                    version, description, author, requirements, added_at, refreshed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    identifier,
                    candidate.title_id,
                    candidate.build_id,
                    identity.name,
                    identity.mod_type,
                    identity.source,
                    identity.source_url,
                    identity.version,
                    identity.description,
                    identity.author,
                    None,
                    now,
                    now,
                ),
            )
        return identifiers

    def list_catalog(
        self, title_id: str, *, build_id: str | None = None
    ) -> list[tuple[str, ModCandidate]]:
        query = "SELECT * FROM switch_mod_catalog WHERE title_id = ?"
        params: tuple[str, ...] = (title_id,)
        if build_id is not None:
            query += " AND build_id = ?"
            params = (title_id, build_id)
        rows = self._conn.execute(
            query + " ORDER BY name COLLATE NOCASE, source", params
        ).fetchall()
        return [(str(row["id"]), self._row_to_candidate(row)) for row in rows]

    def get_catalog(self, catalog_id: str) -> ModCandidate | None:
        row = self._conn.execute(
            "SELECT * FROM switch_mod_catalog WHERE id = ?", (catalog_id,)
        ).fetchone()
        return self._row_to_candidate(row) if row is not None else None

    @staticmethod
    def _catalog_id(candidate: ModCandidate) -> str:
        identity = candidate.identity
        raw = "\0".join(
            (
                candidate.title_id,
                candidate.build_id or "",
                identity.source,
                identity.source_url,
                identity.name,
            )
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _row_to_candidate(row: sqlite3.Row) -> ModCandidate:
        return ModCandidate(
            title_id=str(row["title_id"]),
            build_id=row["build_id"],
            identity=ModIdentity(
                name=str(row["name"]),
                mod_type=str(row["mod_type"]),
                source=str(row["source"]),
                source_url=str(row["source_url"]),
                version=row["version"],
                description=row["description"],
                author=row["author"],
            ),
            match_confidence=1.0 if row["build_id"] else 0.7,
        )

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
