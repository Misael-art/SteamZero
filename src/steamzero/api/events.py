# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato paginado e reconectável para o log de eventos persistido."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from steamzero.core.state import StateStore

SYSTEM_CORRELATION_ID = "00000000000000000000000000"
MAX_PAGE_SIZE = 256
DEFAULT_PAGE_SIZE = 64

PUBLIC_EVENT_KINDS = (
    "job.progress",
    "job.state",
    "operation.state",
    "session.state",
    "session.environment",
    "session.resume",
    "entity.changed",
    "alert",
)
JOB_EVENT_KINDS = ("job.progress", "job.state")
OPERATION_EVENT_KINDS = ("operation.state",)
JOB_TERMINAL_STATES = frozenset({"completed", "cancelled", "rolled-back", "rollback-failed"})
OPERATION_TERMINAL_STATES = frozenset(
    {"committed", "rolled-back", "rollback-failed", "recovery-required"}
)


@dataclass(frozen=True)
class EventPage:
    events: tuple[dict[str, Any], ...]
    cursor: str
    has_more: bool
    limit: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": list(self.events),
            "count": len(self.events),
            "cursor": self.cursor,
            "hasMore": self.has_more,
            "limit": self.limit,
        }


def parse_event_cursor(value: str | None, *, default: int = 0) -> int:
    if value is None:
        return default
    if not value.isascii() or not value.isdecimal() or len(value) > 19:
        raise ValueError("cursor de evento inválido")
    cursor = int(value)
    if cursor < 0 or cursor > 9_223_372_036_854_775_807:
        raise ValueError("cursor de evento fora do intervalo")
    return cursor


def event_page(
    store: StateStore,
    *,
    cursor: str | None,
    limit: int = DEFAULT_PAGE_SIZE,
    kinds: tuple[str, ...] = (),
    entities: tuple[str, ...] = (),
) -> EventPage:
    after_seq = parse_event_cursor(cursor)
    rows, has_more = store.events_page(
        after_seq=after_seq,
        limit=limit,
        kinds=list(kinds) or None,
        entities=list(entities) or None,
    )
    events = tuple(_public_event(store, row) for row in rows)
    next_cursor = str(events[-1]["seq"]) if events else str(after_seq)
    return EventPage(events=events, cursor=next_cursor, has_more=has_more, limit=limit)


def follow_events(
    store: StateStore,
    *,
    cursor: str | None,
    kinds: tuple[str, ...],
    entities: tuple[str, ...] = (),
    limit: int = DEFAULT_PAGE_SIZE,
    poll_interval: float = 0.25,
    idle_timeout: float | None = None,
    terminal_states: frozenset[str] = frozenset(),
    stop_requested: Callable[[], bool] | None = None,
) -> Iterator[dict[str, Any]]:
    """Entrega eventos incrementalmente sem acumular histórico em memória."""
    if poll_interval < 0:
        raise ValueError("poll_interval não pode ser negativo")
    if idle_timeout is not None and idle_timeout < 0:
        raise ValueError("idle_timeout não pode ser negativo")
    current = str(store.latest_event_seq()) if cursor is None else cursor
    last_activity = time.monotonic()
    while True:
        if stop_requested is not None and stop_requested():
            return
        page = event_page(
            store,
            cursor=current,
            limit=limit,
            kinds=kinds,
            entities=entities,
        )
        if page.events:
            last_activity = time.monotonic()
            for event in page.events:
                yield event
                if terminal_states and event.get("state") in terminal_states:
                    return
            current = page.cursor
            if page.has_more:
                continue
        if idle_timeout is not None and time.monotonic() - last_activity >= idle_timeout:
            return
        time.sleep(poll_interval)


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    encoded = row.get("payload_json")
    if not isinstance(encoded, str):
        return {}
    try:
        value = json.loads(encoded)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _entity_id(row: dict[str, Any], prefix: str) -> str | None:
    entity = row.get("entity")
    if not isinstance(entity, str):
        return None
    marker = prefix + ":"
    if entity.startswith(marker) and len(entity) > len(marker):
        return entity[len(marker) :]
    return entity if ":" not in entity and entity else None


def _job_correlation(store: StateStore, job_id: str | None) -> str:
    if job_id is None:
        return SYSTEM_CORRELATION_ID
    job = store.get_job(job_id)
    if job is None:
        return SYSTEM_CORRELATION_ID
    correlation = job.get("correlation_id")
    return correlation if isinstance(correlation, str) and correlation else SYSTEM_CORRELATION_ID


def _public_event(store: StateStore, row: dict[str, Any]) -> dict[str, Any]:
    kind = str(row["kind"])
    payload = _payload(row)
    job_id = _entity_id(row, "job") if kind.startswith("job.") else None
    correlation = payload.get("correlationId")
    event: dict[str, Any] = {
        "seq": int(row["seq"]),
        "ts": str(row["ts"]),
        "kind": kind,
        "correlationId": (
            correlation
            if isinstance(correlation, str) and correlation
            else _job_correlation(store, job_id)
        ),
    }
    if job_id is not None:
        event["jobId"] = job_id
    operation_id = _entity_id(row, "operation") if kind == "operation.state" else None
    if operation_id is not None:
        event["operationId"] = operation_id
    if kind == "job.progress":
        event["progress"] = {
            key: payload.get(key)
            for key in ("stage", "current", "total", "unit", "rate", "currentItem")
            if key in payload
        }
    elif kind in {"job.state", "operation.state", "session.state"}:
        state = payload.get("state")
        if isinstance(state, str):
            event["state"] = state
    if kind == "session.state":
        session_id = _entity_id(row, "session")
        if session_id is not None:
            event["sessionId"] = session_id
        game_id = payload.get("gameId")
        if isinstance(game_id, str):
            event["gameId"] = game_id
    elif kind == "session.environment":
        digest = payload.get("digest")
        changes = payload.get("changes")
        if isinstance(digest, str):
            event["digest"] = digest
        if isinstance(changes, list) and all(isinstance(item, str) for item in changes):
            event["changes"] = changes
    elif kind == "session.resume":
        suspended = payload.get("suspendedSeconds")
        if isinstance(suspended, (int, float)) and not isinstance(suspended, bool):
            event["suspendedSeconds"] = suspended
    elif kind == "alert" and isinstance(payload.get("error"), dict):
        event["error"] = payload["error"]
    return event
