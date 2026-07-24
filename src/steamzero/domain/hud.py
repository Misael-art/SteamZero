# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Catálogo HUD e evidência geométrica automatizada para 1280x800."""

from __future__ import annotations

from typing import Any

from steamzero.api import contracts

MANGO_CONFIG = {
    "basic": "fps,frametime,frame_timing=0,cpu_stats=0,gpu_stats=0",
    "detailed": "fps,frametime,cpu_stats,gpu_stats,ram,vram,battery,battery_watt",
}

_PRESETS = (
    {
        "id": "compact",
        "label": "Compacto",
        "mode": "basic",
        "metrics": ["fps", "frametime"],
        "layout": {
            "anchor": "top-left",
            "maxWidth": 360,
            "maxHeight": 84,
            "margin": 16,
            "fitsViewport": True,
        },
    },
    {
        "id": "detailed",
        "label": "Detalhado",
        "mode": "detailed",
        "metrics": [
            "fps",
            "frametime",
            "cpu_stats",
            "gpu_stats",
            "ram",
            "vram",
            "battery",
            "battery_watt",
        ],
        "layout": {
            "anchor": "top-left",
            "maxWidth": 520,
            "maxHeight": 196,
            "margin": 16,
            "fitsViewport": True,
        },
    },
)


def hud_catalog(*, mangohud_available: bool | None = None) -> dict[str, Any]:
    """Publica fatos estáticos sem alegar legibilidade ou execução no host."""

    runtime_state = (
        "ready"
        if mangohud_available is True
        else "unavailable"
        if mangohud_available is False
        else "unverified"
    )
    detail = {
        "ready": "Executável MangoHud observado localmente; renderização em jogo não verificada.",
        "unavailable": "Executável MangoHud não observado; presets permanecem apenas declarativos.",
        "unverified": "Disponibilidade do MangoHud não foi consultada.",
    }[runtime_state]
    payload = {
        "schemaVersion": 1,
        "viewport": {"width": 1280, "height": 800},
        "runtime": {"state": runtime_state, "tool": "MangoHud", "detail": detail},
        "presets": [
            {**preset, "config": MANGO_CONFIG[str(preset["mode"])]} for preset in _PRESETS
        ],
        "evidence": {
            "method": "deterministic-layout-budget",
            "state": "verified-offscreen",
            "proves": [
                "Os limites declarados de cada preset cabem em 1280x800 com margem.",
                "Config, métricas e geometria são determinísticos e schema-valid.",
            ],
            "doesNotProve": [
                "Renderização real do overlay durante um jogo.",
                "Legibilidade, ausência de obstrução, conforto ou preferência humana.",
            ],
            "humanReview": {
                "state": "PENDING-HUMAN",
                "items": ["legibilidade", "obstrução do jogo", "conforto visual"],
            },
        },
    }
    contracts.validate(payload, "gtool-hud-v1.schema.json")
    return payload
