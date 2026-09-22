# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato fechado para o estado de acessibilidade consultável pela cena."""

from __future__ import annotations

from collections.abc import Mapping
from math import isfinite
from typing import Any

from steamzero.domain.scene_typing import ValueType

DEFAULT_ACCESSIBILITY: dict[str, Any] = {
    "highContrast": False,
    "reducedMotion": False,
    "visualScale": 1.0,
}

ACCESSIBILITY_FIELDS: dict[str, ValueType] = {
    "highContrast": ValueType.BOOLEAN,
    "reducedMotion": ValueType.BOOLEAN,
    "visualScale": ValueType.NUMBER,
}

ACCESSIBILITY_BINDING_TYPES: dict[str, ValueType] = {
    f"accessibility.{field}": value_type for field, value_type in ACCESSIBILITY_FIELDS.items()
}


def normalize_accessibility(values: Mapping[str, Any] | None) -> dict[str, Any]:
    """Aplica defaults e rejeita valores de host com tipo incorreto."""
    normalized = dict(DEFAULT_ACCESSIBILITY)
    if values is None:
        return normalized
    for field, value_type in ACCESSIBILITY_FIELDS.items():
        if field not in values:
            continue
        value = values[field]
        if value_type is ValueType.BOOLEAN:
            if not isinstance(value, bool):
                raise ValueError(f"accessibility.{field} exige booleano")
        elif value_type is ValueType.NUMBER and (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not isfinite(float(value))
            or value <= 0
        ):
            raise ValueError(f"accessibility.{field} exige número positivo")
        normalized[field] = value
    return normalized
