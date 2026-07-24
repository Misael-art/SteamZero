# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Read model limitado de playtime, recentes e “Continuar jogando”."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from steamzero.api import contracts
from steamzero.core.errors import SteamZeroError
from steamzero.core.session_state import ACTIVE_SESSION_STATES
from steamzero.core.state import StateStore

StoreFactory = Callable[[], StateStore]
_INTERRUPTED_CODES = frozenset({"E-SESSION-INTERRUPTED", "E-SESSION-RESUME-DEGRADED"})
_SOURCES = frozenset({"steam", "emulation", "unknown"})


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _decode_metadata(raw: object) -> dict[str, Any]:
    try:
        value = json.loads(str(raw or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _encode_cursor(started_at: str, game_id: str) -> str:
    raw = json.dumps([started_at, game_id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> tuple[str | None, str | None]:
    if cursor is None:
        return None, None
    if not cursor or len(cursor) > 1024 or "\x00" in cursor:
        raise SteamZeroError("E-API-SCHEMA", detail="cursor de playtime inválido")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.b64decode(padded, altchars=b"-_", validate=True))
    except (ValueError, json.JSONDecodeError) as exc:
        raise SteamZeroError("E-API-SCHEMA", detail="cursor de playtime inválido") from exc
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise SteamZeroError("E-API-SCHEMA", detail="cursor de playtime inválido")
    try:
        datetime.fromisoformat(value[0])
    except ValueError as exc:
        raise SteamZeroError("E-API-SCHEMA", detail="cursor de playtime inválido") from exc
    return value[0], value[1]


class PlaytimeCatalog:
    """Projeta sessões canônicas sem observar processos ou inventar ownership."""

    def __init__(self, store_factory: StoreFactory = StateStore) -> None:
        self._store_factory = store_factory

    def list(self, *, limit: int = 20, cursor: str | None = None) -> dict[str, Any]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise SteamZeroError("E-API-SCHEMA", detail="limit deve estar entre 1 e 100")
        before_started_at, before_game_id = _decode_cursor(cursor)
        with self._store_factory() as store:
            store.migrate()
            rows, has_more = store.list_playtime_games(
                limit=limit,
                before_started_at=before_started_at,
                before_game_id=before_game_id,
            )
            total = store.playtime_total_seconds()
        games = [self._game(row) for row in rows]
        next_cursor = (
            _encode_cursor(str(rows[-1]["last_started_at"]), str(rows[-1]["game_id"]))
            if has_more and rows
            else None
        )
        payload = {
            "schemaVersion": 1,
            "generatedAt": _now_iso(),
            "totalPlayedSeconds": total,
            "games": games,
            "page": {
                "limit": limit,
                "hasMore": has_more,
                "nextCursor": next_cursor,
            },
        }
        contracts.validate(payload, "feat-playtime-v1.schema.json")
        return payload

    def get(self, game_id: str) -> dict[str, Any]:
        self._validate_game_id(game_id)
        with self._store_factory() as store:
            store.migrate()
            row = store.playtime_game(game_id)
        if row is None:
            raise SteamZeroError("E-API-SCHEMA", detail="jogo sem sessões registradas")
        payload = {
            "schemaVersion": 1,
            "generatedAt": _now_iso(),
            "game": self._game(row),
        }
        contracts.validate(payload, "feat-playtime-v1.schema.json")
        return payload

    @classmethod
    def _game(cls, row: dict[str, Any]) -> dict[str, Any]:
        metadata = _decode_metadata(row.get("latest_metadata_json"))
        source = metadata.get("source", "unknown")
        if source not in _SOURCES:
            source = "unknown"
        title_value = row.get("game_title") or metadata.get("title")
        title = str(title_value).strip()[:160] if title_value else f"Jogo {row['game_id']}"
        state = str(row["latest_state"])
        failure_code = row.get("latest_failure_code")
        if state in ACTIVE_SESSION_STATES:
            continue_state = "in-progress"
        elif failure_code in _INTERRUPTED_CODES:
            continue_state = "interrupted"
        elif row.get("game_state") in {"unavailable", "quarantined", "incomplete"}:
            continue_state = "unavailable"
        else:
            continue_state = "ready"
        action = cls._action(
            game_id=str(row["game_id"]),
            source=str(source),
            continue_state=continue_state,
        )
        return {
            "gameId": str(row["game_id"]),
            "title": title,
            "coverUrl": str(metadata.get("coverUrl") or "")[:4096],
            "source": source,
            "platformId": row.get("platform_id") or metadata.get("platformId"),
            "playedSeconds": int(row.get("played_seconds") or 0),
            "sessionCount": int(row.get("session_count") or 0),
            "lastPlayedAt": str(row["last_started_at"]),
            "continueState": continue_state,
            "latestSession": {
                "sessionId": str(row["latest_session_id"]),
                "state": state,
                "startedAt": str(row["latest_started_at"]),
                "updatedAt": str(row["latest_updated_at"]),
                "finishedAt": row.get("latest_finished_at"),
                "playedSeconds": int(row.get("latest_played_seconds") or 0),
                "durationSource": str(row.get("latest_duration_source") or "unavailable"),
                "failureCode": failure_code,
            },
            "action": action,
        }

    @staticmethod
    def _action(*, game_id: str, source: str, continue_state: str) -> dict[str, Any]:
        if continue_state == "in-progress":
            return {
                "kind": "detail",
                "target": game_id,
                "label": "Em andamento",
                "enabled": False,
                "reason": "A sessão ainda está ativa; verifique seu estado antes de relançar.",
            }
        if source == "steam" and game_id.isdigit():
            return {
                "kind": "steam-continue",
                "target": game_id,
                "label": "Continuar",
                "enabled": True,
                "reason": "",
            }
        if source == "emulation":
            return {
                "kind": "emulation-continue",
                "target": game_id,
                "label": "Continuar",
                "enabled": continue_state != "unavailable",
                "reason": (
                    "O jogo não está disponível na biblioteca."
                    if continue_state == "unavailable"
                    else ""
                ),
            }
        return {
            "kind": "detail",
            "target": game_id,
            "label": "Origem desconhecida",
            "enabled": False,
            "reason": "A sessão legada não identifica um launcher seguro.",
        }

    @staticmethod
    def _validate_game_id(game_id: str) -> None:
        if not isinstance(game_id, str) or not game_id or len(game_id) > 160 or "\x00" in game_id:
            raise SteamZeroError("E-API-SCHEMA", detail="gameId inválido")
