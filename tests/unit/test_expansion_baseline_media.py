# SPDX-License-Identifier: GPL-3.0-or-later
"""Behavioral coverage for the canonical media pipeline baseline."""

from __future__ import annotations

import io
import os
from pathlib import Path

import pytest

from steamzero.core import transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain import media_pipeline as media_module
from steamzero.domain.media_pipeline import (
    AuditReport,
    CollectionResult,
    MediaPipeline,
    OptimizeResult,
    ViewResult,
    _detect_pillow,
    _is_managed,
    _optimize_pillow,
    _optimized_from_master,
    _publish_link,
    _steam_stem,
    _valid_image_file,
    _validate_image_magic,
    canonical_media_kind,
)
from steamzero.domain.media_registry import MediaMasterEntry
from steamzero.domain.switch_media import (
    GameMediaManager,
    GameMediaState,
    GameMediaStorePort,
)
from steamzero.ports import GameIdentity, MediaCandidate

PNG = b"\x89PNG\r\n\x1a\nfixture-media"


class _Store(GameMediaStorePort):
    def __init__(self) -> None:
        self.data: dict[str, GameMediaState] = {}

    def load(self, game_id: str) -> GameMediaState | None:
        return self.data.get(game_id)

    def save(self, state: GameMediaState) -> None:
        self.data[state.game_id] = state

    def list_all(self) -> list[GameMediaState]:
        return list(self.data.values())

    def delete(self, game_id: str) -> None:
        self.data.pop(game_id, None)

    def save_candidate_selection(self, game_id: str, candidate_idx: int, media_kind: str) -> None:
        state = self.data[game_id]
        state.selected_candidate_idx = candidate_idx
        state.media_kind = media_kind

    def clear_selection(self, game_id: str) -> None:
        state = self.data[game_id]
        state.selected_candidate_idx = -1
        state.candidates = []
        state.candidate_count = 0


class _RemoteProvider:
    name = "fixture"

    def __init__(self, result: list[MediaCandidate] | BaseException) -> None:
        self.result = result

    def supported_kinds(self) -> frozenset[str]:
        return frozenset({"boxart"})

    def supported_platforms(self) -> frozenset[str]:
        return frozenset({"switch"})

    def search(
        self,
        identity: GameIdentity,
        media_kinds: list[str],
        region_priority: list[str] | None = None,
    ) -> list[MediaCandidate]:
        del identity, media_kinds, region_priority
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class _PipelineFake:
    def __init__(self, root: Path) -> None:
        self._media_root = root
        self.registry: dict[str, object] = {}
        self.optimized: dict[tuple[str, str], Path] = {}
        self.collect_result = CollectionResult("g", {"box2d": root / "master.png"})
        self.candidate_result = CollectionResult("g", {"box2d": root / "candidate.png"})
        self.optimize_result = OptimizeResult("g")
        self.view_result = ViewResult("g")
        self.publish_plan: transaction.Plan | None = None
        self.unpublish_plan: transaction.Plan | None = None

    def collect(self, **_kwargs: object) -> CollectionResult:
        return self.collect_result

    def collect_from_candidate(self, **_kwargs: object) -> CollectionResult:
        return self.candidate_result

    def optimize(self, game_id: str, profile: str | None = None) -> OptimizeResult:
        del game_id, profile
        return self.optimize_result

    def view_steam(self, *_args: object, **_kwargs: object) -> ViewResult:
        return self.view_result

    def view_steam_plan(self, *_args: object, **_kwargs: object) -> transaction.Plan | None:
        return self.publish_plan

    def unpublish_steam_plan(self, *_args: object, **_kwargs: object) -> transaction.Plan | None:
        return self.unpublish_plan

    def audit(self) -> AuditReport:
        return AuditReport(stats={"fixture": 1})

    def plan_prune_orphan_cache(self) -> transaction.Plan:
        return transaction.plan_write_files({}, root=self._media_root, kind="fixture")

    def get_registry_entry(self, game_id: str) -> object | None:
        return self.registry.get(game_id)

    def find_optimized(self, game_id: str, profile: str) -> Path | None:
        return self.optimized.get((game_id, profile))

    def _find_optimized(self, game_id: str, profile: str) -> Path | None:
        return self.find_optimized(game_id, profile)


def _candidate(kind: str = "boxart") -> MediaCandidate:
    return MediaCandidate(
        url="https://example.invalid/media",
        media_kind=kind,
        provider="fixture",
        confidence=0.9,
        width=600,
        height=900,
        region="wor",
        license="fixture",
        attribution="fixture",
    )


