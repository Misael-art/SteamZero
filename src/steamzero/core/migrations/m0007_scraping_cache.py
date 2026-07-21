# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Migração 0007 — cache de scraping e metadados de mídia externa.

Adiciona tabelas para:
- Cache de consultas a provedores (``scraping_cache_entry``): evita raspar
  o mesmo jogo duas vezes e permite reprocessar sem rede.
- Catálogo de artefatos baixados (``scraping_media``): associa o arquivo
  concreto ao jogo, com hash e dimensões.
- Monitoramento de saúde dos provedores (``scraping_provider_status``):
  circuit breaker por provider (falhas consecutivas abrem o circuito).
- Credenciais criptografadas (``scraping_credential``): tokens e chaves API
  nunca em claro no state.db — o valor é cifrado via core.secret.

Todas as tabelas têm prefixo ``scraping_`` para evitar colisão com entidades
do modelo de domínio (STATE-MODEL).
"""

from __future__ import annotations

import sqlite3

_DDL = """
CREATE TABLE scraping_cache_entry (
  id              TEXT PRIMARY KEY,
  game_id         TEXT REFERENCES game(id),
  platform_slug   TEXT NOT NULL,
  lookup_key      TEXT NOT NULL,
  lookup_method   TEXT NOT NULL CHECK (lookup_method IN (
                    'hash_sha1','hash_md5','hash_crc32','hash_sha256','title_id','serial','name','fuzzy')),
  provider        TEXT NOT NULL,
  media_kind      TEXT NOT NULL,
  url             TEXT NOT NULL,
  license         TEXT,
  attribution     TEXT,
  etag            TEXT,
  region          TEXT,
  language        TEXT,
  width           INTEGER,
  height          INTEGER,
  confidence      REAL NOT NULL DEFAULT 1.0,
  http_status     INTEGER,
  error           TEXT,
  last_checked    TEXT NOT NULL,
  expires_at      TEXT
);

CREATE INDEX idx_cache_lookup ON scraping_cache_entry(lookup_key, media_kind);
CREATE INDEX idx_cache_game   ON scraping_cache_entry(game_id);

CREATE TABLE scraping_media (
  id                TEXT PRIMARY KEY,
  cache_entry_id    TEXT NOT NULL REFERENCES scraping_cache_entry(id),
  game_id           TEXT NOT NULL REFERENCES game(id),
  media_kind        TEXT NOT NULL,
  file_hash         TEXT NOT NULL,
  size              INTEGER NOT NULL,
  width             INTEGER,
  height            INTEGER,
  mime_type         TEXT,
  state             TEXT NOT NULL CHECK (state IN ('staged','committed','orphaned')),
  created_at        TEXT NOT NULL,
  committed_at      TEXT
);

CREATE INDEX idx_media_game ON scraping_media(game_id, media_kind);

CREATE TABLE scraping_provider_status (
  provider              TEXT PRIMARY KEY,
  last_ok               TEXT,
  last_error            TEXT,
  error_count           INTEGER DEFAULT 0,
  consecutive_failures  INTEGER DEFAULT 0,
  circuit_open_since    TEXT,
  total_requests        INTEGER DEFAULT 0,
  total_bytes           INTEGER DEFAULT 0
);

CREATE TABLE scraping_credential (
  provider        TEXT NOT NULL,
  key_name        TEXT NOT NULL,
  value_encrypted TEXT,
  PRIMARY KEY (provider, key_name)
);
"""


def up(conn: sqlite3.Connection) -> None:
    for statement in _DDL.split(";"):
        stmt = statement.strip()
        if stmt:
            conn.execute(stmt)
