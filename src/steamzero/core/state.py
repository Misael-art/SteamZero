# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""State Store SQLite (ADR-0005, STATE-MODEL, MIGRATION-VERSIONING).

- SQLite WAL, foreign_keys=ON, busy_timeout — writer único no daemon.
- Schema versionado por ``PRAGMA user_version``; migrações encadeiam N->N+1,
  cada uma numa transação, com **backup do state.db antes de migrar**; falha =>
  restaura o backup (E-STATE-MIGRATION) — versão anterior operante (RT-14).
- Journal transacional fica FORA do db (core.journal): sobrevive a corrupção.
- ``export_json`` produz um dump canônico legível (steamzero state export).
- Segredos NUNCA entram em claro aqui (SR-13) — responsabilidade do chamador.

O State Store é uma porta de persistência distinta de core.fs (que rege escrita
de arquivos avulsos). O backup do próprio db passa por core.fs.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any

from steamzero.core import fs, paths
from steamzero.core.errors import SteamZeroError
from steamzero.core.migrations import LATEST, MIGRATIONS
from steamzero.core.session_state import ACTIVE_SESSION_STATES, can_transition

_JOB_COLUMNS = (
    "id",
    "type",
    "params_json",
    "priority",
    "state",
    "progress_json",
    "operation_id",
    "correlation_id",
    "created_by",
    "constraints_json",
    "checkpoints_json",
    "result_json",
    "error_code",
    "created_at",
    "updated_at",
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class StateStore:
    """Acesso ao State Store. Use como context manager para fechar a conexão."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or paths.state_db()
        fs.ensure_dir(self._path.parent)
        self._conn = sqlite3.connect(self._path, isolation_level=None)
        self._closed = False
        self._conn.row_factory = sqlite3.Row
        self._apply_pragmas()

    def _apply_pragmas(self) -> None:
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA synchronous=NORMAL")

    @property
    def path(self) -> Path:
        return self._path

    def adapter_connection(self) -> sqlite3.Connection:
        """Return the migrated store connection to repository adapters.

        Domain repositories share the store transaction and pragmas instead of
        opening competing SQLite writers.  Callers must keep the ``StateStore``
        context alive and must never close the returned connection.
        """
        return self._conn

    @property
    def user_version(self) -> int:
        row = self._conn.execute("PRAGMA user_version").fetchone()
        return int(row[0])

    def _set_user_version(self, version: int) -> None:
        # PRAGMA não aceita placeholder; version é int validado.
        self._conn.execute(f"PRAGMA user_version={int(version)}")

    # -- migração -----------------------------------------------------------
    def migrate(self) -> int:
        """Aplica migrações pendentes; retorna a versão final. Idempotente."""
        current = self.user_version
        if current >= LATEST:
            return current
        backup = self._backup_before_migration() if current > 0 else None
        try:
            for version, fn in MIGRATIONS:
                if version > current:
                    self._conn.execute("BEGIN")
                    fn(self._conn)
                    self._set_user_version(version)
                    self._conn.execute("COMMIT")
        except Exception as exc:
            self._conn.execute("ROLLBACK")
            if backup is not None:
                self._restore_from_backup(backup)
            raise SteamZeroError("E-STATE-MIGRATION", detail=f"falha ao migrar: {exc}") from exc
        return self.user_version

    def _backup_before_migration(self) -> Path:
        self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        dest = paths.backups_dir() / f"state-premigration-{_now_iso().replace(':', '')}.db"
        data = self._path.read_bytes()
        fs.write_atomic(dest, data)
        return dest

    def _restore_from_backup(self, backup: Path) -> None:
        self._conn.close()
        fs.write_atomic(self._path, backup.read_bytes())
        self._conn = sqlite3.connect(self._path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._apply_pragmas()

    # -- integridade --------------------------------------------------------
    def integrity_ok(self) -> bool:
        row = self._conn.execute("PRAGMA integrity_check").fetchone()
        return bool(row) and row[0] == "ok"

    def check_integrity(self) -> None:
        if not self.integrity_ok():
            raise SteamZeroError("E-STATE-INTEGRITY", detail="integrity_check falhou")

    # -- jobs ---------------------------------------------------------------
    def save_job(self, job: dict[str, Any]) -> None:
        """Insere ou atualiza um job (upsert por id). Colunas de _JOB_COLUMNS."""
        row = {col: job.get(col) for col in _JOB_COLUMNS}
        row["updated_at"] = _now_iso()
        row.setdefault("created_at", row["updated_at"])
        if row.get("created_at") is None:
            row["created_at"] = row["updated_at"]
        placeholders = ",".join(f":{c}" for c in _JOB_COLUMNS)
        updates = ",".join(f"{c}=excluded.{c}" for c in _JOB_COLUMNS if c != "id")
        cols = ",".join(_JOB_COLUMNS)
        # SQL montado só de _JOB_COLUMNS (constantes) + placeholders; valores por :param.
        sql = (
            f"INSERT INTO job ({cols}) VALUES ({placeholders}) "  # noqa: S608
            f"ON CONFLICT(id) DO UPDATE SET {updates}"
        )
        self._conn.execute(sql, row)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM job WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row is not None else None

    def list_jobs(self, *, states: list[str] | None = None) -> list[dict[str, Any]]:
        if states:
            marks = ",".join("?" for _ in states)
            sql = f"SELECT * FROM job WHERE state IN ({marks}) ORDER BY created_at"  # noqa: S608
            rows = self._conn.execute(sql, states).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM job ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]

    def list_jobs_page(
        self,
        *,
        limit: int,
        before_id: str | None = None,
        states: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Lista jobs em ordem recency com paginação keyset e memória limitada."""
        bounded = _bounded_page_limit(limit)
        clauses: list[str] = []
        values: list[Any] = []
        if before_id is not None:
            clauses.append("id < ?")
            values.append(before_id)
        if states:
            marks = ",".join("?" for _ in states)
            clauses.append(f"state IN ({marks})")
            values.extend(states)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        values.append(bounded + 1)
        rows = self._conn.execute(
            f"SELECT * FROM job{where} ORDER BY id DESC LIMIT ?",  # noqa: S608
            values,
        ).fetchall()
        return [dict(row) for row in rows[:bounded]], len(rows) > bounded

    # -- operações ----------------------------------------------------------
    def save_operation(
        self,
        operation_id: str,
        *,
        journal_path: str | None = None,
        state: str = "active",
        backup_path: str | None = None,
    ) -> None:
        """Registra/atualiza uma operação (referenciada por job.operation_id)."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            previous = self._conn.execute(
                "SELECT state FROM operation WHERE id=?", (operation_id,)
            ).fetchone()
            self._conn.execute(
                "INSERT INTO operation (id, journal_path, state, backup_path) VALUES (?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET journal_path=excluded.journal_path, "
                "state=excluded.state, backup_path=excluded.backup_path",
                (operation_id, journal_path, state, backup_path),
            )
            if previous is None or previous["state"] != state:
                self.append_event(
                    "operation.state",
                    entity=f"operation:{operation_id}",
                    payload={"state": state},
                )
            self._conn.execute("COMMIT")
        except Exception:
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            raise

    def get_operation(self, operation_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM operation WHERE id=?", (operation_id,)).fetchone()
        return dict(row) if row is not None else None

    def list_operations_page(
        self, *, limit: int, before_id: str | None = None
    ) -> tuple[list[dict[str, Any]], bool]:
        """Lista operações em ordem recency sem materializar o histórico inteiro."""
        bounded = _bounded_page_limit(limit)
        if before_id is None:
            rows = self._conn.execute(
                "SELECT * FROM operation ORDER BY id DESC LIMIT ?", (bounded + 1,)
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM operation WHERE id < ? ORDER BY id DESC LIMIT ?",
                (before_id, bounded + 1),
            ).fetchall()
        return [dict(row) for row in rows[:bounded]], len(rows) > bounded

    def count_operations(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS total FROM operation").fetchone()
        return int(row["total"]) if row is not None else 0

    # -- device -------------------------------------------------------------
    def save_device(self, device: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO device (id, kind, dmi_fingerprint, quirks_json) VALUES (?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, "
            "dmi_fingerprint=excluded.dmi_fingerprint, quirks_json=excluded.quirks_json",
            (
                device["id"],
                device["kind"],
                device.get("dmi_fingerprint"),
                device.get("quirks_json"),
            ),
        )

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM device WHERE id=?", (device_id,)).fetchone()
        return dict(row) if row is not None else None

    # -- components / adapters --------------------------------------------
    def save_component(self, component: dict[str, Any]) -> None:
        """Persiste o estado detectado de um componente (upsert por id)."""
        cols = (
            "id",
            "adapter_id",
            "kind",
            "version",
            "origin",
            "state",
            "verified_at",
            "manifest_hash",
        )
        row = {col: component.get(col) for col in cols}
        row["verified_at"] = row["verified_at"] or _now_iso()
        placeholders = ",".join(f":{col}" for col in cols)
        updates = ",".join(f"{col}=excluded.{col}" for col in cols if col != "id")
        sql = (
            f"INSERT INTO component ({','.join(cols)}) VALUES ({placeholders}) "  # noqa: S608
            f"ON CONFLICT(id) DO UPDATE SET {updates}"
        )
        self._conn.execute(sql, row)

    def get_component(self, component_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM component WHERE id=?", (component_id,)).fetchone()
        return dict(row) if row is not None else None

    def list_components(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM component ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    # -- storage volumes ----------------------------------------------------
    def save_volume(self, volume: dict[str, Any]) -> None:
        cols = ("id", "uuid", "label", "fstype", "role", "state", "capacity", "free", "last_seen")
        row = {c: volume.get(c) for c in cols}
        placeholders = ",".join(f":{c}" for c in cols)
        updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "id")
        sql = (
            f"INSERT INTO storage_volume ({','.join(cols)}) VALUES ({placeholders}) "  # noqa: S608
            f"ON CONFLICT(id) DO UPDATE SET {updates}"
        )
        self._conn.execute(sql, row)

    def get_volume_by_uuid(self, uuid: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM storage_volume WHERE uuid=?", (uuid,)).fetchone()
        return dict(row) if row is not None else None

    def list_volumes(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM storage_volume ORDER BY uuid").fetchall()
        return [dict(r) for r in rows]

    # -- profiles -----------------------------------------------------------
    def save_profile(self, profile: dict[str, Any]) -> None:
        cols = ("id", "scope", "kind", "payload_json", "priority", "profile_owner")
        row = {c: profile.get(c) for c in cols}
        placeholders = ",".join(f":{c}" for c in cols)
        updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "id")
        sql = (
            f"INSERT INTO profile ({','.join(cols)}) VALUES ({placeholders}) "  # noqa: S608
            f"ON CONFLICT(id) DO UPDATE SET {updates}"
        )
        self._conn.execute(sql, row)

    def save_profiles(self, profiles: list[dict[str, Any]]) -> None:
        """Persiste um conjunto de perfis como uma única mudança atômica."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            for profile in profiles:
                self.save_profile(profile)
            self._conn.execute("COMMIT")
        except Exception:
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            raise

    def replace_profiles(
        self, profiles: list[dict[str, Any]], *, delete_ids: Sequence[str] = ()
    ) -> None:
        """Aplica upserts e remoções allowlisted em uma única transação."""
        if any(not value or len(value) > 240 or "\x00" in value for value in delete_ids):
            raise ValueError("profile id inválido")
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            for profile in profiles:
                self.save_profile(profile)
            for profile_id in delete_ids:
                self._conn.execute("DELETE FROM profile WHERE id=?", (profile_id,))
            self._conn.execute("COMMIT")
        except Exception:
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            raise

    def get_profile(self, profile_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM profile WHERE id=?", (profile_id,)).fetchone()
        return dict(row) if row is not None else None

    def list_profiles(
        self, *, kind: str | None = None, owner: str | None = None
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        values: list[str] = []
        if kind is not None:
            clauses.append("kind=?")
            values.append(kind)
        if owner is not None:
            clauses.append("profile_owner=?")
            values.append(owner)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM profile{where} ORDER BY id",  # noqa: S608 - cláusulas fixas
            values,
        ).fetchall()
        return [dict(row) for row in rows]

    # -- game sessions -----------------------------------------------------
    def create_game_session(self, session: dict[str, Any]) -> None:
        """Cria uma sessão e adquire atomicamente a exclusividade por owner."""
        now = _now_iso()
        row = {
            "id": session["id"],
            "game_id": session["game_id"],
            "state": session["state"],
            "pid": session.get("pid"),
            "start_ticks": session.get("start_ticks"),
            "profile_digest": session.get("profile_digest"),
            "owner": session["owner"],
            "started_at": session.get("started_at") or now,
            "updated_at": now,
            "finished_at": session.get("finished_at"),
            "exit_code": session.get("exit_code"),
            "failure_code": session.get("failure_code"),
            "metadata_json": session.get("metadata_json"),
        }
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                """
                INSERT INTO game_session (
                  id,game_id,state,pid,start_ticks,profile_digest,owner,started_at,updated_at,
                  finished_at,exit_code,failure_code,metadata_json
                ) VALUES (
                  :id,:game_id,:state,:pid,:start_ticks,:profile_digest,:owner,:started_at,:updated_at,
                  :finished_at,:exit_code,:failure_code,:metadata_json
                )
                """,
                row,
            )
            self.append_event(
                "session.state",
                entity=f"session:{row['id']}",
                payload={"state": row["state"], "gameId": row["game_id"]},
            )
            self._conn.execute("COMMIT")
        except Exception:
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            raise

    def transition_game_session(
        self, session_id: str, target: str, **changes: Any
    ) -> dict[str, Any]:
        """Faz compare-and-transition serializado e emite o evento canônico."""
        allowed = {
            "pid",
            "start_ticks",
            "profile_digest",
            "finished_at",
            "exit_code",
            "failure_code",
            "metadata_json",
            "played_seconds",
            "duration_source",
        }
        if not set(changes).issubset(allowed):
            raise SteamZeroError("E-API-SCHEMA", detail="campo de sessão não permitido")
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            current_row = self._conn.execute(
                "SELECT * FROM game_session WHERE id=?", (session_id,)
            ).fetchone()
            if current_row is None:
                raise SteamZeroError("E-STATE-INTEGRITY", detail="sessão de jogo ausente")
            current = str(current_row["state"])
            if not can_transition(current, target):
                raise SteamZeroError(
                    "E-STATE-INTEGRITY",
                    detail=f"transição de sessão inválida: {current} -> {target}",
                )
            assignments = ["state=?", "updated_at=?"]
            values: list[Any] = [target, _now_iso()]
            for key in sorted(changes):
                assignments.append(f"{key}=?")
                values.append(changes[key])
            values.append(session_id)
            self._conn.execute(
                f"UPDATE game_session SET {','.join(assignments)} WHERE id=?",  # noqa: S608
                values,
            )
            self.append_event(
                "session.state",
                entity=f"session:{session_id}",
                payload={"state": target, "gameId": current_row["game_id"]},
            )
            updated = self._conn.execute(
                "SELECT * FROM game_session WHERE id=?", (session_id,)
            ).fetchone()
            self._conn.execute("COMMIT")
        except Exception:
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            raise
        if updated is None:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="sessão desapareceu após transição")
        return dict(updated)

    def latest_game_session(self, game_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM game_session WHERE game_id=? ORDER BY updated_at DESC,id DESC LIMIT 1",
            (game_id,),
        ).fetchone()
        return dict(row) if row is not None else None

    def active_game_session(self, owner: str) -> dict[str, Any] | None:
        placeholders = ",".join("?" for _ in ACTIVE_SESSION_STATES)
        values = [owner, *sorted(ACTIVE_SESSION_STATES)]
        row = self._conn.execute(
            f"SELECT * FROM game_session WHERE owner=? AND state IN ({placeholders}) "  # noqa: S608
            "ORDER BY updated_at DESC LIMIT 1",
            values,
        ).fetchone()
        return dict(row) if row is not None else None

    def active_game_sessions(self, owner: str) -> list[dict[str, Any]]:
        """Sessões ativas com processo observável (PID persistido).

        Usado pelo probe de recursos (GAP-G30): a identidade efêmera
        (pid, start_ticks) permite atribuir consumo do emulador sem ler
        command line nem caminhos.
        """
        placeholders = ",".join("?" for _ in ACTIVE_SESSION_STATES)
        values = [owner, *sorted(ACTIVE_SESSION_STATES)]
        rows = self._conn.execute(
            f"SELECT * FROM game_session WHERE owner=? AND state IN ({placeholders}) "  # noqa: S608
            "AND pid IS NOT NULL ORDER BY updated_at DESC",
            values,
        ).fetchall()
        return [dict(row) for row in rows]

    def playtime_total_seconds(self) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(played_seconds), 0) FROM game_session"
        ).fetchone()
        return int(row[0]) if row is not None else 0

    def list_playtime_games(
        self,
        *,
        limit: int,
        before_started_at: str | None = None,
        before_game_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Agrega playtime por jogo e anexa sua sessão mais recente."""
        bounded = _bounded_page_limit(limit)
        cursor_clause = ""
        values: list[Any] = []
        if before_started_at is not None or before_game_id is not None:
            if not before_started_at or not before_game_id:
                raise ValueError("cursor de playtime incompleto")
            cursor_clause = (
                "WHERE (aggregate.last_started_at < ? OR "
                "(aggregate.last_started_at = ? AND aggregate.game_id > ?))"
            )
            values.extend((before_started_at, before_started_at, before_game_id))
        values.append(bounded + 1)
        rows = self._conn.execute(
            f"""
            WITH aggregate AS (
              SELECT
                game_id,
                SUM(played_seconds) AS played_seconds,
                COUNT(*) AS session_count,
                MAX(started_at) AS last_started_at
              FROM game_session
              GROUP BY game_id
            ),
            latest AS (
              SELECT
                game_session.*,
                ROW_NUMBER() OVER (
                  PARTITION BY game_id
                  ORDER BY started_at DESC, id DESC
                ) AS position
              FROM game_session
            )
            SELECT
              aggregate.game_id,
              aggregate.played_seconds,
              aggregate.session_count,
              aggregate.last_started_at,
              latest.id AS latest_session_id,
              latest.state AS latest_state,
              latest.started_at AS latest_started_at,
              latest.updated_at AS latest_updated_at,
              latest.finished_at AS latest_finished_at,
              latest.failure_code AS latest_failure_code,
              latest.played_seconds AS latest_played_seconds,
              latest.duration_source AS latest_duration_source,
              latest.metadata_json AS latest_metadata_json,
              game.title AS game_title,
              game.platform_id AS platform_id,
              game.state AS game_state
            FROM aggregate
            JOIN latest
              ON latest.game_id = aggregate.game_id AND latest.position = 1
            LEFT JOIN game ON game.id = aggregate.game_id
            {cursor_clause}
            ORDER BY aggregate.last_started_at DESC, aggregate.game_id ASC
            LIMIT ?
            """,  # noqa: S608 - cursor_clause é uma constante fechada
            values,
        ).fetchall()
        return [dict(row) for row in rows[:bounded]], len(rows) > bounded

    def playtime_game(self, game_id: str) -> dict[str, Any] | None:
        rows, _ = self.list_playtime_games(limit=100)
        for row in rows:
            if row["game_id"] == game_id:
                return row
        # A consulta paginada é limitada; uma busca pontual não pode desaparecer.
        aggregate = self._conn.execute(
            """
            SELECT
              game_id,
              SUM(played_seconds) AS played_seconds,
              COUNT(*) AS session_count,
              MAX(started_at) AS last_started_at
            FROM game_session
            WHERE game_id=?
            GROUP BY game_id
            """,
            (game_id,),
        ).fetchone()
        if aggregate is None:
            return None
        latest = self.latest_game_session(game_id)
        if latest is None:
            return None
        game = self._conn.execute("SELECT * FROM game WHERE id=?", (game_id,)).fetchone()
        return {
            **dict(aggregate),
            "latest_session_id": latest["id"],
            "latest_state": latest["state"],
            "latest_started_at": latest["started_at"],
            "latest_updated_at": latest["updated_at"],
            "latest_finished_at": latest["finished_at"],
            "latest_failure_code": latest["failure_code"],
            "latest_played_seconds": latest["played_seconds"],
            "latest_duration_source": latest["duration_source"],
            "latest_metadata_json": latest["metadata_json"],
            "game_title": game["title"] if game is not None else None,
            "platform_id": game["platform_id"] if game is not None else None,
            "game_state": game["state"] if game is not None else None,
        }

    # -- library (platform / game / rom) ------------------------------------
    def save_platform(self, platform: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO platform (id, name, esde_folder, extensions_json) VALUES (?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, "
            "esde_folder=excluded.esde_folder, extensions_json=excluded.extensions_json",
            (
                platform["id"],
                platform["name"],
                platform.get("esde_folder"),
                platform.get("extensions_json"),
            ),
        )

    def save_game(self, game: dict[str, Any]) -> None:
        cols = ("id", "platform_id", "title", "canonical_path_id", "multi_disc_group", "state")
        row = {c: game.get(c) for c in cols}
        placeholders = ",".join(f":{c}" for c in cols)
        updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "id")
        sql = (
            f"INSERT INTO game ({','.join(cols)}) VALUES ({placeholders}) "  # noqa: S608
            f"ON CONFLICT(id) DO UPDATE SET {updates}"
        )
        self._conn.execute(sql, row)

    def save_rom(self, rom: dict[str, Any]) -> None:
        cols = (
            "id",
            "game_id",
            "volume_id",
            "relpath",
            "size",
            "hash_blake2b",
            "format",
            "verified_at",
        )
        row = {c: rom.get(c) for c in cols}
        placeholders = ",".join(f":{c}" for c in cols)
        updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "id")
        sql = (
            f"INSERT INTO rom_file ({','.join(cols)}) VALUES ({placeholders}) "  # noqa: S608
            f"ON CONFLICT(id) DO UPDATE SET {updates}"
        )
        self._conn.execute(sql, row)

    def find_rom_by_hash(self, hash_blake2b: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM rom_file WHERE hash_blake2b=?", (hash_blake2b,)
        ).fetchone()
        return dict(row) if row is not None else None

    def list_roms(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM rom_file ORDER BY relpath").fetchall()
        return [dict(r) for r in rows]

    # -- BIOS ---------------------------------------------------------------
    def save_bios_item(self, item: dict[str, Any]) -> None:
        cols = (
            "id",
            "platform_id",
            "relpath",
            "hash",
            "region",
            "version",
            "state",
            "last_validated",
        )
        row = {c: item.get(c) for c in cols}
        placeholders = ",".join(f":{c}" for c in cols)
        updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "id")
        sql = (
            f"INSERT INTO bios_item ({','.join(cols)}) VALUES ({placeholders}) "  # noqa: S608
            f"ON CONFLICT(id) DO UPDATE SET {updates}"
        )
        self._conn.execute(sql, row)

    def list_bios(self, platform_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM bios_item WHERE platform_id=? ORDER BY relpath", (platform_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def save_bios_object(self, item: dict[str, Any]) -> None:
        """Upsert an immutable CAS object; its full hash never enters logs."""
        self._conn.execute(
            "INSERT INTO bios_object (sha256,size,state,last_validated,operation_id) "
            "VALUES (:sha256,:size,:state,:last_validated,:operation_id) "
            "ON CONFLICT(sha256) DO UPDATE SET size=excluded.size,state=excluded.state, "
            "last_validated=excluded.last_validated,operation_id=excluded.operation_id",
            item,
        )

    def list_bios_objects(self) -> list[dict[str, Any]]:
        rows = self._conn.execute("SELECT * FROM bios_object ORDER BY sha256").fetchall()
        return [dict(row) for row in rows]

    # -- keys/firmware (nunca hash completo; só hash_truncated — SR-14) ------
    def save_firmware_key_item(self, item: dict[str, Any]) -> None:
        cols = (
            "id",
            "kind",
            "platform_id",
            "hash_truncated",
            "state",
            "keyset",
            "revision",
            "version",
            "relpath",
            "last_validated",
        )
        row = {c: item.get(c) for c in cols}
        placeholders = ",".join(f":{c}" for c in cols)
        updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "id")
        sql = (
            f"INSERT INTO firmware_key_item ({','.join(cols)}) VALUES ({placeholders}) "  # noqa: S608
            f"ON CONFLICT(id) DO UPDATE SET {updates}"
        )
        self._conn.execute(sql, row)

    def list_firmware_key_items(
        self, platform_id: str, *, kind: str | None = None
    ) -> list[dict[str, Any]]:
        if kind is None:
            rows = self._conn.execute(
                "SELECT * FROM firmware_key_item WHERE platform_id=? ORDER BY relpath",
                (platform_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM firmware_key_item WHERE platform_id=? AND kind=? ORDER BY relpath",
                (platform_id, kind),
            ).fetchall()
        return [dict(r) for r in rows]

    # -- saves --------------------------------------------------------------
    def save_save_entry(self, entry: dict[str, Any]) -> None:
        cols = (
            "id",
            "game_id",
            "kind",
            "timeline_seq",
            "created_at",
            "device_id",
            "hash",
            "size",
            "origin",
            "conflict_group",
            "profile_owner",
        )
        row = {c: entry.get(c) for c in cols}
        placeholders = ",".join(f":{c}" for c in cols)
        updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "id")
        sql = (
            f"INSERT INTO save_entry ({','.join(cols)}) VALUES ({placeholders}) "  # noqa: S608
            f"ON CONFLICT(id) DO UPDATE SET {updates}"
        )
        self._conn.execute(sql, row)

    def list_saves(self, game_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM save_entry WHERE game_id=? ORDER BY timeline_seq", (game_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def max_timeline_seq(self, game_id: str) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(timeline_seq), 0) FROM save_entry WHERE game_id=?", (game_id,)
        ).fetchone()
        return int(row[0])

    def get_save_entry(self, entry_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM save_entry WHERE id=?", (entry_id,)).fetchone()
        return dict(row) if row is not None else None

    # -- sync queue ---------------------------------------------------------
    def save_sync_entry(self, entry: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO sync_queue (id, save_entry_id, direction, state) VALUES (?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET direction=excluded.direction, state=excluded.state",
            (entry["id"], entry["save_entry_id"], entry.get("direction"), entry["state"]),
        )

    def set_sync_state(self, sync_id: str, new_state: str) -> None:
        self._conn.execute("UPDATE sync_queue SET state=? WHERE id=?", (new_state, sync_id))

    def list_sync_queue(self, *, state: str | None = None) -> list[dict[str, Any]]:
        if state is not None:
            rows = self._conn.execute(
                "SELECT * FROM sync_queue WHERE state=? ORDER BY id", (state,)
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM sync_queue ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    # -- ambiente da sessão -----------------------------------------------
    def save_session_environment(
        self, payload: dict[str, Any], digest: str, *, changes: list[str]
    ) -> None:
        """Atualiza o snapshot e seu evento como uma única transação."""
        observed_at = str(payload.get("observedAt") or _now_iso())
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            self._conn.execute(
                """
                INSERT INTO session_environment (id,observed_at,digest,payload_json)
                VALUES ('current',?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                  observed_at=excluded.observed_at,
                  digest=excluded.digest,
                  payload_json=excluded.payload_json
                """,
                (observed_at, digest, encoded),
            )
            self.append_event(
                "session.environment",
                entity="session-environment:current",
                payload={"digest": digest, "changes": changes},
            )
            self._conn.execute("COMMIT")
        except Exception:
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
            raise

    def get_session_environment(self) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM session_environment WHERE id='current'").fetchone()
        return dict(row) if row is not None else None

    def record_session_resume(self, suspended_seconds: float) -> int:
        """Registra uma retomada observada, sem alegar um hook pré-suspend."""
        bounded = max(0.0, min(float(suspended_seconds), 31_536_000.0))
        return self.append_event(
            "session.resume",
            entity="system-session:current",
            payload={"suspendedSeconds": round(bounded, 3)},
        )

    # -- event log ----------------------------------------------------------
    def append_event(self, kind: str, *, entity: str | None = None, payload: Any = None) -> int:
        cur = self._conn.execute(
            "INSERT INTO event_log (ts, kind, entity, payload_json) VALUES (?,?,?,?)",
            (
                _now_iso(),
                kind,
                entity,
                json.dumps(payload, ensure_ascii=False) if payload else None,
            ),
        )
        return int(cur.lastrowid or 0)

    def events_since(self, seq: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM event_log WHERE seq > ? ORDER BY seq", (seq,)
        ).fetchall()
        return [dict(r) for r in rows]

    def events_page(
        self,
        *,
        after_seq: int,
        limit: int,
        kinds: list[str] | None = None,
        entities: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Lê uma página crescente do log append-only, com filtros exatos."""
        if after_seq < 0:
            raise ValueError("after_seq não pode ser negativo")
        bounded = _bounded_page_limit(limit)
        clauses = ["seq > ?"]
        values: list[Any] = [after_seq]
        if kinds:
            marks = ",".join("?" for _ in kinds)
            clauses.append(f"kind IN ({marks})")
            values.extend(kinds)
        if entities:
            marks = ",".join("?" for _ in entities)
            clauses.append(f"entity IN ({marks})")
            values.extend(entities)
        values.append(bounded + 1)
        sql = (
            "SELECT * FROM event_log WHERE "  # noqa: S608 - fixed fragments/placeholders
            + " AND ".join(clauses)
            + " ORDER BY seq LIMIT ?"
        )
        rows = self._conn.execute(sql, values).fetchall()
        return [dict(row) for row in rows[:bounded]], len(rows) > bounded

    def latest_event_seq(self) -> int:
        row = self._conn.execute("SELECT COALESCE(MAX(seq), 0) FROM event_log").fetchone()
        return int(row[0])

    # -- export -------------------------------------------------------------
    def export_json(self) -> dict[str, Any]:
        """Dump canônico do estado (steamzero state export)."""
        tables = [
            r[0]
            for r in self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            ).fetchall()
        ]
        data: dict[str, Any] = {
            "schemaVersion": self.user_version,
            "generatedAt": _now_iso(),
            "tables": {},
        }
        for table in tables:
            rows = self._conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()  # noqa: S608
            data["tables"][table] = [dict(r) for r in rows]
        return data

    def close(self) -> None:
        if self._closed:
            return
        self._conn.close()
        self._closed = True

    def __del__(self) -> None:
        # Last-resort guard for exceptional/test paths. Normal ownership must
        # still use the context manager or call close() explicitly.
        with suppress(Exception):
            self.close()

    def __enter__(self) -> StateStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def open_state(path: Path | None = None) -> StateStore:
    """Abre (e migra) o State Store, retornando um StateStore pronto."""
    store = StateStore(path)
    store.migrate()
    return store


def _bounded_page_limit(limit: int) -> int:
    if not 1 <= limit <= 256:
        raise ValueError("limit precisa estar entre 1 e 256")
    return limit
