# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Loader e registry dos manifestos adapter-v1."""

from __future__ import annotations

import hashlib
import importlib.resources
import json
import re
from dataclasses import dataclass
from typing import Any

from jsonschema import ValidationError

from steamzero.api import contracts
from steamzero.core.errors import SteamZeroError

_SCHEMA = "adapter-v1.schema.json"
_FLATPAK_COMMIT_RE = re.compile(r"^[a-f0-9]{64}$")
_FLATPAK_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,254}$")
_FLATPAK_REMOTE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


@dataclass(frozen=True)
class AdapterSource:
    type: str
    version: str
    priority: int
    ref: str | None = None
    remote: str | None = None
    url: str | None = None
    sha256: str | None = None
    end_of_life: bool = False


@dataclass(frozen=True)
class AdapterManifest:
    schema_version: int
    id: str
    kind: str
    platforms: tuple[str, ...]
    capabilities: frozenset[str]
    sources: tuple[AdapterSource, ...]
    license: str
    upstream: str
    verify_smoke_test: tuple[str, ...]
    conflicts: tuple[str, ...]
    requires: tuple[str, ...]
    manifest_hash: str
    raw: dict[str, Any]

    def preferred_source(self, source_type: str | None = None) -> AdapterSource:
        candidates = [s for s in self.sources if source_type is None or s.type == source_type]
        if not candidates:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=f"adapter {self.id} não oferece fonte {source_type!r}",
            )
        return min(candidates, key=lambda source: source.priority)


def load_manifest(data: dict[str, Any]) -> AdapterManifest:
    """Valida schema e invariantes semânticas e retorna um modelo imutável."""
    try:
        contracts.validate(data, _SCHEMA)
    except (ValidationError, KeyError, TypeError, ValueError) as exc:
        raise SteamZeroError("E-API-SCHEMA", detail=f"adapter inválido: {exc}") from exc

    capabilities = frozenset(str(value) for value in data["capabilities"])
    missing = {"detect", "status"} - capabilities
    if missing:
        raise SteamZeroError(
            "E-API-SCHEMA", detail=f"adapter {data['id']} sem capacidades: {sorted(missing)}"
        )
    smoke = tuple(str(value) for value in data.get("verify", {}).get("smokeTest", ()))
    if "install" in capabilities and ("verify" not in capabilities or not smoke):
        raise SteamZeroError(
            "E-API-SCHEMA",
            detail=f"adapter instalável {data['id']} exige capability verify e smokeTest",
        )
    if any("\x00" in argument or len(argument) > 256 for argument in smoke):
        raise SteamZeroError("E-API-SCHEMA", detail=f"adapter {data['id']} tem smokeTest inválido")

    sources = tuple(
        AdapterSource(
            type=source["type"],
            version=source["version"],
            priority=source["priority"],
            ref=source.get("ref"),
            remote=source.get("remote"),
            url=source.get("url"),
            sha256=source.get("sha256"),
            end_of_life=source.get("endOfLife", False),
        )
        for source in data["sources"]
    )
    if any(source.type != "flatpak" and not source.sha256 for source in sources):
        raise SteamZeroError(
            "E-SUPPLY-NO-CHECKSUM", detail=f"adapter {data['id']} tem artefato sem sha256"
        )
    for source in sources:
        if source.type == "flatpak" and not _FLATPAK_COMMIT_RE.fullmatch(source.version):
            raise SteamZeroError(
                "E-SUPPLY-NO-CHECKSUM",
                detail=f"adapter {data['id']} tem commit Flatpak não pinado",
            )
        if source.type == "flatpak" and (
            source.ref is None
            or source.remote is None
            or not _FLATPAK_REF_RE.fullmatch(source.ref)
            or not _FLATPAK_REMOTE_RE.fullmatch(source.remote)
        ):
            raise SteamZeroError(
                "E-API-SCHEMA", detail=f"adapter {data['id']} tem origem Flatpak inválida"
            )

    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return AdapterManifest(
        schema_version=data["schemaVersion"],
        id=data["id"],
        kind=data["kind"],
        platforms=tuple(data["platforms"]),
        capabilities=capabilities,
        sources=sources,
        license=data["license"],
        upstream=data["upstream"],
        verify_smoke_test=smoke,
        conflicts=tuple(data.get("conflicts", ())),
        requires=tuple(data.get("requires", ())),
        manifest_hash=hashlib.sha256(canonical.encode()).hexdigest(),
        raw=data,
    )


class AdapterRegistry:
    """Registry fechado, sem duplicatas ou dependências inexistentes."""

    def __init__(self, manifests: list[AdapterManifest]) -> None:
        self._items: dict[str, AdapterManifest] = {}
        for manifest in manifests:
            if manifest.id in self._items:
                raise SteamZeroError("E-API-SCHEMA", detail=f"adapter duplicado: {manifest.id}")
            self._items[manifest.id] = manifest
        known = set(self._items)
        for manifest in manifests:
            unknown = (set(manifest.requires) | set(manifest.conflicts)) - known
            if unknown:
                raise SteamZeroError(
                    "E-API-SCHEMA",
                    detail=f"adapter {manifest.id} referencia IDs ausentes: {sorted(unknown)}",
                )

    @classmethod
    def bundled(cls) -> AdapterRegistry:
        directory = importlib.resources.files("steamzero.adapters").joinpath("manifests")
        manifests: list[AdapterManifest] = []
        for entry in sorted(directory.iterdir(), key=lambda item: item.name):
            if entry.name.endswith(".adapter.json"):
                data = json.loads(entry.read_text(encoding="utf-8"))
                manifests.append(load_manifest(data))
        registry = cls(manifests)
        from steamzero.adapters.lockfile import validate_registry_lock

        validate_registry_lock(registry.list())
        return registry

    def get(self, adapter_id: str) -> AdapterManifest:
        try:
            return self._items[adapter_id]
        except KeyError as exc:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail=f"adapter desconhecido: {adapter_id}"
            ) from exc

    def list(self) -> list[AdapterManifest]:
        return [self._items[key] for key in sorted(self._items)]
