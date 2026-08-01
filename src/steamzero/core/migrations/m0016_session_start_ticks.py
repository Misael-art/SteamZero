# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""start_ticks da sessão de jogo (identidade efêmera PID/start-time, GAP-G30).

A sessão ativa guarda o PID do emulador desde m0004. A coluna ``start_ticks``
recebe o start-time (campo 22 de /proc/<pid>/stat) registrado no momento do
spawn: junto do PID forma a identidade efêmera que permite ao probe de
recursos rejeitar PID reutilizado sem herdar identidade antiga. Sessões
criadas antes desta migração ficam com ``NULL`` e o probe verifica o marcador
``STEAMZERO_CLASS`` no environ como segunda evidência. Nenhum command line ou
caminho é persistido.
"""

from __future__ import annotations

import sqlite3


def up(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE game_session ADD COLUMN start_ticks INTEGER")
