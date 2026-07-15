# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Lockfile empacotado dos componentes declarativos.

O manifesto descreve capacidades; o lockfile congela a origem efetivamente
promovida. O registry só fica disponível quando os dois artefatos concordam.
"""

from __future__ import annotations

import importlib.resources
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from jsonschema import ValidationError

from steamzero.api import contracts
from steamzero.core.errors import SteamZeroError

if TYPE_CHECKING:
    from steamzero.adapters.registry import AdapterManifest

_SCHEMA = "component-lock-v1.schema.json"


@dataclass(frozen=True)
class LockedSource:
    type: str
    version: str
    priority: int
    ref: str | None
    remote: str | None
    url: str | None
    sha256: str | None
    end_of_life: bool


@dataclass(frozen=True)
class LockedComponent:
    id: str
    manifest_hash: str
    source: LockedSource


@dataclass(frozen=True)
class ComponentLock:
    schema_version: int
    components: tuple[LockedComponent, ...]

    def get(self, adapter_id: str) -> LockedComponent:
        for component in self.components:
            if component.id == adapter_id:
                return component
        raise SteamZeroError(
            "E-SUPPLY-CHECKSUM", detail=f"adapter {adapter_id} ausente do lockfile"
        )


def load_component_lock(data: dict[str, Any]) -> ComponentLock:
    try:
        contracts.validate(data, _SCHEMA)
    except (ValidationError, KeyError, TypeError, ValueError) as exc:
        raise SteamZeroError("E-API-SCHEMA", detail=f"lockfile inválido: {exc}") from exc
    components = tuple(
        LockedComponent(
            id=item["id"],
            manifest_hash=item["manifestHash"],
            source=LockedSource(
                type=item["source"]["type"],
                version=item["source"]["version"],
                priority=item["source"]["priority"],
                ref=item["source"].get("ref"),
                remote=item["source"].get("remote"),
                url=item["source"].get("url"),
                sha256=item["source"].get("sha256"),
                end_of_life=item["source"].get("endOfLife", False),
            ),
        )
        for item in data["components"]
    )
    ids = [component.id for component in components]
    if len(ids) != len(set(ids)):
        raise SteamZeroError("E-API-SCHEMA", detail="lockfile contém adapters duplicados")
    return ComponentLock(schema_version=data["schemaVersion"], components=components)


def bundled_component_lock() -> ComponentLock:
    entry = importlib.resources.files("steamzero.adapters").joinpath("component-lock.json")
    return load_component_lock(json.loads(entry.read_text(encoding="utf-8")))


def validate_registry_lock(
    manifests: list[AdapterManifest], component_lock: ComponentLock | None = None
) -> ComponentLock:
    """Recusa drift entre manifestos empacotados e o lockfile promovido."""
    locked = component_lock or bundled_component_lock()
    manifest_ids = {manifest.id for manifest in manifests}
    lock_ids = {component.id for component in locked.components}
    if manifest_ids != lock_ids:
        raise SteamZeroError(
            "E-SUPPLY-CHECKSUM",
            detail=(
                "lockfile diverge do registry: "
                f"sem lock={sorted(manifest_ids - lock_ids)}, "
                f"órfãos={sorted(lock_ids - manifest_ids)}"
            ),
        )
    for manifest in manifests:
        entry = locked.get(manifest.id)
        source = manifest.preferred_source()
        observed = (
            manifest.manifest_hash,
            source.type,
            source.version,
            source.priority,
            source.ref,
            source.remote,
            source.url,
            source.sha256,
            source.end_of_life,
        )
        expected = (
            entry.manifest_hash,
            entry.source.type,
            entry.source.version,
            entry.source.priority,
            entry.source.ref,
            entry.source.remote,
            entry.source.url,
            entry.source.sha256,
            entry.source.end_of_life,
        )
        if observed != expected:
            raise SteamZeroError(
                "E-SUPPLY-CHECKSUM",
                detail=f"lockfile divergente para {manifest.id}",
            )
    return locked
