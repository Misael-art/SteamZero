# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Loader e registry dos manifestos adapter-v1."""

from __future__ import annotations

import importlib.resources
import json
import re
from builtins import list as builtin_list
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from jsonschema import ValidationError

from steamzero.api import contracts
from steamzero.core import crypto
from steamzero.core.errors import SteamZeroError

_SCHEMA = "adapter-v1.schema.json"
_RETIRED_SCHEMA = "retired-adapter-catalog-v1.schema.json"
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
class KeyRequirement:
    """Requisito de keyset declarado por um adapter (nunca conteúdo de key)."""

    platform: str
    keyset: str
    minimum_key_revision: int | None = None


@dataclass(frozen=True)
class FirmwareRequirement:
    """Requisito de firmware declarado por um adapter."""

    platform: str
    minimum_version: str | None = None


@dataclass(frozen=True)
class AdapterPresentation:
    """Como o adapter se apresenta na UI, declarado no manifesto.

    Existe para tirar nome e ícone de um dict Python paralelo ao contrato.
    Apresentação hardcoded funciona como allowlist implícita: um emulador
    declarado em manifesto mas ausente do dict aparece sem nome e sem ícone, e a
    causa fica invisível porque nada falha.
    """

    display_name: str
    icon_asset: str


@dataclass(frozen=True)
class AdapterTombstone:
    """Decisão explícita de retirada com manifesto histórico verificável."""

    adapter_id: str
    retired_at: str
    last_supported_version: str
    reason: str
    replacement_adapter_id: str | None
    deployment_policy: str
    data_policy: str
    legacy_manifest: AdapterManifest


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
    requires_keys: KeyRequirement | None = None
    requires_firmware: FirmwareRequirement | None = None
    presentation: AdapterPresentation | None = None

    def preferred_source(
        self, source_type: str | None = None, *, allow_eol: bool = True
    ) -> AdapterSource:
        matching = [s for s in self.sources if source_type is None or s.type == source_type]
        candidates = (
            matching if allow_eol else [source for source in matching if not source.end_of_life]
        )
        if not candidates:
            if matching:
                raise SteamZeroError(
                    "E-SUPPLY-UPSTREAM-GONE",
                    detail=f"todas as fontes {source_type or 'disponíveis'} de {self.id} estão EOL",
                )
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
    priorities = [source.priority for source in sources]
    if len(priorities) != len(set(priorities)):
        raise SteamZeroError(
            "E-API-SCHEMA", detail=f"adapter {data['id']} tem prioridades de fonte duplicadas"
        )
    if any(source.type != "flatpak" and not source.sha256 for source in sources):
        raise SteamZeroError(
            "E-SUPPLY-NO-CHECKSUM", detail=f"adapter {data['id']} tem artefato sem sha256"
        )
    for source in sources:
        if source.type == "flatpak" and (source.url is not None or source.sha256 is not None):
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail=f"adapter {data['id']} mistura campos Flatpak e portáteis",
            )
        if source.type != "flatpak" and (source.ref is not None or source.remote is not None):
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail=f"adapter {data['id']} mistura campos portáteis e Flatpak",
            )
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

    platforms = tuple(data["platforms"])
    requires_keys = _parse_key_requirement(data.get("requiresKeys"), data["id"], platforms)
    requires_firmware = _parse_firmware_requirement(
        data.get("requiresFirmware"), data["id"], platforms
    )

    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return AdapterManifest(
        schema_version=data["schemaVersion"],
        id=data["id"],
        kind=data["kind"],
        platforms=platforms,
        capabilities=capabilities,
        sources=sources,
        license=data["license"],
        upstream=data["upstream"],
        verify_smoke_test=smoke,
        conflicts=tuple(data.get("conflicts", ())),
        requires=tuple(data.get("requires", ())),
        manifest_hash=crypto.digest_bytes(canonical.encode()).hexdigest,
        raw=data,
        requires_keys=requires_keys,
        requires_firmware=requires_firmware,
        presentation=_parse_presentation(data.get("presentation")),
    )


def load_retired_catalog(data: dict[str, Any]) -> list[AdapterTombstone]:
    """Carrega tombstones sem transformar ausência de manifesto em retirada.

    O manifesto histórico é parte do tombstone para que um deployment já
    instalado ainda possa ser observado e desinstalado, sem reabrir instalação,
    atualização, reparo, launch ou configuração.
    """
    try:
        contracts.validate(data, _RETIRED_SCHEMA)
    except (ValidationError, KeyError, TypeError, ValueError) as exc:
        raise SteamZeroError("E-API-SCHEMA", detail=f"catálogo retired inválido: {exc}") from exc
    tombstones: list[AdapterTombstone] = []
    for item in data["tombstones"]:
        legacy = load_manifest(item["legacyManifest"])
        if legacy.id != item["adapterId"]:
            raise SteamZeroError(
                "E-API-SCHEMA", detail="tombstone não confere com manifesto legado"
            )
        source = legacy.preferred_source(allow_eol=True)
        if source.version != item["lastSupportedVersion"]:
            raise SteamZeroError(
                "E-API-SCHEMA", detail=f"tombstone {legacy.id} não confere com última versão"
            )
        if "uninstall" not in legacy.capabilities:
            raise SteamZeroError(
                "E-API-SCHEMA", detail=f"tombstone {legacy.id} não permite desinstalação segura"
            )
        tombstones.append(
            AdapterTombstone(
                adapter_id=item["adapterId"],
                retired_at=item["retiredAt"],
                last_supported_version=item["lastSupportedVersion"],
                reason=item["reason"],
                replacement_adapter_id=item.get("replacementAdapterId"),
                deployment_policy=item["deploymentPolicy"],
                data_policy=item["dataPolicy"],
                legacy_manifest=legacy,
            )
        )
    return tombstones


