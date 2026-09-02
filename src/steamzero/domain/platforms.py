# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Registry declarativo de plataformas e projeção segura para a UI."""

from __future__ import annotations

import importlib.resources
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit

from jsonschema import ValidationError

from steamzero.api import contracts
from steamzero.core.errors import SteamZeroError

_SCHEMA = "platform-manifest-v1.schema.json"
_REQUIREMENT_KINDS = frozenset({"keys", "firmware"})


@dataclass(frozen=True)
class PlatformManifest:
    schema_version: int
    id: str
    kind: str
    name: str
    short_name: str
    icon_key: str
    artwork_asset: str
    systems: tuple[str, ...]
    capabilities: tuple[dict[str, Any], ...]
    areas: tuple[dict[str, Any], ...]
    emulators: tuple[dict[str, Any], ...]
    media: dict[str, Any]
    controls: dict[str, Any]
    timing: dict[str, Any]
    presets: tuple[dict[str, Any], ...]
    cloud: dict[str, Any] | None
    requirements: tuple[str, ...]


def load_platform_manifest(data: dict[str, Any]) -> PlatformManifest:
    """Valida schema, referências internas, URLs e unicidade sem executar dados."""
    try:
        contracts.validate(data, _SCHEMA)
    except (ValidationError, KeyError, TypeError, ValueError) as exc:
        raise SteamZeroError(
            "E-API-SCHEMA", detail=f"manifesto de plataforma inválido: {exc}"
        ) from exc

    for field in ("capabilities", "areas", "emulators", "presets"):
        values = [str(item["id"]) for item in data[field]]
        if len(values) != len(set(values)):
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail=f"plataforma {data['id']} possui {field} duplicados",
            )
    precedences = [int(item["precedence"]) for item in data["emulators"]]
    if len(precedences) != len(set(precedences)):
        raise SteamZeroError(
            "E-API-SCHEMA",
            detail=f"plataforma {data['id']} possui precedências duplicadas",
        )
    capability_ids = {str(item["id"]) for item in data["capabilities"]}
    unknown = {
        str(area["capabilityId"])
        for area in data["areas"]
        if area["capabilityId"] not in capability_ids
    }
    if unknown:
        raise SteamZeroError(
            "E-API-SCHEMA",
            detail=f"plataforma {data['id']} referencia capabilities ausentes: {sorted(unknown)}",
        )
    action_ids = [
        str(capability["action"]["id"])
        for capability in data["capabilities"]
        if capability["action"] is not None
    ]
    if len(action_ids) != len(set(action_ids)):
        raise SteamZeroError(
            "E-API-SCHEMA",
            detail=f"plataforma {data['id']} possui actions duplicadas",
        )

    requirements = tuple(str(item) for item in data.get("requirements", ()))
    unknown_requirements = set(requirements) - _REQUIREMENT_KINDS
    if unknown_requirements:
        raise SteamZeroError(
            "E-API-SCHEMA",
            detail=(
                f"plataforma {data['id']} possui requisitos desconhecidos: "
                f"{sorted(unknown_requirements)}"
            ),
        )

    cloud = data["cloud"]
    if data["kind"] == "cloud":
        if cloud is None or data["emulators"]:
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail=f"plataforma cloud {data['id']} exige cloud e não aceita emuladores",
            )
        parsed = urlsplit(str(cloud["launchUrl"]))
        try:
            port = parsed.port
        except ValueError as exc:
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail=f"plataforma cloud {data['id']} possui porta inválida",
            ) from exc
        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or parsed.password is not None
            or port not in {None, 443}
            or parsed.hostname not in cloud["allowedHosts"]
        ):
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail=f"plataforma cloud {data['id']} possui launchUrl fora da allowlist",
            )
    elif cloud is not None:
        raise SteamZeroError(
            "E-API-SCHEMA",
            detail=f"plataforma emulada {data['id']} não pode declarar cloud",
        )

    return PlatformManifest(
        schema_version=data["schemaVersion"],
        id=data["id"],
        kind=data["kind"],
        name=data["name"],
        short_name=data["shortName"],
        icon_key=data["iconKey"],
        artwork_asset=data["artworkAsset"],
        systems=tuple(data["systems"]),
        capabilities=tuple(dict(item) for item in data["capabilities"]),
        areas=tuple(dict(item) for item in data["areas"]),
        emulators=tuple(dict(item) for item in data["emulators"]),
        media=dict(data["media"]),
        controls=dict(data["controls"]),
        timing=dict(data["timing"]),
        presets=tuple(dict(item) for item in data["presets"]),
        cloud=dict(cloud) if cloud is not None else None,
        requirements=requirements,
    )


