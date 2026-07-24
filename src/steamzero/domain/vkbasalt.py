# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Presets fechados e configuração por jogo para vkBasalt."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from steamzero.api import contracts
from steamzero.core.errors import SteamZeroError

MODES = frozenset({"off", "cas", "fxaa", "smaa"})
_GAME_ID = re.compile(r"^[0-9]{1,32}$")
_CONFIGS = {
    "cas": (
        "# Managed by SteamZero; per-game preset.\n"
        "effects = cas\n"
        "enableOnLaunch = True\n"
        "casSharpness = 0.4\n"
    ),
    "fxaa": (
        "# Managed by SteamZero; per-game preset.\n"
        "effects = fxaa\n"
        "enableOnLaunch = True\n"
        "fxaaQualitySubpix = 0.75\n"
        "fxaaQualityEdgeThreshold = 0.166\n"
        "fxaaQualityEdgeThresholdMin = 0.0312\n"
    ),
    "smaa": (
        "# Managed by SteamZero; per-game preset.\n"
        "effects = smaa\n"
        "enableOnLaunch = True\n"
        "smaaEdgeDetection = luma\n"
        "smaaThreshold = 0.1\n"
        "smaaMaxSearchSteps = 16\n"
        "smaaMaxSearchStepsDiag = 8\n"
        "smaaCornerRounding = 25\n"
    ),
}


def config_path(config_root: Path, game_id: str) -> Path:
    if _GAME_ID.fullmatch(game_id) is None:
        raise SteamZeroError("E-API-SCHEMA", detail="gameId vkBasalt inválido")
    return config_root / f"{game_id}.conf"


def render_config(mode: str) -> bytes:
    if mode == "off" or mode not in MODES:
        raise SteamZeroError("E-API-SCHEMA", detail="preset vkBasalt inválido")
    return _CONFIGS[mode].encode("utf-8")


def catalog(*, available: bool) -> dict[str, Any]:
    presets = [
        {
            "id": "off",
            "label": "Desligado",
            "effect": "none",
            "gpuCost": "none",
            "costLabel": "Sem custo adicional",
            "completeOff": True,
            "requiresCapability": False,
        },
        {
            "id": "cas",
            "label": "Nitidez CAS",
            "effect": "cas",
            "gpuCost": "low",
            "costLabel": "Custo baixo estimado",
            "completeOff": False,
            "requiresCapability": True,
        },
        {
            "id": "fxaa",
            "label": "Antisserrilhado FXAA",
            "effect": "fxaa",
            "gpuCost": "medium",
            "costLabel": "Custo médio estimado",
            "completeOff": False,
            "requiresCapability": True,
        },
        {
            "id": "smaa",
            "label": "Antisserrilhado SMAA",
            "effect": "smaa",
            "gpuCost": "high",
            "costLabel": "Custo alto estimado",
            "completeOff": False,
            "requiresCapability": True,
        },
    ]
    payload = {
        "schemaVersion": 1,
        "available": available,
        "scope": "game",
        "defaultMode": "off",
        "costBasis": "qualitative",
        "costNotice": "O impacto real depende do jogo, resolução e GPU.",
        "presets": presets,
    }
    contracts.validate(payload, "gtool-vkbasalt-v1.schema.json")
    return payload
