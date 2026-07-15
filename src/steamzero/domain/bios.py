# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""BIOS/firmware store central (F-BI-01/03, CONTENT-POLICY, AC-BI-01/02).

O banco (bios-db-v1) contém APENAS hashes/metadados — nunca conteúdo. O produto
valida arquivos que o usuário já possui contra os hashes; nunca obtém, sugere ou
baixa BIOS/keys. BIOS ausente é reportada com plataforma+emulador e ação
"importar arquivo local" (texto FIXO do catálogo, sem link — AC-BI-02). Hashes
completos e nomes de keys NUNCA vão para logs (AC-BI-01/SR-14): só hash truncado.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steamzero.api import contracts
from steamzero.core import fs, ids, log, paths, transaction
from steamzero.core.errors import SteamZeroError, build_error
from steamzero.core.state import StateStore

_TRUNC = 12  # caracteres de hash expostos em log/relatório (SR-14)


class BiosDatabase:
    """Banco de hashes de BIOS de uma plataforma (validado contra o schema)."""

    def __init__(self, data: dict[str, Any]) -> None:
        contracts.validate(data, "bios-db-v1.schema.json")  # rejeita campo de conteúdo
        self.platform: str = data["platform"]
        self.entries: list[dict[str, Any]] = data["entries"]

    def by_sha256(self, sha256: str) -> dict[str, Any] | None:
        return next((e for e in self.entries if e["sha256"] == sha256), None)

    def required(self) -> list[dict[str, Any]]:
        return [e for e in self.entries if e.get("required")]


@dataclass(frozen=True)
class BiosStatus:
    name: str
    region: str | None
    required: bool
    present: bool
    error: dict[str, Any] | None  # objeto de erro quando ausente (texto fixo)


@dataclass(frozen=True)
class BiosImportResult:
    status: str  # imported | incompatible
    name: str | None
    hash_truncated: str


class BiosStore:
    def __init__(
        self, store: StateStore, db: BiosDatabase, *, logger: log.StructuredLogger | None = None
    ) -> None:
        self._store = store
        self._db = db
        self._log = logger or log.get_logger()

    def status(self, *, adapter: str | None = None) -> list[BiosStatus]:
        """Lista o estado de cada BIOS obrigatória (present/missing). AC-BI-02."""
        present_hashes = {b["hash"] for b in self._store.list_bios(self._db.platform)}
        result: list[BiosStatus] = []
        for entry in self._db.required():
            if adapter is not None and not _used_by(entry, adapter):
                continue
            present = entry["sha256"] in present_hashes
            error = None if present else build_error("E-CONTENT-BIOS-MISSING")
            result.append(
                BiosStatus(
                    name=entry["name"],
                    region=entry.get("region"),
                    required=True,
                    present=present,
                    error=error,
                )
            )
        return result

    def import_bios(self, provided: Path) -> BiosImportResult:
        """Valida um arquivo local pelo hash e o registra se conhecido.

        Nunca loga o hash completo nem o nome de key (SR-14): só hash truncado.
        """
        sha = fs.hash_file(provided, algo="sha256")
        trunc = sha[:_TRUNC]
        entry = self._db.by_sha256(sha)
        if entry is None:
            self._log.warning(
                "bios.import.unknown", platform=self._db.platform, hashTruncated=trunc
            )
            raise SteamZeroError(
                "E-CONTENT-FW-INCOMPAT",
                detail=f"arquivo não corresponde a nenhuma BIOS conhecida (hash {trunc}…)",
            )
        dest = fs.resolve_within(
            paths.bios_dir(), paths.bios_dir() / self._db.platform / entry["name"]
        )
        fs.copy_file_atomic(provided, dest)
        if fs.hash_file(dest, algo="sha256") != sha:
            fs.remove_file(dest)
            raise SteamZeroError("E-STORAGE-IO", detail="cópia da BIOS divergiu da origem")
        self._store.save_bios_item(
            {
                "id": ids.new_ulid(),
                "platform_id": self._db.platform,
                "relpath": f"{self._db.platform}/{entry['name']}",
                "hash": sha,  # armazenado no state (não é log)
                "region": entry.get("region"),
                "version": None,
                "state": "present",
                "last_validated": _now_iso(),
            }
        )
        # log só com hash truncado — nunca o hash completo nem conteúdo (AC-BI-01)
        self._log.info("bios.import.ok", platform=self._db.platform, hashTruncated=trunc)
        return BiosImportResult("imported", entry["name"], trunc)

    def plan_link(
        self, name: str, *, consumer_root: Path, consumer_relpath: str
    ) -> transaction.Plan:
        """Planeja um link seguro do store central para um consumidor (F-BI-02)."""
        entry = next((item for item in self._db.entries if item["name"] == name), None)
        source = paths.bios_dir() / self._db.platform / name
        if entry is None or not source.is_file():
            raise SteamZeroError("E-CONTENT-BIOS-MISSING", detail="BIOS central ausente")
        if fs.hash_file(source, algo="sha256") != entry["sha256"]:
            raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="BIOS central corrompida")
        relative = fs.validate_relative_entry(consumer_relpath)
        return transaction.plan_symlink_files(
            {source: consumer_root / relative}, root=consumer_root, kind="bios.link"
        )

    @staticmethod
    def apply_link(plan_id: str, confirm_token: str) -> transaction.ApplyResult:
        return transaction.apply(plan_id, confirm_token)

    @staticmethod
    def rollback_link(operation_id: str) -> transaction.RollbackResult:
        return transaction.rollback(operation_id, reason="bios-link")


def _used_by(entry: dict[str, Any], adapter: str) -> bool:
    return any(u.get("adapter") == adapter for u in entry.get("usedBy", []))


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
