# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Migração 0006 — metadados de keys/firmware importados (WI-1, ADR-0021).

Estende ``firmware_key_item`` (baseline) com a revisão/versão derivada do
arquivo importado e o relpath no store central. Segredo: nunca há coluna de
hash completo nem conteúdo — apenas ``hash_truncated`` (SR-14), já no baseline.
"""

from __future__ import annotations

import sqlite3


def up(conn: sqlite3.Connection) -> None:
    # ALTER TABLE ADD COLUMN é aditivo; linhas antigas recebem NULL.
    conn.execute("ALTER TABLE firmware_key_item ADD COLUMN keyset TEXT")
    conn.execute("ALTER TABLE firmware_key_item ADD COLUMN revision INTEGER")
    conn.execute("ALTER TABLE firmware_key_item ADD COLUMN version TEXT")
    conn.execute("ALTER TABLE firmware_key_item ADD COLUMN relpath TEXT")
    conn.execute("ALTER TABLE firmware_key_item ADD COLUMN last_validated TEXT")
