from __future__ import annotations

import hashlib
import os
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from steamzero.core import fs, paths, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain.media_optimizer import (
    KIND_TO_STEAM_PROFILES,
    MASTER_EXTENSIONS,
    STEAM_PROFILES,
    UI_PREVIEW,
    OptimizerCapability,
    OptimizerProfile,
)
from steamzero.domain.media_registry import MediaMasterEntry, MediaRegistry, Provenance
from steamzero.ports import MediaCandidate, MediaProviderPort

_OWNERSHIP_MARKER = "# SteamZero-Boot-Managed: true"
_MAX_DOWNLOAD = 32 * 1024 * 1024
_KIND_ALIASES = {"boxart": "box2d", "grid": "box2d"}


def canonical_media_kind(kind: str) -> str:
    return _KIND_ALIASES.get(kind, kind)


def _download_candidate(url: str) -> bytes:
    from urllib.parse import urlsplit

    if urlsplit(url).scheme.casefold() != "https":
        raise SteamZeroError(
            "E-SCRAPE-DOWNLOAD-FAILED", detail="mídia remota exige HTTPS"
        )
    request = urllib.request.Request(url, headers={"User-Agent": "SteamZero/0.1"})  # noqa: S310
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        data = bytes(response.read(_MAX_DOWNLOAD + 1))
    if len(data) > _MAX_DOWNLOAD:
        raise SteamZeroError(
            "E-CONTENT-LIMIT", detail="mídia remota excede 32 MiB"
        )
    return data


@dataclass
class CollectionResult:
    game_id: str
    collected: dict[str, Path] = field(default_factory=dict)
    failed: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return bool(self.collected)


@dataclass
class OptimizeResult:
    game_id: str
    optimized: dict[str, Path] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return bool(self.optimized)


@dataclass
class ViewResult:
    game_id: str
    published: dict[str, Path] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return bool(self.published)


@dataclass
class AuditFinding:
    severity: str
    category: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "category": self.category, "detail": self.detail}


@dataclass
class AuditReport:
    findings: list[AuditFinding] = field(default_factory=list)
    stats: dict[str, int] = field(default_factory=dict)

    def add(self, severity: str, category: str, detail: str) -> None:
        self.findings.append(AuditFinding(severity, category, detail))

    def to_dict(self) -> dict[str, object]:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "stats": self.stats,
        }


