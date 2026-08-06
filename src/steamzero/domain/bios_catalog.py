# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Catalog-driven, content-addressed BIOS imports.

This module deliberately never uses a supplied filename to identify firmware.
The name is only a locator while scanning; the SHA-256 matched against the
versioned catalog chooses the logical identity, canonical view and consumers.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
import zipfile
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import IO, Any

from steamzero.api import contracts
from steamzero.core import fs, ids, paths
from steamzero.core.errors import SteamZeroError

MAX_ENTRIES = 10_000
MAX_TOTAL_BYTES = 2 * 1024**3
MAX_FILE_BYTES = 64 * 1024**2
MAX_DEPTH = 32
MAX_RATIO = 200
_CHUNK = 1024 * 1024
_TRUNC = 12


@dataclass(frozen=True)
class BiosIdentity:
    id: str
    platform_id: str
    canonical_name: str
    required: bool
    group: str | None
    variants: tuple[dict[str, Any], ...]
    consumers: tuple[dict[str, Any], ...]


class BiosCatalog:
    """Validated catalog with indexes that reject ambiguous hash ownership."""

    def __init__(self, data: dict[str, Any]) -> None:
        contracts.validate(data, "bios-catalog-v2.schema.json")
        self.data = data
        self.digest = hashlib.sha256(
            json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self._by_hash: dict[str, BiosIdentity] = {}
        self._identities: list[BiosIdentity] = []
        names: set[tuple[str, str]] = set()
        for raw in data["entries"]:
            identity = BiosIdentity(
                id=raw["id"],
                platform_id=raw["platformId"],
                canonical_name=raw["canonicalName"],
                required=bool(raw.get("required", False)),
                group=raw.get("group"),
                variants=tuple(raw["acceptedVariants"]),
                consumers=tuple(raw["consumers"]),
            )
            key = (identity.platform_id, identity.canonical_name)
            if key in names:
                raise SteamZeroError("E-API-CONTRACT", detail="nome canônico de BIOS duplicado")
            names.add(key)
            self._identities.append(identity)
            for variant in identity.variants:
                digest = str(variant["sha256"])
                existing = self._by_hash.get(digest)
                if existing is not None and existing.id != identity.id:
                    raise SteamZeroError(
                        "E-API-CONTRACT", detail="hash de BIOS ambíguo no catálogo"
                    )
                self._by_hash[digest] = identity

    @classmethod
    def bundled(cls) -> BiosCatalog:
        location = Path(__file__).parents[1] / "bios_catalogs" / "index-v2.json"
        return cls(json.loads(location.read_text(encoding="utf-8")))

    def by_hash(self, digest: str) -> BiosIdentity | None:
        return self._by_hash.get(digest)

    def requirements(self, platform_id: str | None = None) -> list[BiosIdentity]:
        return [
            item
            for item in self._identities
            if platform_id is None or item.platform_id == platform_id
        ]


@dataclass(frozen=True)
class ScanCandidate:
    source_member: str
    sha256: str
    size: int
    identity: BiosIdentity | None
    category: str

    def public(self) -> dict[str, Any]:
        return {
            "sourceMember": self.source_member,
            "hashTruncated": self.sha256[:_TRUNC],
            "size": self.size,
            "identityId": self.identity.id if self.identity else None,
            "platformId": self.identity.platform_id if self.identity else None,
            "canonicalName": self.identity.canonical_name if self.identity else None,
            "category": self.category,
        }


@dataclass(frozen=True)
class BiosScan:
    scan_id: str
    source: Path
    source_type: str
    fingerprint: str
    candidates: tuple[ScanCandidate, ...]
    examined: int
    total_bytes: int

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for candidate in self.candidates:
            counts[candidate.category] = counts.get(candidate.category, 0) + 1
        return {
            "scanId": self.scan_id,
            "sourceType": self.source_type,
            "examined": self.examined,
            "totalBytes": self.total_bytes,
            "counts": counts,
            "candidates": [candidate.public() for candidate in self.candidates],
        }


class BiosScanner:
    """Read-only scanner for a regular file, directory or non-encrypted ZIP."""

    def __init__(self, catalog: BiosCatalog) -> None:
        self._catalog = catalog

    def scan(self, source: Path) -> BiosScan:
        entries: list[tuple[str, Path | zipfile.ZipInfo]]
        if source.is_symlink() or not source.exists():
            raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="origem de BIOS insegura")
        if source.is_dir():
            source_type, entries = "directory", self._directory_entries(source)
        elif source.is_file() and source.suffix.casefold() == ".zip":
            source_type, entries = "zip", self._zip_entries(source)
        elif source.is_file():
            source_type, entries = "file", [(source.name, source)]
        else:
            raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="origem de BIOS não é regular")
        seen: set[str] = set()
        candidates: list[ScanCandidate] = []
        total = 0
        for member, value in entries:
            declared_size = self._entry_size(value)
            if (
                declared_size == 0
                or declared_size > MAX_FILE_BYTES
                or self._zip_ratio_unsafe(value)
            ):
                total += declared_size
                candidates.append(ScanCandidate(member, "", declared_size, None, "unknown-ignored"))
                continue
            digest, size = self._hash_entry(source, source_type, member, value)
            total += size
            identity = self._catalog.by_hash(digest)
            if digest in seen:
                category = "duplicate-source"
            elif identity is None:
                category = "unknown-ignored"
            else:
                category = "new"
            seen.add(digest)
            candidates.append(ScanCandidate(member, digest, size, identity, category))
        return BiosScan(
            ids.new_ulid(),
            source,
            source_type,
            self._fingerprint(source, source_type, entries),
            tuple(candidates),
            len(entries),
            total,
        )

    def _directory_entries(self, source: Path) -> list[tuple[str, Path | zipfile.ZipInfo]]:
        entries: list[tuple[str, Path | zipfile.ZipInfo]] = []
        for root, dirs, names in os.walk(source, followlinks=False):
            current = Path(root)
            depth = len(current.relative_to(source).parts)
            if depth > MAX_DEPTH:
                raise SteamZeroError("E-CONTENT-LIMIT", detail="diretório de BIOS profundo demais")
            dirs[:] = [name for name in dirs if not (current / name).is_symlink()]
            for name in names:
                candidate = current / name
                if candidate.is_symlink():
                    continue
                try:
                    info = candidate.stat(follow_symlinks=False)
                except OSError as exc:
                    raise SteamZeroError(
                        "E-CONTENT-UNSAFE-PATH", detail="arquivo de BIOS ilegível"
                    ) from exc
                if not stat.S_ISREG(info.st_mode):
                    continue
                entries.append((str(candidate.relative_to(source)), candidate))
                if len(entries) > MAX_ENTRIES:
                    raise SteamZeroError(
                        "E-CONTENT-LIMIT", detail="muitos arquivos na origem de BIOS"
                    )
        return entries

    def _zip_entries(self, source: Path) -> list[tuple[str, Path | zipfile.ZipInfo]]:
        try:
            with zipfile.ZipFile(source) as archive:
                infos = archive.infolist()
        except (OSError, zipfile.BadZipFile) as exc:
            raise SteamZeroError("E-CONTENT-UNSAFE-ARCHIVE", detail="pack ZIP inválido") from exc
        if len(infos) > MAX_ENTRIES:
            raise SteamZeroError("E-CONTENT-LIMIT", detail="muitas entradas no pack de BIOS")
        total = 0
        entries: list[tuple[str, Path | zipfile.ZipInfo]] = []
        for info in infos:
            self._validate_zip_info(info)
            if info.is_dir():
                continue
            total += info.file_size
            if total > MAX_TOTAL_BYTES:
                raise SteamZeroError("E-CONTENT-LIMIT", detail="pack de BIOS excede o limite")
            entries.append((info.filename, info))
        return entries

    @staticmethod
    def _entry_size(value: Path | zipfile.ZipInfo) -> int:
        if isinstance(value, Path):
            return value.stat(follow_symlinks=False).st_size
        return value.file_size

    @staticmethod
    def _zip_ratio_unsafe(value: Path | zipfile.ZipInfo) -> bool:
        return (
            isinstance(value, zipfile.ZipInfo)
            and bool(value.compress_size)
            and (value.file_size > value.compress_size * MAX_RATIO)
        )

    @staticmethod
    def _validate_zip_info(info: zipfile.ZipInfo) -> None:
        path = PurePosixPath(info.filename)
        mode = info.external_attr >> 16
        if (
            info.flag_bits & 0x1
            or info.filename.startswith("/")
            or ".." in path.parts
            or "\x00" in info.filename
        ):
            raise SteamZeroError("E-CONTENT-UNSAFE-ARCHIVE", detail="entrada ZIP insegura")
        file_type = stat.S_IFMT(mode)
        if stat.S_ISLNK(mode) or (file_type and not stat.S_ISREG(mode) and not info.is_dir()):
            raise SteamZeroError("E-CONTENT-UNSAFE-ARCHIVE", detail="tipo de entrada ZIP inseguro")
        if len(path.parts) > MAX_DEPTH:
            raise SteamZeroError("E-CONTENT-LIMIT", detail="entrada ZIP profunda demais")

    def _hash_entry(
        self, source: Path, source_type: str, member: str, value: Path | zipfile.ZipInfo
    ) -> tuple[str, int]:
        if source_type != "zip":
            path = value
            if not isinstance(path, Path):
                raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="origem de BIOS inválida")
            size = path.stat(follow_symlinks=False).st_size
            if not 0 < size <= MAX_FILE_BYTES:
                raise SteamZeroError("E-CONTENT-LIMIT", detail="arquivo de BIOS fora dos limites")
            return fs.hash_file(path, algo="sha256"), size
        info = value
        if not isinstance(info, zipfile.ZipInfo):
            raise SteamZeroError("E-CONTENT-UNSAFE-ARCHIVE", detail="entrada ZIP inválida")
        with zipfile.ZipFile(source) as archive, archive.open(info) as stream:
            return self._hash_stream(stream)

    @staticmethod
    def _hash_stream(stream: IO[bytes]) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        while block := stream.read(_CHUNK):
            size += len(block)
            if size > MAX_FILE_BYTES:
                raise SteamZeroError("E-CONTENT-LIMIT", detail="arquivo de BIOS fora dos limites")
            digest.update(block)
        if size == 0:
            raise SteamZeroError("E-CONTENT-LIMIT", detail="arquivo de BIOS vazio")
        return digest.hexdigest(), size

    @staticmethod
    def _fingerprint(source: Path, source_type: str, entries: list[tuple[str, Any]]) -> str:
        digest = hashlib.sha256(source_type.encode())
        for member, value in entries:
            if isinstance(value, Path):
                info = value.stat(follow_symlinks=False)
                token = f"{member}\0{info.st_size}\0{info.st_mtime_ns}".encode()
            else:
                token = f"{member}\0{value.CRC}\0{value.file_size}\0{value.date_time}".encode()
            digest.update(token)
        return digest.hexdigest()