class PlatformRegistry:
    """Registry fechado e ordenado; IDs nunca escolhem símbolos executáveis."""

    def __init__(self, manifests: list[PlatformManifest]) -> None:
        self._items: dict[str, PlatformManifest] = {}
        for manifest in manifests:
            if manifest.id in self._items:
                raise SteamZeroError("E-API-SCHEMA", detail=f"plataforma duplicada: {manifest.id}")
            self._items[manifest.id] = manifest

    @classmethod
    @lru_cache(maxsize=1)
    def bundled(cls) -> PlatformRegistry:
        """Manifestos empacotados, validados uma única vez por processo.

        O snapshot compõe o registry repetidamente (por jogo e por emulador);
        antes do cache cada chamada relia e revalidava os 36 manifestos contra
        o schema — ~77 ms por chamada, dezenas de chamadas por snapshot.
        Os manifestos são estáticos da release: cache é seguro e idempotente.
        """
        directory = importlib.resources.files("steamzero.platform_manifests")
        manifests: list[PlatformManifest] = []
        for entry in sorted(directory.iterdir(), key=lambda item: item.name):
            if entry.name.endswith(".platform.json"):
                value = json.loads(entry.read_text(encoding="utf-8"))
                if not isinstance(value, dict):
                    raise SteamZeroError(
                        "E-API-SCHEMA", detail=f"{entry.name} precisa conter objeto JSON"
                    )
                manifests.append(load_platform_manifest(value))
        return cls(manifests)

    def get(self, platform_id: str) -> PlatformManifest:
        try:
            return self._items[platform_id]
        except KeyError as exc:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail=f"plataforma desconhecida: {platform_id}"
            ) from exc

    def list(self) -> list[PlatformManifest]:
        return list(self._items.values())

    def emulator_ids_for(self, platform_id: str) -> tuple[str, ...]:
        """Adapters que ESTA plataforma declara, na ordem do manifesto.

        A relação plataforma→emulador sempre existiu em ``manifest.emulators``;
        o que faltava era alguém consultá-la. A central de emulação montava a
        lista a partir do registro inteiro de adapters, então Dolphin (GameCube
        e Wii) e PPSSPP (PSP) apareciam sob Nintendo Switch — e herdavam os
        requisitos de keys e firmware do Switch, que não se aplicam a eles.

        Plataforma desconhecida levanta (via :meth:`get`) em vez de devolver
        vazio: vazio é indistinguível de "nenhum emulador declarado", que é o
        caso legítimo das plataformas de nuvem.
        """
        return tuple(
            str(emulator["adapterId"])
            for emulator in self.get(platform_id).emulators
            if emulator.get("adapterId")
        )


def platform_placeholder(manifest: PlatformManifest) -> dict[str, Any]:
    """Projeta uma plataforma ainda não composta sem alegar disponibilidade."""
    capabilities = {item["id"]: item for item in manifest.capabilities}
    areas: list[dict[str, Any]] = []
    area_data: dict[str, Any] = {}
    for declared in manifest.areas:
        capability = capabilities[declared["capabilityId"]]
        state = str(capability["state"])
        presentation_state = "unverified" if state == "ready" else state
        status = (
            "Verificação pendente"
            if state == "ready"
            else "Planejado"
            if state == "planned"
            else "Indisponível"
        )
        areas.append(
            {
                "id": declared["id"],
                "label": declared["label"],
                "iconKey": declared["iconKey"],
                "state": presentation_state,
                "statusLabel": status,
                "badge": None,
            }
        )
        action = capability["action"]
        projected_action = (
            {
                "id": action["id"],
                "label": action["label"],
                "enabled": False,
                "reason": capability["detail"],
                "requiresConfirmation": action["requiresConfirmation"],
            }
            if action is not None
            else None
        )
        area_data[str(declared["id"])] = {
            "cards": [
                {
                    "id": capability["id"],
                    "title": capability["label"],
                    "detail": capability["detail"],
                    "state": presentation_state,
                    "statusLabel": status,
                }
            ],
            "primaryAction": projected_action,
        }
    emulator_rows = [
        {
            "id": emulator["id"],
            "displayName": emulator["name"],
            "name": emulator["name"],
            "platform": manifest.id,
            "state": "unverified",
            "statusLabel": "Não verificado",
            "installState": "unverified",
            "sourceState": "unverified",
            "installable": False,
            "capabilities": [],
            "adapterId": emulator["adapterId"],
            "precedence": emulator["precedence"],
            "role": emulator["role"],
        }
        for emulator in manifest.emulators
    ]
    blockers = ["A composição operacional desta plataforma ainda não foi verificada neste host."]
    requirements = {
        kind: _declared_requirement(kind, manifest.name) for kind in manifest.requirements
    }
    return {
        "id": manifest.id,
        "kind": manifest.kind,
        "name": manifest.name,
        "shortName": manifest.short_name,
        "iconKey": manifest.icon_key,
        "state": "planned",
        "statusLabel": "Integração planejada",
        "readiness": {
            "percent": 0,
            "title": "Integração planejada",
            "detail": blockers[0],
            "blockers": blockers,
        },
        "scopes": [
            {
                "id": scope_id,
                "label": label,
                "iconKey": icon,
                "enabled": scope_id == "global",
                "reason": (
                    None
                    if scope_id == "global"
                    else "Escopo depende da composição operacional da plataforma."
                ),
            }
            for scope_id, label, icon in (
                ("global", "Global", "globe"),
                ("emulator", "Emulador", "emulator"),
                ("game", "Por jogo", "gamepad"),
                ("handheld", "Portátil", "handheld"),
                ("dock", "Dock", "dock"),
            )
        ],
        "selectedScope": "global",
        "areas": areas,
        "selectedArea": str(areas[0]["id"]),
        "emulators": emulator_rows,
        "games": [],
        "requirements": requirements,
        "fallbackArtworkAsset": manifest.artwork_asset,
        "capabilities": [
            {
                "id": item["id"],
                "label": item["label"],
                "state": item["state"],
                "detail": item["detail"],
            }
            for item in manifest.capabilities
        ],
        "media": dict(manifest.media),
        "controls": dict(manifest.controls),
        "timing": dict(manifest.timing),
        "presets": [dict(item) for item in manifest.presets],
        "cloud": dict(manifest.cloud) if manifest.cloud is not None else None,
        "areaData": area_data,
    }


def _declared_requirement(kind: str, platform_name: str) -> dict[str, Any]:
    label = "Keys" if kind == "keys" else "Firmware"
    return {
        "kind": kind,
        "status": "unverified",
        "required": None,
        "installed": None,
        "detail": f"{label} de {platform_name} ainda não verificado neste host.",
        "blocksPlay": False,
    }
