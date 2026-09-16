# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Declarative, read-only multi-disc resolution.

The resolver deliberately knows nothing about emulators or the State Store.
It turns a platform manifest plus observed files into a bounded proposal.  A
playlist is only safe to create when the platform and its adapter have
explicitly declared the descriptor contract.
"""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from steamzero.core import fs

MultiDiscState = Literal[
    "ready",
    "incomplete",
    "ambiguous",
    "conflict",
    "stale",
    "needs-extraction",
    "needs-platform-contract",
    "needs-companion-descriptor",
]

_DISC_MARKER = re.compile(
    r"(?P<open>[\[(])?\s*(?P<kind>disc|disk)\s*(?P<number>\d+)"
    r"(?:\s+of\s+(?P<total>\d+))?\s*(?P<close>[\])])?",
    re.IGNORECASE,
)
_CD_MARKER = re.compile(r"(?<![A-Za-z])cd\s*(?P<number>\d+)(?!\d)", re.IGNORECASE)
_SIDE_MARKER = re.compile(r"(?<![A-Za-z])side\s*(?P<side>[AB])(?![A-Za-z])", re.IGNORECASE)
_EMPTY_DELIMITERS = re.compile(r"\(\s*\)|\[\s*\]")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class MultiDiscPolicy:
    enabled: bool
    descriptor: str
    media: tuple[str, ...]
    filename_patterns: tuple[str, ...]
    requires_continuous_sequence: bool
    allow_side_labels: bool = False

    @classmethod
    def from_manifest(cls, manifest: Mapping[str, object]) -> MultiDiscPolicy:
        raw = manifest.get("multiDisc")
        if not isinstance(raw, Mapping):
            media = manifest.get("media")
            raw = media.get("multiDisc") if isinstance(media, Mapping) else None
        if not isinstance(raw, Mapping):
            return cls(False, "", (), (), True)
        values = raw.get("media")
        media = tuple(
            sorted(
                {
                    value.casefold().lstrip(".")
                    for value in values
                    if isinstance(value, str) and value.strip()
                }
            )
            if isinstance(values, Sequence) and not isinstance(values, (str, bytes, bytearray))
            else ()
        )
        patterns = raw.get("filenamePatterns")
        filename_patterns = tuple(
            sorted(
                {value.casefold() for value in patterns if isinstance(value, str) and value.strip()}
            )
            if isinstance(patterns, Sequence) and not isinstance(patterns, (str, bytes, bytearray))
            else ()
        )
        return cls(
            enabled=raw.get("enabled") is True,
            descriptor=(raw.get("descriptor") or "").casefold()
            if isinstance(raw.get("descriptor"), str)
            else "",
            media=media,
            filename_patterns=filename_patterns,
            requires_continuous_sequence=raw.get("requiresContinuousSequence", True) is True,
            allow_side_labels=raw.get("allowSideLabels") is True,
        )


@dataclass(frozen=True)
class DiscMarker:
    number: int
    total: int | None
    kind: str
    label: str = ""


@dataclass(frozen=True)
class MultiDiscPart:
    path: Path
    number: int
    total: int | None
    format: str = ""
    content_hash: str | None = None


DiscLifecycle = Literal["active", "converted", "missing", "stale", "conflict"]


@dataclass(frozen=True)
class DiscRecord:
    """Stable identity and current projection of one physical disc."""

    set_id: str
    disc_number: int
    disc_total: int
    format: str
    path: Path | None
    content_hash: str | None
    accepted_formats: tuple[str, ...]
    state: DiscLifecycle
    conversion_history: tuple[Mapping[str, str], ...] = ()

    @property
    def identity(self) -> str:
        return f"{self.set_id}:disc-{self.disc_number}"


@dataclass(frozen=True)
class MultiDiscSet:
    """Canonical logical set; the descriptor is only a derived projection."""

    set_id: str
    platform_id: str
    system_id: str
    normalized_title: str
    discs: tuple[DiscRecord, ...]
    descriptor_path: Path | None = None
    descriptor_hash: str | None = None
    descriptor_origin: Literal["user", "generated"] | None = None
    descriptor_state: Literal["current", "stale", "conflict", "missing"] = "missing"


@dataclass(frozen=True)
class MultiDiscResolution:
    state: MultiDiscState
    platform_id: str
    system_id: str
    normalized_title: str
    display_title: str
    group_key: str
    parts: tuple[MultiDiscPart, ...]
    descriptor_path: Path | None = None
    descriptor_origin: Literal["user", "generated"] | None = None
    reason: str = ""

    @property
    def disc_total(self) -> int:
        return len(self.parts)

    @property
    def set_id(self) -> str:
        return self.group_key


def _clean_title(value: str) -> str:
    value = _EMPTY_DELIMITERS.sub(" ", value)
    return _WHITESPACE.sub(" ", value).strip(" -_")


def _normalise_title(value: str) -> str:
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value).casefold()).strip()


def parse_disc_marker(stem: str, policy: MultiDiscPolicy) -> tuple[str, DiscMarker] | None:
    """Extract one supported marker and remove only that marker from a title."""

    match = _DISC_MARKER.search(stem)
    if match is not None and {"disc", "disk"} & set(policy.filename_patterns or ("disc", "disk")):
        return _clean_title(stem[: match.start()] + stem[match.end() :]), DiscMarker(
            number=int(match.group("number")),
            total=int(match.group("total")) if match.group("total") else None,
            kind=match.group("kind").casefold(),
        )
    match = _CD_MARKER.search(stem)
    if match is not None and "cd" in policy.filename_patterns:
        return _clean_title(stem[: match.start()] + stem[match.end() :]), DiscMarker(
            number=int(match.group("number")), total=None, kind="cd"
        )
    if policy.allow_side_labels and "side" in policy.filename_patterns:
        match = _SIDE_MARKER.search(stem)
        if match is not None:
            side = match.group("side").casefold()
            return _clean_title(stem[: match.start()] + stem[match.end() :]), DiscMarker(
                number=1 if side == "a" else 2, total=2, kind="side", label=side.upper()
            )
    return None


def _safe_regular_file(path: Path) -> bool:
    try:
        return not path.is_symlink() and path.is_file()
    except OSError:
        return False


def _format_for(path: Path) -> str:
    return path.suffix.casefold().lstrip(".")


def _content_hash(path: Path) -> str | None:
    """Read the physical content hash without turning scan failures into writes."""

    try:
        return fs.hash_file(path)
    except OSError:
        return None


def _group_key(platform_id: str, system_id: str, title: str) -> str:
    return ":".join((platform_id, system_id, _normalise_title(title)))


def _resolution(
    *,
    state: MultiDiscState,
    platform_id: str,
    system_id: str,
    title: str,
    parts: Sequence[MultiDiscPart] = (),
    descriptor_path: Path | None = None,
    descriptor_origin: Literal["user", "generated"] | None = None,
    reason: str = "",
) -> MultiDiscResolution:
    return MultiDiscResolution(
        state=state,
        platform_id=platform_id,
        system_id=system_id,
        normalized_title=_normalise_title(title),
        display_title=title,
        group_key=_group_key(platform_id, system_id, title),
        parts=tuple(sorted(parts, key=lambda part: part.number)),
        descriptor_path=descriptor_path,
        descriptor_origin=descriptor_origin,
        reason=reason,
    )


def resolve_multidisc(
    platform_id: str,
    system_id: str,
    files: Sequence[Path],
    manifest: Mapping[str, object],
    *,
    existing_descriptor: Path | None = None,
    existing_descriptor_managed: bool = False,
) -> tuple[MultiDiscResolution, ...]:
    """Resolve all candidate sets without writing or mutating user content."""

    policy = MultiDiscPolicy.from_manifest(manifest)
    groups: dict[str, list[tuple[Path, DiscMarker, str]]] = defaultdict(list)
    for path in files:
        if path.suffix.casefold().lstrip(".") in {"m3u", "cue"}:
            continue
        parsed = parse_disc_marker(path.stem, policy)
        if parsed is None:
            continue
        title, marker = parsed
        groups[_group_key(platform_id, system_id, title)].append((path, marker, title))

    if not groups:
        return ()
    results: list[MultiDiscResolution] = []
    for key in sorted(groups):
        entries = groups[key]
        title = entries[0][2]
        parts = tuple(
            MultiDiscPart(
                path,
                marker.number,
                marker.total,
                _format_for(path),
                _content_hash(path),
            )
            for path, marker, _ in entries
        )
        if not policy.enabled or policy.descriptor != "m3u":
            results.append(
                _resolution(
                    state="needs-platform-contract",
                    platform_id=platform_id,
                    system_id=system_id,
                    title=title,
                    parts=parts,
                    reason="A plataforma não declarou um contrato de playlist m3u.",
                )
            )
            continue
        if len(parts) < 2:
            continue
        if any(not _safe_regular_file(part.path) or part.content_hash is None for part in parts):
            results.append(
                _resolution(
                    state="ambiguous",
                    platform_id=platform_id,
                    system_id=system_id,
                    title=title,
                    parts=parts,
                    reason="O conjunto contém arquivo ausente, irregular ou symlink.",
                )
            )
            continue
        suffixes = {_format_for(part.path) for part in parts}
        if not suffixes.issubset(policy.media):
            archive_formats = {"zip", "7z", "rar"}
            media = manifest.get("media")
            container_policy = (
                str(media.get("containerPolicy") or "") if isinstance(media, Mapping) else ""
            )
            if suffixes & archive_formats and container_policy == "extract":
                state: MultiDiscState = "needs-extraction"
                reason = "O adapter exige extração antes de uma playlist m3u."
            else:
                state = "needs-platform-contract"
                reason = "O adapter não declarou suporte aos formatos encontrados."
            results.append(
                _resolution(
                    state=state,
                    platform_id=platform_id,
                    system_id=system_id,
                    title=title,
                    parts=parts,
                    reason=reason,
                )
            )
            continue
        numbers = [part.number for part in parts]
        if len(numbers) != len(set(numbers)):
            state = "ambiguous"
            reason = "O conjunto contém números de disco duplicados."
        elif numbers[0] != 1 or (
            policy.requires_continuous_sequence and numbers != list(range(1, len(numbers) + 1))
        ):
            state = "incomplete"
            reason = "A sequência de discos não começa em 1 ou contém lacunas."
        elif any(part.total is not None and part.total != len(parts) for part in parts):
            state = "incomplete"
            reason = "O total declarado pelos nomes não corresponde ao conjunto."
        elif existing_descriptor is not None and not existing_descriptor_managed:
            state = "conflict"
            reason = "Já existe uma playlist não gerenciada pelo SteamZero."
        else:
            state = "ready"
            reason = "Conjunto contínuo e compatível; playlist pode ser planejada."
        results.append(
            _resolution(
                state=state,
                platform_id=platform_id,
                system_id=system_id,
                title=title,
                parts=parts,
                descriptor_path=existing_descriptor,
                descriptor_origin=("user" if not existing_descriptor_managed else "generated")
                if existing_descriptor is not None
                else None,
                reason=reason,
            )
        )
    return tuple(results)


def reconcile_multidisc_set(
    resolution: MultiDiscResolution,
    existing: MultiDiscSet | None = None,
    *,
    explicit_links: Mapping[str, str] | None = None,
) -> MultiDiscSet:
    """Reconcile observed media with stable identities, never by name alone.

    Set identity and disc number are authoritative.  A changed hash/path is a
    conversion of the same disc when that identity is already known; a new
    number is a new active disc.  Name matching is intentionally not performed
    here: callers may create an explicit link after a reviewed conversion.
    """

    previous = {disc.disc_number: disc for disc in existing.discs} if existing else {}
    links = dict(explicit_links or {})
    observed_numbers = {part.number for part in resolution.parts}
    records: list[DiscRecord] = []
    total = max(resolution.disc_total, max(previous, default=0))
    for part in resolution.parts:
        old = previous.get(part.number)
        old_link = links.get(str(part.path))
        if old is not None and old_link not in {None, old.identity}:
            state: DiscLifecycle = "conflict"
            history = old.conversion_history
        elif old is not None and old.content_hash == part.content_hash:
            state = "active"
            history = old.conversion_history
        elif old is not None and old.content_hash is not None and part.content_hash is not None:
            state = "converted"
            history = (
                *old.conversion_history,
                {
                    "fromHash": old.content_hash,
                    "fromFormat": old.format,
                    "toHash": part.content_hash,
                    "toFormat": part.format or _format_for(part.path),
                },
            )
        else:
            state = "active"
            history = old.conversion_history if old is not None else ()
        accepted_formats = (
            old.accepted_formats if old is not None else (part.format or _format_for(part.path),)
        )
        current_format = part.format or _format_for(part.path)
        if current_format not in accepted_formats:
            state = "conflict"
        records.append(
            DiscRecord(
                set_id=resolution.set_id,
                disc_number=part.number,
                disc_total=total,
                format=part.format or _format_for(part.path),
                path=part.path,
                content_hash=part.content_hash,
                accepted_formats=tuple(sorted(set(accepted_formats))),
                state=state,
                conversion_history=history,
            )
        )
    for number, old in previous.items():
        if number not in observed_numbers:
            records.append(
                DiscRecord(
                    set_id=old.set_id,
                    disc_number=old.disc_number,
                    disc_total=old.disc_total,
                    format=old.format,
                    path=old.path,
                    content_hash=old.content_hash,
                    accepted_formats=old.accepted_formats,
                    state="missing",
                    conversion_history=old.conversion_history,
                )
            )
    records.sort(key=lambda disc: disc.disc_number)
    descriptor_state: Literal["current", "stale", "conflict", "missing"] = "missing"
    if resolution.descriptor_path is not None:
        descriptor_state = "conflict" if resolution.state == "conflict" else "current"
    return MultiDiscSet(
        set_id=resolution.set_id,
        platform_id=resolution.platform_id,
        system_id=resolution.system_id,
        normalized_title=resolution.normalized_title,
        discs=tuple(records),
        descriptor_path=resolution.descriptor_path,
        descriptor_origin=resolution.descriptor_origin,
        descriptor_state=descriptor_state,
    )


__all__ = [
    "DiscLifecycle",
    "DiscMarker",
    "DiscRecord",
    "MultiDiscPart",
    "MultiDiscPolicy",
    "MultiDiscResolution",
    "MultiDiscSet",
    "MultiDiscState",
    "parse_disc_marker",
    "reconcile_multidisc_set",
    "resolve_multidisc",
]
