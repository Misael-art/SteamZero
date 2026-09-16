# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Declarative, read-only multi-disc resolution.

The resolver deliberately knows nothing about emulators or the State Store.
It turns a platform manifest plus observed files into a bounded proposal.  A
playlist is only safe to create when the platform and its adapter have
explicitly declared the descriptor contract.
"""

from __future__ import annotations

import hashlib
import re
import stat
import unicodedata
import zipfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Literal

from steamzero.core import fs, safezip
from steamzero.core.errors import SteamZeroError

MultiDiscState = Literal[
    "ready",
    "incomplete",
    "ambiguous",
    "conflict",
    "stale",
    "needs-extraction",
    "needs-platform-contract",
    "needs-companion-descriptor",
    "needs-review",
]

_DISC_MARKER = re.compile(
    r"(?P<open>[\[(])?\s*(?P<kind>disc|disk)\s*(?P<number>\d+)"
    r"(?:\s+of\s+(?P<total>\d+))?\s*(?P<close>[\])])?",
    re.IGNORECASE,
)
_CD_MARKER = re.compile(r"(?<![A-Za-z])cd\s*(?P<number>\d+)(?!\d)", re.IGNORECASE)
_SIDE_MARKER = re.compile(r"(?<![A-Za-z])side\s*(?P<side>[AB])(?![A-Za-z])", re.IGNORECASE)
_LABEL_MARKER = re.compile(
    r"(?<![A-Za-z])(?:disc|disk)\s*(?P<label>[A-Z])(?![A-Za-z])", re.IGNORECASE
)
_ROLE_MARKER = re.compile(
    r"(?<![A-Za-z])(?P<role>system|program|data|user|opening|ending|boot|install)"
    r"(?:\s+disk)?(?:\s+(?P<label>[A-Z]))?(?![A-Za-z])",
    re.IGNORECASE,
)
_EMPTY_DELIMITERS = re.compile(r"\(\s*\)|\[\s*\]")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class MultiDiscPolicy:
    enabled: bool
    descriptor: str
    media: tuple[str, ...]
    filename_patterns: tuple[str, ...]
    requires_continuous_sequence: bool
    container_policy: Literal["native", "extract", ""] = ""
    allow_side_labels: bool = False
    ordering_model: Literal["ordinal", "ordinal-and-role", "role"] = "ordinal"
    allowed_disc_labels: tuple[str, ...] = ()
    adapter_playlist_support: Literal["proven", "unproven", "unsupported"] = "proven"
    archive_member_formats: tuple[str, ...] = ()
    letter_labels_are_ordinal: bool = False
    role_order: tuple[str, ...] = ()

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
        labels = raw.get("allowedDiscLabels")
        allowed_labels = tuple(
            sorted({value.casefold() for value in labels if isinstance(value, str)})
            if isinstance(labels, Sequence) and not isinstance(labels, (str, bytes, bytearray))
            else ()
        )
        archive_policy = raw.get("archiveMemberPolicy")
        archive_formats = (
            archive_policy.get("allowedFormats") if isinstance(archive_policy, Mapping) else None
        )
        role_order_raw = raw.get("roleOrder")
        role_order_values: Sequence[object] = (
            role_order_raw
            if isinstance(role_order_raw, Sequence)
            and not isinstance(role_order_raw, (str, bytes, bytearray))
            else ()
        )
        adapter_support = raw.get("adapterPlaylistSupport", "proven")
        ordering_model = raw.get("orderingModel", "ordinal")
        manifest_media = manifest.get("media")
        container_policy_raw = (
            manifest_media.get("containerPolicy") if isinstance(manifest_media, Mapping) else ""
        )
        container_policy: Literal["native", "extract", ""] = ""
        if str(container_policy_raw) == "native":
            container_policy = "native"
        elif str(container_policy_raw) == "extract":
            container_policy = "extract"
        return cls(
            enabled=raw.get("enabled") is True,
            descriptor=(raw.get("descriptor") or "").casefold()
            if isinstance(raw.get("descriptor"), str)
            else "",
            media=media,
            filename_patterns=filename_patterns,
            requires_continuous_sequence=raw.get("requiresContinuousSequence", True) is True,
            container_policy=container_policy,
            allow_side_labels=raw.get("allowSideLabels") is True,
            ordering_model=(
                ordering_model
                if ordering_model in {"ordinal", "ordinal-and-role", "role"}
                else "ordinal"
            ),
            allowed_disc_labels=allowed_labels,
            adapter_playlist_support=(
                adapter_support
                if adapter_support in {"proven", "unproven", "unsupported"}
                else "proven"
            ),
            archive_member_formats=tuple(
                sorted(
                    {
                        value.casefold().lstrip(".")
                        for value in archive_formats
                        if isinstance(value, str) and value.strip()
                    }
                )
                if isinstance(archive_formats, Sequence)
                and not isinstance(archive_formats, (str, bytes, bytearray))
                else ()
            ),
            letter_labels_are_ordinal=(
                isinstance(archive_policy, Mapping)
                and archive_policy.get("letterLabelsAreOrdinal") is True
            ),
            role_order=tuple(
                value.casefold() for value in role_order_values if isinstance(value, str)
            ),
        )


@dataclass(frozen=True)
class DiscMarker:
    number: int | None
    total: int | None
    kind: str
    label: str = ""
    role: str | None = None


@dataclass(frozen=True)
class MultiDiscPart:
    path: Path
    number: int | None
    total: int | None
    format: str = ""
    content_hash: str | None = None
    disc_label: str = ""
    disc_role: str | None = None
    archive_path: Path | None = None
    member_path: str | None = None
    member_hash: str | None = None
    archive_hash: str | None = None
    source_origin: Literal["user", "generated"] = "user"

    @property
    def adapter_order(self) -> int | None:
        """Return the stable order implied by the ordinal contract."""

        return self.number


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
    disc_label: str = ""
    disc_role: str | None = None
    archive_path: Path | None = None
    member_path: str | None = None
    member_hash: str | None = None
    archive_hash: str | None = None
    source_origin: Literal["user", "generated"] = "user"

    @property
    def adapter_order(self) -> int:
        """Return the persisted disc order used by the adapter projection."""

        return self.disc_number

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
        declared = {part.total for part in self.parts if part.total is not None}
        return next(iter(declared)) if len(declared) == 1 else len(self.parts)

    @property
    def set_id(self) -> str:
        return self.group_key


def _clean_title(value: str) -> str:
    value = _EMPTY_DELIMITERS.sub(" ", value)
    return _WHITESPACE.sub(" ", value).strip(" -_")


def _normalise_title(value: str) -> str:
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", value).casefold()).strip()


def parse_disc_marker(stem: str, policy: MultiDiscPolicy) -> tuple[str, DiscMarker] | None:
    """Extract ordinal, letter and semantic role markers from one title."""

    spans: list[tuple[int, int]] = []
    number: int | None = None
    total: int | None = None
    kind = ""
    label = ""
    role: str | None = None
    numeric = _DISC_MARKER.search(stem)
    if numeric is not None and {"disc", "disk"} & set(policy.filename_patterns or ("disc", "disk")):
        number = int(numeric.group("number"))
        total = int(numeric.group("total")) if numeric.group("total") else None
        kind = numeric.group("kind").casefold()
        spans.append(numeric.span())
    cd = _CD_MARKER.search(stem)
    if number is None and cd is not None and "cd" in policy.filename_patterns:
        number = int(cd.group("number"))
        kind = "cd"
        spans.append(cd.span())
    semantic = _ROLE_MARKER.search(stem)
    if semantic is not None and "role" in policy.filename_patterns:
        role = semantic.group("role").casefold()
        label = (semantic.group("label") or "").upper()
        spans.append(semantic.span())
    letter = _LABEL_MARKER.search(stem)
    if letter is not None and (
        "label" in policy.filename_patterns
        or letter.group("label").casefold() in policy.allowed_disc_labels
    ):
        label = letter.group("label").upper()
        if number is None and policy.letter_labels_are_ordinal and role is None:
            number = ord(label) - ord("A") + 1
        if not kind:
            kind = "label"
        if not any(start <= letter.start() and letter.end() <= end for start, end in spans):
            spans.append(letter.span())
    if policy.allow_side_labels and "side" in policy.filename_patterns:
        side = _SIDE_MARKER.search(stem)
        if side is not None:
            label = side.group("side").upper()
            number = 1 if label == "A" else 2
            total = 2
            kind = "side"
            spans.append(side.span())
    if not spans:
        return None
    remaining = stem
    for start, end in sorted(spans, reverse=True):
        remaining = remaining[:start] + remaining[end:]
    return _clean_title(remaining), DiscMarker(number, total, kind, label, role)


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


@dataclass(frozen=True)
class ArchiveMember:
    """A validated archive member; no member is extracted by the scanner."""

    archive_path: Path
    member_path: str
    format: str
    member_hash: str
    archive_hash: str
    size: int


ArchiveInspectionState = Literal["ready", "conflict", "unsafe", "unsupported"]


@dataclass(frozen=True)
class ArchiveInspection:
    archive_path: Path
    state: ArchiveInspectionState
    members: tuple[ArchiveMember, ...] = ()
    archive_hash: str | None = None
    reason: str = ""


def _hash_stream(stream: IO[bytes], limit: int) -> tuple[str, int]:
    hasher = hashlib.blake2b(digest_size=64)
    size = 0
    while chunk := stream.read(1 << 16):
        size += len(chunk)
        if size > limit:
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-ARCHIVE", detail=f"membro excede o teto de {limit} bytes"
            )
        hasher.update(chunk)
    return hasher.hexdigest(), size


def inspect_archive(
    archive_path: Path,
    *,
    allowed_formats: Sequence[str] = (),
    limits: safezip.SafeZipLimits = safezip.DEFAULT_LIMITS,
) -> ArchiveInspection:
    """Inspect a ZIP index and hash its members without materializing them."""

    if archive_path.is_symlink() or not archive_path.is_file():
        return ArchiveInspection(archive_path, "unsafe", reason="archive ausente ou symlink")
    if archive_path.suffix.casefold() != ".zip":
        return ArchiveInspection(
            archive_path, "unsupported", reason="scanner de archive ainda suporta apenas ZIP"
        )
    archive_hash: str | None = None
    try:
        archive_hash = fs.hash_file(archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if len(infos) > limits.max_entries:
                raise SteamZeroError(
                    "E-CONTENT-UNSAFE-ARCHIVE", detail=f"contagem > {limits.max_entries}"
                )
            seen: set[str] = set()
            members: list[ArchiveMember] = []
            allowed = {value.casefold().lstrip(".") for value in allowed_formats}
            for info in infos:
                if info.is_dir() or info.filename.endswith("/"):
                    continue
                if (info.external_attr >> 16) & 0xFFFF and stat.S_ISLNK(
                    (info.external_attr >> 16) & 0xFFFF
                ):
                    raise SteamZeroError(
                        "E-CONTENT-UNSAFE-PATH", detail=f"symlink em archive: {info.filename!r}"
                    )
                rel = fs.validate_relative_entry(info.filename)
                rendered = rel.as_posix()
                if rendered in seen:
                    raise SteamZeroError(
                        "E-CONTENT-UNSAFE-ARCHIVE", detail=f"membro duplicado: {rendered!r}"
                    )
                seen.add(rendered)
                if info.file_size > limits.max_entry_bytes:
                    raise SteamZeroError(
                        "E-CONTENT-UNSAFE-ARCHIVE", detail=f"membro excede o teto: {rendered!r}"
                    )
                if info.compress_size and info.file_size > limits.max_ratio * info.compress_size:
                    raise SteamZeroError(
                        "E-CONTENT-UNSAFE-ARCHIVE",
                        detail=f"razão de expansão insegura: {rendered!r}",
                    )
                with archive.open(info) as stream:
                    member_hash, size = _hash_stream(stream, limits.max_entry_bytes)
                if size != info.file_size:
                    raise SteamZeroError(
                        "E-CONTENT-INCOMPLETE", detail=f"tamanho divergente: {rendered!r}"
                    )
                member_format = Path(rendered).suffix.casefold().lstrip(".")
                if not allowed or member_format in allowed:
                    members.append(
                        ArchiveMember(
                            archive_path,
                            rendered,
                            member_format,
                            member_hash,
                            archive_hash,
                            size,
                        )
                    )
    except (OSError, zipfile.BadZipFile, ValueError, SteamZeroError) as exc:
        state: ArchiveInspectionState = (
            "unsafe"
            if isinstance(exc, SteamZeroError)
            and exc.code in {"E-CONTENT-UNSAFE-PATH", "E-CONTENT-UNSAFE-ARCHIVE"}
            else "conflict"
        )
        return ArchiveInspection(archive_path, state, archive_hash=archive_hash, reason=str(exc))
    return ArchiveInspection(archive_path, "ready", tuple(members), archive_hash)


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
        parts=tuple(sorted(parts, key=lambda part: (part.number is None, part.number or 0))),
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
        if path.suffix.casefold().lstrip(".") == "m3u":
            continue
        if path.suffix.casefold() == ".bin" and path.with_suffix(".cue").is_file():
            # BIN is a companion of the CUE descriptor, not another disc.
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
        state: MultiDiscState
        suffixes = {_format_for(part.path) for part in parts}
        if not suffixes.issubset(policy.media):
            archive_formats = {"zip", "7z", "rar"}
            media = manifest.get("media")
            container_policy = (
                str(media.get("containerPolicy") or "") if isinstance(media, Mapping) else ""
            )
            if suffixes & archive_formats and container_policy == "extract":
                state = "needs-extraction"
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
        if any(number is None for number in numbers):
            state = "needs-review"
            reason = (
                "O conjunto usa papéis sem número; a ordem do adapter ainda não foi comprovada."
            )
        elif len(numbers) != len(set(numbers)):
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
        elif policy.adapter_playlist_support != "proven":
            state = "needs-platform-contract"
            reason = "O adapter ainda não comprovou suporte a M3U para esta plataforma."
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


class ArchiveAwareMultiDiscResolver:
    """Resolve logical games contained inside ZIPs without extracting them."""

    def __init__(
        self,
        manifest: Mapping[str, object],
        *,
        limits: safezip.SafeZipLimits = safezip.DEFAULT_LIMITS,
    ) -> None:
        self.policy = MultiDiscPolicy.from_manifest(manifest)
        self.limits = limits

    def resolve(
        self,
        platform_id: str,
        system_id: str,
        archives: Sequence[Path],
    ) -> tuple[MultiDiscResolution, ...]:
        """Return one resolution per internal title, never one per archive."""

        groups: dict[str, list[MultiDiscPart]] = defaultdict(list)
        titles: dict[str, str] = {}
        seen_archives: set[str] = set()
        for archive in sorted(archives, key=lambda value: value.name.casefold()):
            inspected = inspect_archive(
                archive,
                allowed_formats=self.policy.archive_member_formats or self.policy.media,
                limits=self.limits,
            )
            if inspected.state != "ready" or inspected.archive_hash is None:
                continue
            # A second ZIP with the same physical hash is a duplicate source,
            # not a second disc. Different hashes remain candidates and are
            # resolved as conflicts below when they collide on identity.
            if inspected.archive_hash in seen_archives:
                continue
            seen_archives.add(inspected.archive_hash)
            for member in inspected.members:
                parsed = parse_disc_marker(Path(member.member_path).stem, self.policy)
                if parsed is None:
                    continue
                title, marker = parsed
                key = _group_key(platform_id, system_id, title)
                part = MultiDiscPart(
                    path=archive,
                    number=marker.number,
                    total=marker.total,
                    format=member.format,
                    content_hash=member.archive_hash,
                    disc_label=marker.label,
                    disc_role=marker.role,
                    archive_path=archive,
                    member_path=member.member_path,
                    member_hash=member.member_hash,
                    archive_hash=member.archive_hash,
                )
                groups[key].append(part)
                titles[key] = title

        resolutions: list[MultiDiscResolution] = []
        for key in sorted(groups):
            if len(groups[key]) < 2 and not any(
                part.total is not None and part.total > 1 for part in groups[key]
            ):
                # A lone ``Disk A``/``System Disk`` is not enough evidence for
                # a logical multi-disc set. Keep it as a regular archive
                # candidate until a companion or explicit total appears.
                continue
            parts = tuple(
                sorted(
                    groups[key],
                    key=lambda part: (
                        part.number is None,
                        part.number or 0,
                        self.policy.role_order.index(part.disc_role)
                        if part.disc_role in self.policy.role_order
                        else len(self.policy.role_order),
                        part.disc_label.casefold(),
                        part.member_path or "",
                    ),
                )
            )
            state, reason = self._validate_parts(parts)
            resolutions.append(
                _resolution(
                    state=state,
                    platform_id=platform_id,
                    system_id=system_id,
                    title=titles[key],
                    parts=parts,
                    reason=reason,
                )
            )
        return tuple(resolutions)

    def _validate_parts(self, parts: Sequence[MultiDiscPart]) -> tuple[MultiDiscState, str]:
        if not self.policy.enabled or self.policy.descriptor != "m3u":
            return "needs-platform-contract", "a plataforma não declarou descritor M3U"
        if not parts:
            return "needs-review", "archive não contém imagens reconhecidas"
        identities = [(part.number, part.disc_role, part.disc_label.casefold()) for part in parts]
        if len(identities) != len(set(identities)):
            return "conflict", "há discos ou papéis duplicados com conteúdo divergente"
        numbers = [part.number for part in parts]
        totals = {part.total for part in parts if part.total is not None}
        state: MultiDiscState
        if any(number is None for number in numbers):
            state = "needs-review"
            reason = "papéis sem número exigem ordem explícita do adapter"
        elif numbers[0] != 1 or (
            self.policy.requires_continuous_sequence and numbers != list(range(1, len(numbers) + 1))
        ):
            state = "incomplete"
            reason = "sequência de discos ausente ou descontínua"
        elif len(totals) == 1 and next(iter(totals)) != len(parts):
            state = "incomplete"
            reason = "total declarado não corresponde ao conjunto"
        elif self.policy.adapter_playlist_support == "unsupported":
            state = "needs-platform-contract"
            reason = "o adapter não declara suporte a M3U para estes archives"
        elif self.policy.container_policy == "extract":
            state = "needs-extraction"
            reason = "playlist só pode apontar para imagens extraídas e gerenciadas"
        elif self.policy.adapter_playlist_support != "proven":
            state = "needs-platform-contract"
            reason = "o adapter ainda não comprovou suporte a M3U"
        else:
            state = "ready"
            reason = "conjunto interno completo e compatível"
        return state, reason


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
        if part.number is None:
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="disco por papel precisa de ordem persistida pelo adapter"
            )
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
                disc_label=part.disc_label,
                disc_role=part.disc_role,
                archive_path=part.archive_path,
                member_path=part.member_path,
                member_hash=part.member_hash,
                archive_hash=part.archive_hash,
                source_origin=part.source_origin,
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
                    disc_label=old.disc_label,
                    disc_role=old.disc_role,
                    archive_path=old.archive_path,
                    member_path=old.member_path,
                    member_hash=old.member_hash,
                    archive_hash=old.archive_hash,
                    source_origin=old.source_origin,
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
    "ArchiveAwareMultiDiscResolver",
    "ArchiveInspection",
    "ArchiveInspectionState",
    "ArchiveMember",
    "DiscLifecycle",
    "DiscMarker",
    "DiscRecord",
    "MultiDiscPart",
    "MultiDiscPolicy",
    "MultiDiscResolution",
    "MultiDiscSet",
    "MultiDiscState",
    "inspect_archive",
    "parse_disc_marker",
    "reconcile_multidisc_set",
    "resolve_multidisc",
]
