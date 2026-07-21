# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Migração 0008 — mods para emuladores Switch.

Adiciona tabelas para:
- ``switch_mod``: mods instalados por jogo, com estado e caminho.
- ``switch_mod_catalog``: cache do catálogo remoto (mods disponíveis).
- ``switch_game_build_id``: Build IDs detectados por jogo para casamento
  preciso de mods.
"""

from __future__ import annotations

import sqlite3

_DDL = """
CREATE TABLE switch_mod (
  id              TEXT PRIMARY KEY,
  game_id         TEXT NOT NULL REFERENCES game(id),
  catalog_id      TEXT,
  title_id        TEXT NOT NULL,
  build_id        TEXT,
  name            TEXT NOT NULL,
  mod_type        TEXT NOT NULL CHECK (mod_type IN (
                    'performance','graphics','ultrawide','gameplay','patch','other')),
  source          TEXT NOT NULL,
  version         TEXT,
  state           TEXT NOT NULL CHECK (state IN (
                    'discovered','downloaded','installed','active','inactive','error')),
  install_path    TEXT,
  emulator_id     TEXT,
  installed_at    TEXT NOT NULL,
  activated_at    TEXT
);

CREATE INDEX idx_switch_mod_game ON switch_mod(game_id);
CREATE INDEX idx_switch_mod_state ON switch_mod(state);

CREATE TABLE switch_mod_catalog (
  id              TEXT PRIMARY KEY,
  title_id        TEXT NOT NULL,
  build_id        TEXT,
  name            TEXT NOT NULL,
  mod_type        TEXT NOT NULL,
  source          TEXT NOT NULL,
  source_url      TEXT NOT NULL,
  version         TEXT,
  description     TEXT,
  author          TEXT,
  requirements    TEXT,
  added_at        TEXT NOT NULL,
  refreshed_at    TEXT NOT NULL
);

CREATE INDEX idx_catalog_title_id ON switch_mod_catalog(title_id);
CREATE INDEX idx_catalog_source ON switch_mod_catalog(source);

CREATE TABLE switch_game_build_id (
  game_id         TEXT NOT NULL REFERENCES game(id),
  title_id        TEXT NOT NULL,
  build_id        TEXT NOT NULL,
  detected_from   TEXT NOT NULL DEFAULT 'rom',
  detected_at     TEXT NOT NULL,
  PRIMARY KEY (game_id, build_id)
);

CREATE INDEX idx_build_id_title ON switch_game_build_id(title_id);
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
