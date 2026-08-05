# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Vínculo durável do estado ``repairing`` à operação de reparo (Etapa 1).

m0017 ampliou o vocabulário de ``component.state`` para incluir ``repairing``,
mas sem operação vinculada um reparo interrompido fica indistinguível de um
deployment corrompido — foi o que tornou o G25 difícil de ler.

``component.operation_id`` liga o marcador ao arquivo de operação durável
(``component-operations/<operationId>.json``, schemaVersion 2) que o lifecycle
grava antes de qualquer efeito. O recovery reconcilia o par: marcador sem
operação válida é órfão e volta ao estado observado; operação em ``applying``
mantém o ``repairing`` exposto.

Coluna adicionada por ``ALTER TABLE`` (SQLite não altera CHECK por ALTER, mas
novas colunas são permitidas) por cima da tabela recriada em m0017. Índice leve
para reconciliação por adapter.
"""

from __future__ import annotations

import sqlite3


def up(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE component ADD COLUMN operation_id TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_component_operation ON component(operation_id)")
