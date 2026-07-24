# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Persistência de cheats no state.db via StateStore.

Implementa a porta interna ``CheatDatabasePort`` definida em domain.switch_cheats.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime

from steamzero.domain.switch_cheats import (
    CheatDatabasePort,
    CheatType,
    InstalledCheat,
)
from steamzero.ports import CheatCandidate, CheatIdentity


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

    # --- Remote catalog ------------------------------------------------------

    def replace_catalog(
        self, title_id: str, candidates: list[CheatCandidate]
    ) -> list[str]:
        """Substitui atomicamente o recorte de cheats de um Title ID."""
        now = datetime.now(UTC).isoformat()
        self._conn.execute("DELETE FROM switch_cheat_catalog WHERE title_id = ?", (title_id,))
        identifiers: list[str] = []
        for candidate in candidates:
            identifier = self._catalog_id(candidate)
            identifiers.append(identifier)
            identity = candidate.identity
            self._conn.execute(
                """INSERT INTO switch_cheat_catalog
                   (id, title_id, build_id, name, cheat_type, source, source_url,
                    codes, description, author, version, added_at, refreshed_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    identifier,
                    candidate.title_id,
                    candidate.build_id,
                    identity.name,
                    identity.cheat_type,
                    identity.source,
                    identity.source_url,
                    json.dumps(candidate.codes, ensure_ascii=False),
                    identity.description,
                    identity.author,
                    identity.version,
                    now,
                    now,
                ),
            )
        return identifiers

    def list_catalog(
        self, title_id: str, *, build_id: str | None = None
    ) -> list[tuple[str, CheatCandidate]]:
        query = "SELECT * FROM switch_cheat_catalog WHERE title_id = ?"
        params: tuple[str, ...] = (title_id,)
        if build_id is not None:
            query += " AND build_id = ?"
            params = (title_id, build_id)
        rows = self._conn.execute(
            query + " ORDER BY name COLLATE NOCASE, source", params
        ).fetchall()
        return [(str(row["id"]), self._row_to_candidate(row)) for row in rows]

    def get_catalog(self, catalog_id: str) -> CheatCandidate | None:
        row = self._conn.execute(
            "SELECT * FROM switch_cheat_catalog WHERE id = ?", (catalog_id,)
        ).fetchone()
        return self._row_to_candidate(row) if row is not None else None

    @staticmethod
    def _catalog_id(candidate: CheatCandidate) -> str:
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
    def _row_to_candidate(row: sqlite3.Row) -> CheatCandidate:
        try:
            decoded = json.loads(str(row["codes"]))
        except json.JSONDecodeError:
            decoded = []
        codes = tuple(value for value in decoded if isinstance(value, str))
        return CheatCandidate(
            title_id=str(row["title_id"]),
            build_id=row["build_id"],
            identity=CheatIdentity(
                name=str(row["name"]),
                cheat_type=str(row["cheat_type"]),
                source=str(row["source"]),
                source_url=str(row["source_url"]),
                description=row["description"],
                author=row["author"],
                version=row["version"],
            ),
            codes=codes,
            match_confidence=1.0 if row["build_id"] else 0.7,
        )

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
