# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Vocabulário completo de estados do componente (Etapa 1 — lifecycle).

A baseline restringia ``component.state`` a
``('installed','degraded','missing','staged')``. Faltavam três estados que o
lifecycle precisa distinguir para não mentir:

- ``outdated``: deployment íntegro, porém a fonte fixada avançou. Antes isso
  virava ``degraded``, e foi o que fez o Citron aparecer quebrado no host
  quando o que mudara era só o pin — o usuário lê "degradado" e conclui
  corrupção onde bastava atualizar.
- ``repairing``: reparo em curso. Sem ele, uma interrupção no meio do reparo
  fica indistinguível de um deployment corrompido, e o recovery não sabe se
  retoma ou reverte.
- ``retired``: adapter sem fonte suportada, removido do conjunto ativo por
  decisão registrada. Diferente de ``missing``, que significa "não instalado,
  mas instalável".

SQLite não altera CHECK constraint por ``ALTER TABLE``: a tabela é recriada com
o vocabulário novo e as linhas são copiadas. Nenhum estado existente muda de
valor — a migração só amplia o que passa a ser aceito.
"""

from __future__ import annotations

import sqlite3


def up(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE component_new (
          id            TEXT PRIMARY KEY,
          adapter_id    TEXT NOT NULL,
          kind          TEXT NOT NULL CHECK (kind IN ('emulator','frontend','tool')),
          version       TEXT,
          origin        TEXT CHECK (origin IN ('flatpak','appimage','native')),
          state         TEXT NOT NULL CHECK (state IN (
                          'installed','degraded','missing','staged',
                          'outdated','repairing','retired')),
          verified_at   TEXT,
          manifest_hash TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO component_new
          (id, adapter_id, kind, version, origin, state, verified_at, manifest_hash)
        SELECT id, adapter_id, kind, version, origin, state, verified_at, manifest_hash
        FROM component
        """
    )
    conn.execute("DROP TABLE component")
    conn.execute("ALTER TABLE component_new RENAME TO component")