@dataclass
class BiosImportPlan:
    plan_id: str
    confirm_token: str
    scan: BiosScan
    selected: tuple[ScanCandidate, ...]
    catalog_digest: str
    expires_at: datetime
    added_bytes: int
    status: str = "pending"
    created_objects: list[Path] = field(default_factory=list)
    created_views: list[Path] = field(default_factory=list)

    def public(self) -> dict[str, Any]:
        return {
            "planId": self.plan_id,
            "confirmToken": self.confirm_token,
            "sourceFingerprint": self.scan.fingerprint,
            "sourceType": self.scan.source_type,
            "catalogVersionHash": self.catalog_digest[:_TRUNC],
            "addedBytes": self.added_bytes,
            "rollbackGuarantee": "objects and views created by this operation",
            "preview": [candidate.public() for candidate in self.selected],
            "expiresAt": self.expires_at.isoformat(),
        }


@dataclass
class BiosRollbackPlan:
    """Revisão efêmera e confirmável de uma importação já aplicada."""

    plan_id: str
    confirm_token: str
    operation_id: str
    source_fingerprint: str
    expires_at: datetime
    status: str = "pending"

    def public(self) -> dict[str, Any]:
        return {
            "planId": self.plan_id,
            "confirmToken": self.confirm_token,
            "operationId": self.operation_id,
            "sourceFingerprint": self.source_fingerprint,
            "rollbackGuarantee": "objects and views created by this operation",
            "expiresAt": self.expires_at.isoformat(),
        }


