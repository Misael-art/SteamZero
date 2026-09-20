# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Transacionaliza archives multidisco em uma projeção consumível.

O scanner somente indexa containers. Este adapter é a etapa explícita e
cancelável que transforma um conjunto validado em arquivos derivados e uma
playlist M3U gerenciada. A origem nunca é escrita; a publicação final passa
pela transação do SteamZero e deixa a playlist anterior intacta em falha.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from steamzero.core import fs, ids, paths, safezip, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain.multidisc import (
    ArchiveAwareMultiDiscResolver,
    DiscRecord,
    MultiDiscPart,
    MultiDiscPolicy,
    MultiDiscResolution,
    MultiDiscSet,
    inspect_archive,
    parse_disc_marker,
    resolve_multidisc,
)
from steamzero.domain.multidisc_artifacts import OWNERSHIP_MARKER, render_descriptor

_ARCHIVE_SUFFIXES = frozenset({".7z", ".rar", ".zip"})
_CHUNK = 1 << 16
_SEVEN_ZIP_TIMEOUT = 60
_SAFE_SLUG = re.compile(r"[^a-z0-9._-]+")

MaterializationState = Literal[
    "ready",
    "ready-unverified",
    "current",
    "conflict",
    "needs-review",
    "needs-extraction",
    "needs-platform-contract",
    "unsupported-content",
    "unsafe",
]


@dataclass(frozen=True)
class MaterializationRequest:
    platform_id: str
    system_id: str
    title: str
    source_paths: tuple[Path, ...]
    library_root: Path
    manifest: Mapping[str, object]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "platformId": self.platform_id,
            "systemId": self.system_id,
            "title": self.title,
            "sourcePaths": [str(path) for path in self.source_paths],
            "libraryRoot": str(self.library_root),
            "manifest": dict(self.manifest),
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> MaterializationRequest:
        paths_value = value.get("sourcePaths")
        manifest = value.get("manifest")
        if not isinstance(paths_value, list) or not paths_value:
            raise SteamZeroError("E-API-SCHEMA", detail="sourcePaths inválido")
        if not isinstance(manifest, Mapping):
            raise SteamZeroError("E-API-SCHEMA", detail="manifest inválido")
        strings = [item for item in paths_value if isinstance(item, str) and item]
        if len(strings) != len(paths_value):
            raise SteamZeroError("E-API-SCHEMA", detail="sourcePaths inválido")
        return cls(
            platform_id=str(value.get("platformId") or ""),
            system_id=str(value.get("systemId") or ""),
            title=str(value.get("title") or ""),
            source_paths=tuple(Path(item) for item in strings),
            library_root=Path(str(value.get("libraryRoot") or "")),
            manifest=dict(manifest),
        )


@dataclass(frozen=True)
class MaterializationInspection:
    state: MaterializationState
    reason: str
    resolution: MultiDiscResolution | None
    destination: Path
    descriptor_path: Path
    extractor: str


@dataclass(frozen=True)
class PreparedMaterialization:
    inspection: MaterializationInspection
    staging_root: Path
    plan: transaction.Plan | None
    descriptor_path: Path
    source_hashes: Mapping[Path, str]


def _normalise(value: str) -> str:
    return " ".join(value.casefold().split())


def _slug(value: str) -> str:
    result = _SAFE_SLUG.sub("-", _normalise(value)).strip("-._")
    return (result[:96] or "set") if result else "set"


def _archive_backend(path: Path) -> str:
    if path.suffix.casefold() == ".zip":
        return "zip"
    if path.suffix.casefold() in {".7z", ".rar"}:
        return "7z" if shutil.which("7z") or shutil.which("7zz") else "unavailable"
    return "unsupported"


def _member_format(member: str) -> str:
    return Path(member).suffix.casefold().lstrip(".")


def _set_id(platform_id: str, system_id: str, title: str) -> str:
    return f"{platform_id}:{system_id}:{_normalise(title)}"


