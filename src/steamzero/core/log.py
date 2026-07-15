# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Logging estruturado JSONL (ADR-0011, SR-13/14/20).

- Uma linha JSON por evento; campos obrigatórios ts/level/event/correlationId.
- ``operationId``/``jobId`` propagados por ``bind`` (rastreabilidade fim-a-fim).
- Segredos (``Secret``) mascarados recursivamente antes de serializar (SR-13);
  conteúdo protegido nunca é logado (SR-14 — responsabilidade do chamador).
- Arquivo 0600 (via core.fs.AppendWriter); rotação por tamanho.
- Fonte de verdade do suporte é o JSONL; a UI usa o event bus, não parseia log.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from steamzero.core import fs, ids, paths
from steamzero.core.secret import MASK, Secret

_LEVELS = {"debug": 10, "info": 20, "warning": 30, "error": 40}
_DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MiB


def new_correlation_id() -> str:
    """Novo correlationId (ULID) para amarrar uma cadeia de operações."""
    return ids.new_ulid()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def sanitize(obj: Any) -> Any:
    """Mascara ``Secret`` recursivamente em dict/list/tuple; demais tipos intactos."""
    if isinstance(obj, Secret):
        return MASK
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize(v) for v in obj]
    return obj


class StructuredLogger:
    """Logger JSONL com contexto vinculável (correlationId, operationId, jobId)."""

    def __init__(
        self,
        path: Path,
        *,
        correlation_id: str,
        context: dict[str, Any] | None = None,
        min_level: str = "info",
        max_bytes: int = _DEFAULT_MAX_BYTES,
    ) -> None:
        self._path = path
        self._correlation_id = correlation_id
        self._context = dict(context or {})
        if min_level not in _LEVELS:
            raise ValueError(f"nível inválido: {min_level}")
        self._min = _LEVELS[min_level]
        self._max_bytes = max_bytes

    @property
    def path(self) -> Path:
        return self._path

    @property
    def correlation_id(self) -> str:
        return self._correlation_id

    def bind(self, **context: Any) -> StructuredLogger:
        """Retorna um logger-filho com contexto adicional (ex.: operationId)."""
        merged = {**self._context, **context}
        # min_level como nome novamente
        name = next(k for k, v in _LEVELS.items() if v == self._min)
        return StructuredLogger(
            self._path,
            correlation_id=self._correlation_id,
            context=merged,
            min_level=name,
            max_bytes=self._max_bytes,
        )

    def _emit(self, level: str, event: str, fields: dict[str, Any]) -> None:
        if _LEVELS[level] < self._min:
            return
        record: dict[str, Any] = {
            "ts": _now_iso(),
            "level": level,
            "event": event,
            "correlationId": self._correlation_id,
        }
        record.update(sanitize(self._context))
        record.update(sanitize(fields))
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        self._rotate_if_needed()
        with fs.AppendWriter(self._path) as writer:
            writer.write_line(line, fsync=level == "error")

    def _rotate_if_needed(self) -> None:
        if self._path.exists() and self._path.stat().st_size >= self._max_bytes:
            fs.rotate_log(self._path)

    def debug(self, event: str, **fields: Any) -> None:
        self._emit("debug", event, fields)

    def info(self, event: str, **fields: Any) -> None:
        self._emit("info", event, fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._emit("warning", event, fields)

    def error(self, event: str, **fields: Any) -> None:
        self._emit("error", event, fields)


def get_logger(
    *, correlation_id: str | None = None, min_level: str = "info", path: Path | None = None
) -> StructuredLogger:
    """Logger padrão apontando para ``logs/core.jsonl`` (ou ``path`` em testes)."""
    return StructuredLogger(
        path or paths.core_log(),
        correlation_id=correlation_id or new_correlation_id(),
        min_level=min_level,
    )