class BiosLibrary:
    """CAS store and scan/plan/apply facade used by UI, bridge and CLI."""

    def __init__(self, catalog: BiosCatalog | None = None) -> None:
        self.catalog = catalog or BiosCatalog.bundled()
        self.scanner = BiosScanner(self.catalog)
        self._scans: dict[str, BiosScan] = {}
        self._plans: dict[str, BiosImportPlan] = {}
        self._rollback_plans: dict[str, BiosRollbackPlan] = {}

    def scan(self, source: Path) -> dict[str, Any]:
        result = self.scanner.scan(source)
        candidates = tuple(
            replace(candidate, category="already-present")
            if candidate.identity
            and candidate.category == "new"
            and self._object_path(candidate.sha256).is_file()
            else candidate
            for candidate in result.candidates
        )
        result = replace(result, candidates=candidates)
        self._scans[result.scan_id] = result
        summary = result.summary()
        present = {candidate.identity.id for candidate in candidates if candidate.identity}
        summary["missingRequired"] = [
            identity.id
            for identity in self.catalog.requirements()
            if identity.required
            and identity.id not in present
            and not any(
                self._object_path(str(variant["sha256"])).is_file() for variant in identity.variants
            )
        ]
        return summary

    def scan_status(self, scan_id: str) -> dict[str, Any]:
        scan = self._scans.get(scan_id)
        if scan is None:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="varredura de BIOS não encontrada")
        return scan.summary()

    def import_plan(self, scan_id: str, selection: list[str] | None = None) -> dict[str, Any]:
        scan = self._scans.get(scan_id)
        if scan is None:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="varredura de BIOS expirada")
        allowed = set(
            selection
            if selection is not None
            else [candidate.sha256 for candidate in scan.candidates]
        )
        selected = tuple(
            candidate
            for candidate in scan.candidates
            if candidate.identity and candidate.category == "new" and candidate.sha256 in allowed
        )
        objects = {candidate.sha256: candidate for candidate in selected}
        added = sum(
            candidate.size
            for digest, candidate in objects.items()
            if not self._object_path(digest).exists()
        )
        plan = BiosImportPlan(
            ids.new_ulid(),
            secrets.token_urlsafe(24),
            scan,
            selected,
            self.catalog.digest,
            datetime.now(UTC) + timedelta(hours=1),
            added,
        )
        self._plans[plan.plan_id] = plan
        return plan.public()

    def import_apply(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        plan = self._plans.get(plan_id)
        if plan is None or plan.status != "pending" or plan.confirm_token != confirm_token:
            raise SteamZeroError(
                "E-TX-CONFIRM-REQUIRED", detail="confirmação de importação inválida"
            )
        if datetime.now(UTC) > plan.expires_at or plan.catalog_digest != self.catalog.digest:
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="plano de BIOS expirou ou catálogo mudou"
            )
        current = self.scanner.scan(plan.scan.source)
        if current.fingerprint != plan.scan.fingerprint:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="origem de BIOS mudou após a varredura")
        current_by_hash = {candidate.sha256: candidate for candidate in current.candidates}
        try:
            for candidate in plan.selected:
                refreshed = current_by_hash.get(candidate.sha256)
                if refreshed is None or refreshed.identity is None:
                    raise SteamZeroError(
                        "E-TX-STALE-PLAN", detail="candidato de BIOS não pode ser revalidado"
                    )
                object_path = self._object_path(candidate.sha256)
                if object_path.exists():
                    if (
                        object_path.is_symlink()
                        or fs.hash_file(object_path, algo="sha256") != candidate.sha256
                    ):
                        raise SteamZeroError(
                            "E-CONTENT-INCOMPLETE", detail="objeto central de BIOS conflita"
                        )
                else:
                    self._publish_object(current, refreshed, object_path)
                    plan.created_objects.append(object_path)
                view = self._view_path(refreshed.identity)
                if view.exists() or view.is_symlink():
                    if (
                        not view.is_symlink()
                        or fs.hash_file(view, algo="sha256") != candidate.sha256
                    ):
                        raise SteamZeroError(
                            "E-CONTENT-INCOMPLETE", detail="projeção canônica de BIOS conflita"
                        )
                else:
                    fs.symlink_atomic(object_path, view)
                    plan.created_views.append(view)
            plan.status = "applied"
            plan.confirm_token = ""
            return {
                "operationId": plan.plan_id,
                "status": "applied",
                "imported": len(plan.selected),
                "addedBytes": plan.added_bytes,
            }
        except Exception:
            self.import_rollback(plan.plan_id)
            raise

    def import_rollback(self, operation_id: str) -> dict[str, Any]:
        plan = self._plans.get(operation_id)
        if plan is None:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="operação de BIOS não encontrada")
        for view in reversed(plan.created_views):
            fs.remove_file(view)
        for object_path in reversed(plan.created_objects):
            fs.remove_file(object_path)
        plan.created_views.clear()
        plan.created_objects.clear()
        plan.status = "rolled-back"
        return {"operationId": operation_id, "status": "rolled-back"}

    def rollback_plan(self, operation_id: str) -> dict[str, Any]:
        """Congela a operação de importação antes de permitir a reversão."""
        operation = self._plans.get(operation_id)
        if operation is None:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="operação de BIOS não encontrada")
        if operation.status == "rolled-back":
            return {
                "operationId": operation_id,
                "status": "already-rolled-back",
                "idempotent": True,
            }
        if operation.status != "applied":
            raise SteamZeroError("E-TX-STALE-PLAN", detail="operação de BIOS não está aplicada")
        plan = BiosRollbackPlan(
            plan_id=ids.new_ulid(),
            confirm_token=secrets.token_urlsafe(24),
            operation_id=operation_id,
            source_fingerprint=operation.scan.fingerprint,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        self._rollback_plans[plan.plan_id] = plan
        return plan.public()

    def rollback_apply(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        plan = self._rollback_plans.get(plan_id)
        if plan is None or plan.status != "pending" or plan.confirm_token != confirm_token:
            raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="confirmação de rollback inválida")
        if datetime.now(UTC) > plan.expires_at:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano de rollback de BIOS expirou")
        operation = self._plans.get(plan.operation_id)
        if operation is None or operation.status != "applied":
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="operação de BIOS mudou antes do rollback"
            )
        result = self.import_rollback(plan.operation_id)
        plan.status = "applied"
        plan.confirm_token = ""
        return result

    def status(self, platform_id: str | None = None) -> dict[str, Any]:
        entries = []
        for identity in self.catalog.requirements(platform_id):
            present = any(self._object_path(str(v["sha256"])).is_file() for v in identity.variants)
            entries.append(
                {
                    "id": identity.id,
                    "platformId": identity.platform_id,
                    "canonicalName": identity.canonical_name,
                    "required": identity.required,
                    "present": present,
                }
            )
        return {"entries": entries}

    def audit(self) -> dict[str, Any]:
        issues: list[str] = []
        for identity in self.catalog.requirements():
            for variant in identity.variants:
                object_path = self._object_path(str(variant["sha256"]))
                view = self._view_path(identity)
                if (
                    object_path.exists()
                    and fs.hash_file(object_path, algo="sha256") != variant["sha256"]
                ):
                    issues.append("object-hash-divergent")
                if (view.exists() or view.is_symlink()) and (
                    not view.is_symlink() or not view.exists()
                ):
                    issues.append("projection-broken")
        return {"status": "ok" if not issues else "repair-required", "issues": sorted(set(issues))}

    @staticmethod
    def _object_path(digest: str) -> Path:
        return paths.bios_dir() / "objects" / "sha256" / digest[:2] / digest

    @staticmethod
    def _view_path(identity: BiosIdentity) -> Path:
        return paths.bios_dir() / "platforms" / identity.platform_id / identity.canonical_name

    @staticmethod
    def _publish_object(scan: BiosScan, candidate: ScanCandidate, destination: Path) -> None:
        if scan.source_type == "zip":
            with (
                zipfile.ZipFile(scan.source) as archive,
                archive.open(candidate.source_member) as stream,
            ):
                fs.write_stream_atomic(destination, stream, max_bytes=MAX_FILE_BYTES)
        else:
            source = (
                scan.source if scan.source_type == "file" else scan.source / candidate.source_member
            )
            fs.copy_file_atomic(source, destination)
        if fs.hash_file(destination, algo="sha256") != candidate.sha256:
            fs.remove_file(destination)
            raise SteamZeroError("E-TX-VERIFY-FAILED", detail="objeto de BIOS divergiu da origem")
