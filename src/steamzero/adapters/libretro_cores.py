# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Executor transacional dos cores Libretro publicados em arquivo 7z pinado.

O Buildbot do Libretro publica os cores Linux em um arquivo único. Este módulo
nunca extrai o arquivo inteiro nem aceita nomes vindos do cliente: cada adapter
declara um único core e seu digest, a entrada do 7z é conferida contra o caminho
canônico e só então é copiada para o diretório do RetroArch dentro de um plano
confirmável. Arquivo de terceiro no destino não é sobrescrito.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import py7zr

from steamzero.adapters.engine import ArtifactPort
from steamzero.adapters.registry import AdapterManifest, AdapterRegistry, AdapterSource
from steamzero.core import crypto, fs, paths, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore

_ARCHIVE_PREFIX = (
    "RetroArch-Linux-x86_64/RetroArch-Linux-x86_64.AppImage.home/.config/retroarch/cores/"
)
_MAX_CORE_BYTES = 128 * 1024 * 1024
_METADATA_DIR = ".steamzero-managed"


@dataclass(frozen=True)
class PreparedLibretroCore:
    manifest: AdapterManifest
    source: AdapterSource
    plan: transaction.Plan


class LibretroCoreExecutor:
    """Instala um core declarado sem tocar nos demais arquivos do RetroArch."""

    def __init__(
        self,
        store: StateStore,
        registry: AdapterRegistry,
        artifacts: ArtifactPort,
        *,
        core_root: Path | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._artifacts = artifacts
        self._root = core_root or _default_core_root()
        fs.ensure_dir(self._root)

    def status(self, adapter_id: str) -> dict[str, object]:
        manifest, source, core_id, digest = self._details(adapter_id)
        target = self._target(core_id)
        metadata = self._metadata_path(manifest.id)
        if not target.exists() and not target.is_symlink() and not metadata.exists():
            return {"id": adapter_id, "state": "missing"}
        try:
            if target.is_symlink() or not target.is_file():
                raise ValueError("core ausente ou não é arquivo regular")
            if metadata.is_symlink() or not metadata.is_file():
                raise ValueError("metadados de ownership ausentes")
            raw = json.loads(metadata.read_text(encoding="utf-8"))
            if raw != self._metadata(manifest, source, core_id, digest):
                raise ValueError("metadados do core divergem do manifesto")
            if target.stat().st_size > _MAX_CORE_BYTES:
                raise ValueError("core excede o limite de tamanho")
            if fs.hash_file(target, algo="sha256") != digest:
                raise ValueError("checksum do core diverge")
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return {
                "id": adapter_id,
                "state": "degraded",
                "version": source.version,
                "origin": source.type,
                "detail": str(exc),
            }
        return {
            "id": adapter_id,
            "state": "installed",
            "version": source.version,
            "origin": source.type,
            "sha256": digest,
        }

    def plan_install(self, adapter_id: str, *, force: bool = False) -> PreparedLibretroCore:
        manifest, source, core_id, digest = self._details(adapter_id)
        target = self._target(core_id)
        metadata_path = self._metadata_path(manifest.id)
        status = self.status(adapter_id)
        if status["state"] == "installed" and not force:
            return PreparedLibretroCore(
                manifest,
                source,
                transaction.plan_write_files({}, root=self._root, kind="libretro.install"),
            )
        present = (
            target.exists()
            or target.is_symlink()
            or metadata_path.exists()
            or metadata_path.is_symlink()
        )
        if present and not self._owned_target(manifest, source, core_id, digest):
            raise SteamZeroError(
                "E-CONTENT-INCOMPLETE",
                detail="core existente não é gerenciado pelo SteamZero; recusa sobrescrever",
            )

        extracted = self._extract_verified(manifest, source, core_id, digest)
        metadata = json.dumps(
            self._metadata(manifest, source, core_id, digest),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        plan = transaction.plan_copy_files(
            {extracted: target},
            root=self._root,
            kind="libretro.install",
            writes={metadata_path: metadata},
            replace_existing=target.exists() or target.is_symlink(),
        )
        return PreparedLibretroCore(manifest, source, plan)

    def plan_uninstall(self, adapter_id: str) -> PreparedLibretroCore:
        manifest, source, core_id, digest = self._details(adapter_id)
        if not self._owned_target(manifest, source, core_id, digest):
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail="core ausente ou sem ownership verificável; recusa remover",
            )
        plan = transaction.plan_write_files(
            {},
            root=self._root,
            kind="libretro.uninstall",
            removals={self._target(core_id), self._metadata_path(manifest.id)},
        )
        return PreparedLibretroCore(manifest, source, plan)

    def apply(self, prepared: PreparedLibretroCore, confirm_token: str) -> transaction.ApplyResult:
        def verify() -> None:
            expected = "missing" if prepared.plan.kind == "libretro.uninstall" else "installed"
            if self.status(prepared.manifest.id)["state"] != expected:
                raise RuntimeError("estado do core após apply não confere com o plano")

        result = transaction.apply(prepared.plan.plan_id, confirm_token, smoke=verify)
        try:
            self.persist_status(prepared.manifest.id)
        except Exception:
            transaction.rollback(result.operation_id, reason="libretro-state-failed")
            raise
        return result

    def rollback(self, adapter_id: str, operation_id: str) -> transaction.RollbackResult:
        result = transaction.rollback(operation_id, reason="libretro-manual")
        self.persist_status(adapter_id)
        return result

    def persist_status(self, adapter_id: str) -> None:
        manifest = self._registry.get(adapter_id)
        observed = self.status(adapter_id)
        self._store.save_component(
            {
                "id": adapter_id,
                "adapter_id": adapter_id,
                "kind": manifest.kind,
                "version": observed.get("version"),
                "origin": observed.get("origin"),
                "state": observed["state"],
                "manifest_hash": manifest.manifest_hash,
            }
        )

    def _extract_verified(
        self, manifest: AdapterManifest, source: AdapterSource, core_id: str, digest: str
    ) -> Path:
        if source.sha256 is None:
            raise SteamZeroError("E-SUPPLY-NO-CHECKSUM", detail="arquivo de cores sem digest")
        artifact = self._artifacts.fetch(source)
        if crypto.digest_bytes(artifact).hexdigest != source.sha256:
            raise SteamZeroError("E-SUPPLY-CHECKSUM", detail="arquivo de cores diverge do pin")
        cache = paths.data_home() / "downloads" / "libretro" / source.sha256
        if cache.exists() or cache.is_symlink():
            if (
                cache.is_symlink()
                or not cache.is_file()
                or fs.hash_file(cache, algo="sha256") != source.sha256
            ):
                raise SteamZeroError("E-SUPPLY-CHECKSUM", detail="cache de cores diverge do pin")
        else:
            fs.write_atomic(cache, artifact, mode=0o600)

        expected_name = _ARCHIVE_PREFIX + f"{core_id}_libretro.so"
        stage = paths.staging_dir() / "libretro" / source.sha256 / manifest.id
        fs.ensure_dir(stage)
        try:
            with py7zr.SevenZipFile(cache, mode="r") as archive:
                names = archive.getnames()
                if names.count(expected_name) != 1:
                    raise ValueError("arquivo não contém exatamente o core declarado")
                archive.extract(path=stage, targets=[expected_name])
        except (OSError, ValueError, py7zr.Bad7zFile) as exc:
            raise SteamZeroError(
                "E-SUPPLY-REMOTE-FAILED", detail=f"arquivo de cores inválido: {exc}"
            ) from exc
        extracted = stage / expected_name
        try:
            if (
                not fs.is_within(stage, extracted)
                or extracted.is_symlink()
                or not extracted.is_file()
            ):
                raise ValueError("extração do core não é arquivo regular seguro")
            if extracted.stat().st_size > _MAX_CORE_BYTES:
                raise ValueError("core excede o limite de tamanho")
            if fs.hash_file(extracted, algo="sha256") != digest:
                raise ValueError("digest do core extraído diverge do manifesto")
        except (OSError, ValueError) as exc:
            raise SteamZeroError("E-SUPPLY-CHECKSUM", detail=str(exc)) from exc
        return extracted

    def _owned_target(
        self, manifest: AdapterManifest, source: AdapterSource, core_id: str, digest: str
    ) -> bool:
        target = self._target(core_id)
        metadata = self._metadata_path(manifest.id)
        if (
            target.is_symlink()
            or metadata.is_symlink()
            or not target.is_file()
            or not metadata.is_file()
        ):
            return False
        try:
            return (
                json.loads(metadata.read_text(encoding="utf-8"))
                == self._metadata(manifest, source, core_id, digest)
                and fs.hash_file(target, algo="sha256") == digest
            )
        except (OSError, ValueError, json.JSONDecodeError):
            return False

    def _details(self, adapter_id: str) -> tuple[AdapterManifest, AdapterSource, str, str]:
        manifest = self._registry.get(adapter_id)
        if manifest.kind != "core" or manifest.core is None:
            raise SteamZeroError("E-API-SCHEMA", detail=f"{adapter_id} não é adapter de core")
        source = manifest.preferred_source("archive", allow_eol=False)
        return manifest, source, manifest.core.id, manifest.core.sha256

    def _target(self, core_id: str) -> Path:
        return self._root / f"{core_id}_libretro.so"

    def _metadata_path(self, adapter_id: str) -> Path:
        return self._root / _METADATA_DIR / f"{adapter_id}.json"

    @staticmethod
    def _metadata(
        manifest: AdapterManifest, source: AdapterSource, core_id: str, digest: str
    ) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "adapterId": manifest.id,
            "coreId": core_id,
            "coreSha256": digest,
            "archiveSha256": source.sha256,
            "version": source.version,
            "manifestHash": manifest.manifest_hash,
        }


def _default_core_root() -> Path:
    return Path.home() / ".var/app/org.libretro.RetroArch/config/retroarch/cores"
