# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Keys/firmware store para Switch (WI-1, ADR-0021, CONTENT-POLICY, SR-14).

Os bancos (keys-db-v1/firmware-db-v1) contêm APENAS hashes/metadados — nunca
conteúdo de key nem firmware. O produto valida arquivos que o usuário já possui
contra os hashes; nunca obtém, sugere ou baixa keys/firmware. Nomes de key e
hashes completos NUNCA vão para logs/state em claro (SR-14): só hash truncado.

O cruzamento pré-execução compara o requisito mínimo de um jogo (revisão de key /
versão de firmware) com o que está instalado, produzindo um aviso consultável —
nunca bloqueia silenciosamente nem corrompe estado.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steamzero.api import contracts
from steamzero.core import fs, ids, log, paths, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore

_TRUNC = 12  # caracteres de hash expostos em log/relatório (SR-14)


class KeysDatabase:
    """Banco de hashes de um keyset (validado contra o schema)."""

    def __init__(self, data: dict[str, Any]) -> None:
        contracts.validate(data, "keys-db-v1.schema.json")
        self.platform: str = data["platform"]
        self.keyset: str = data["keyset"]
        self.entries: list[dict[str, Any]] = data["entries"]

    def by_sha256(self, sha256: str) -> dict[str, Any] | None:
        return next((e for e in self.entries if e["sha256"] == sha256), None)


class FirmwareDatabase:
    """Banco de hashes de firmware (validado contra o schema)."""

    def __init__(self, data: dict[str, Any]) -> None:
        contracts.validate(data, "firmware-db-v1.schema.json")
        self.platform: str = data["platform"]
        self.entries: list[dict[str, Any]] = data["entries"]

    def by_sha256(self, sha256: str) -> dict[str, Any] | None:
        return next((e for e in self.entries if e["sha256"] == sha256), None)


@dataclass(frozen=True)
class ImportResult:
    kind: str  # key | firmware
    status: str  # imported | revalidated
    revision: int | None
    version: str | None
    hash_truncated: str


@dataclass(frozen=True)
class RequirementCheck:
    """Resultado consultável do cruzamento requisito→instalado (pré-execução)."""

    status: str  # ok | outdated | missing | not-required
    kind: str  # keys | firmware
    required: str | None
    installed: str | None
    detail: str

    @property
    def blocks_play(self) -> bool:
        return self.status == "missing"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "kind": self.kind,
            "required": self.required,
            "installed": self.installed,
            "detail": self.detail,
            "blocksPlay": self.blocks_play,
        }


def parse_firmware_version(value: str) -> tuple[int, ...]:
    """Converte '17.0.1' em (17, 0, 1); recusa formato inesperado."""
    parts = value.split(".")
    try:
        return tuple(int(p) for p in parts)
    except ValueError as exc:
        raise SteamZeroError(
            "E-API-SCHEMA", detail=f"versão de firmware inválida: {value!r}"
        ) from exc


