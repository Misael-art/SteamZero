# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify generated multi-disc projections against the current scan result."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from steamzero.core import fs
from steamzero.domain.multidisc import MultiDiscResolution
from steamzero.domain.multidisc_artifacts import OWNERSHIP_MARKER

_SET_PREFIX = "# SteamZero-MultiDisc-Set: "
_DISC_PREFIX = "# SteamZero-MultiDisc-Disc: "


@dataclass(frozen=True)
class ManagedMultiDiscProjection:
    """A current generated descriptor tied to a scan's reconciled set."""

    descriptor_path: Path
    set_id: str
    entries: tuple[Path, ...]


def _expected_member_path(descriptor: Path, index: int, media_format: str) -> Path:
    return descriptor.parent / f"disk-{index:02d}.{media_format.casefold()}"


def read_managed_descriptor(
    path: Path,
    *,
    root: Path,
    logical_set: MultiDiscResolution,
) -> ManagedMultiDiscProjection | None:
    """Accept only the exact materializer output for this current set.

    Ownership comments alone are not proof: the set id, disc identities,
    relative paths, and materialized bytes must match the current archive scan.
    """

    if (
        logical_set.state != "needs-extraction"
        or path.is_symlink()
        or not path.is_file()
        or path.suffix.casefold() != ".m3u"
    ):
        return None
    derived = root / ".steamzero" / "derived"
    platform_root = derived / logical_set.platform_id
    if derived.is_symlink() or platform_root.is_symlink() or path.parent.is_symlink():
        return None
    try:
        resolved_path = path.resolve(strict=True)
        resolved_derived = derived.resolve(strict=True)
        resolved_path.relative_to(resolved_derived)
        resolved_path.relative_to(platform_root.resolve(strict=True))
    except (OSError, ValueError):
        return None

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    if len(lines) != 2 + 2 * len(logical_set.parts):
        return None
    if lines[0] != OWNERSHIP_MARKER or lines[1] != f"{_SET_PREFIX}{logical_set.set_id}":
        return None

    entries: list[Path] = []
    for index, part in enumerate(logical_set.parts, start=1):
        marker = lines[2 + (index - 1) * 2]
        raw_path = lines[3 + (index - 1) * 2]
        if marker != f"{_DISC_PREFIX}{logical_set.set_id}:disc-{index}":
            return None
        try:
            relative = fs.validate_relative_entry(raw_path)
            expected = _expected_member_path(path, index, part.format)
            candidate = path.parent / relative
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(path.parent.resolve(strict=True))
            expected_resolved = expected.resolve(strict=True)
        except (OSError, ValueError):
            return None
        if candidate.is_symlink() or resolved != expected_resolved or not candidate.is_file():
            return None
        expected_hash = part.member_hash or part.content_hash
        if expected_hash is None:
            return None
        try:
            if fs.hash_file(candidate) != expected_hash:
                return None
        except OSError:
            return None
        entries.append(candidate)

    return ManagedMultiDiscProjection(path, logical_set.set_id, tuple(entries))


def discover_managed_projection(
    root: Path, logical_set: MultiDiscResolution
) -> ManagedMultiDiscProjection | None:
    """Find one valid descriptor under the declared platform's derived tree."""

    derived_platform = root / ".steamzero" / "derived" / logical_set.platform_id
    derived_root = root / ".steamzero" / "derived"
    if (
        not root.is_dir()
        or root.is_symlink()
        or derived_root.is_symlink()
        or not derived_platform.is_dir()
        or derived_platform.is_symlink()
    ):
        return None
    matches: list[ManagedMultiDiscProjection] = []
    for path in sorted(derived_platform.rglob("*.m3u"), key=lambda item: str(item).casefold()):
        projection = read_managed_descriptor(path, root=root, logical_set=logical_set)
        if projection is not None:
            matches.append(projection)
            if len(matches) > 1:
                return None
    return matches[0] if matches else None


__all__ = ["ManagedMultiDiscProjection", "discover_managed_projection", "read_managed_descriptor"]
