from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from steamzero.adapters.state_store_media import StateStoreGameMediaAdapter
from steamzero.core import paths, transaction
from steamzero.domain.media_pipeline import MediaPipeline
from steamzero.domain.switch_media import GameMediaManager, GameMediaState, GameMediaStorePort


class _FakeStore(GameMediaStorePort):
    def __init__(self) -> None:
        self._data: dict[str, GameMediaState] = {}

    def load(self, game_id: str) -> GameMediaState | None:
        return self._data.get(game_id)

    def save(self, state: GameMediaState) -> None:
        self._data[state.game_id] = state

    def list_all(self) -> list[GameMediaState]:
        return list(self._data.values())

    def delete(self, game_id: str) -> None:
        self._data.pop(game_id, None)

    def save_candidate_selection(self, game_id: str, candidate_idx: int, media_kind: str) -> None:
        state = self._data.get(game_id)
        if state:
            state.selected_candidate_idx = candidate_idx
            state.media_kind = media_kind

    def clear_selection(self, game_id: str) -> None:
        state = self._data.get(game_id)
        if state:
            state.selected_candidate_idx = -1
            state.candidates = []
            state.candidate_count = 0


class _FakePipeline:
    def __init__(self) -> None:
        self._registry = _FakeRegistry()

    def collect(self, source, game_id, title_id, fingerprint, canonical_name, kind="box2d"):
        from steamzero.domain.media_pipeline import CollectionResult

        return CollectionResult(game_id=game_id, collected={kind: source})

    def collect_from_candidate(self, candidate, game_id, title_id, fingerprint, canonical_name):
        from steamzero.domain.media_pipeline import CollectionResult

        return CollectionResult(game_id=game_id, collected={"boxart": Path("fakepipeline.png")})

    def optimize(self, game_id, profile=None):
        from steamzero.domain.media_pipeline import OptimizeResult

        return OptimizeResult(game_id=game_id)

    def view_steam(self, game_id, steam_user_id, steam_appid):
        from steamzero.domain.media_pipeline import ViewResult

        return ViewResult(game_id=game_id)

    def unpublish_steam_plan(self, game_id, steam_user_id, steam_appid):
        return None

    def audit(self):
        from steamzero.domain.media_pipeline import AuditReport

        return AuditReport()

    def _find_optimized(self, game_id, profile):
        return None

    def get_registry_entry(self, game_id):
        return self._registry.get_entry(game_id)

    def find_optimized(self, game_id, profile):
        return self._find_optimized(game_id, profile)


class _FakeRegistry:
    def __init__(self):
        self.entries: dict[str, object] = {}

    def get_entry(self, game_id):
        return self.entries.get(game_id)


# =============================================================================
# Model
# =============================================================================


class TestGameMediaState:
    def test_minimal(self) -> None:
        state = GameMediaState(game_id="g1", title_id="0100", title="Game")
        assert state.media_source == "fallback"

    def test_with_candidates(self) -> None:
        state = GameMediaState(
            game_id="g1",
            title_id="0100",
            title="Game",
            candidates=[
                {
                    "url": "https://example.com/icon.jpg",
                    "mediaKind": "icon",
                    "provider": "test",
                    "confidence": 0.9,
                }
            ],
            candidate_count=1,
        )
        assert state.candidate_count == 1


# =============================================================================
# Store / resolve / custom / clear (via store directly, no pipeline)
# =============================================================================


class TestStoreResolveFallback:
    def test_store_and_load_custom(self, tmp_path: Path) -> None:
        store = _FakeStore()
        pipeline = _FakePipeline()
        manager = GameMediaManager(store, pipeline)
        art_path = tmp_path / "custom.jpg"
        art_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)
        store.save(
            GameMediaState(
                game_id="g1",
                title_id="0100",
                title="Game",
                media_source="custom",
                media_path=str(art_path),
            )
        )
        result = manager.resolve_effective_media("g1", "0100", "Game")
        assert result.media_source == "custom"

    def test_fallback_when_no_store(self, tmp_path: Path) -> None:
        store = _FakeStore()
        pipeline = _FakePipeline()
        manager = GameMediaManager(store, pipeline)
        result = manager.resolve_effective_media("g1", "0100", "Game")
        assert result.media_source == "fallback"

    def test_clear_media(self) -> None:
        store = _FakeStore()
        pipeline = _FakePipeline()
        manager = GameMediaManager(store, pipeline)
        store.save(
            GameMediaState(
                game_id="g1",
                title_id="0100",
                title="Game",
                media_source="scraper",
                media_path="/path/to/art.jpg",
            )
        )
        result = manager.clear_media("g1")
        assert result is not None
        assert result.media_source == "fallback"
        assert result.media_path is None
        assert result.previous_media_path == "/path/to/art.jpg"

    def test_restore_previous(self) -> None:
        store = _FakeStore()
        pipeline = _FakePipeline()
        manager = GameMediaManager(store, pipeline)
        store.save(
            GameMediaState(
                game_id="g1",
                title_id="0100",
                title="Game",
                media_source="scraper",
                media_path="/path/to/new.jpg",
                previous_media_path="/path/to/old.jpg",
            )
        )
        result = manager.restore_previous("g1")
        assert result is not None
        assert result.media_path == "/path/to/old.jpg"