def _validate_source_paths(request: MaterializationRequest) -> None:
    root = request.library_root.resolve(strict=False)
    if not root.is_dir() or root.is_symlink():
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="raiz de biblioteca inválida")
    for source in request.source_paths:
        if source.is_symlink() or not source.is_file():
            raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail=f"origem inválida: {source}")
        try:
            source.resolve().relative_to(root)
        except ValueError as exc:
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-PATH", detail=f"origem fora da biblioteca: {source}"
            ) from exc


def _external_members(
    archive: Path, *, executable: str, policy: MultiDiscPolicy
) -> tuple[tuple[str, int, str], ...]:
    completed = subprocess.run(  # noqa: S603 - argv sem shell e executável allowlisted
        [executable, "l", "-slt", "-y", str(archive)],
        capture_output=True,
        check=False,
        text=True,
        timeout=_SEVEN_ZIP_TIMEOUT,
    )
    if completed.returncode != 0:
        raise SteamZeroError("E-CONTENT-UNSAFE-ARCHIVE", detail=completed.stderr[-400:])
    records: list[tuple[str, int, str]] = []
    current: dict[str, str] = {}
    for line in [*completed.stdout.splitlines(), ""]:
        if not line.strip():
            name = current.get("Path", "")
            attributes = current.get("Attributes", "")
            if name and "D" not in attributes and "L" not in attributes:
                relative = fs.validate_relative_entry(name)
                fmt = _member_format(str(relative))
                if fmt in policy.archive_member_formats or fmt in policy.media:
                    size = int(current.get("Size", "0"))
                    if size < 0 or size > safezip.DEFAULT_LIMITS.max_entry_bytes:
                        raise SteamZeroError(
                            "E-CONTENT-UNSAFE-ARCHIVE", detail=f"membro excede o teto: {name}"
                        )
                    records.append((str(relative), size, fmt))
            current = {}
            continue
        key, separator, value = line.partition("=")
        if separator:
            current[key] = value
    return tuple(records)


