# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Engine única para lifecycle de artefatos portáveis declarados por adapters."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from steamzero.adapters.registry import AdapterManifest, AdapterRegistry, AdapterSource
from steamzero.core import crypto, fs, paths, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.core.net import NetworkFailure, fetch_bytes
from steamzero.core.state import StateStore

_SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$")
_MAX_ARTIFACT_BYTES = 512 * 1024 * 1024


class ArtifactPort(Protocol):
    """Porta injetável de aquisição; adapters nunca acessam rede diretamente."""

    def fetch(self, source: AdapterSource) -> bytes: ...


class HttpsArtifactPort:
    """Aquisição HTTPS limitada; autenticidade é confirmada pelo SHA-256 pinado."""

    def __init__(self, *, max_bytes: int = _MAX_ARTIFACT_BYTES) -> None:
        self._max_bytes = max_bytes

    def fetch(self, source: AdapterSource) -> bytes:
        if source.url is None or urlparse(source.url).scheme != "https":
            raise SteamZeroError("E-SUPPLY-REMOTE-FAILED", detail="fonte portátil exige URL HTTPS")
        try:
            return fetch_bytes(
                source.url,
                max_bytes=self._max_bytes,
                timeout_seconds=60.0,
                headers={"User-Agent": "SteamZero/0.1 (+https://github.com/Misael-art/SteamZero)"},
                allowed_redirect_hosts={
                    "github.com",
                    "objects.githubusercontent.com",
                    "github-releases.githubusercontent.com",
                },
            )
        except NetworkFailure as exc:
            raise SteamZeroError(
                "E-SUPPLY-REMOTE-FAILED",
                detail=f"falha ao baixar fonte verificada: {exc.detail}",
            ) from exc


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

    def plan_install(
        self,
        adapter_id: str,
        *,
        source_type: str | None = None,
        force: bool = False,
    ) -> PreparedComponent:
        manifest = self._registry.get(adapter_id)
        source = manifest.preferred_source(source_type, allow_eol=False)
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
        operation = "update" if status["state"] != "missing" else "install"
        if operation not in manifest.capabilities:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=f"adapter {adapter_id} não declara capability {operation}",
            )
        if (
            not force
            and status["state"] == "installed"
            and status.get("version") == source.version
            and status.get("sha256") == source.sha256
        ):
            plan = transaction.plan_write_files({}, root=self._root, kind=f"component.{operation}")
            return PreparedComponent(manifest, source, plan)

        artifact = self._artifacts.fetch(source)
        actual = crypto.digest_bytes(artifact).hexdigest
        if actual != source.sha256:
            raise SteamZeroError(
                "E-SUPPLY-CHECKSUM",
                detail=f"checksum divergente para {adapter_id} {source.version}",
            )

        cache_root = paths.data_home() / "downloads" / "components"
        fs.ensure_dir(cache_root)
        cached_artifact = cache_root / source.sha256
        if cached_artifact.exists() or cached_artifact.is_symlink():
            if (
                cached_artifact.is_symlink()
                or not cached_artifact.is_file()
                or self._sha256_file(cached_artifact) != source.sha256
            ):
                raise SteamZeroError(
                    "E-SUPPLY-CHECKSUM",
                    detail="cache local do artefato diverge do checksum publicado",
                )
        else:
            fs.write_atomic(cached_artifact, artifact, mode=0o600)

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

        if payload.exists() or payload.is_symlink():
            if self._sha256_file(payload) != source.sha256:
                if not force:
                    # Instalar por cima de payload divergente apagaria evidência
                    # de adulteração sem que ninguém decidisse isso. O reparo é
                    # a decisão explícita de refazer, e chega com force=True.
                    raise SteamZeroError(
                        "E-COMPONENT-DEGRADED",
                        detail="payload existente diverge; remova o deployment antes de reinstalar",
                    )
                # Reparo: o payload divergente é substituído pelo artefato
                # fixado. A cópia entra na mesma transação, então uma falha no
                # meio restaura o estado anterior em vez de deixar o componente
                # sem payload nenhum.
                plan = transaction.plan_copy_files(
                    {cached_artifact: payload},
                    root=self._root,
                    kind=f"component.{operation}",
                    writes={current: current_bytes},
                    replace_existing=True,
                )
                return PreparedComponent(manifest, source, plan)
            plan = transaction.plan_write_files(
                {current: current_bytes}, root=self._root, kind=f"component.{operation}"
            )
        else:
            plan = transaction.plan_copy_files(
                {cached_artifact: payload},
                root=self._root,
                kind=f"component.{operation}",
                writes={current: current_bytes},
            )
        return PreparedComponent(manifest, source, plan)

    def plan_uninstall(self, adapter_id: str) -> PreparedComponent:
        manifest = self._registry.get(adapter_id)
        if "uninstall" not in manifest.capabilities:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=f"adapter {adapter_id} não declara capability uninstall",
            )
        status = self.status(adapter_id)
        if status["state"] == "missing":
            raise SteamZeroError("E-COMPONENT-DEGRADED", detail="emulador já está ausente")
        version = status.get("version")
        if not isinstance(version, str) or not _SAFE_VERSION.fullmatch(version):
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail="deployment atual não pode ser removido com segurança",
            )
        source = manifest.preferred_source("appimage", allow_eol=True)
        current = self._root / manifest.id / "current.json"
        payload = self._root / manifest.id / "releases" / version / "payload"
        plan = transaction.plan_write_files(
            {},
            root=self._root,
            kind="component.uninstall",
            removals={current, payload},
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
            if prepared.plan.kind == "component.uninstall":
                if status["state"] != "missing":
                    raise RuntimeError("componente continuou detectável após desinstalação")
                return
            if status["state"] != "installed" or status.get("version") != prepared.source.version:
                raise RuntimeError("componente ativado não corresponde ao plano")
            if prepared.source.type == "appimage":
                fs.set_mode(self.payload_path(prepared.manifest.id), 0o700)
            if smoke is not None:
                smoke()

        result = transaction.apply(prepared.plan.plan_id, confirm_token, smoke=verify_component)
        try:
            self.persist_status(prepared.manifest.id)
        except Exception:
            transaction.rollback(result.operation_id, reason="component-state-failed")
            raise
        return result

    def rollback(self, adapter_id: str, operation_id: str) -> transaction.RollbackResult:
        result = transaction.rollback(operation_id, reason="component-manual")
        if self.status(adapter_id)["state"] == "installed":
            source = self._registry.get(adapter_id).preferred_source(allow_eol=True)
            if source.type == "appimage":
                fs.set_mode(self.payload_path(adapter_id), 0o700)
        self.persist_status(adapter_id)
        return result

    def detect(self, adapter_id: str) -> bool:
        return self.status(adapter_id)["state"] == "installed"

    def payload_path(self, adapter_id: str) -> Path:
        status = self.status(adapter_id)
        version = status.get("version")
        if status["state"] != "installed" or not isinstance(version, str):
            raise SteamZeroError("E-COMPONENT-DEGRADED", detail="emulador não instalado")
        return self._root / adapter_id / "releases" / version / "payload"

    def status(self, adapter_id: str) -> dict[str, object]:
        manifest = self._registry.get(adapter_id)
        current = self._root / manifest.id / "current.json"
        if not current.is_file() or current.is_symlink():
            return {"id": adapter_id, "state": "missing"}
        try:
            metadata = json.loads(current.read_text(encoding="utf-8"))
            if metadata.get("schemaVersion") != 1:
                raise ValueError("schema de metadata inválido")
            if metadata.get("adapterId") != manifest.id:
                raise ValueError("metadata pertence a outro adapter")
            version = str(metadata["version"])
            expected = str(metadata["sha256"])
            origin = str(metadata["origin"])
            manifest_drift = metadata.get("manifestHash") != manifest.manifest_hash
            if not _SAFE_VERSION.fullmatch(version) or origin not in {"appimage", "native"}:
                raise ValueError("metadados de origem/versão inválidos")
            payload = self._root / manifest.id / "releases" / version / "payload"
            if not fs.is_within(self._root, payload):
                raise ValueError("payload escapa da raiz de componentes")
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
        if manifest_drift:
            # Divergência de manifesto tem duas causas opostas, e colapsá-las em
            # `degraded` fez o Citron aparecer quebrado no host quando o que
            # havia mudado era só o pin. Se a fonte fixada AGORA difere da que
            # foi implantada, o deployment está íntegro e apenas velho —
            # `outdated`, que se resolve com update. Se a fonte fixada é a mesma
            # e ainda assim o manifesto mudou, o artefato não explica a
            # diferença: isso permanece `degraded`, porque é o sinal de supply
            # chain que a checagem existe para dar.
            pinned = self._pinned_source(manifest)
            if pinned is not None and (version, expected) != pinned:
                return {
                    "id": adapter_id,
                    "state": "outdated",
                    "version": version,
                    "origin": origin,
                    "sha256": expected,
                    "targetVersion": pinned[0],
                    "detail": f"implantado {version}; a fonte fixada agora é {pinned[0]}",
                }
            return {
                "id": adapter_id,
                "state": "degraded",
                "version": version,
                "origin": origin,
                "sha256": expected,
                "detail": "manifesto do deployment divergiu sem mudança na fonte fixada",
            }
        return {
            "id": adapter_id,
            "state": "installed",
            "version": version,
            "origin": origin,
            "sha256": expected,
        }

    @staticmethod
    def _pinned_source(manifest: AdapterManifest) -> tuple[str, str] | None:
        """(versão, sha256) da fonte portátil fixada, ou None se indisponível."""
        try:
            source = manifest.preferred_source(allow_eol=True)
        except SteamZeroError:
            return None
        if source.sha256 is None:
            return None
        return str(source.version), str(source.sha256)

    def persist_status(self, adapter_id: str) -> None:
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
        return crypto.digest_file(path).hexdigest