def test_pipeline_collect_candidate_optimize_and_registry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "media"
    missing = MediaPipeline(root)
    failed = missing.collect(tmp_path / "missing.png", "g", "tid", "fp", "Game")
    assert failed.failed

    source = tmp_path / "source.png"
    source.write_bytes(PNG)
    pipeline = MediaPipeline(
        root,
        optimizer_tool=lambda src, dst, _profile: dst.write_bytes(src.read_bytes()) > 0,
        candidate_fetcher=lambda _url: PNG,
    )
    collected = pipeline.collect(
        source, "g", "tid", "fp", "Game", kind="boxart", platform_id="nes-famicom"
    )
    assert collected.success
    entry = pipeline.get_registry_entry("g")
    assert entry is not None and entry.platform_id == "nes-famicom"
    assert collected.collected["box2d"].is_relative_to(root / "masters" / "nes-famicom")
    assert canonical_media_kind("grid") == "box2d"
    assert canonical_media_kind("hero") == "hero"

    remote = pipeline.collect_from_candidate(
        _candidate("icon"), "g", "tid", "fp", "Game", platform_id="nes-famicom"
    )
    assert remote.success
    entry = pipeline.get_registry_entry("g")
    assert entry is not None and entry.provenance is not None

    invalid = MediaPipeline(root, candidate_fetcher=lambda _url: b"invalid")
    assert invalid.collect_from_candidate(_candidate(), "bad", "tid", "fp", "Bad").failed
    offline = MediaPipeline(
        root,
        candidate_fetcher=lambda _url: (_ for _ in ()).throw(OSError("offline")),
    )
    assert offline.collect_from_candidate(_candidate(), "bad", "tid", "fp", "Bad").failed

    optimized = pipeline.optimize("g", profile="steam-icon")
    assert optimized.success
    assert pipeline.find_optimized("g", "steam-icon") is not None
    second = pipeline.optimize("g", profile="steam-icon")
    assert second.skipped == ["steam-icon"]
    assert pipeline.optimize("missing", profile="steam-icon").failed == ["no-registry-entry"]

    monkeypatch.setattr(media_module, "_detect_pillow", lambda: False)
    no_optimizer = MediaPipeline(root)
    assert no_optimizer.optimize("g").skipped == ["optimizer-unavailable"]


def test_platform_layout_migration_moves_registered_master_and_rolls_back(tmp_path: Path) -> None:
    root = tmp_path / "media"
    source = tmp_path / "source.png"
    source.write_bytes(PNG)
    pipeline = MediaPipeline(root)
    pipeline.collect(source, "g", "tid", "fp", "Game")
    legacy = next((root / "masters" / "switch").rglob("*.png"))
    orphan = root / "masters" / "switch" / "box2d" / "orphan.png"
    orphan.write_bytes(PNG)

    plan = pipeline.plan_platform_layout_migration({"g": "nes-famicom"})
    assert plan.kind == "media.platform-layout-migration"
    assert {action.kind for action in plan.actions} == {"move", "write"}
    applied = pipeline.apply_platform_layout_migration(plan.plan_id, plan.confirm_token)
    migrated = root / "masters" / "nes-famicom" / "box2d" / legacy.name
    assert applied.status == "ok"
    assert migrated.is_file() and not legacy.exists()
    assert orphan.is_file()
    assert pipeline.get_registry_entry("g").platform_id == "nes-famicom"  # type: ignore[union-attr]

    rolled_back = pipeline.rollback_platform_layout_migration(applied.operation_id)
    assert rolled_back.status == "rolled-back"
    assert legacy.is_file() and not migrated.exists()
    assert orphan.is_file()
    assert pipeline.get_registry_entry("g").platform_id == "switch"  # type: ignore[union-attr]


def test_pipeline_rejects_unsafe_or_failed_optimizer_outputs(tmp_path: Path) -> None:
    root = tmp_path / "media"
    source = tmp_path / "source.png"
    source.write_bytes(PNG)
    pipeline = MediaPipeline(root, optimizer_tool=lambda _s, _d, _p: False)
    pipeline.collect(source, "g", "tid", "fp", "Game")
    assert pipeline.optimize("g", "steam-portrait").failed == ["steam-portrait"]

    def broken(_src: Path, _dst: Path, _profile: str) -> bool:
        raise RuntimeError("fixture")

    raising = MediaPipeline(root, optimizer_tool=broken)
    assert raising.optimize("g", "steam-portrait").failed == ["steam-portrait"]

    entry = raising.get_registry_entry("g")
    assert entry is not None
    raising._registry.add_entry(
        MediaMasterEntry(
            game_id="unsafe",
            title_id="tid",
            fingerprint="fp",
            canonical_name="Unsafe",
            confirmed=True,
            masters={"box2d": "../escape.png"},
        )
    )
    assert raising.optimize("unsafe", "steam-portrait").failed == ["steam-portrait"]


