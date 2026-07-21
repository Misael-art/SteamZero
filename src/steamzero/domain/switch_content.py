# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Conteúdo compartilhado Switch com dedupe e mutações transacionais (WI-6).

O store guarda blobs por hash, sem interpretar ou baixar conteúdo. Updates,
DLC, mods, shader cache, saves, keys e firmware continuam sendo arquivos do
próprio usuário. A ativação em emuladores ocorre por links explicitamente
planejados; migração de saves copia e preserva a origem.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from steamzero.core import fs, transaction
from steamzero.core.errors import SteamZeroError

_TITLE_ID = re.compile(r"^[0-9A-F]{16}$")
_KINDS = frozenset(
    {"update", "dlc", "mod", "shader-cache", "save", "keys", "firmware"}
)


@dataclass(frozen=True)
class ContentRecord:
    kind: str
    title_id: str | None
    sha256: str
    size: int
    blob: Path
    version: str | None = None
    emulator_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "titleId": self.title_id,
            "sha256": self.sha256,
            "size": self.size,
            "blob": str(self.blob),
            "version": self.version,
            "emulatorId": self.emulator_id,
        }


@dataclass(frozen=True)
class ContentImportDecision:
    status: str  # planned | duplicate
    record: ContentRecord
    plan: transaction.Plan | None


class SwitchContentManager:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve(strict=False)

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
        if source.is_symlink() or not source.is_file():
            raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="conteúdo não é arquivo regular")
        source = source.resolve(strict=True)
        digest = fs.hash_file(source, algo="sha256")
        blob = fs.resolve_within(self._root, self._root / "blobs" / digest)
        record = ContentRecord(
            normalized_kind,
            normalized_title,
            digest,
            source.stat().st_size,
            blob,
            _safe_label(version, "version"),
            _safe_label(emulator_id, "emulatorId"),
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
            return ContentImportDecision("duplicate", record, None)
        plan = transaction.plan_copy_files(
            {source: blob},
            root=self._root,
            kind="switch-content.import",
            requirements_extra={
                "content": record.to_dict(),
                "sourceHash": fs.hash_file(source),
            },
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
    ):
        raise SteamZeroError("E-API-SCHEMA", detail=f"{field} inválido")
    return normalized
