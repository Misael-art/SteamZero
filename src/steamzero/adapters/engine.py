# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Engine única para lifecycle de artefatos portáveis declarados por adapters."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from steamzero.adapters.registry import AdapterManifest, AdapterRegistry, AdapterSource
from steamzero.core import fs, paths, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore

_SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")


class ArtifactPort(Protocol):
    """Porta injetável de aquisição; adapters nunca acessam rede diretamente."""

    def fetch(self, source: AdapterSource) -> bytes: ...


@dataclass(frozen=True)
class PreparedComponent:
    manifest: AdapterManifest
    source: AdapterSource
    plan: transaction.Plan


class AdapterEngine:
    """Planeja e aplica install/update com checksum e rollback G-FULL."""

    def __init__(
        self,
        store: StateStore,
        registry: AdapterRegistry,
        artifacts: ArtifactPort,
        *,
        root: Path | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._artifacts = artifacts
        self._root = root or paths.data_home() / "components"
        fs.ensure_dir(self._root)

    def plan_install(self, adapter_id: str, *, source_type: str | None = None) -> PreparedComponent:
        manifest = self._registry.get(adapter_id)
        if "install" not in manifest.capabilities:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail=f"adapter {adapter_id} não é instalável"
            )
        source = manifest.preferred_source(source_type)
        if source.type == "flatpak":
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail="executor Flatpak ainda não está habilitado; use uma fonte portável",
            )
        if source.sha256 is None:
            raise SteamZeroError(
                "E-SUPPLY-NO-CHECKSUM", detail=f"fonte {adapter_id}/{source.type} sem sha256"
            )

        status = self.status(adapter_id)
        if (
            status["state"] == "installed"
            and status.get("version") == source.version
            and status.get("sha256") == source.sha256
        ):
            plan = transaction.plan_write_files(
                {}, root=self._root, kind=f"component.{self._operation(adapter_id)}"
            )
            return PreparedComponent(manifest, source, plan)

        artifact = self._artifacts.fetch(source)
        actual = hashlib.sha256(artifact).hexdigest()
        if actual != source.sha256:
            raise SteamZeroError(
                "E-SUPPLY-CHECKSUM",
                detail=f"checksum divergente para {adapter_id} {source.version}",
            )

        component_root = self._root / manifest.id
        payload = component_root / "releases" / source.version / "payload"
        current = component_root / "current.json"
        metadata = {
            "schemaVersion": 1,
            "adapterId": manifest.id,
            "version": source.version,
            "origin": source.type,
            "sha256": source.sha256,
            "manifestHash": manifest.manifest_hash,
        }
        current_bytes = json.dumps(
            metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()

        files: dict[Path, bytes]
        files = {payload: artifact, current: current_bytes}
        plan = transaction.plan_write_files(
            files, root=self._root, kind=f"component.{self._operation(adapter_id)}"
        )
        return PreparedComponent(manifest, source, plan)

    def apply(
        self,
        prepared: PreparedComponent,
        confirm_token: str,
        *,
        smoke: Callable[[], None] | None = None,
    ) -> transaction.ApplyResult:
        def verify_component() -> None:
            status = self.status(prepared.manifest.id)
            if status["state"] != "installed" or status.get("version") != prepared.source.version:
                raise RuntimeError("componente ativado não corresponde ao plano")
            if smoke is not None:
                smoke()

        result = transaction.apply(prepared.plan.plan_id, confirm_token, smoke=verify_component)
        try:
            self._persist_status(prepared.manifest.id)
        except Exception:
            transaction.rollback(result.operation_id, reason="component-state-failed")
            raise
        return result

    def rollback(self, adapter_id: str, operation_id: str) -> transaction.RollbackResult:
        result = transaction.rollback(operation_id, reason="component-manual")
        self._persist_status(adapter_id)
        return result

    def detect(self, adapter_id: str) -> bool:
        return self.status(adapter_id)["state"] == "installed"

    def status(self, adapter_id: str) -> dict[str, object]:
        manifest = self._registry.get(adapter_id)
        current = self._root / manifest.id / "current.json"
        if not current.is_file() or current.is_symlink():
            return {"id": adapter_id, "state": "missing"}
        try:
            metadata = json.loads(current.read_text(encoding="utf-8"))
            version = str(metadata["version"])
            expected = str(metadata["sha256"])
            origin = str(metadata["origin"])
            if not _SAFE_VERSION.fullmatch(version) or origin not in {"appimage", "native"}:
                raise ValueError("metadados de origem/versão inválidos")
            payload = self._root / manifest.id / "releases" / version / "payload"
            actual = self._sha256_file(payload)
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return {"id": adapter_id, "state": "degraded", "detail": str(exc)}
        if actual != expected:
            return {
                "id": adapter_id,
                "state": "degraded",
                "version": version,
                "origin": origin,
                "sha256": expected,
                "detail": "payload ausente ou checksum divergente",
            }
        return {
            "id": adapter_id,
            "state": "installed",
            "version": version,
            "origin": origin,
            "sha256": expected,
        }

    def _operation(self, adapter_id: str) -> str:
        return "update" if self.detect(adapter_id) else "install"

    def _persist_status(self, adapter_id: str) -> None:
        manifest = self._registry.get(adapter_id)
        status = self.status(adapter_id)
        self._store.save_component(
            {
                "id": adapter_id,
                "adapter_id": adapter_id,
                "kind": manifest.kind,
                "version": status.get("version"),
                "origin": status.get("origin"),
                "state": status["state"],
                "manifest_hash": manifest.manifest_hash,
            }
        )

    @staticmethod
    def _sha256_file(path: Path) -> str | None:
        if not path.is_file() or path.is_symlink():
            return None
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1 << 20):
                digest.update(chunk)
        return digest.hexdigest()
