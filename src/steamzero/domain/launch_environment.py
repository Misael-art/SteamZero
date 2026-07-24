# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Compositor puro e fechado do ambiente de lançamento."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from steamzero.api import contracts
from steamzero.core.errors import SteamZeroError

_LAYER_ID = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
_KEY = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_MANAGED_KEYS = frozenset(
    {
        "STEAMZERO_GAME_ID",
        "STEAMZERO_PROFILE_DIGEST",
        "MANGOHUD_CONFIG",
        "LSFG_LEGACY",
        "LSFG_DLL_PATH",
        "LSFG_MULTIPLIER",
        "LSFG_FLOW_SCALE",
        "LSFG_PERFORMANCE_MODE",
        "ENABLE_VKBASALT",
        "VKBASALT_CONFIG_FILE",
    }
)


@dataclass(frozen=True)
class EnvironmentLayer:
    id: str
    values: Mapping[str, str]


@dataclass(frozen=True)
class ComposedEnvironment:
    values: dict[str, str]
    layers: tuple[str, ...]
    managed_keys: tuple[str, ...]

    def public(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schemaVersion": 1,
            "layers": list(self.layers),
            "managedKeys": list(self.managed_keys),
            "collisionPolicy": "reject",
            "shell": False,
        }
        contracts.validate(payload, "gtool-launch-environment-v1.schema.json")
        return payload


def compose_launch_environment(
    base: Mapping[str, str], layers: Sequence[EnvironmentLayer]
) -> ComposedEnvironment:
    """Retorna nova cópia; camadas não podem sobrescrever base nem umas às outras."""

    output = dict(base)
    owners: dict[str, str] = {}
    layer_ids: list[str] = []
    for layer in layers:
        if _LAYER_ID.fullmatch(layer.id) is None or layer.id in layer_ids:
            raise SteamZeroError("E-API-SCHEMA", detail="camada de ambiente inválida")
        layer_ids.append(layer.id)
        for key, value in layer.values.items():
            if (
                key not in _MANAGED_KEYS
                or _KEY.fullmatch(key) is None
                or not isinstance(value, str)
                or not value
                or len(value) > 4096
                or "\x00" in value
            ):
                raise SteamZeroError("E-API-SCHEMA", detail=f"variável gerenciada inválida: {key}")
            if key in owners or key in base:
                raise SteamZeroError(
                    "E-STATE-INTEGRITY", detail=f"colisão de ownership no ambiente: {key}"
                )
            owners[key] = layer.id
            output[key] = value
    return ComposedEnvironment(
        values=output,
        layers=tuple(layer_ids),
        managed_keys=tuple(sorted(owners)),
    )
