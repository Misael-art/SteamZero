from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from steamzero.core import fs, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain.media_optimizer import OptimizerProfile
from steamzero.domain.media_pipeline import (
    AuditReport,
    MediaPipeline,
    OptimizeResult,
    ViewResult,
    canonical_media_kind,
)
from steamzero.ports import GameIdentity, MediaCandidate, MediaProviderPort

_log = logging.getLogger(__name__)


@dataclass
class GameMediaState:
    game_id: str
    title_id: str
    title: str
    media_source: str = "fallback"
    media_kind: str = "icon"
    media_path: str | None = None
    previous_media_path: str | None = None
    developer: str | None = None
    version: str | None = None
    languages: str = ""
    candidates: list[dict[str, Any]] = field(default_factory=list)
    candidate_count: int = 0
    selected_candidate_idx: int = -1
    metadata_state: str = "unavailable"
    reason: str = ""
    checked_at: str = ""
    errors: dict[str, str] = field(default_factory=dict)
    master_state: str = "none"
    optimized_state: str = "none"
    steam_view_state: str = "unpublished"
    steam_appid: int | None = None
    steam_artwork_kinds: list[str] = field(default_factory=list)


class GameMediaStorePort(Protocol):
    def load(self, game_id: str) -> GameMediaState | None: ...

    def save(self, state: GameMediaState) -> None: ...

    def list_all(self) -> list[GameMediaState]: ...

    def delete(self, game_id: str) -> None: ...

    def save_candidate_selection(
        self, game_id: str, candidate_idx: int, media_kind: str
    ) -> None: ...

    def clear_selection(self, game_id: str) -> None: ...