def test_pipeline_views_plans_audit_and_helpers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "media"
    source = tmp_path / "source.png"
    source.write_bytes(PNG)
    pipeline = MediaPipeline(
        root,
        optimizer_tool=lambda src, dst, _profile: dst.write_bytes(src.read_bytes()) > 0,
    )
    pipeline.collect(source, "g", "tid", "fp", "Game")
    pipeline.optimize("g", "steam-portrait")
    grid = tmp_path / "grid"

    viewed = pipeline.view_steam("g", "user", 42, ["ui-preview", "steam-portrait"], grid)
    assert viewed.success
    published = next(iter(viewed.published.values()))
    assert published.is_symlink()
    assert _is_managed(published, root / "optimized")
    assert pipeline.view_steam_plan("g", "user", 42, grid) is not None
    assert pipeline.unpublish_steam_plan("g", "user", 42, grid) is not None

    external = grid / f"{_steam_stem(42, 'steam-portrait')}.png"
    external.unlink()
    external.write_bytes(b"external")
    skipped = pipeline.view_steam("g", "user", 42, ["steam-portrait"], grid)
    assert skipped.skipped == ["steam-portrait:externo-nao-gerenciado"]
    assert pipeline.view_steam("missing", "user", 42, ["steam-icon"], grid).failed

    broken = root / "views" / "steam" / "u" / "grid" / "broken.png"
    broken.parent.mkdir(parents=True)
    broken.symlink_to(root / "missing.png")
    report = pipeline.audit()
    assert report.stats["masterFiles"] >= 1
    assert any(f.category == "broken-link" for f in report.findings)
    assert report.to_dict()["findings"]

    marker = tmp_path / "marker.png"
    marker.write_bytes(PNG + b"\n# SteamZero-Boot-Managed: true\n")
    assert _is_managed(marker)
    assert not _is_managed(tmp_path / "missing")
    assert _validate_image_magic(PNG)
    assert _validate_image_magic(b"\xff\xd8\xfffixture")
    assert _validate_image_magic(b"RIFFxxxxWEBPfixture")
    assert not _validate_image_magic(b"bad")
    assert _valid_image_file(source)
    assert not _valid_image_file(tmp_path / "missing")
    assert _optimized_from_master(source, source)

    fallback_target = tmp_path / "copy.png"
    monkeypatch.setattr(
        "steamzero.domain.media_pipeline.fs.symlink_atomic",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("no links")),
    )
    assert _publish_link(source, fallback_target)
    assert b"SteamZero-Boot-Managed" in fallback_target.read_bytes()


def test_download_candidate_enforces_https_and_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(SteamZeroError):
        media_module._download_candidate("http://example.invalid/media")

    class Response:
        def __init__(self, data: bytes) -> None:
            self.stream = io.BytesIO(data)

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            return self.stream.read(size)

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_a, **_k: Response(PNG),
    )
    assert media_module._download_candidate("https://example.invalid/media") == PNG
    monkeypatch.setattr(media_module, "_MAX_DOWNLOAD", 4)
    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_k: Response(b"12345"))
    with pytest.raises(SteamZeroError):
        media_module._download_candidate("https://example.invalid/media")