class KeysFirmwareStore:
    def __init__(
        self,
        store: StateStore,
        *,
        keys_db: KeysDatabase | None = None,
        firmware_db: FirmwareDatabase | None = None,
        logger: log.StructuredLogger | None = None,
    ) -> None:
        self._store = store
        self._keys_db = keys_db
        self._firmware_db = firmware_db
        self._log = logger or log.get_logger()

    # -- importação local auditada -----------------------------------------
    def import_keys(self, provided: Path) -> ImportResult:
        if self._keys_db is None:
            raise SteamZeroError("E-COMPONENT-DEGRADED", detail="banco de keys indisponível")
        sha = fs.hash_file(provided, algo="sha256")
        trunc = sha[:_TRUNC]
        entry = self._keys_db.by_sha256(sha)
        if entry is None:
            # Nunca loga nome de key nem hash completo (SR-14).
            self._log.warning(
                "keys.import.unknown", platform=self._keys_db.platform, hashTruncated=trunc
            )
            raise SteamZeroError(
                "E-CONTENT-KEYS-INCOMPAT",
                detail=f"arquivo de keys não reconhecido (hash {trunc}…)",
            )
        revision = int(entry["keyRevision"])
        relpath = f"{self._keys_db.platform}/{self._keys_db.keyset}.keys"
        existing_id = self._existing_item_id(
            self._keys_db.platform,
            kind="key",
            relpath=relpath,
            hash_truncated=trunc,
            revision=revision,
        )
        record_id = existing_id or ids.new_ulid()
        self._materialize(provided, sha, relpath, paths.keys_dir())
        self._store.save_firmware_key_item(
            {
                "id": record_id,
                "kind": "key",
                "platform_id": self._keys_db.platform,
                "hash_truncated": trunc,
                "state": "present",
                "keyset": self._keys_db.keyset,
                "revision": revision,
                "version": None,
                "relpath": relpath,
                "last_validated": _now_iso(),
            }
        )
        status = "revalidated" if existing_id else "imported"
        self._audit_import(
            kind="key",
            platform=self._keys_db.platform,
            item_id=record_id,
            status=status,
            hash_truncated=trunc,
        )
        self._log.info("keys.import.ok", platform=self._keys_db.platform, hashTruncated=trunc)
        return ImportResult("key", status, revision, None, trunc)

    def import_firmware(self, provided: Path) -> ImportResult:
        if self._firmware_db is None:
            raise SteamZeroError("E-COMPONENT-DEGRADED", detail="banco de firmware indisponível")
        sha = fs.hash_file(provided, algo="sha256")
        trunc = sha[:_TRUNC]
        entry = self._firmware_db.by_sha256(sha)
        if entry is None:
            self._log.warning(
                "firmware.import.unknown",
                platform=self._firmware_db.platform,
                hashTruncated=trunc,
            )
            raise SteamZeroError(
                "E-CONTENT-FW-INCOMPAT",
                detail=f"arquivo de firmware não reconhecido (hash {trunc}…)",
            )
        version = str(entry["version"])
        relpath = f"{self._firmware_db.platform}/{version}"
        existing_id = self._existing_item_id(
            self._firmware_db.platform,
            kind="firmware",
            relpath=relpath,
            hash_truncated=trunc,
            version=version,
        )
        record_id = existing_id or ids.new_ulid()
        self._materialize(provided, sha, relpath, paths.firmware_dir())
        self._store.save_firmware_key_item(
            {
                "id": record_id,
                "kind": "firmware",
                "platform_id": self._firmware_db.platform,
                "hash_truncated": trunc,
                "state": "present",
                "keyset": None,
                "revision": None,
                "version": version,
                "relpath": relpath,
                "last_validated": _now_iso(),
            }
        )
        status = "revalidated" if existing_id else "imported"
        self._audit_import(
            kind="firmware",
            platform=self._firmware_db.platform,
            item_id=record_id,
            status=status,
            hash_truncated=trunc,
        )
        self._log.info(
            "firmware.import.ok", platform=self._firmware_db.platform, hashTruncated=trunc
        )
        return ImportResult("firmware", status, None, version, trunc)

    def _existing_item_id(
        self,
        platform: str,
        *,
        kind: str,
        relpath: str,
        hash_truncated: str,
        revision: int | None = None,
        version: str | None = None,
    ) -> str | None:
        """Retorna a identidade estável de um conteúdo já materializado."""
        for item in self._store.list_firmware_key_items(platform, kind=kind):
            if (
                item.get("relpath") == relpath
                and item.get("hash_truncated") == hash_truncated
                and item.get("revision") == revision
                and item.get("version") == version
            ):
                return str(item["id"])
        return None

    def _audit_import(
        self,
        *,
        kind: str,
        platform: str,
        item_id: str,
        status: str,
        hash_truncated: str,
    ) -> None:
        # Um evento por tentativa bem-sucedida, inclusive revalidação idempotente.
        self._store.append_event(
            f"{kind}.import.{status}",
            entity=f"firmware-key:{item_id}",
            payload={
                "platform": platform,
                "status": status,
                "hashTruncated": hash_truncated,
            },
        )

    def _materialize(self, provided: Path, sha: str, relpath: str, root: Path) -> None:
        dest = fs.resolve_within(root, root / relpath)
        fs.copy_file_atomic(provided, dest)
        if fs.hash_file(dest, algo="sha256") != sha:
            fs.remove_file(dest)
            raise SteamZeroError("E-STORAGE-IO", detail="cópia divergiu da origem")

    # -- estado instalado ---------------------------------------------------
    def installed_key_revision(self, platform: str) -> int | None:
        """Maior revisão de key presente (um keyset inclui as revisões menores)."""
        revisions = [
            int(item["revision"])
            for item in self._store.list_firmware_key_items(platform, kind="key")
            if item.get("state") == "present" and item.get("revision") is not None
        ]
        return max(revisions) if revisions else None

    def installed_firmware_version(self, platform: str) -> str | None:
        """Maior versão de firmware presente."""
        versions = [
            str(item["version"])
            for item in self._store.list_firmware_key_items(platform, kind="firmware")
            if item.get("state") == "present" and item.get("version")
        ]
        if not versions:
            return None
        return max(versions, key=parse_firmware_version)

    # -- cruzamento pré-execução -------------------------------------------
    def check_key_requirement(
        self, platform: str, *, minimum_revision: int | None
    ) -> RequirementCheck:
        installed = self.installed_key_revision(platform)
        req = None if minimum_revision is None else f"rev{minimum_revision}"
        if minimum_revision is None:
            return RequirementCheck(
                "not-required",
                "keys",
                None,
                None if installed is None else f"rev{installed}",
                "O jogo não declara requisito mínimo de keys.",
            )
        if installed is None:
            return RequirementCheck(
                "missing", "keys", req, None, "Nenhum keyset importado para esta plataforma."
            )
        inst = f"rev{installed}"
        if minimum_revision is not None and installed < minimum_revision:
            return RequirementCheck(
                "outdated",
                "keys",
                req,
                inst,
                f"Keys instaladas ({inst}) abaixo do mínimo exigido ({req}).",
            )
        return RequirementCheck("ok", "keys", req, inst, "Keys compatíveis.")

    def check_firmware_requirement(
        self, platform: str, *, minimum_version: str | None
    ) -> RequirementCheck:
        installed = self.installed_firmware_version(platform)
        if minimum_version is None:
            return RequirementCheck(
                "not-required",
                "firmware",
                None,
                installed,
                "O jogo não declara requisito mínimo de firmware.",
            )
        if installed is None:
            return RequirementCheck(
                "missing", "firmware", minimum_version, None, "Nenhum firmware importado."
            )
        if minimum_version is not None and parse_firmware_version(
            installed
        ) < parse_firmware_version(minimum_version):
            return RequirementCheck(
                "outdated",
                "firmware",
                minimum_version,
                installed,
                f"Firmware instalado ({installed}) abaixo do mínimo exigido ({minimum_version}).",
            )
        return RequirementCheck(
            "ok", "firmware", minimum_version, installed, "Firmware compatível."
        )

    # -- linking para o consumidor -----------------------------------------
    def plan_link_keys(
        self, platform: str, *, consumer_root: Path, consumer_relpath: str
    ) -> transaction.Plan:
        if self._keys_db is None:
            raise SteamZeroError("E-COMPONENT-DEGRADED", detail="banco de keys indisponível")
        relpath = f"{platform}/{self._keys_db.keyset}.keys"
        source = paths.keys_dir() / relpath
        if not source.is_file():
            raise SteamZeroError("E-CONTENT-KEYS-MISSING", detail="keyset central ausente")
        relative = fs.validate_relative_entry(consumer_relpath)
        return transaction.plan_symlink_files(
            {source: consumer_root / relative}, root=consumer_root, kind="keys.link"
        )

    @staticmethod
    def apply_link(plan_id: str, confirm_token: str) -> transaction.ApplyResult:
        return transaction.apply(plan_id, confirm_token)

    @staticmethod
    def rollback_link(operation_id: str) -> transaction.RollbackResult:
        return transaction.rollback(operation_id, reason="keys-link")


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
