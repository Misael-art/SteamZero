# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Migração 0001 — schema baseline do State Store (STATE-MODEL).

Cria todas as entidades normativas do modelo lógico. Colunas seguem
docs/05-data/STATE-MODEL.md. Nada de paths absolutos (volume_id + relpath).
``profile_owner`` reservado desde v1 (Q9 multi-usuário), não exposto na v1.
"""

from __future__ import annotations

import sqlite3

_DDL = """
CREATE TABLE device (
  id              TEXT PRIMARY KEY,
  kind            TEXT NOT NULL CHECK (kind IN ('deck-lcd','deck-oled','desktop')),
  dmi_fingerprint TEXT,
  quirks_json     TEXT
);

CREATE TABLE storage_volume (
  id        TEXT PRIMARY KEY,
  uuid      TEXT NOT NULL UNIQUE,
  label     TEXT,
  fstype    TEXT,
  role      TEXT NOT NULL CHECK (role IN ('internal','microsd','usb')),
  state     TEXT NOT NULL CHECK (state IN ('mounted','missing','io-error')),
  capacity  INTEGER,
  free      INTEGER,
  last_seen TEXT
);

CREATE TABLE component (
  id            TEXT PRIMARY KEY,
  adapter_id    TEXT NOT NULL,
  kind          TEXT NOT NULL CHECK (kind IN ('emulator','frontend','tool')),
  version       TEXT,
  origin        TEXT CHECK (origin IN ('flatpak','appimage','native')),
  state         TEXT NOT NULL CHECK (state IN ('installed','degraded','missing','staged')),
  verified_at   TEXT,
  manifest_hash TEXT
);

CREATE TABLE platform (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  esde_folder     TEXT,
  extensions_json TEXT
);

CREATE TABLE game (
  id                TEXT PRIMARY KEY,
  platform_id       TEXT NOT NULL REFERENCES platform(id),
  title             TEXT NOT NULL,
  canonical_path_id TEXT,
  multi_disc_group  TEXT,
  state             TEXT NOT NULL CHECK (
                      state IN ('ready','missing-bios','unavailable','quarantined','incomplete'))
);

CREATE TABLE rom_file (
  id           TEXT PRIMARY KEY,
  game_id      TEXT NOT NULL REFERENCES game(id),
  volume_id    TEXT REFERENCES storage_volume(id),
  relpath      TEXT NOT NULL,
  size         INTEGER,
  hash_blake2b TEXT,
  format       TEXT,
  verified_at  TEXT
);

CREATE TABLE bios_item (
  id             TEXT PRIMARY KEY,
  platform_id    TEXT REFERENCES platform(id),
  relpath        TEXT,
  hash           TEXT,
  region         TEXT,
  version        TEXT,
  state          TEXT NOT NULL CHECK (state IN ('present','missing','unknown','incompatible')),
  last_validated TEXT
);

CREATE TABLE firmware_key_item (
  id             TEXT PRIMARY KEY,
  kind           TEXT NOT NULL CHECK (kind IN ('firmware','key')),
  platform_id    TEXT REFERENCES platform(id),
  hash_truncated TEXT,
  state          TEXT
);

CREATE TABLE save_entry (
  id             TEXT PRIMARY KEY,
  game_id        TEXT NOT NULL REFERENCES game(id),
  kind           TEXT NOT NULL CHECK (kind IN ('save','state')),
  timeline_seq   INTEGER NOT NULL,
  created_at     TEXT,
  device_id      TEXT REFERENCES device(id),
  hash           TEXT,
  size           INTEGER,
  origin         TEXT CHECK (origin IN ('local','cloud','checkpoint')),
  conflict_group TEXT,
  profile_owner  TEXT
);

CREATE TABLE media_item (
  id       TEXT PRIMARY KEY,
  game_id  TEXT NOT NULL REFERENCES game(id),
  kind     TEXT NOT NULL CHECK (kind IN ('boxart','screenshot','video')),
  provider TEXT,
  license  TEXT,
  relpath  TEXT,
  hash     TEXT,
  state    TEXT NOT NULL CHECK (state IN ('ok','orphaned','quarantined'))
);

CREATE TABLE profile (
  id            TEXT PRIMARY KEY,
  scope         TEXT NOT NULL CHECK (scope IN ('game','platform','device','mode')),
  kind          TEXT NOT NULL CHECK (kind IN ('performance','controls','display')),
  payload_json  TEXT,
  priority      INTEGER,
  profile_owner TEXT
);

CREATE TABLE operation (
  id           TEXT PRIMARY KEY,
  journal_path TEXT,
  state        TEXT NOT NULL,
  backup_path  TEXT
);

CREATE TABLE job (
  id              TEXT PRIMARY KEY,
  type            TEXT NOT NULL,
  params_json     TEXT,
  priority        TEXT NOT NULL,
  state           TEXT NOT NULL,
  progress_json   TEXT,
  operation_id    TEXT REFERENCES operation(id),
  correlation_id  TEXT,
  created_by      TEXT CHECK (created_by IN ('ui','cli','qam','scheduler')),
  constraints_json TEXT,
  checkpoints_json TEXT,
  result_json     TEXT,
  error_code      TEXT,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);

CREATE TABLE backup (
  id             TEXT PRIMARY KEY,
  operation_id   TEXT REFERENCES operation(id),
  manifest_json  TEXT,
  size           INTEGER,
  retained_until TEXT
);

CREATE TABLE sync_queue (
  id            TEXT PRIMARY KEY,
  save_entry_id TEXT REFERENCES save_entry(id),
  direction     TEXT,
  state         TEXT NOT NULL CHECK (state IN ('pending','in-flight','conflicted','done'))
);

CREATE TABLE compat_fact (
  id               TEXT PRIMARY KEY,
  subject          TEXT NOT NULL CHECK (subject IN ('steamos','steam-client','component')),
  version          TEXT,
  tested_with_json TEXT,
  verdict          TEXT CHECK (verdict IN ('ok','degraded','broken'))
);

CREATE TABLE event_log (
  seq          INTEGER PRIMARY KEY AUTOINCREMENT,
  ts           TEXT NOT NULL,
  kind         TEXT NOT NULL,
  entity       TEXT,
  payload_json TEXT
);

CREATE INDEX idx_job_state ON job(state);
CREATE INDEX idx_rom_volume ON rom_file(volume_id);
CREATE INDEX idx_save_game ON save_entry(game_id);
CREATE INDEX idx_event_kind ON event_log(kind);
"""


def up(conn: sqlite3.Connection) -> None:
    # statement a statement (não executescript: este força COMMIT implícito e
    # quebraria a transação BEGIN/COMMIT gerida por StateStore.migrate).
    for statement in _DDL.split(";"):
        stmt = statement.strip()
        if stmt:
            conn.execute(stmt)
