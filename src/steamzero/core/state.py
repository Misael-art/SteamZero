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
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any

from steamzero.core import fs, paths
from steamzero.core.errors import SteamZeroError
from steamzero.core.migrations import LATEST, MIGRATIONS

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
        self._conn.execute(
            "INSERT INTO operation (id, journal_path, state, backup_path) VALUES (?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET journal_path=excluded.journal_path, "
            "state=excluded.state, backup_path=excluded.backup_path",
            (operation_id, journal_path, state, backup_path),
        )

    def get_operation(self, operation_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM operation WHERE id=?", (operation_id,)).fetchone()
        return dict(row) if row is not None else None

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

    def get_profile(self, profile_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM profile WHERE id=?", (profile_id,)).fetchone()
        return dict(row) if row is not None else None

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
        self._conn.close()

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
