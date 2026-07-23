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
    m0007_scraping_cache,
    m0008_switch_mods,
    m0009_switch_cheats,
    m0010_switch_media,
    m0011_media_hub,
    m0012_media_read_model,
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
    (7, m0007_scraping_cache.up),
    (8, m0008_switch_mods.up),
    (9, m0009_switch_cheats.up),
    (10, m0010_switch_media.up),
    (11, m0011_media_hub.up),
    (12, m0012_media_read_model.up),
]

LATEST = max(v for v, _ in MIGRATIONS)