def test_media_manager_candidates_mutations_and_wrappers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    store = _Store()
    pipeline = _PipelineFake(tmp_path / "media")
    candidate = _candidate()
    known_error = SteamZeroError("E-SCRAPE-PROVIDER-UNREACHABLE", detail="fixture")
    manager = GameMediaManager(
        store,
        pipeline,  # type: ignore[arg-type]
        [
            _RemoteProvider([candidate]),
            _RemoteProvider(known_error),
            _RemoteProvider(RuntimeError()),
        ],
    )
    state = manager.search_candidates("g", "tid", "Game", hashes={"sha1": "x"})
    assert state.candidate_count == 1
    assert state.errors
    assert manager.select_candidate("g", -1) is None
    assert manager.select_candidate("g", 0) is not None
    applied = manager.apply_selected_candidate("g", "tid", "fp", "Game")
    assert applied is not None and applied.media_source == "scraper"

    pipeline.candidate_result = CollectionResult("g", failed=["fixture"])
    assert manager.apply_selected_candidate("g", "tid", "fp", "Game") is None
    store.data["g"].selected_candidate_idx = -1
    assert manager.apply_selected_candidate("g", "tid", "fp", "Game") is None

    assert manager.import_custom_media("g", tmp_path / "missing", "tid", "fp", "Game") is None
    custom = tmp_path / "custom.png"
    custom.write_bytes(PNG)
    imported = manager.import_custom_media("g", custom, "tid", "fp", "Game")
    assert imported is not None and imported.media_source == "custom"
    assert manager.clear_media("missing") is None
    assert manager.restore_previous("missing") is None
    store.data["g"].previous_media_path = None
    assert manager.restore_previous("g") is None

    assert manager.optimize_game("g") is pipeline.optimize_result
    assert manager.publish_steam("g", "user", 42) is pipeline.view_result
    assert manager.plan_publish_steam("g", "user", 42, grid_dir=tmp_path) is None
    assert manager.unpublish_steam("g", "user", 42, grid_dir=tmp_path) is None
    assert manager.audit().stats == {"fixture": 1}
    assert manager.plan_prune_orphan_cache().kind == "fixture"

    grid = tmp_path / "grid"
    grid.mkdir()
    (grid / "42p.png").write_bytes(PNG)
    refreshed = manager.refresh_steam_publication("g", 42, grid_dir=grid)
    assert refreshed is not None and refreshed.steam_view_state == "published"
    assert manager.refresh_steam_publication("missing", 42, grid_dir=grid) is None

    store.save(GameMediaState("custom", "t", "C", media_source="custom", media_path="x"))
    store.save(GameMediaState("native", "t", "N", media_source="nca", media_path="x"))
    store.save(
        GameMediaState(
            "published",
            "t",
            "P",
            media_source="emulator-cache",
            media_path="x",
            optimized_state="ready",
            steam_view_state="published",
        )
    )
    stats = manager.coverage_stats()
    assert stats["total"] == 4
    assert stats["custom"] == 2
    assert stats["steam_published"] == 2

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    fallback = manager._ensure_fallback("tid")
    assert fallback is not None and fallback.read_bytes().startswith(b"\x89PNG")
    assert manager._ensure_fallback("tid") == fallback


def test_media_manager_resolution_states_and_view_detection(tmp_path: Path) -> None:
    store = _Store()
    pipeline = _PipelineFake(tmp_path / "media")
    manager = GameMediaManager(store, pipeline)  # type: ignore[arg-type]
    existing_file = tmp_path / "custom.png"
    existing_file.write_bytes(PNG)
    store.save(
        GameMediaState(
            "g",
            "tid",
            "Game",
            media_source="custom",
            media_path=str(existing_file),
            steam_appid=42,
        )
    )
    pipeline.registry["g"] = object()
    pipeline.optimized[("g", "steam-icon")] = tmp_path / "optimized.png"
    state = manager.resolve_effective_media("g", "tid", "Game", steam_appid=42)
    assert state.master_state == "collected"
    assert state.optimized_state == "ready"
    assert "steam-icon" in state.steam_artwork_kinds

    views = pipeline._media_root / "views" / "steam" / "u" / "grid"
    views.mkdir(parents=True)
    (views / "g_art.png").write_bytes(PNG)
    assert manager._has_steam_views("g")
    assert manager._resolve_steam_state("g", 42) == "published"
    assert manager._resolve_steam_state("g", None) == "no-steam-appid"
    assert manager._resolve_artwork_kinds("g", None) == []

    os.remove(existing_file)
    degraded = manager.resolve_effective_media("g", "tid", "Game")
    assert degraded.media_source == "fallback"


def test_pillow_optimizer_and_remaining_helper_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from PIL import Image

    source = tmp_path / "source.png"
    Image.new("RGB", (32, 32), color=(10, 20, 30)).save(source)
    target = tmp_path / "target.png"
    assert _detect_pillow()
    assert _optimize_pillow(source, target, "steam-icon")
    assert target.is_file()
    assert not _optimize_pillow(tmp_path / "missing.png", target, "steam-icon")
    assert _steam_stem(1, "steam-landscape") == "1"
    assert _steam_stem(1, "steam-hero") == "1_hero"
    assert _steam_stem(1, "steam-logo") == "1_logo"
    assert _steam_stem(1, "steam-icon") == "1_icon"
    assert _steam_stem(1, "unknown") == "1"

    failed_target = tmp_path / "failed.png"
    monkeypatch.setattr(
        "steamzero.domain.media_pipeline.fs.symlink_atomic",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("no links")),
    )
    monkeypatch.setattr(
        "steamzero.domain.media_pipeline.fs.write_atomic",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("no writes")),
    )
    assert not _publish_link(source, failed_target)

    dangling = tmp_path / "dangling.png"
    dangling.symlink_to(tmp_path / "absent.png")
    assert not _is_managed(dangling, tmp_path)
    assert not _optimized_from_master(tmp_path / "absent", source)
