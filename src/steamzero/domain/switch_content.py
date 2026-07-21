# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Conteúdo compartilhado Switch com dedupe e mutações transacionais (WI-6).

O store guarda blobs por hash, sem interpretar ou baixar conteúdo. Updates,
DLC, mods, shader cache, saves, keys e firmware continuam sendo arquivos do
próprio usuário. A ativação em emuladores ocorre por links explicitamente
planejados; migração de saves copia e preserva a origem.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steamzero.core import fs, transaction
from steamzero.core.errors import SteamZeroError

_TITLE_ID = re.compile(r"^[0-9A-F]{16}$")
_KINDS = frozenset(
    {"update", "dlc", "mod", "shader-cache", "save", "keys", "firmware"}
)


@dataclass(frozen=True)
class ContentRecord:
    record_key: str
    kind: str
    title_id: str | None
    sha256: str
    size: int
    blob: Path
    version: str | None = None
    emulator_id: str | None = None
    state: str = "available"

    def to_dict(self) -> dict[str, object]:
        return {
            "recordKey": self.record_key,
            "kind": self.kind,
            "titleId": self.title_id,
            "sha256": self.sha256,
            "size": self.size,
            "blob": str(self.blob),
            "version": self.version,
            "emulatorId": self.emulator_id,
            "state": self.state,
        }


@dataclass(frozen=True)
class ContentImportDecision:
    status: str  # planned | duplicate
    record: ContentRecord
    plan: transaction.Plan | None


