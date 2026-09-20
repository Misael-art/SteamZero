# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Plan and safely import local RetroFE artwork into the AURA media registry.

RetroFE stores artwork below a collection directory, while the canonical
library stores a technical platform id and a stable game id.  This module is
the deliberately boring bridge between those two identities.  It only accepts
regular files below an allowlisted asset directory, requires a unique title
match within a platform, and never replaces an existing master by default.

The importer is intentionally plan-first: callers can inspect every decision
before applying it.  It does not download, execute, extract, or remove files.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from steamzero.core import fs
from steamzero.core.title_variants import title_variants
from steamzero.domain.media_registry import MediaMasterEntry, MediaRegistry

_PLATFORM_BY_COLLECTION: dict[str, str] = {
    "commodore amiga": "amiga",
    "nintendo entertainment system": "nes-famicom",
    "nintendo famicom": "nes-famicom",
    "nintendo super famicom": "snes",
    "super nintendo entertainment system": "snes",
    "nintendo switch": "switch",
    "sharp x68000": "x68000",
    "sony playstation": "playstation",
    "sony playstation 2": "playstation-2",
}

_ASSET_KIND_BY_DIRECTORY: dict[str, str] = {
    "artwork_front": "box2d",
    "box": "box2d",
    "cover": "box2d",
    "medium_front": "box2d",
    "screentitle": "box2d",
    "fanart": "fanart",
    "screenshot": "screenshot",
    "screenshots": "screenshot",
    "video": "video",
    "videos": "video",
}
_SUPPORTED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".avif", ".mp4", ".webm"})
_SAFE_COMPONENT = re.compile(r"[^\w]+", re.UNICODE)


def collection_platform(name: str) -> str | None:
    """Resolve a RetroFE collection name without guessing user collections."""

    normalized = _normalize_text(name)
    for collection, platform in _PLATFORM_BY_COLLECTION.items():
        if normalized == collection or normalized.startswith(collection + " "):
            return platform
    return None


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value)).casefold()
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(_SAFE_COMPONENT.sub(" ", without_marks).split())


def _asset_kind(path: Path) -> str | None:
    for component in reversed(path.parts[:-1]):
        directory = component.casefold()
        kind = _ASSET_KIND_BY_DIRECTORY.get(directory)
        if kind is None and directory.startswith("fanart"):
            kind = "fanart"
        if kind is None and directory.startswith("screenshot"):
            kind = "screenshot"
        if kind:
            return kind
    return None


def _asset_title(path: Path) -> str:
    return path.stem


def _variant_keys(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(_normalize_text(variant) for variant in title_variants(value)))


def _match_score(game: Mapping[str, object], asset_title: str) -> int:
    names: list[str] = [str(game.get("name") or game.get("title") or "")]
    variants = game.get("titleVariants")
    if isinstance(variants, Sequence) and not isinstance(variants, (str, bytes)):
        names.extend(str(value) for value in variants)
    game_keys = tuple(dict.fromkeys(key for name in names for key in _variant_keys(name) if key))
    asset_keys = _variant_keys(asset_title)
    if not game_keys or not asset_keys:
        return 0
    if set(game_keys) & set(asset_keys):
        return 100
    # A clean RetroFE filename may omit region/translation tags.  Permit this
    # only as a lower-confidence match; plan() still rejects ties.
    game_clean = _normalize_text(game_keys[-1])
    asset_clean = _normalize_text(asset_keys[-1])
    if game_clean and game_clean == asset_clean:
        return 80
    return 0


@dataclass(frozen=True)
class RetroFEAsset:
    source: Path
    collection: str
    platform_id: str
    kind: str
    title: str
    sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "source": str(self.source),
            "collection": self.collection,
            "platformId": self.platform_id,
            "kind": self.kind,
            "title": self.title,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class ImportDecision:
    state: str
    asset: RetroFEAsset
    game_id: str = ""
    game_title: str = ""
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "gameId": self.game_id,
            "gameTitle": self.game_title,
            "reason": self.reason,
            "asset": self.asset.to_dict(),
        }


@dataclass(frozen=True)
class RetroFEImportPlan:
    source_root: Path
    decisions: tuple[ImportDecision, ...]

    @property
    def accepted(self) -> tuple[ImportDecision, ...]:
        return tuple(decision for decision in self.decisions if decision.state == "accepted")

    def to_dict(self) -> dict[str, object]:
        counts: dict[str, int] = defaultdict(int)
        for decision in self.decisions:
            counts[decision.state] += 1
        return {
            "sourceRoot": str(self.source_root),
            "counts": dict(sorted(counts.items())),
            "decisions": [decision.to_dict() for decision in self.decisions],
        }


@dataclass(frozen=True)
class ImportResult:
    imported: tuple[str, ...] = ()
    skipped_existing: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()


