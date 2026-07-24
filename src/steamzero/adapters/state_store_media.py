from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from steamzero.domain.switch_media import GameMediaState, GameMediaStorePort


class StateStoreGameMediaAdapter(GameMediaStorePort):
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def load(self, game_id: str) -> GameMediaState | None:
        row = self._conn.execute(
            "SELECT * FROM switch_game_media WHERE game_id = ?", (game_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_state(row)

    def save(self, state: GameMediaState) -> None:
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """INSERT OR REPLACE INTO switch_game_media
               (game_id, title_id, title, media_source, media_kind, media_path,
                previous_media_path, developer, version, languages,
                metadata_state, reason, checked_at,
                selected_candidate_idx, candidate_json, master_state,
                optimized_state, steam_view_state, steam_appid,
                steam_artwork_json, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                state.game_id,
                state.title_id,
                state.title,
                state.media_source,
                state.media_kind,
                state.media_path,
                state.previous_media_path,
                state.developer,
                state.version,
                state.languages,
                state.metadata_state,
                state.reason,
                state.checked_at,
                state.selected_candidate_idx,
                json.dumps(state.candidates),
                state.master_state,
                state.optimized_state,
                state.steam_view_state,
                state.steam_appid,
                json.dumps(state.steam_artwork_kinds),
                now,
            ),
        )
        self._conn.commit()

    def list_all(self) -> list[GameMediaState]:
        rows = self._conn.execute("SELECT * FROM switch_game_media ORDER BY title").fetchall()
        return [self._row_to_state(r) for r in rows]

    def delete(self, game_id: str) -> None:
        self._conn.execute("DELETE FROM switch_game_media WHERE game_id = ?", (game_id,))
        self._conn.commit()

    def save_candidate_selection(self, game_id: str, candidate_idx: int, media_kind: str) -> None:
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """UPDATE switch_game_media
               SET selected_candidate_idx = ?, media_kind = ?, updated_at = ?
               WHERE game_id = ?""",
            (candidate_idx, media_kind, now, game_id),
        )
        self._conn.commit()

    def clear_selection(self, game_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """UPDATE switch_game_media
               SET selected_candidate_idx = -1, candidate_json = '[]',
                   updated_at = ?
               WHERE game_id = ?""",
            (now, game_id),
        )
        self._conn.commit()

    @staticmethod
    def _row_to_state(row: sqlite3.Row) -> GameMediaState:
        candidates = json.loads(row["candidate_json"]) if row["candidate_json"] else []
        return GameMediaState(
            game_id=row["game_id"],
            title_id=row["title_id"],
            title=row["title"],
            media_source=row["media_source"],
            media_kind=row["media_kind"],
            media_path=row["media_path"],
            previous_media_path=row["previous_media_path"],
            developer=row["developer"],
            version=row["version"],
            languages=row["languages"],
            metadata_state=row["metadata_state"],
            reason=row["reason"],
            checked_at=row["checked_at"],
            selected_candidate_idx=row["selected_candidate_idx"],
            candidates=candidates,
            candidate_count=len(candidates),
            master_state=row["master_state"],
            optimized_state=row["optimized_state"],
            steam_view_state=row["steam_view_state"],
            steam_appid=row["steam_appid"],
            steam_artwork_kinds=(
                json.loads(row["steam_artwork_json"]) if row["steam_artwork_json"] else []
            ),
        )