# =============================================================================
# Search and candidates
# =============================================================================


class TestSearchCandidates:
    def test_empty_when_no_providers(self) -> None:
        store = _FakeStore()
        pipeline = _FakePipeline()
        manager = GameMediaManager(store, pipeline)
        result = manager.search_candidates("g1", "0100", "Game")
        assert result.candidate_count == 0
        assert result.metadata_state == "degraded"
        assert "fallback local" in result.reason

    def test_candidate_navigation(self) -> None:
        store = _FakeStore()
        pipeline = _FakePipeline()
        manager = GameMediaManager(store, pipeline)
        store.save(
            GameMediaState(
                game_id="g1",
                title_id="0100",
                title="Game",
                candidates=[
                    {
                        "url": "https://example.com/1.jpg",
                        "mediaKind": "boxart",
                        "provider": "fake",
                        "confidence": 0.9,
                    },
                    {
                        "url": "https://example.com/2.jpg",
                        "mediaKind": "boxart",
                        "provider": "fake2",
                        "confidence": 0.8,
                    },
                ],
                candidate_count=2,
            )
        )
        result = manager.select_candidate("g1", 1)
        assert result is not None
        assert result.selected_candidate_idx == 1
        assert result.candidates[1]["provider"] == "fake2"


def test_prune_orphan_cache_is_transactional_and_rollback_restores_bytes(
    tmp_path: Path, isolated_xdg_root: Path
) -> None:
    media_root = tmp_path / "media"
    orphan = media_root / "masters" / "switch" / "icon" / "orphan.png"
    orphan.parent.mkdir(parents=True)
    original = b"\x89PNG\r\n\x1a\norphan"
    orphan.write_bytes(original)
    pipeline = MediaPipeline(media_root)

    plan = pipeline.plan_prune_orphan_cache()
    assert paths.plan_path(plan.plan_id).is_relative_to(isolated_xdg_root)
    assert paths.plan_path(plan.plan_id).is_file()
    applied = transaction.apply(plan.plan_id, plan.confirm_token)
    assert paths.journal_path(applied.operation_id).is_relative_to(isolated_xdg_root)
    assert paths.backup_for(applied.operation_id).is_relative_to(isolated_xdg_root)

    assert not orphan.exists()
    rolled_back = transaction.rollback(applied.operation_id, reason="test")
    assert rolled_back.status == "rolled-back"
    assert orphan.read_bytes() == original


# =============================================================================
# Persistence via StateStore
# =============================================================================