class MediaPipeline:
    def __init__(
        self,
        media_root: Path,
        providers: list[MediaProviderPort] | None = None,
        optimizer_tool: Callable[[Path, Path, str], bool] | None = None,
        candidate_fetcher: Callable[[str], bytes] | None = None,
    ) -> None:
        self._media_root = media_root
        self._providers = providers or []
        self._optimizer_tool = optimizer_tool
        self._candidate_fetcher = candidate_fetcher or _download_candidate
        self._registry = MediaRegistry.load(media_root)

    # --- 1. COLLECT ---
    def collect(
        self,
        source: Path,
        game_id: str,
        title_id: str,
        fingerprint: str,
        canonical_name: str,
        kind: str = "box2d",
    ) -> CollectionResult:
        result = CollectionResult(game_id=game_id)
        try:
            data = source.read_bytes()
        except OSError as e:
            result.failed.append(str(e))
            return result
        kind = canonical_media_kind(kind)
        sha256 = hashlib.sha256(data).hexdigest()
        ext = MASTER_EXTENSIONS.get(kind, ".png")
        master_rel = Path("masters") / "switch" / kind / f"{sha256}{ext}"
        master_path = self._media_root / master_rel
        fs.ensure_dir(master_path.parent)
        if not master_path.is_file():
            fs.write_atomic(master_path, data)
        result.collected[kind] = master_path
        previous = self._registry.get_entry(game_id)
        masters = dict(previous.masters) if previous is not None else {}
        masters[kind] = master_rel.as_posix()
        entry = MediaMasterEntry(
            game_id=game_id,
            title_id=title_id,
            fingerprint=fingerprint,
            canonical_name=canonical_name,
            metadata_origin="local-import",
            confirmed=True,
            masters=masters,
        )
        self._registry.add_entry(entry)
        self._registry.save(self._media_root)
        return result

    def collect_from_candidate(
        self,
        candidate: MediaCandidate,
        game_id: str,
        title_id: str,
        fingerprint: str,
        canonical_name: str,
    ) -> CollectionResult:
        result = CollectionResult(game_id=game_id)
        kind = canonical_media_kind(candidate.media_kind)
        ext = MASTER_EXTENSIONS.get(kind, ".png")
        try:
            data = self._candidate_fetcher(candidate.url)
        except (OSError, SteamZeroError) as e:
            result.failed.append(str(e))
            return result
        if not _validate_image_magic(data):
            result.failed.append("invalid-magic")
            return result
        sha256 = hashlib.sha256(data).hexdigest()
        master_rel = Path("masters") / "switch" / kind / f"{sha256}{ext}"
        master_path = self._media_root / master_rel
        fs.ensure_dir(master_path.parent)
        if not master_path.is_file():
            fs.write_atomic(master_path, data)
        result.collected[kind] = master_path
        provenance = Provenance(
            provider=candidate.provider,
            source_url=candidate.url,
            license=candidate.license,
            attribution=candidate.attribution,
            hash_sha256=sha256,
        )
        previous = self._registry.get_entry(game_id)
        masters = dict(previous.masters) if previous is not None else {}
        masters[kind] = master_rel.as_posix()
        entry = MediaMasterEntry(
            game_id=game_id,
            title_id=title_id,
            fingerprint=fingerprint,
            canonical_name=canonical_name,
            metadata_origin=candidate.provider,
            confirmed=True,
            provenance=provenance,
            masters=masters,
        )
        self._registry.add_entry(entry)
        self._registry.save(self._media_root)
        return result

    # --- 2. OPTIMIZE ---
    def optimize(
        self, game_id: str, profile: str | None = None
    ) -> OptimizeResult:
        result = OptimizeResult(game_id=game_id)
        caps = self._detect_optimizer()
        if not caps.ok:
            result.skipped.append("optimizer-unavailable")
            return result
        entry = self._registry.get_entry(game_id)
        if entry is None:
            result.failed.append("no-registry-entry")
            return result
        profiles = [profile] if profile else list(STEAM_PROFILES)
        for pname in profiles:
            for kind, steam_kinds in KIND_TO_STEAM_PROFILES.items():
                if pname not in steam_kinds:
                    continue
                raw_master = entry.masters.get(kind)
                if raw_master is None:
                    continue
                master_rel = Path(raw_master)
                expected_root = Path("masters") / "switch" / kind
                if (
                    master_rel.is_absolute()
                    or ".." in master_rel.parts
                    or not master_rel.is_relative_to(expected_root)
                ):
                    result.failed.append(pname)
                    continue
                master_path = self._media_root / master_rel
                if master_path.is_symlink() or not master_path.is_file():
                    continue
                profile_def = OptimizerProfile.steam_profiles()
                pd = next((p for p in profile_def if p.kind == pname), None)
                if pd is None:
                    continue
                opt_rel = (
                    Path("optimized")
                    / "switch"
                    / pname
                    / f"{game_id}_{pd.key}{MASTER_EXTENSIONS.get(kind, '.png')}"
                )
                opt_path = self._media_root / opt_rel
                if (
                    opt_path.is_file()
                    and not opt_path.is_symlink()
                    and opt_path.stat().st_size > 0
                    and opt_path.stat().st_mtime_ns >= master_path.stat().st_mtime_ns
                ):
                    result.skipped.append(pname)
                    continue
                fs.ensure_dir(opt_path.parent)
                staging = opt_path.with_suffix(f".staging{opt_path.suffix}")
                try:
                    ok = self._optimize(master_path, staging, pname)
                except Exception:
                    result.failed.append(pname)
                    continue
                if (
                    not ok
                    or staging.is_symlink()
                    or not staging.is_file()
                    or staging.stat().st_size <= 0
                    or staging.stat().st_size > _MAX_DOWNLOAD
                    or not _valid_image_file(staging)
                ):
                    result.failed.append(pname)
                    if staging.is_file() and not staging.is_symlink():
                        fs.remove_file(staging)
                    continue
                fs.move_file(staging, opt_path)
                if staging.is_file():
                    fs.remove_file(staging)
                result.optimized[pname] = opt_path
        return result

    def _optimize(self, src: Path, dst: Path, profile: str) -> bool:
        if self._optimizer_tool is not None:
            return self._optimizer_tool(src, dst, profile)
        return _optimize_pillow(src, dst, profile)

    def _detect_optimizer(self) -> OptimizerCapability:
        if self._optimizer_tool is not None:
            return OptimizerCapability(available=True, name="external")
        if _detect_pillow():
            return OptimizerCapability(available=True, name="pillow", version="builtin")
        return OptimizerCapability(
            available=False,
            reason="optimizer-unavailable: instale Pillow ou forneça ferramenta externa",
        )

    # --- 3. VIEW ---
    def view_steam(
        self,
        game_id: str,
        steam_user_id: str,
        steam_appid: int,
        profiles: list[str] | None = None,
        grid_dir: Path | None = None,
    ) -> ViewResult:
        result = ViewResult(game_id=game_id)
        pnames = profiles or list(STEAM_PROFILES)
        for pname in pnames:
            if pname == UI_PREVIEW:
                continue
            opt_rel = self._find_optimized(game_id, pname)
            if opt_rel is None:
                result.failed.append(pname)
                continue
            opt_path = self._media_root / opt_rel
            if not opt_path.is_file():
                result.failed.append(pname)
                continue
            stem = _steam_stem(steam_appid, pname)
            ext = opt_path.suffix
            target_grid = grid_dir or paths.media_steam_grid_dir(steam_user_id)
            grid_path = target_grid / f"{stem}{ext}"
            fs.ensure_dir(grid_path.parent)
            if grid_path.is_file() and not _is_managed(
                grid_path, self._media_root / "optimized"
            ):
                result.skipped.append(f"{pname}:externo-nao-gerenciado")
                continue
            if grid_path.is_symlink() or grid_path.is_file():
                fs.remove_file(grid_path)
            ok = _publish_link(opt_path, grid_path)
            if not ok:
                result.failed.append(pname)
                continue
            result.published[pname] = grid_path
        return result

    def view_steam_plan(
        self,
        game_id: str,
        steam_user_id: str,
        steam_appid: int,
        grid_dir: Path | None = None,
    ) -> transaction.Plan | None:
        pnames = [k for k in STEAM_PROFILES if k != UI_PREVIEW]
        links: dict[Path, Path] = {}
        for pname in pnames:
            opt_rel = self._find_optimized(game_id, pname)
            if opt_rel is None:
                continue
            opt_path = self._media_root / opt_rel
            if not opt_path.is_file():
                continue
            stem = _steam_stem(steam_appid, pname)
            ext = opt_path.suffix
            target_grid = grid_dir or paths.media_steam_grid_dir(steam_user_id)
            grid_path = target_grid / f"{stem}{ext}"
            if grid_path.is_file() and not _is_managed(
                grid_path, self._media_root / "optimized"
            ):
                continue
            links[opt_path] = grid_path
        if not links:
            return None
        return transaction.plan_symlink_files(
            links,
            root=grid_dir or paths.media_views_dir(),
            kind="media.view-steam",
            replace_existing=True,
        )

    def unpublish_steam_plan(
        self,
        game_id: str,
        steam_user_id: str,
        steam_appid: int,
        grid_dir: Path | None = None,
    ) -> transaction.Plan | None:
        removals: set[Path] = set()
        grid_dir = grid_dir or paths.media_steam_grid_dir(steam_user_id)
        for pname in [k for k in STEAM_PROFILES if k != UI_PREVIEW]:
            for ext in (".png", ".jpg", ".webp"):
                stem = _steam_stem(steam_appid, pname)
                candidate = grid_dir / f"{stem}{ext}"
                if (candidate.is_file() or candidate.is_symlink()) and _is_managed(
                    candidate, self._media_root / "optimized"
                ):
                    removals.add(candidate)
        if not removals:
            return None
        writes: dict[Path, bytes] = {}
        return transaction.plan_write_files(
            writes,
            removals=removals,
            root=grid_dir,
            kind="media.unpublish-steam",
        )

    # --- 4. AUDIT ---
    def audit(self) -> AuditReport:
        report = AuditReport()
        masters_dir = self._media_root / "masters"
        optimized_dir = self._media_root / "optimized"
        views_dir = self._media_root / "views"

        master_files: set[str] = set()
        if masters_dir.is_dir():
            for f in masters_dir.rglob("*"):
                if f.is_file() and not f.is_symlink():
                    master_files.add(str(f.relative_to(masters_dir)))
        report.stats["masterFiles"] = len(master_files)

        opt_files: set[str] = set()
        if optimized_dir.is_dir():
            for f in optimized_dir.rglob("*"):
                if f.is_file() and not f.is_symlink():
                    opt_files.add(str(f.relative_to(optimized_dir)))
        report.stats["optimizedFiles"] = len(opt_files)

        view_files: set[str] = set()
        if views_dir.is_dir():
            for f in views_dir.rglob("*"):
                if f.is_symlink():
                    view_files.add(str(f.relative_to(views_dir)))
                    if not f.exists():
                        report.add(
                            "error",
                            "broken-link",
                            f"Link quebrado: {f} -> {os.readlink(str(f))}",
                        )
        report.stats["viewLinks"] = len(view_files)

        orphan_masters = 0
        for master_rel in master_files:
            master_path = masters_dir / master_rel
            found = any(
                (optimized_dir / p).exists()
                for p in opt_files
                if _optimized_from_master(optimized_dir / p, master_path)
            )
            if not found:
                orphan_masters += 1
        report.stats["orphanMasters"] = orphan_masters

        for game_id in self._registry.entries:
            if not any(
                (optimized_dir / p).is_file()
                for p in opt_files
                if game_id in p
            ):
                mstr = self._registry.entries[game_id]
                if mstr.confirmed:
                    report.add(
                        "warning",
                        "optimized-missing",
                        f"Jogo {game_id} ({mstr.canonical_name}) sem optimized",
                    )

        report.add("info", "audit-complete", f"Auditoria concluída: {report.stats}")
        return report

    def plan_prune_orphan_cache(self) -> transaction.Plan:
        """Planeja remover somente masters sem referência no registro canônico."""
        masters_dir = self._media_root / "masters"
        referenced = {
            (self._media_root / relpath).resolve(strict=False)
            for entry in self._registry.entries.values()
            for relpath in entry.masters.values()
        }
        removals: set[Path] = set()
        if masters_dir.is_dir() and not masters_dir.is_symlink():
            for candidate in masters_dir.rglob("*"):
                if not candidate.is_file() or candidate.is_symlink():
                    continue
                resolved = candidate.resolve(strict=True)
                if (
                    resolved.is_relative_to(masters_dir.resolve(strict=True))
                    and resolved not in referenced
                ):
                    removals.add(resolved)
        return transaction.plan_write_files(
            {},
            removals=removals,
            root=self._media_root,
            kind="media.prune-orphan-cache",
        )

    def _find_optimized(self, game_id: str, profile: str) -> Path | None:
        opt_root = self._media_root / "optimized" / "switch" / profile
        if not opt_root.is_dir():
            return None
        for f in opt_root.iterdir():
            if f.is_file() and game_id in f.name:
                return f.relative_to(self._media_root)
        return None

    def get_registry_entry(self, game_id: str) -> MediaMasterEntry | None:
        return self._registry.get_entry(game_id)

    def find_optimized(self, game_id: str, profile: str) -> Path | None:
        return self._find_optimized(game_id, profile)