def _parse_presentation(value: Any) -> AdapterPresentation | None:
    """Apresentação declarada, quando o manifesto a traz.

    Opcional por compatibilidade: manifesto sem ``presentation`` continua válido
    e a ausência é visível como ``None``, em vez de virar nome vazio silencioso.
    """
    if not isinstance(value, dict):
        return None
    name = value.get("displayName")
    icon = value.get("iconAsset")
    if not isinstance(name, str) or not isinstance(icon, str) or not name or not icon:
        return None
    return AdapterPresentation(display_name=name, icon_asset=icon)


def _parse_key_requirement(
    value: Any, adapter_id: str, platforms: tuple[str, ...]
) -> KeyRequirement | None:
    if value is None:
        return None
    _require_declared_platform(value["platform"], adapter_id, platforms, "requiresKeys")
    return KeyRequirement(
        platform=value["platform"],
        keyset=value["keyset"],
        minimum_key_revision=value.get("minimumKeyRevision"),
    )


def _parse_firmware_requirement(
    value: Any, adapter_id: str, platforms: tuple[str, ...]
) -> FirmwareRequirement | None:
    if value is None:
        return None
    _require_declared_platform(value["platform"], adapter_id, platforms, "requiresFirmware")
    return FirmwareRequirement(
        platform=value["platform"],
        minimum_version=value.get("minimumVersion"),
    )


def _require_declared_platform(
    platform: str, adapter_id: str, platforms: tuple[str, ...], field: str
) -> None:
    if platform not in platforms:
        raise SteamZeroError(
            "E-API-SCHEMA",
            detail=f"adapter {adapter_id}: {field}.platform {platform!r} não está em platforms",
        )


class AdapterRegistry:
    """Registry fechado, sem duplicatas ou dependências inexistentes."""

    def __init__(
        self, manifests: list[AdapterManifest], *, retired: list[AdapterTombstone] | None = None
    ) -> None:
        self._items: dict[str, AdapterManifest] = {}
        for manifest in manifests:
            if manifest.id in self._items:
                raise SteamZeroError("E-API-SCHEMA", detail=f"adapter duplicado: {manifest.id}")
            self._items[manifest.id] = manifest
        self._retired = {item.adapter_id: item for item in retired or []}
        overlap = set(self._items) & set(self._retired)
        if overlap:
            raise SteamZeroError(
                "E-API-SCHEMA", detail=f"adapter ativo e retired: {sorted(overlap)}"
            )
        if len(self._retired) != len(retired or []):
            raise SteamZeroError(
                "E-API-SCHEMA", detail="catálogo retired contém adapters duplicados"
            )
        known = set(self._items)
        for manifest in manifests:
            unknown = (set(manifest.requires) | set(manifest.conflicts)) - known
            if unknown:
                raise SteamZeroError(
                    "E-API-SCHEMA",
                    detail=f"adapter {manifest.id} referencia IDs ausentes: {sorted(unknown)}",
                )
        for tombstone in self._retired.values():
            replacement = tombstone.replacement_adapter_id
            if replacement is not None and replacement not in self._items:
                raise SteamZeroError(
                    "E-API-SCHEMA",
                    detail=f"tombstone {tombstone.adapter_id} referencia substituto ausente",
                )

    @classmethod
    @lru_cache(maxsize=1)
    def bundled(cls) -> AdapterRegistry:
        directory = importlib.resources.files("steamzero.adapters").joinpath("manifests")
        manifests: list[AdapterManifest] = []
        for entry in sorted(directory.iterdir(), key=lambda item: item.name):
            if entry.name.endswith(".adapter.json"):
                data = json.loads(entry.read_text(encoding="utf-8"))
                manifests.append(load_manifest(data))
        retired_entry = importlib.resources.files("steamzero.adapters").joinpath(
            "retired-adapters.json"
        )
        retired = load_retired_catalog(json.loads(retired_entry.read_text(encoding="utf-8")))
        registry = cls(manifests, retired=retired)
        from steamzero.adapters.lockfile import validate_registry_lock

        validate_registry_lock(registry.list())
        return registry

    def get(self, adapter_id: str) -> AdapterManifest:
        try:
            return self._items[adapter_id]
        except KeyError as exc:
            tombstone = self._retired.get(adapter_id)
            if tombstone is not None:
                return tombstone.legacy_manifest
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail=f"adapter desconhecido: {adapter_id}"
            ) from exc

    def list(self) -> list[AdapterManifest]:
        return [self._items[key] for key in sorted(self._items)]

    def list_including_retired(self) -> builtin_list[AdapterManifest]:
        return [self.get(adapter_id) for adapter_id in sorted({*self._items, *self._retired})]

    def retired(self, adapter_id: str) -> AdapterTombstone | None:
        return self._retired.get(adapter_id)