class SwitchContentManager:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve(strict=False)

    @property
    def index_path(self) -> Path:
        return self._root / "index-v1.json"

    def plan_import(
        self,
        source: Path,
        *,
        kind: str,
        title_id: str | None = None,
        version: str | None = None,
        emulator_id: str | None = None,
    ) -> ContentImportDecision:
        normalized_kind = _validate_kind(kind)
        normalized_title = _validate_title_id(title_id)
        if normalized_kind in {"update", "dlc"} and normalized_title is None:
            raise SteamZeroError(
                "E-API-SCHEMA", detail=f"titleId é obrigatório para {normalized_kind}"
            )
        if source.is_symlink() or not source.is_file():
            raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="conteúdo não é arquivo regular")
        source = source.resolve(strict=True)
        digest = fs.hash_file(source, algo="sha256")
        blob = fs.resolve_within(self._root, self._root / "blobs" / digest)
        record_key = _record_key(
            normalized_kind,
            normalized_title,
            digest,
            version,
            emulator_id,
        )
        record = ContentRecord(
            record_key,
            normalized_kind,
            normalized_title,
            digest,
            source.stat().st_size,
            blob,
            _safe_label(version, "version"),
            _safe_label(emulator_id, "emulatorId"),
        )
        index = self._load_index()
        existing_record = next(
            (entry for entry in index["records"] if entry["recordKey"] == record_key), None
        )
        if blob.exists() or blob.is_symlink():
            if (
                blob.is_symlink()
                or not blob.is_file()
                or fs.hash_file(blob, algo="sha256") != digest
            ):
                raise SteamZeroError(
                    "E-CONTENT-INCOMPLETE", detail="blob compartilhado existente diverge do hash"
                )
            if existing_record is not None:
                return ContentImportDecision(
                    "duplicate", self._record_from_entry(existing_record), None
                )
        if existing_record is None:
            index["records"].append(self._entry_from_record(record))
            index["records"].sort(key=lambda item: item["recordKey"])
        index_bytes = _encode_index(index)
        requirements = {
            "content": record.to_dict(),
            "sourceHash": fs.hash_file(source),
        }
        if blob.exists():
            plan = transaction.plan_write_files(
                {self.index_path: index_bytes},
                root=self._root,
                kind="switch-content.import",
            )
        else:
            plan = transaction.plan_copy_files(
                {source: blob},
                root=self._root,
                kind="switch-content.import",
                requirements_extra=requirements,
                writes={self.index_path: index_bytes},
            )
        return ContentImportDecision("planned", record, plan)

    def apply_import(
        self, plan_id: str, confirm_token: str
    ) -> transaction.ApplyResult:
        plan = transaction.load_plan(plan_id)
        if plan.kind != "switch-content.import" or Path(plan.root) != self._root:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não pertence ao store Switch")
        return transaction.apply(plan_id, confirm_token)

    @staticmethod
    def rollback(operation_id: str) -> transaction.RollbackResult:
        return transaction.rollback(operation_id, reason="switch-content")

    def plan_link(
        self,
        record: ContentRecord,
        *,
        consumer_root: Path,
        consumer_relpath: str,
    ) -> transaction.Plan:
        blob = fs.resolve_within(self._root, record.blob)
        if (
            blob.is_symlink()
            or not blob.is_file()
            or fs.hash_file(blob, algo="sha256") != record.sha256
        ):
            raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="blob ausente ou corrompido")
        relative = fs.validate_relative_entry(consumer_relpath)
        return transaction.plan_symlink_files(
            {blob: consumer_root / relative},
            root=consumer_root,
            kind="switch-content.link",
        )

    def list_records(
        self, *, title_id: str | None = None, kind: str | None = None
    ) -> list[ContentRecord]:
        normalized_title = _validate_title_id(title_id)
        normalized_kind = _validate_kind(kind) if kind is not None else None
        records = [self._record_from_entry(entry) for entry in self._load_index()["records"]]
        return [
            record
            for record in records
            if (normalized_title is None or record.title_id == normalized_title)
            and (normalized_kind is None or record.kind == normalized_kind)
        ]

    def plan_set_active(self, record_key: str, *, active: bool) -> transaction.Plan:
        index = self._load_index()
        selected = next(
            (entry for entry in index["records"] if entry["recordKey"] == record_key), None
        )
        if selected is None:
            raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="conteúdo não catalogado")
        if selected["kind"] not in {"update", "dlc"}:
            raise SteamZeroError(
                "E-API-SCHEMA", detail="somente updates e DLC podem ser ativados"
            )
        selected_record = self._record_from_entry(selected)
        if (
            selected_record.state == "unavailable"
            or selected_record.blob.is_symlink()
            or not selected_record.blob.is_file()
            or fs.hash_file(selected_record.blob, algo="sha256") != selected_record.sha256
        ):
            raise SteamZeroError(
                "E-CONTENT-INCOMPLETE",
                detail="conteúdo ausente ou corrompido não pode ser ativado",
            )
        if active and selected["kind"] == "update":
            for entry in index["records"]:
                if entry["kind"] == "update" and entry["titleId"] == selected["titleId"]:
                    entry["state"] = "inactive"
        selected["state"] = "active" if active else "inactive"
        return transaction.plan_write_files(
            {self.index_path: _encode_index(index)},
            root=self._root,
            kind="switch-content.state",
        )

    def apply_state(self, plan_id: str, confirm_token: str) -> transaction.ApplyResult:
        plan = transaction.load_plan(plan_id)
        if plan.kind != "switch-content.state" or Path(plan.root) != self._root:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não altera estado Switch")
        return transaction.apply(plan_id, confirm_token)

    def integrity_report(self) -> dict[str, object]:
        index = self._load_index()
        known: set[str] = set()
        valid = 0
        missing: list[str] = []
        for entry in index["records"]:
            record = self._record_from_entry(entry)
            known.add(record.sha256)
            if (
                record.blob.is_file()
                and not record.blob.is_symlink()
                and fs.hash_file(record.blob, algo="sha256") == record.sha256
            ):
                valid += 1
            else:
                missing.append(record.record_key)
        blob_root = self._root / "blobs"
        orphans = [path.name for path in fs.iter_files(blob_root) if path.name not in known]
        return {
            "state": "ready" if not missing and not orphans else "attention",
            "validRecords": valid,
            "missingRecords": sorted(missing),
            "orphanBlobs": sorted(orphans),
        }

    def plan_recover_index(self) -> transaction.Plan:
        index = self._load_index()
        for entry in index["records"]:
            record = self._record_from_entry(entry)
            intact = (
                record.blob.is_file()
                and not record.blob.is_symlink()
                and fs.hash_file(record.blob, algo="sha256") == record.sha256
            )
            if not intact:
                entry["state"] = "unavailable"
            elif entry["state"] == "unavailable":
                entry["state"] = "available"
        return transaction.plan_write_files(
            {self.index_path: _encode_index(index)},
            root=self._root,
            kind="switch-content.recover",
        )

    def apply_recovery(self, plan_id: str, confirm_token: str) -> transaction.ApplyResult:
        plan = transaction.load_plan(plan_id)
        if plan.kind != "switch-content.recover" or Path(plan.root) != self._root:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não recupera índice Switch")
        return transaction.apply(plan_id, confirm_token)

    def _load_index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"schemaVersion": 1, "records": []}
        if self.index_path.is_symlink() or not self.index_path.is_file():
            raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="índice Switch inválido")
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SteamZeroError(
                "E-CONTENT-INCOMPLETE", detail=f"índice Switch corrompido: {exc}"
            ) from exc
        if not isinstance(data, dict) or data.get("schemaVersion") != 1:
            raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="versão do índice Switch inválida")
        records = data.get("records")
        if not isinstance(records, list):
            raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="registros do índice inválidos")
        normalized: list[dict[str, object]] = []
        keys: set[str] = set()
        for raw in records:
            if not isinstance(raw, dict):
                raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="registro Switch inválido")
            record = self._record_from_entry(raw)
            if record.record_key in keys:
                raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="recordKey Switch duplicada")
            keys.add(record.record_key)
            normalized.append(self._entry_from_record(record))
        return {"schemaVersion": 1, "records": normalized}

    def _record_from_entry(self, entry: dict[str, object]) -> ContentRecord:
        try:
            kind = _validate_kind(str(entry["kind"]))
            title_id = _validate_title_id(
                str(entry["titleId"]) if entry.get("titleId") is not None else None
            )
            digest = str(entry["sha256"])
            if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise ValueError("sha256")
            blob_relpath = fs.validate_relative_entry(str(entry["blobRelpath"]))
            blob = fs.resolve_within(self._root, self._root / blob_relpath)
            state = str(entry["state"])
            if state not in {"available", "active", "inactive", "unavailable"}:
                raise ValueError("state")
            raw_size = entry["size"]
            if not isinstance(raw_size, int) or raw_size < 0:
                raise ValueError("size")
            record = ContentRecord(
                str(entry["recordKey"]),
                kind,
                title_id,
                digest,
                raw_size,
                blob,
                _safe_label(
                    str(entry["version"]) if entry.get("version") is not None else None,
                    "version",
                ),
                _safe_label(
                    str(entry["emulatorId"])
                    if entry.get("emulatorId") is not None
                    else None,
                    "emulatorId",
                ),
                state,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SteamZeroError(
                "E-CONTENT-INCOMPLETE", detail=f"registro Switch inválido: {exc}"
            ) from exc
        expected_key = _record_key(
            record.kind,
            record.title_id,
            record.sha256,
            record.version,
            record.emulator_id,
        )
        if record.record_key != expected_key:
            raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="recordKey Switch divergente")
        return record

    def _entry_from_record(self, record: ContentRecord) -> dict[str, object]:
        return {
            "recordKey": record.record_key,
            "kind": record.kind,
            "titleId": record.title_id,
            "sha256": record.sha256,
            "size": record.size,
            "blobRelpath": str(record.blob.relative_to(self._root)),
            "version": record.version,
            "emulatorId": record.emulator_id,
            "state": record.state,
        }

    @staticmethod
    def apply_link(plan_id: str, confirm_token: str) -> transaction.ApplyResult:
        plan = transaction.load_plan(plan_id)
        if plan.kind != "switch-content.link":
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não é link Switch")
        return transaction.apply(plan_id, confirm_token)

    @staticmethod
    def apply_restore(plan_id: str, confirm_token: str) -> transaction.ApplyResult:
        plan = transaction.load_plan(plan_id)
        if plan.kind != "switch-content.restore":
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não é restore Switch")
        return transaction.apply(plan_id, confirm_token)

    def plan_restore(
        self, record: ContentRecord, *, target: Path, target_root: Path
    ) -> transaction.Plan:
        blob = fs.resolve_within(self._root, record.blob)
        if blob.is_symlink() or not blob.is_file():
            raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="blob não está disponível")
        if fs.hash_file(blob, algo="sha256") != record.sha256:
            raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="blob falhou na verificação")
        return transaction.plan_copy_files(
            {blob: target}, root=target_root, kind="switch-content.restore"
        )

    @staticmethod
    def plan_invalidate_shader_cache(
        cache_root: Path,
        files: list[str],
        *,
        title_id: str,
        compatibility_fingerprint: str,
    ) -> transaction.Plan:
        title = _validate_title_id(title_id)
        fingerprint = _safe_label(compatibility_fingerprint, "compatibilityFingerprint")
        if title is None or fingerprint is None:
            raise SteamZeroError("E-API-SCHEMA", detail="title/fingerprint vazio")
        moves: dict[Path, Path] = {}
        for name in files:
            relative = fs.validate_relative_entry(name)
            source = cache_root / relative
            target = cache_root / ".invalidated" / title / fingerprint / relative
            moves[source] = target
        return transaction.plan_move_files(
            moves, root=cache_root, kind="switch-shader.invalidate"
        )

    @staticmethod
    def apply_shader_invalidation(
        plan_id: str, confirm_token: str
    ) -> transaction.ApplyResult:
        plan = transaction.load_plan(plan_id)
        if plan.kind != "switch-shader.invalidate":
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não é invalidação de shader")
        return transaction.apply(plan_id, confirm_token)

    @staticmethod
    def plan_migrate_saves(
        source_root: Path,
        target_root: Path,
        mappings: dict[str, str],
    ) -> transaction.Plan:
        copies: dict[Path, Path] = {}
        for source_name, target_name in mappings.items():
            source_rel = fs.validate_relative_entry(source_name)
            target_rel = fs.validate_relative_entry(target_name)
            source = fs.resolve_within(source_root, source_root / source_rel)
            if source.is_symlink() or not source.is_file():
                raise SteamZeroError(
                    "E-CONTENT-UNSAFE-PATH", detail=f"save de origem inválido: {source_name}"
                )
            copies[source] = target_root / target_rel
        return transaction.plan_copy_files(
            copies, root=target_root, kind="switch-saves.migrate"
        )

    @staticmethod
    def apply_save_migration(
        plan_id: str, confirm_token: str
    ) -> transaction.ApplyResult:
        plan = transaction.load_plan(plan_id)
        if plan.kind != "switch-saves.migrate":
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não é migração de saves")
        return transaction.apply(plan_id, confirm_token)


def _validate_title_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.upper()
    if _TITLE_ID.fullmatch(normalized) is None:
        raise SteamZeroError("E-API-SCHEMA", detail=f"titleId inválido: {value!r}")
    return normalized


def _validate_kind(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in _KINDS:
        raise SteamZeroError("E-API-SCHEMA", detail=f"tipo de conteúdo inválido: {value!r}")
    return normalized


def _safe_label(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if (
        not 1 <= len(normalized) <= 128
        or any(ord(char) < 0x20 for char in normalized)
        or "/" in normalized
        or "\\" in normalized
        or normalized in {".", ".."}
    ):
        raise SteamZeroError("E-API-SCHEMA", detail=f"{field} inválido")
    return normalized


def _record_key(
    kind: str,
    title_id: str | None,
    sha256: str,
    version: str | None,
    emulator_id: str | None,
) -> str:
    identity = json.dumps(
        {
            "kind": kind,
            "titleId": title_id,
            "sha256": sha256,
            "version": _safe_label(version, "version"),
            "emulatorId": _safe_label(emulator_id, "emulatorId"),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return fs.hash_bytes(identity, algo="sha256")


def _encode_index(index: dict[str, Any]) -> bytes:
    return (json.dumps(index, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
