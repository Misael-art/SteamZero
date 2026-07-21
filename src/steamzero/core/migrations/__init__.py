# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Migrações de schema do State Store (MIGRATION-VERSIONING).

Cada migração: função ``(conn) -> None`` idempotente por guarda de versão
(``PRAGMA user_version``). ``0001`` estabelece o schema baseline (STATE-MODEL).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from steamzero.core.migrations import (
    m0001_baseline,
    m0002_desktop_experience,
    m0003_gameplay_runtime,
    m0004_game_session,
    m0005_session_environment,
    m0006_keys_firmware,
)

Migration = Callable[[sqlite3.Connection], None]

#: Lista ordenada (versão, função). LATEST = maior versão.
MIGRATIONS: list[tuple[int, Migration]] = [
    (1, m0001_baseline.up),
    (2, m0002_desktop_experience.up),
    (3, m0003_gameplay_runtime.up),
    (4, m0004_game_session.up),
    (5, m0005_session_environment.up),
    (6, m0006_keys_firmware.up),
]

LATEST = max(v for v, _ in MIGRATIONS)