def _iter_assets(source_root: Path) -> Iterable[RetroFEAsset]:
    if not source_root.is_dir() or source_root.is_symlink():
        return ()
    assets: list[RetroFEAsset] = []
    for collection_dir in sorted(source_root.iterdir(), key=lambda path: path.name.casefold()):
        if not collection_dir.is_dir() or collection_dir.is_symlink():
            continue
        platform_id = collection_platform(collection_dir.name)
        if not platform_id:
            continue
        artwork_root = collection_dir / "medium_artwork"
        if not artwork_root.is_dir() or artwork_root.is_symlink():
            continue
        for path in sorted(artwork_root.rglob("*"), key=lambda item: str(item).casefold()):
            if (
                not path.is_file()
                or path.is_symlink()
                or path.suffix.casefold() not in _SUPPORTED_EXTENSIONS
            ):
                continue
            kind = _asset_kind(path.relative_to(artwork_root))
            if not kind:
                continue
            data = path.read_bytes()
            assets.append(
                RetroFEAsset(
                    source=path,
                    collection=collection_dir.name,
                    platform_id=platform_id,
                    kind=kind,
                    title=_asset_title(path),
                    sha256=hashlib.sha256(data).hexdigest(),
                )
            )
    return assets


def plan_import(source_root: Path, games: Sequence[Mapping[str, object]]) -> RetroFEImportPlan:
    """Create a deterministic import plan from a library read model."""

    by_platform: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for game in games:
        if str(game.get("contentKind") or "base") != "base":
            continue
        game_id = str(game.get("id") or "")
        title = str(game.get("name") or game.get("title") or "")
        platform = str(game.get("platform") or game.get("platformId") or "")
        if game_id and title and platform:
            by_platform[platform].append(game)

    decisions: list[ImportDecision] = []
    for asset in _iter_assets(source_root):
        candidates = by_platform.get(asset.platform_id, [])
        scored = sorted(
            ((_match_score(game, asset.title), game) for game in candidates),
            key=lambda pair: (-pair[0], str(pair[1].get("id") or "")),
        )
        if not scored or scored[0][0] == 0:
            decisions.append(ImportDecision("unmatched", asset, reason="no-title-match"))
            continue
        top_score = scored[0][0]
        top = [game for score, game in scored if score == top_score]
        if len(top) != 1:
            decisions.append(ImportDecision("ambiguous", asset, reason="title-match-tie"))
            continue
        game = top[0]
        decisions.append(
            ImportDecision(
                "accepted",
                asset,
                game_id=str(game["id"]),
                game_title=str(game.get("name") or game.get("title") or ""),
            )
        )
    return RetroFEImportPlan(source_root=source_root, decisions=tuple(decisions))


def apply_import(
    plan: RetroFEImportPlan,
    media_root: Path,
    games_by_id: Mapping[str, Mapping[str, object]],
    *,
    replace: bool = False,
) -> ImportResult:
    """Publish accepted assets without deleting or replacing by default."""

    registry = MediaRegistry.load(media_root)
    imported: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []
    for decision in plan.accepted:
        game = games_by_id.get(decision.game_id)
        if game is None:
            failed.append(f"{decision.game_id}:missing-library-record")
            continue
        previous = registry.get_entry(decision.game_id)
        masters = dict(previous.masters) if previous else {}
        if decision.asset.kind in masters and not replace:
            skipped.append(f"{decision.game_id}:{decision.asset.kind}")
            continue
        try:
            data = decision.asset.source.read_bytes()
            if hashlib.sha256(data).hexdigest() != decision.asset.sha256:
                raise ValueError("source-changed-after-plan")
            extension = decision.asset.source.suffix.casefold()
            if extension == ".jpeg":
                extension = ".jpg"
            relative = (
                Path("masters")
                / decision.asset.platform_id
                / decision.asset.kind
                / (decision.asset.sha256 + extension)
            )
            target = media_root / relative
            fs.ensure_dir(target.parent)
            if not target.is_file():
                fs.write_atomic(target, data)
            masters[decision.asset.kind] = relative.as_posix()
            entry = MediaMasterEntry(
                game_id=decision.game_id,
                title_id=str(game.get("titleId") or ""),
                fingerprint=str(game.get("fingerprint") or ""),
                canonical_name=str(game.get("name") or game.get("title") or ""),
                platform_id=decision.asset.platform_id,
                aliases=previous.aliases if previous else (),
                metadata_origin="retrofe-local",
                confirmed=True,
                provenance=previous.provenance if previous else None,
                masters=masters,
            )
            registry.add_entry(entry)
            existing_platform = registry.platforms.get(decision.asset.platform_id)
            existing_kinds = existing_platform.kinds if existing_platform else ()
            registry.register_platform(
                decision.asset.platform_id,
                decision.asset.platform_id,
                tuple(sorted(set(existing_kinds) | {decision.asset.kind})),
            )
            imported.append(f"{decision.game_id}:{decision.asset.kind}")
        except (OSError, ValueError) as exc:
            failed.append(f"{decision.game_id}:{decision.asset.kind}:{exc}")
    if imported:
        registry.save(media_root)
    return ImportResult(tuple(imported), tuple(skipped), tuple(failed))