def _validate_image_magic(data: bytes) -> bool:
    if len(data) < 8:
        return False
    return (
        data.startswith(b"\x89PNG\r\n\x1a\n")
        or data.startswith(b"\xff\xd8\xff")
        or (data.startswith(b"RIFF") and data[8:12] == b"WEBP")
    )


def _valid_image_file(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            return _validate_image_magic(stream.read(12))
    except OSError:
        return False


def _steam_stem(appid: int, profile: str) -> str:
    suffixes = {
        "steam-portrait": "p",
        "steam-landscape": "",
        "steam-hero": "_hero",
        "steam-logo": "_logo",
        "steam-icon": "_icon",
    }
    suffix = suffixes.get(profile, "")
    return f"{appid}{suffix}"


def _is_managed(path: Path, optimized_root: Path | None = None) -> bool:
    try:
        if path.is_symlink():
            if optimized_root is None:
                return True
            resolved = path.resolve(strict=True)
            return resolved.is_file() and fs.is_within(optimized_root.resolve(), resolved)
        content = path.read_bytes()
        return _OWNERSHIP_MARKER.encode() in content
    except OSError:
        return False


def _publish_link(source: Path, target: Path) -> bool:
    try:
        if target.is_symlink() or target.exists():
            fs.remove_file(target)
        fs.symlink_atomic(source, target)
        return True
    except OSError:
        try:
            data = source.read_bytes() + f"\n{_OWNERSHIP_MARKER}\n".encode()
            fs.write_atomic(target, data)
            return True
        except OSError:
            return False


def _detect_pillow() -> bool:
    import importlib.util
    return importlib.util.find_spec("PIL") is not None


def _optimize_pillow(src: Path, dst: Path, profile: str) -> bool:
    from PIL import Image, ImageOps

    width, height, _ = STEAM_PROFILES.get(profile, (128, 128, "ui_preview"))
    try:
        src_img = Image.open(src)
        work_img = ImageOps.exif_transpose(src_img) or src_img
        rgba = work_img.convert("RGBA")
        lanczos = Image.LANCZOS if hasattr(Image, "LANCZOS") else Image.Resampling.LANCZOS
        resized = ImageOps.fit(rgba, (width, height), method=lanczos)
        resized.save(dst, format="PNG" if dst.suffix.lower() == ".png" else "JPEG", quality=95)
        return True
    except Exception:
        return False


def _optimized_from_master(opt_path: Path, master_path: Path) -> bool:
    try:
        return opt_path.stat().st_size > 0
    except OSError:
        return False