class GameMediaManager:
    def __init__(
        self,
        store: GameMediaStorePort,
        pipeline: MediaPipeline,
        providers: list[MediaProviderPort] | None = None,
    ) -> None:
        self._store = store
        self._pipeline = pipeline
        self._providers = providers or []
        self._fallback_path: Path | None = None

    def resolve_effective_media(
        self,
        game_id: str,
        title_id: str,
        title: str,
        rom_path: Path | None = None,
        fingerprint: str = "",
        steam_appid: int | None = None,
    ) -> GameMediaState:
        existing = self._store.load(game_id)
        if existing:
            if steam_appid is not None:
                existing.steam_appid = steam_appid
            existing.steam_view_state = self._resolve_steam_state(game_id, existing.steam_appid)
            existing.master_state = self._resolve_master_state(game_id)
            existing.optimized_state = self._resolve_optimized_state(game_id)
            existing.steam_artwork_kinds = self._resolve_artwork_kinds(
                game_id, existing.steam_appid
            )
            if existing.media_source == "custom" and existing.media_path:
                p = Path(existing.media_path)
                if p.is_file():
                    return existing
            if existing.media_source == "scraper" and existing.media_path:
                p = Path(existing.media_path)
                if p.is_file():
                    return existing
            existing.media_source = "fallback"
            existing.media_path = None

        state = GameMediaState(
            game_id=game_id,
            title_id=title_id,
            title=title,
            steam_appid=steam_appid,
        )

        fallback = self._ensure_fallback(title_id)
        if fallback:
            state.media_source = "fallback"
            state.media_path = str(fallback)
            state.media_kind = "icon"
            state.metadata_state = "fallback"
            state.reason = "nenhuma mídia disponível"
        state.master_state = self._resolve_master_state(game_id)
        state.optimized_state = self._resolve_optimized_state(game_id)
        state.steam_view_state = self._resolve_steam_state(game_id, steam_appid)
        self._store.save(state)
        return state

    def search_candidates(
        self,
        game_id: str,
        title_id: str,
        title: str,
        media_kinds: list[str] | None = None,
        fingerprint: str = "",
        hashes: dict[str, str] | None = None,
    ) -> GameMediaState:
        kinds = media_kinds or ["boxart", "grid", "hero", "icon", "logo", "screenshot"]
        state = self._store.load(game_id) or GameMediaState(
            game_id=game_id, title_id=title_id, title=title
        )
        state.metadata_state = "searching"
        self._store.save(state)

        identity = GameIdentity(
            game_id=game_id,
            title=title,
            platform_slug="switch",
            title_id=title_id,
            hashes=hashes or {},
        )
        all_candidates: list[MediaCandidate] = []
        provider_errors: dict[str, str] = {}
        for provider in self._providers:
            try:
                results = provider.search(identity, kinds)
                all_candidates.extend(results)
            except SteamZeroError as exc:
                provider_errors[provider.name] = exc.code
                _log.debug("provider %s falhou com código conhecido", provider.name)
                continue
            except Exception:
                provider_errors[provider.name] = "E-SCRAPE-PROVIDER-UNREACHABLE"
                _log.debug("provider %s falhou sem detalhe serializável", provider.name)
                continue
        all_candidates.sort(key=lambda c: (-c.confidence, c.media_kind))
        state.candidates = [
            {
                "url": c.url,
                "mediaKind": c.media_kind,
                "provider": c.provider,
                "confidence": c.confidence,
                "width": c.width,
                "height": c.height,
                "region": c.region,
                "license": c.license,
                "attribution": c.attribution,
            }
            for c in all_candidates
        ]
        state.candidate_count = len(state.candidates)
        state.errors = provider_errors
        state.metadata_state = (
            "candidates-found"
            if state.candidates
            else "degraded"
            if provider_errors or not self._providers
            else "no-results"
        )
        if not self._providers:
            state.reason = "Nenhum provider remoto configurado; fallback local preservado."
        elif provider_errors and not state.candidates:
            state.reason = "Providers remotos falharam; fallback local preservado."
        state.selected_candidate_idx = -1
        self._store.save(state)
        return state

    def select_candidate(self, game_id: str, idx: int) -> GameMediaState | None:
        state = self._store.load(game_id)
        if state is None or idx < 0 or idx >= len(state.candidates):
            return None
        state.selected_candidate_idx = idx
        self._store.save_candidate_selection(game_id, idx, state.media_kind)
        return state

    def apply_selected_candidate(
        self, game_id: str, title_id: str, fingerprint: str, canonical_name: str
    ) -> GameMediaState | None:
        state = self._store.load(game_id)
        if state is None or state.selected_candidate_idx < 0:
            return None
        candidate_data = state.candidates[state.selected_candidate_idx]
        kind = canonical_media_kind(str(candidate_data.get("mediaKind", "boxart")))
        candidate = MediaCandidate(
            url=candidate_data["url"],
            media_kind=kind,
            provider=candidate_data.get("provider", "unknown"),
            confidence=candidate_data.get("confidence", 0.5),
            width=candidate_data.get("width"),
            height=candidate_data.get("height"),
            region=candidate_data.get("region"),
            license=candidate_data.get("license", ""),
            attribution=candidate_data.get("attribution", ""),
        )
        result = self._pipeline.collect_from_candidate(
            candidate=candidate,
            game_id=game_id,
            title_id=title_id,
            fingerprint=fingerprint,
            canonical_name=canonical_name,
        )
        if not result.success:
            state.metadata_state = "failed"
            state.reason = "coleção falhou"
            self._store.save(state)
            return None

        master_path = next(iter(result.collected.values()))
        state.previous_media_path = state.media_path
        state.media_path = str(master_path)
        state.media_source = "scraper"
        state.media_kind = kind
        state.metadata_state = "confirmed"
        state.master_state = "collected"
        self._store.save(state)
        return state

    def import_custom_media(
        self,
        game_id: str,
        src_path: Path,
        title_id: str,
        fingerprint: str,
        canonical_name: str,
    ) -> GameMediaState | None:
        if not src_path.is_file():
            return None
        result = self._pipeline.collect(
            source=src_path,
            game_id=game_id,
            title_id=title_id,
            fingerprint=fingerprint,
            canonical_name=canonical_name,
            kind="box2d",
        )
        if not result.success:
            return None
        state = self._store.load(game_id)
        if state is None:
            return None
        master_path = next(iter(result.collected.values()))
        state.previous_media_path = state.media_path
        state.media_path = str(master_path)
        state.media_source = "custom"
        state.media_kind = "box2d"
        state.metadata_state = "confirmed"
        state.master_state = "collected"
        self._store.save(state)
        return state

    def clear_media(self, game_id: str) -> GameMediaState | None:
        state = self._store.load(game_id)
        if state is None:
            return None
        state.previous_media_path = state.media_path
        state.media_path = None
        state.media_source = "fallback"
        state.media_kind = "icon"
        state.metadata_state = "fallback"
        state.selected_candidate_idx = -1
        state.candidates = []
        state.candidate_count = 0
        self._store.clear_selection(game_id)
        self._store.save(state)
        return state

    def restore_previous(self, game_id: str) -> GameMediaState | None:
        state = self._store.load(game_id)
        if state is None or not state.previous_media_path:
            return None
        state.media_path = state.previous_media_path
        state.previous_media_path = None
        state.media_source = "custom" if state.media_path else "fallback"
        self._store.save(state)
        return state

    def optimize_game(self, game_id: str, profile: str | None = None) -> OptimizeResult:
        result = self._pipeline.optimize(game_id, profile=profile)
        state = self._store.load(game_id)
        if state is not None:
            state.optimized_state = self._resolve_optimized_state(game_id)
            self._store.save(state)
        return result

    def publish_steam(
        self,
        game_id: str,
        steam_user_id: str,
        steam_appid: int,
        *,
        grid_dir: Path | None = None,
    ) -> ViewResult:
        return self._pipeline.view_steam(game_id, steam_user_id, steam_appid, grid_dir=grid_dir)

    def plan_publish_steam(
        self,
        game_id: str,
        steam_user_id: str,
        steam_appid: int,
        *,
        grid_dir: Path,
    ) -> transaction.Plan | None:
        return self._pipeline.view_steam_plan(
            game_id,
            steam_user_id,
            steam_appid,
            grid_dir=grid_dir,
        )

    def unpublish_steam(
        self,
        game_id: str,
        steam_user_id: str,
        steam_appid: int,
        *,
        grid_dir: Path | None = None,
    ) -> transaction.Plan | None:
        return self._pipeline.unpublish_steam_plan(
            game_id,
            steam_user_id,
            steam_appid,
            grid_dir=grid_dir,
        )

    def refresh_steam_publication(
        self,
        game_id: str,
        steam_appid: int,
        *,
        grid_dir: Path,
    ) -> GameMediaState | None:
        state = self._store.load(game_id)
        if state is None:
            return None
        state.steam_appid = steam_appid
        stems = {
            "steam-portrait": f"{steam_appid}p",
            "steam-landscape": str(steam_appid),
            "steam-hero": f"{steam_appid}_hero",
            "steam-logo": f"{steam_appid}_logo",
            "steam-icon": f"{steam_appid}_icon",
        }
        published = [
            profile
            for profile, stem in stems.items()
            if any(
                (grid_dir / f"{stem}{extension}").is_file()
                or (grid_dir / f"{stem}{extension}").is_symlink()
                for extension in (".png", ".jpg", ".webp")
            )
        ]
        state.steam_artwork_kinds = published
        state.steam_view_state = "published" if published else "unpublished"
        self._store.save(state)
        return state

    def audit(self, platform_id: str | None = None) -> AuditReport:
        return self._pipeline.audit(platform_id=platform_id)

    def plan_prune_orphan_cache(self) -> transaction.Plan:
        return self._pipeline.plan_prune_orphan_cache()

    def coverage_stats(self) -> dict[str, int]:
        states = self._store.list_all()
        return {
            "total": len(states),
            "custom": sum(1 for s in states if s.media_source == "custom"),
            "scraper": sum(1 for s in states if s.media_source == "scraper"),
            "native": sum(1 for s in states if s.media_source == "nca"),
            "emulator_cache": sum(1 for s in states if s.media_source == "emulator-cache"),
            "fallback": sum(1 for s in states if s.media_source == "fallback"),
            "missing": sum(1 for s in states if s.media_path is None),
            "optimized": sum(1 for s in states if s.optimized_state == "ready"),
            "steam_published": sum(1 for s in states if s.steam_view_state == "published"),
        }

    def _ensure_fallback(self, title_id: str) -> Path | None:
        fallback_dir = Path.home() / ".cache" / "steamzero" / "media" / "fallback"
        fallback_path = fallback_dir / f"{title_id}.png"
        if fallback_path.is_file():
            return fallback_path
        try:
            import struct
            import zlib

            fs.ensure_dir(fallback_dir)
            h, w = 256, 256
            raw = b""
            for y in range(h):
                for x in range(w):
                    r = (x ^ y) & 0xFF
                    g = (x + y) & 0xFF
                    b_val = (x * y) & 0xFF
                    raw += struct.pack("BBB", r, g, b_val)

            def _chunk(tag: bytes, data: bytes) -> bytes:
                c = tag + data
                crc = zlib.crc32(c) & 0xFFFFFFFF
                return struct.pack(">I", len(data)) + c + struct.pack(">I", crc)

            sig = b"\x89PNG\r\n\x1a\n"
            ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
            raw_data = b""
            for y in range(h):
                raw_data += b"\x00" + raw[y * w * 3 : (y + 1) * w * 3]
            compressed = zlib.compress(raw_data)
            png_data = sig + _chunk(b"IHDR", ihdr)
            png_data += _chunk(b"IDAT", compressed)
            png_data += _chunk(b"IEND", b"")
            fs.write_atomic(fallback_path, png_data)
            return fallback_path if fallback_path.is_file() else None
        except (OSError, ImportError):
            return None

    def _resolve_master_state(self, game_id: str) -> str:
        entry = self._pipeline.get_registry_entry(game_id)
        return "collected" if entry else "none"

    def _resolve_optimized_state(self, game_id: str) -> str:
        for pname in OptimizerProfile.steam_profiles():
            if self._pipeline.find_optimized(game_id, pname.kind):
                return "ready"
        return "none"

    def _resolve_steam_state(self, game_id: str, steam_appid: int | None) -> str:
        if steam_appid is None:
            return "no-steam-appid"
        return "published" if self._has_steam_views(game_id) else "unpublished"

    def _resolve_artwork_kinds(self, game_id: str, steam_appid: int | None) -> list[str]:
        if steam_appid is None:
            return []
        kinds: list[str] = []
        for pname in OptimizerProfile.steam_profiles():
            if self._pipeline._find_optimized(game_id, pname.kind):
                kinds.append(pname.kind)
        return kinds

    def _has_steam_views(self, game_id: str) -> bool:
        views_root = self._pipeline._media_root / "views" / "steam"
        if not views_root.is_dir():
            return False
        for user_dir in views_root.iterdir():
            grid_dir = user_dir / "grid"
            if grid_dir.is_dir():
                for f in grid_dir.iterdir():
                    if f.name.startswith(game_id):
                        return True
        return False
