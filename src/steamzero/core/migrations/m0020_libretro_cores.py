# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Permite persistir cores Libretro e sua origem em arquivo pinado.

SQLite não permite ampliar um ``CHECK`` in-place. A tabela é recriada mantendo
todas as colunas trazidas por m0019, para que uma instalação antiga preserve o
vínculo de operação de reparo ao ganhar o quarto tipo de componente.
"""

from __future__ import annotations

import sqlite3


def up(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE component_new (
          id            TEXT PRIMARY KEY,
          adapter_id    TEXT NOT NULL,
          kind          TEXT NOT NULL CHECK (kind IN ('emulator','frontend','tool','core')),
          version       TEXT,
          origin        TEXT CHECK (origin IN ('flatpak','appimage','native','archive')),
          state         TEXT NOT NULL CHECK (state IN (
                          'installed','degraded','missing','staged',
                          'outdated','repairing','retired')),
          verified_at   TEXT,
          manifest_hash TEXT,
          operation_id  TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO component_new
          (id, adapter_id, kind, version, origin, state, verified_at,
           manifest_hash, operation_id)
        SELECT id, adapter_id, kind, version, origin, state, verified_at,
               manifest_hash, operation_id
        FROM component
        """
    )
    conn.execute("DROP TABLE component")
    conn.execute("ALTER TABLE component_new RENAME TO component")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_component_operation ON component(operation_id)")
