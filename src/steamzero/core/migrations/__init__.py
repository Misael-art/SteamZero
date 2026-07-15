# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Migrações de schema do State Store (MIGRATION-VERSIONING).

Cada migração: função ``(conn) -> None`` idempotente por guarda de versão
(``PRAGMA user_version``). ``0001`` estabelece o schema baseline (STATE-MODEL).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from steamzero.core.migrations import m0001_baseline

Migration = Callable[[sqlite3.Connection], None]

#: Lista ordenada (versão, função). LATEST = maior versão.
MIGRATIONS: list[tuple[int, Migration]] = [
    (1, m0001_baseline.up),
]

LATEST = max(v for v, _ in MIGRATIONS)