class TestStateStorePersistence:
    @pytest.fixture
    def conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(":memory:")
        c.row_factory = sqlite3.Row
        c.execute(
            """CREATE TABLE switch_game_media (
                game_id TEXT PRIMARY KEY,
                title_id TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                media_source TEXT NOT NULL DEFAULT 'fallback',
                media_kind TEXT NOT NULL DEFAULT 'icon',
                media_path TEXT,
                previous_media_path TEXT,
                developer TEXT,
                version TEXT,
                languages TEXT NOT NULL DEFAULT '',
                metadata_state TEXT NOT NULL DEFAULT 'unavailable',
                reason TEXT NOT NULL DEFAULT '',
                checked_at TEXT NOT NULL DEFAULT '',
                selected_candidate_idx INTEGER NOT NULL DEFAULT -1,
                candidate_json TEXT NOT NULL DEFAULT '[]',
                master_state TEXT NOT NULL DEFAULT 'none',
                optimized_state TEXT NOT NULL DEFAULT 'none',
                steam_view_state TEXT NOT NULL DEFAULT 'unpublished',
                steam_appid INTEGER,
                steam_artwork_json TEXT NOT NULL DEFAULT '[]',
                errors_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )"""
        )
        yield c
        c.close()

    def test_save_and_load(self, conn: sqlite3.Connection) -> None:
        adapter = StateStoreGameMediaAdapter(conn)
        state = GameMediaState(
            game_id="g1",
            title_id="0100",
            title="Game",
            media_source="scraper",
            media_path="/path/to/icon.jpg",
            candidates=[
                {
                    "url": "https://example.com/1.jpg",
                    "mediaKind": "icon",
                    "provider": "test",
                    "confidence": 0.9,
                }
            ],
            candidate_count=1,
            master_state="collected",
            optimized_state="ready",
            steam_view_state="published",
            steam_appid=123,
            steam_artwork_kinds=["steam-icon"],
            errors={"screenscraper": "E-SCRAPE-QUOTA-EXCEEDED"},
        )
        adapter.save(state)
        loaded = adapter.load("g1")
        assert loaded is not None
        assert loaded.game_id == "g1"
        assert loaded.media_source == "scraper"
        assert loaded.candidate_count == 1
        assert loaded.master_state == "collected"
        assert loaded.optimized_state == "ready"
        assert loaded.steam_view_state == "published"
        assert loaded.steam_appid == 123
        assert loaded.steam_artwork_kinds == ["steam-icon"]
        assert loaded.errors == {"screenscraper": "E-SCRAPE-QUOTA-EXCEEDED"}

    def test_errors_cleared_on_successful_resave(self, conn: sqlite3.Connection) -> None:
        adapter = StateStoreGameMediaAdapter(conn)
        failed = GameMediaState(game_id="g1", title_id="0100", title="Game")
        failed.errors = {"screenscraper": "E-SCRAPE-QUOTA-EXCEEDED"}
        adapter.save(failed)
        assert adapter.load("g1").errors == {"screenscraper": "E-SCRAPE-QUOTA-EXCEEDED"}
        ok = GameMediaState(game_id="g1", title_id="0100", title="Game")
        adapter.save(ok)
        assert adapter.load("g1").errors == {}

    def test_list_all(self, conn: sqlite3.Connection) -> None:
        adapter = StateStoreGameMediaAdapter(conn)
        adapter.save(GameMediaState(game_id="g1", title_id="0100", title="A Game"))
        adapter.save(GameMediaState(game_id="g2", title_id="0101", title="B Game"))
        all_states = adapter.list_all()
        assert len(all_states) == 2

    def test_delete(self, conn: sqlite3.Connection) -> None:
        adapter = StateStoreGameMediaAdapter(conn)
        adapter.save(GameMediaState(game_id="g1", title_id="0100", title="Game"))
        adapter.delete("g1")
        assert adapter.load("g1") is None

    def test_survives_restart(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        conn1 = sqlite3.connect(str(db_path))
        conn1.row_factory = sqlite3.Row
        conn1.execute(
            """CREATE TABLE switch_game_media (
                game_id TEXT PRIMARY KEY,
                title_id TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                media_source TEXT NOT NULL DEFAULT 'fallback',
                media_kind TEXT NOT NULL DEFAULT 'icon',
                media_path TEXT,
                previous_media_path TEXT,
                developer TEXT,
                version TEXT,
                languages TEXT NOT NULL DEFAULT '',
                metadata_state TEXT NOT NULL DEFAULT 'unavailable',
                reason TEXT NOT NULL DEFAULT '',
                checked_at TEXT NOT NULL DEFAULT '',
                selected_candidate_idx INTEGER NOT NULL DEFAULT -1,
                candidate_json TEXT NOT NULL DEFAULT '[]',
                master_state TEXT NOT NULL DEFAULT 'none',
                optimized_state TEXT NOT NULL DEFAULT 'none',
                steam_view_state TEXT NOT NULL DEFAULT 'unpublished',
                steam_appid INTEGER,
                steam_artwork_json TEXT NOT NULL DEFAULT '[]',
                errors_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )"""
        )
        a1 = StateStoreGameMediaAdapter(conn1)
        a1.save(GameMediaState(game_id="g1", title_id="0100", title="Persistent"))
        conn1.close()

        conn2 = sqlite3.connect(str(db_path))
        conn2.row_factory = sqlite3.Row
        a2 = StateStoreGameMediaAdapter(conn2)
        loaded = a2.load("g1")
        assert loaded is not None
        assert loaded.title == "Persistent"
        conn2.close()


# =============================================================================
# Coverage stats
# =============================================================================


class TestCoverageStats:
    def test_stats_categories(self) -> None:
        store = _FakeStore()
        pipeline = _FakePipeline()
        manager = GameMediaManager(store, pipeline)
        store.save(GameMediaState(game_id="g1", title_id="0100", title="G1", media_source="custom"))
        store.save(GameMediaState(game_id="g2", title_id="0101", title="G2", media_source="nca"))
        store.save(
            GameMediaState(
                game_id="g3",
                title_id="0102",
                title="G3",
                media_source="fallback",
            )
        )
        stats = manager.coverage_stats()
        assert stats["total"] == 3
        assert stats["custom"] == 1
        assert stats["native"] == 1
        assert stats["fallback"] == 1