def _external_member_bytes(archive: Path, member: str, *, executable: str) -> bytes:
    process = subprocess.Popen(  # noqa: S603 - argv sem shell e membro atômico
        [executable, "x", "-so", "-y", str(archive), member],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.stdout is None:
        process.kill()
        process.wait(timeout=5)
        raise SteamZeroError("E-CONTENT-UNSAFE-ARCHIVE", detail="backend externo sem stdout")
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = process.stdout.read(_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > safezip.DEFAULT_LIMITS.max_entry_bytes:
            process.kill()
            process.wait(timeout=5)
            raise SteamZeroError("E-CONTENT-UNSAFE-ARCHIVE", detail="membro externo excede o teto")
        chunks.append(chunk)
    stderr = process.stderr.read() if process.stderr is not None else b""
    return_code = process.wait(timeout=_SEVEN_ZIP_TIMEOUT)
    if return_code != 0:
        raise SteamZeroError(
            "E-CONTENT-UNSAFE-ARCHIVE", detail=stderr.decode(errors="replace")[-400:]
        )
    return b"".join(chunks)


def _external_resolutions(
    request: MaterializationRequest, policy: MultiDiscPolicy, executable: str
) -> tuple[MultiDiscResolution, ...]:
    groups: dict[str, list[MultiDiscPart]] = defaultdict(list)
    titles: dict[str, str] = {}
    for archive in request.source_paths:
        archive_hash = fs.hash_file(archive)
        for member, _size, fmt in _external_members(archive, executable=executable, policy=policy):
            parsed = parse_disc_marker(Path(member).stem, policy)
            if parsed is None:
                continue
            title, marker = parsed
            key = _set_id(request.platform_id, request.system_id, title)
            member_bytes = _external_member_bytes(archive, member, executable=executable)
            member_hash = fs.hash_bytes(member_bytes)
            groups[key].append(
                MultiDiscPart(
                    path=archive,
                    number=marker.number,
                    total=marker.total,
                    format=fmt,
                    content_hash=member_hash,
                    disc_label=marker.label,
                    disc_role=marker.role,
                    archive_path=archive,
                    member_path=member,
                    member_hash=member_hash,
                    archive_hash=archive_hash,
                    variant_key=_normalise(title),
                )
            )
            titles[key] = title
    results: list[MultiDiscResolution] = []
    for key, parts in sorted(groups.items()):
        ordered = tuple(sorted(parts, key=lambda part: (part.number is None, part.number or 0)))
        numbers = [part.number for part in ordered]
        if len(ordered) < 2:
            continue
        if any(number is None for number in numbers):
            state: Literal["needs-review", "needs-extraction", "needs-platform-contract"] = (
                "needs-review"
            )
            reason = "archive externo contém discos sem ordem declarada"
        elif numbers != list(range(1, len(numbers) + 1)):
            state = "needs-review"
            reason = "archive externo contém sequência de discos descontínua"
        elif policy.adapter_playlist_support == "unsupported":
            state = "needs-platform-contract"
            reason = "o adapter não declara suporte a M3U"
        else:
            state = "needs-extraction"
            reason = "archive externo precisa de extração gerenciada"
        results.append(
            MultiDiscResolution(
                state=state,
                platform_id=request.platform_id,
                system_id=request.system_id,
                normalized_title=_normalise(titles[key]),
                display_title=titles[key],
                group_key=key,
                parts=ordered,
                reason=reason,
            )
        )
    return tuple(results)


class MultiDiscMaterializer:
    """Planeja e publica uma projeção M3U sem tocar no acervo original."""

    def destination(self, request: MaterializationRequest, title: str) -> Path:
        return (
            request.library_root
            / ".steamzero"
            / "derived"
            / _slug(request.platform_id)
            / _slug(title)
        )

    def inspect(self, request: MaterializationRequest) -> MaterializationInspection:
        _validate_source_paths(request)
        policy = MultiDiscPolicy.from_manifest(request.manifest)
        destination = self.destination(request, request.title)
        descriptor = destination / f"{_slug(request.title)}.m3u"
        archive_paths = [
            path for path in request.source_paths if path.suffix.casefold() in _ARCHIVE_SUFFIXES
        ]
        extractor = "none"
        if archive_paths:
            backends = {_archive_backend(path) for path in archive_paths}
            if "unavailable" in backends:
                return MaterializationInspection(
                    "unsupported-content",
                    "archive RAR/7z requer o backend 7z/7zz, que não está disponível",
                    None,
                    destination,
                    descriptor,
                    "unavailable",
                )
            if len(backends) != 1:
                return MaterializationInspection(
                    "needs-review",
                    "o conjunto mistura containers com backends diferentes",
                    None,
                    destination,
                    descriptor,
                    "mixed",
                )
            extractor = next(iter(backends))
            if extractor == "zip":
                archive_inspections = [
                    inspect_archive(
                        path,
                        allowed_formats=policy.archive_member_formats or policy.media,
                        limits=safezip.DEFAULT_LIMITS,
                    )
                    for path in archive_paths
                ]
                unsafe = next(
                    (item for item in archive_inspections if item.state == "unsafe"), None
                )
                if unsafe is not None:
                    return MaterializationInspection(
                        "unsafe",
                        unsafe.reason or "archive rejeitado pelos limites de segurança",
                        None,
                        destination,
                        descriptor,
                        extractor,
                    )
                resolutions = ArchiveAwareMultiDiscResolver(
                    request.manifest, limits=safezip.DEFAULT_LIMITS
                ).resolve(request.platform_id, request.system_id, archive_paths)
            else:
                executable = shutil.which("7z") or shutil.which("7zz")
                if executable is None:
                    raise SteamZeroError("E-CONTENT-UNSUPPORTED", detail="backend 7z ausente")
                resolutions = _external_resolutions(request, policy, executable)
        else:
            resolutions = resolve_multidisc(
                request.platform_id,
                request.system_id,
                request.source_paths,
                request.manifest,
            )
        desired = _normalise(request.title)
        matching = [item for item in resolutions if not desired or item.normalized_title == desired]
        if len(matching) != 1:
            reason = (
                "archive contém mais de um conjunto; selecione o título exato"
                if len(resolutions) > 1
                else "nenhum conjunto multidisco compatível foi reconhecido"
            )
            return MaterializationInspection(
                "needs-review" if len(resolutions) > 1 else "unsupported-content",
                reason,
                None,
                destination,
                descriptor,
                extractor,
            )
        resolution = matching[0]
        destination = self.destination(request, resolution.display_title)
        descriptor = destination / f"{_slug(resolution.display_title)}.m3u"
        if policy.adapter_playlist_support == "unsupported":
            return MaterializationInspection(
                "needs-platform-contract",
                resolution.reason or "adapter sem contrato M3U",
                resolution,
                destination,
                descriptor,
                extractor,
            )
        if resolution.state in {"conflict", "ambiguous", "incomplete", "needs-review"}:
            return MaterializationInspection(
                "conflict" if resolution.state == "conflict" else "needs-review",
                resolution.reason,
                resolution,
                destination,
                descriptor,
                extractor,
            )
        if descriptor.is_symlink():
            return MaterializationInspection(
                "conflict",
                "playlist destino é symlink",
                resolution,
                destination,
                descriptor,
                extractor,
            )
        if descriptor.is_file():
            content = descriptor.read_text(encoding="utf-8")
            if not content.startswith(OWNERSHIP_MARKER + "\n"):
                return MaterializationInspection(
                    "conflict",
                    "playlist existente não possui ownership SteamZero",
                    resolution,
                    destination,
                    descriptor,
                    extractor,
                )
        state: MaterializationState = (
            "ready-unverified"
            if resolution.state == "needs-platform-contract"
            else "needs-extraction"
            if resolution.state == "needs-extraction"
            else "ready"
        )
        return MaterializationInspection(
            state, resolution.reason, resolution, destination, descriptor, extractor
        )

    def prepare(
        self,
        request: MaterializationRequest,
        operation_id: str,
        *,
        safepoint: Callable[[], None] | None = None,
        inspection: MaterializationInspection | None = None,
    ) -> PreparedMaterialization:
        inspection = inspection or self.inspect(request)
        if inspection.resolution is None or inspection.state in {
            "conflict",
            "needs-review",
            "needs-platform-contract",
            "unsupported-content",
            "unsafe",
        }:
            raise SteamZeroError("E-CONTENT-INCOMPLETE", detail=inspection.reason)
        resolution = inspection.resolution
        staging_root = paths.staging_for(operation_id)
        source_hashes: dict[Path, str] = {}
        copies: list[tuple[Path, Path]] = []
        records: list[DiscRecord] = []
        total = len(resolution.parts)
        for index, part in enumerate(resolution.parts, start=1):
            if safepoint is not None:
                safepoint()
            if part.archive_path is None:
                source = part.path
                source_hash = fs.hash_file(source)
                if part.content_hash is not None and source_hash != part.content_hash:
                    raise SteamZeroError("E-TX-STALE-PLAN", detail=f"origem mudou: {source}")
                source_hashes[source] = source_hash
                staged = fs.resolve_within_staging(
                    staging_root, staging_root / "discs" / f"disk-{index:02d}.{part.format}"
                )
                fs.copy_file_atomic(source, staged)
            else:
                archive = part.archive_path
                archive_hash = fs.hash_file(archive)
                if part.archive_hash is not None and archive_hash != part.archive_hash:
                    raise SteamZeroError("E-TX-STALE-PLAN", detail=f"archive mudou: {archive}")
                source_hashes[archive] = archive_hash
                data = self._extract_member(archive, part.member_path or "", part.format)
                digest = fs.hash_bytes(data)
                if part.member_hash is not None and digest != part.member_hash:
                    raise SteamZeroError(
                        "E-CONTENT-UNSAFE-ARCHIVE", detail=f"hash divergente: {part.member_path}"
                    )
                staged = fs.stage_bytes(operation_id, f"discs/disk-{index:02d}.{part.format}", data)
            target = inspection.destination / f"disk-{index:02d}.{part.format}"
            copies.append((staged, target))
            records.append(
                DiscRecord(
                    set_id=resolution.set_id,
                    disc_number=index,
                    disc_total=total,
                    format=part.format,
                    path=target,
                    content_hash=fs.hash_file(staged),
                    accepted_formats=(part.format,),
                    state="active",
                    disc_label=part.disc_label,
                    disc_role=part.disc_role,
                    source_origin="generated",
                    order=index,
                )
            )
        logical_set = MultiDiscSet(
            set_id=resolution.set_id,
            platform_id=resolution.platform_id,
            system_id=resolution.system_id,
            normalized_title=resolution.normalized_title,
            discs=tuple(records),
            descriptor_path=inspection.descriptor_path,
            descriptor_origin="generated",
        )
        descriptor_content = render_descriptor(logical_set).encode("utf-8")
        existing_targets = [target for _source, target in copies if target.exists()]
        replace_existing = bool(existing_targets or inspection.descriptor_path.exists())
        if replace_existing and not inspection.descriptor_path.is_file():
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="destino derivado não é arquivo gerenciado"
            )
        plan = transaction.plan_copy_files(
            copies,
            root=request.library_root,
            kind="multidisc.materialize.commit",
            writes={inspection.descriptor_path: descriptor_content},
            replace_existing=replace_existing,
            requirements_extra={
                "setId": resolution.set_id,
                "descriptorHash": fs.hash_bytes(descriptor_content, algo="sha256"),
            },
        )
        return PreparedMaterialization(
            inspection, staging_root, plan, inspection.descriptor_path, source_hashes
        )

    def run(
        self,
        request: MaterializationRequest,
        *,
        safepoint: Callable[[], None] | None = None,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> dict[str, Any]:
        operation_id = ids.new_ulid()
        prepared: PreparedMaterialization | None = None
        try:
            inspection = self.inspect(request)
            if inspection.state in {"conflict", "needs-review", "needs-platform-contract"}:
                raise SteamZeroError("E-CONTENT-INCOMPLETE", detail=inspection.reason)
            prepared = self.prepare(
                request, operation_id, safepoint=safepoint, inspection=inspection
            )
            if progress is not None:
                progress(1, 1, str(prepared.descriptor_path))
            if safepoint is not None:
                safepoint()
            if prepared.plan is None:
                return {"status": "current", "descriptor": str(prepared.descriptor_path)}
            result = transaction.apply(prepared.plan.plan_id, prepared.plan.confirm_token)
            return {
                "status": "materialized",
                "operationId": result.operation_id,
                "descriptor": str(prepared.descriptor_path),
                "setId": prepared.inspection.resolution.set_id
                if prepared.inspection.resolution is not None
                else None,
            }
        finally:
            fs.remove_tree(paths.staging_for(operation_id))

    @staticmethod
    def _extract_member(archive: Path, member: str, fmt: str) -> bytes:
        if archive.suffix.casefold() == ".zip":
            with zipfile.ZipFile(archive) as handle:
                try:
                    info = handle.getinfo(member)
                except KeyError as exc:
                    raise SteamZeroError(
                        "E-TX-STALE-PLAN", detail=f"membro ausente: {member}"
                    ) from exc
                if info.filename != member:
                    raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="membro ambíguo")
                with handle.open(info) as source:
                    data = source.read(safezip.DEFAULT_LIMITS.max_entry_bytes + 1)
                if len(data) > safezip.DEFAULT_LIMITS.max_entry_bytes:
                    raise SteamZeroError("E-CONTENT-UNSAFE-ARCHIVE", detail="membro excede o teto")
                return data
        executable = shutil.which("7z") or shutil.which("7zz")
        if executable is None:
            raise SteamZeroError("E-CONTENT-UNSUPPORTED", detail=f"backend ausente para .{fmt}")
        return _external_member_bytes(archive, member, executable=executable)


__all__ = [
    "MaterializationInspection",
    "MaterializationRequest",
    "MultiDiscMaterializer",
    "PreparedMaterialization",
]
