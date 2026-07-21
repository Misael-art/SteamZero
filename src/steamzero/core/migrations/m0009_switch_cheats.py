# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Migração 0009 — cheats para emuladores Switch.

Adiciona tabelas para:
- ``switch_cheat``: cheats instalados por jogo, com estado e códigos.
- ``switch_cheat_catalog``: cache do catálogo remoto de cheats.
"""

from __future__ import annotations

import sqlite3

_DDL = """
CREATE TABLE switch_cheat (
  id              TEXT PRIMARY KEY,
  game_id         TEXT NOT NULL REFERENCES game(id),
  title_id        TEXT NOT NULL,
  build_id        TEXT,
  name            TEXT NOT NULL,
  cheat_type      TEXT NOT NULL CHECK (cheat_type IN (
                    'gold','infinite','speed','items','unlock','stats','other')),
  source          TEXT NOT NULL,
  version         TEXT,
  state           TEXT NOT NULL CHECK (state IN (
                    'discovered','downloaded','installed','active','inactive','error')),
  install_path    TEXT,
  emulator_id     TEXT,
  code_count      INTEGER NOT NULL DEFAULT 0,
  enabled         INTEGER NOT NULL DEFAULT 0,
  installed_at    TEXT NOT NULL,
  activated_at    TEXT
);

CREATE INDEX idx_switch_cheat_game ON switch_cheat(game_id);
CREATE INDEX idx_switch_cheat_title ON switch_cheat(title_id);

CREATE TABLE switch_cheat_catalog (
  id              TEXT PRIMARY KEY,
  title_id        TEXT NOT NULL,
  build_id        TEXT,
  name            TEXT NOT NULL,
  cheat_type      TEXT NOT NULL,
  source          TEXT NOT NULL,
  source_url      TEXT NOT NULL,
  codes           TEXT NOT NULL DEFAULT '',
  description     TEXT,
  author          TEXT,
  version         TEXT,
  added_at        TEXT NOT NULL,
  refreshed_at    TEXT NOT NULL
);

CREATE INDEX idx_cheat_catalog_title ON switch_cheat_catalog(title_id);
CREATE INDEX idx_cheat_catalog_source ON switch_cheat_catalog(source);
"""


def up(conn: sqlite3.Connection) -> None:
    for statement in _DDL.split(";"):
        stmt = statement.strip()
        if stmt:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError as exc:
                if "already exists" not in str(exc):
                    raise
