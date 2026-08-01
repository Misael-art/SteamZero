# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Persistência de health dos providers de mídia no state.db (G28).

Usa a tabela ``scraping_provider_status`` (m0007) estendida por m0015 com
``last_error_code``, ``last_error_category`` e ``state``. Só códigos/categorias
estáveis e timestamps UTC ISO são gravados — nunca segredos ou detalhes.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from steamzero.core.errors import provider_error_category
from steamzero.domain.provider_health import (
    CIRCUIT_OPEN_THRESHOLD,
    ProviderHealth,
    ProviderHealthStorePort,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class StateStoreProviderHealthAdapter(ProviderHealthStorePort):
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record_success(self, provider: str, *, byte_count: int = 0) -> None:
        now = _now_iso()
        self._conn.execute(
            """
            INSERT INTO scraping_provider_status
              (provider, last_ok, total_requests, total_bytes, consecutive_failures,
               error_count, state, last_error_code, last_error_category)
            VALUES (?,?,1,?,0,0,'active',NULL,NULL)
            ON CONFLICT(provider) DO UPDATE SET
              last_ok=excluded.last_ok,
              total_requests=total_requests+1,
              total_bytes=total_bytes+excluded.total_bytes,
              consecutive_failures=0,
              error_count=0,
              state='active',
              last_error_code=NULL,
              last_error_category=NULL,
              circuit_open_since=NULL
            """,
            (provider, now, byte_count),
        )
        self._conn.commit()

    def record_failure(self, provider: str, *, error_code: str) -> None:
        now = _now_iso()
        category = provider_error_category(error_code)
        row = self._conn.execute(
            "SELECT consecutive_failures FROM scraping_provider_status WHERE provider=?",
            (provider,),
        ).fetchone()
        failures = int(row["consecutive_failures"]) + 1 if row is not None else 1
        state = "inactive" if failures >= CIRCUIT_OPEN_THRESHOLD else "active"
        circuit_open_since = now if failures == CIRCUIT_OPEN_THRESHOLD else None
        self._conn.execute(
            """
            INSERT INTO scraping_provider_status
              (provider, last_error, last_error_code, last_error_category,
               error_count, consecutive_failures, circuit_open_since,
               total_requests, state)
            VALUES (?,?,?,?,1,?,?,1,?)
            ON CONFLICT(provider) DO UPDATE SET
              last_error=excluded.last_error,
              last_error_code=excluded.last_error_code,
              last_error_category=excluded.last_error_category,
              error_count=error_count+1,
              consecutive_failures=excluded.consecutive_failures,
              circuit_open_since=COALESCE(
                excluded.circuit_open_since, scraping_provider_status.circuit_open_since),
              total_requests=total_requests+1,
              state=excluded.state
            """,
            (provider, now, error_code, category, failures, circuit_open_since, state),
        )
        self._conn.commit()

    def list_all(self) -> list[ProviderHealth]:
        rows = self._conn.execute(
            "SELECT * FROM scraping_provider_status ORDER BY provider"
        ).fetchall()
        return [self._row_to_health(row) for row in rows]

    def load(self, provider: str) -> ProviderHealth | None:
        row = self._conn.execute(
            "SELECT * FROM scraping_provider_status WHERE provider=?", (provider,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_health(row)

    @staticmethod
    def _row_to_health(row: sqlite3.Row) -> ProviderHealth:
        return ProviderHealth(
            provider=str(row["provider"]),
            state=str(row["state"]),
            last_ok=row["last_ok"],
            last_error=row["last_error"],
            last_error_code=row["last_error_code"],
            last_error_category=row["last_error_category"],
            error_count=int(row["error_count"] or 0),
            consecutive_failures=int(row["consecutive_failures"] or 0),
            circuit_open_since=row["circuit_open_since"],
            total_requests=int(row["total_requests"] or 0),
        )
