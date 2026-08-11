# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Cache SQLite de scraping: evita consultas repetidas a provedores.

Duas camadas:
1. ``scraping_cache_entry`` — metadados da consulta (url, etag, validade).
2. ``scraping_media`` — artefatos baixados com hash, dimensões, estado.

O cache é endereçado por ``lookup_key`` (hash da ROM, title_id ou nome
normalizado) + ``media_kind``. Uma entrada expirada ou com ``error`` não nulo
pode ser refeita.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from steamzero.core import fs, ids, paths
from steamzero.ports import MediaCandidate


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class CacheEntry:
    """Entrada do cache de scraping (metadados da consulta + artefato).

    ``cached_at`` e ``expires_at`` em ISO 8601. ``error`` preenchido significa
    que a consulta original falhou; ``http_status`` guarda o código HTTP.
    """

    id: str
    game_id: str | None
    platform_slug: str
    lookup_key: str
    lookup_method: str
    provider: str
    media_kind: str
    url: str
    license: str
    attribution: str
    etag: str | None
    region: str | None
    language: str | None
    width: int | None
    height: int | None
    confidence: float
    http_status: int | None
    error: str | None
    last_checked: str
    expires_at: str | None


class ScrapingCache:
    """Cache persistente de scraping em SQLite.

    Usa o mesmo state.db do SteamZero (via conexão injetada) ou um path
    independente para isolamento em testes.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._path = db_path or (paths.state_home() / "scraping-cache.db")
        fs.ensure_dir(self._path.parent)
        self._conn = sqlite3.connect(self._path, isolation_level=None)
        self._closed = False
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA busy_timeout=5000")
        # A troca para WAL exige lock exclusivo e não espera busy handler;
        # em abertura concorrente do mesmo arquivo (processos paralelos) a
        # primeira conexão vence e as demais esperam em retry limitado.
        for _attempt in range(20):
            try:
                self._conn.execute("PRAGMA journal_mode=WAL")
                break
            except sqlite3.OperationalError:
                time.sleep(0.05)
        else:
            raise
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scraping_cache_entry (
              id              TEXT PRIMARY KEY,
              game_id         TEXT,
              platform_slug   TEXT NOT NULL DEFAULT '',
              lookup_key      TEXT NOT NULL,
              lookup_method   TEXT NOT NULL,
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
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scraping_media (
              id                TEXT PRIMARY KEY,
              cache_entry_id    TEXT NOT NULL REFERENCES scraping_cache_entry(id),
              game_id           TEXT NOT NULL,
              media_kind        TEXT NOT NULL,
              file_hash         TEXT NOT NULL,
              size              INTEGER NOT NULL,
              width             INTEGER,
              height            INTEGER,
              mime_type         TEXT,
              state             TEXT NOT NULL DEFAULT 'staged',
              created_at        TEXT NOT NULL,
              committed_at      TEXT
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scraping_provider_status (
              provider              TEXT PRIMARY KEY,
              last_ok               TEXT,
              last_error            TEXT,
              error_count           INTEGER DEFAULT 0,
              consecutive_failures  INTEGER DEFAULT 0,
              circuit_open_since    TEXT,
              total_requests        INTEGER DEFAULT 0,
              total_bytes           INTEGER DEFAULT 0
            )
            """
        )
        # Uma falha por (chave, tipo, provider): registrar a mesma falha de novo
        # atualiza a linha em vez de acumular entradas mortas.
        self._conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_scraping_error_dedup
            ON scraping_cache_entry(lookup_key, media_kind, provider)
            WHERE error IS NOT NULL
            """
        )

    @contextmanager
    def atomic(self) -> Iterator[None]:
        """Transação explícita: publica a escrita só no COMMIT.

        Uma exceção dentro do bloco faz ROLLBACK — nenhuma entrada parcial
        (ex.: entry sem media) é publicada.
        """
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    # -- cache entries -------------------------------------------------------

    def get_cached(
        self,
        lookup_key: str,
        media_kind: str,
        provider: str,
        *,
        max_age_hours: int = 24,
    ) -> CacheEntry | None:
        """Retorna entrada do cache se existir e não expirou.

        ``provider="*"`` casa com qualquer provider (cache-first do dispatcher);
        qualquer outro valor filtra pelo provider exato.
        """
        cutoff = (datetime.now(UTC) - timedelta(hours=max_age_hours)).isoformat()
        if provider == "*":
            row = self._conn.execute(
                """
                SELECT * FROM scraping_cache_entry
                WHERE lookup_key=? AND media_kind=?
                  AND last_checked > ? AND error IS NULL
                ORDER BY last_checked DESC LIMIT 1
                """,
                (lookup_key, media_kind, cutoff),
            ).fetchone()
        else:
            row = self._conn.execute(
                """
                SELECT * FROM scraping_cache_entry
                WHERE lookup_key=? AND media_kind=? AND provider=?
                  AND last_checked > ? AND error IS NULL
                ORDER BY last_checked DESC LIMIT 1
                """,
                (lookup_key, media_kind, provider, cutoff),
            ).fetchone()
        if row is None:
            return None
        return CacheEntry(**dict(row))

    def get_cached_by_game(
        self,
        game_id: str,
        media_kind: str,
        *,
        max_age_hours: int = 24,
    ) -> list[CacheEntry]:
        """Retorna todas as entradas de cache para um jogo + tipo de mídia."""
        cutoff = (datetime.now(UTC) - timedelta(hours=max_age_hours)).isoformat()
        rows = self._conn.execute(
            """
            SELECT * FROM scraping_cache_entry
            WHERE game_id=? AND media_kind=? AND last_checked > ? AND error IS NULL
            ORDER BY confidence DESC, last_checked DESC
            """,
            (game_id, media_kind, cutoff),
        ).fetchall()
        return [CacheEntry(**dict(r)) for r in rows]

    def save_cache_entry(
        self, candidate: MediaCandidate, identity_key: str, *, platform_slug: str = ""
    ) -> str:
        """Persiste um candidato no cache. Retorna o ID da entrada."""
        entry_id = ids.new_ulid()
        expires = candidate.expires_at or (datetime.now(UTC) + timedelta(days=7)).isoformat()
        self._conn.execute(
            """
            INSERT INTO scraping_cache_entry
              (id, game_id, platform_slug, lookup_key, lookup_method,
               provider, media_kind, url, license, attribution,
               etag, region, language, width, height, confidence,
               http_status, error, last_checked, expires_at)
            VALUES (?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?)
            """,
            (
                entry_id,
                candidate.hash or identity_key,
                platform_slug,
                identity_key,
                "fuzzy",
                candidate.provider,
                candidate.media_kind,
                candidate.url,
                candidate.license,
                candidate.attribution,
                candidate.etag,
                candidate.region,
                candidate.language,
                candidate.width,
                candidate.height,
                candidate.confidence,
                None,
                None,
                _now_iso(),
                expires,
            ),
        )
        return entry_id

    def mark_error(
        self,
        lookup_key: str,
        media_kind: str,
        provider: str,
        error_code: str | None,
        http_status: int | None = None,
        *,
        platform_slug: str = "",
    ) -> None:
        """Registra falha de consulta para evitar retentativas imediatas.

        Idempotente por (chave, tipo, provider): repetir a mesma falha atualiza
        a mesma linha, sem acumular entradas mortas.
        """
        self._conn.execute(
            """
            INSERT INTO scraping_cache_entry
              (id, platform_slug, lookup_key, lookup_method, provider, media_kind,
               url, error, http_status, last_checked, confidence)
            VALUES (?,?,?,?,?, ?,?,?,?,?, ?)
            ON CONFLICT(lookup_key, media_kind, provider) WHERE error IS NOT NULL
            DO UPDATE SET
              error=excluded.error, http_status=excluded.http_status,
              last_checked=excluded.last_checked
            """,
            (
                ids.new_ulid(),
                platform_slug,
                lookup_key,
                "fuzzy",
                provider,
                media_kind,
                "",
                error_code,
                http_status,
                _now_iso(),
                0.0,
            ),
        )

    # -- media artifacts -----------------------------------------------------

    def save_media(
        self,
        cache_entry_id: str,
        game_id: str,
        media_kind: str,
        data: bytes,
        *,
        width: int | None = None,
        height: int | None = None,
        mime_type: str | None = None,
    ) -> str:
        """Registra um artefato baixado no cache. Retorna o ID do registro."""
        media_id = ids.new_ulid()
        file_hash = fs.hash_bytes(data, algo="sha256")
        self._conn.execute(
            """
            INSERT INTO scraping_media
              (id, cache_entry_id, game_id, media_kind,
               file_hash, size, width, height, mime_type, state,
               created_at)
            VALUES (?,?,?,?, ?,?,?,?,?,?, ?)
            """,
            (
                media_id,
                cache_entry_id,
                game_id,
                media_kind,
                file_hash,
                len(data),
                width,
                height,
                mime_type,
                "staged",
                _now_iso(),
            ),
        )
        return media_id

    def commit_media(self, media_id: str) -> None:
        """Marca um artefato como committed."""
        self._conn.execute(
            "UPDATE scraping_media SET state='committed', committed_at=? WHERE id=?",
            (_now_iso(), media_id),
        )

    def orphan_media(self, media_id: str) -> None:
        """Marca um artefato como órfão (descartado)."""
        self._conn.execute("UPDATE scraping_media SET state='orphaned' WHERE id=?", (media_id,))

    # -- provider status -----------------------------------------------------

    def record_success(self, provider: str, byte_count: int = 0) -> None:
        self._conn.execute(
            """
            INSERT INTO scraping_provider_status
              (provider, last_ok, total_requests, total_bytes, consecutive_failures)
            VALUES (?,?,1,?,0)
            ON CONFLICT(provider) DO UPDATE SET
              last_ok=excluded.last_ok, total_requests=total_requests+1,
              total_bytes=total_bytes+excluded.total_bytes,
              consecutive_failures=0, error_count=error_count
            """,
            (provider, _now_iso(), byte_count),
        )

    def record_failure(self, provider: str) -> None:
        self._conn.execute(
            """
            INSERT INTO scraping_provider_status
              (provider, last_error, error_count, consecutive_failures)
            VALUES (?,?,1,1)
            ON CONFLICT(provider) DO UPDATE SET
              last_error=excluded.last_error, error_count=error_count+1,
              consecutive_failures=consecutive_failures+1
            """,
            (provider, _now_iso()),
        )

    def circuit_is_open(self, provider: str, *, max_failures: int = 5) -> bool:
        """True se o provider está em circuit-breaker (falhas consecutivas)."""
        row = self._conn.execute(
            "SELECT consecutive_failures FROM scraping_provider_status WHERE provider=?",
            (provider,),
        ).fetchone()
        return row is not None and int(row["consecutive_failures"]) >= max_failures

    # -- maintenance ---------------------------------------------------------

    def prune_expired(self, *, older_than_days: int = 30) -> int:
        """Remove entradas expiradas. Retorna número de removidas."""
        cutoff = (datetime.now(UTC) - timedelta(days=older_than_days)).isoformat()
        cur = self._conn.execute(
            "DELETE FROM scraping_cache_entry WHERE last_checked < ?", (cutoff,)
        )
        return cur.rowcount

    @property
    def path(self) -> Path:
        return self._path

    def close(self) -> None:
        if self._closed:
            return
        self._conn.close()
        self._closed = True

    def __del__(self) -> None:
        with suppress(Exception):
            self.close()

    def __enter__(self) -> ScrapingCache:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
