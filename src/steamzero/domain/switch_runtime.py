# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Políticas de runtime Switch: dock/portátil, controles e LSFG (WI-7/WI-8).

O domínio produz configuração genérica e explicável. A tradução para chaves de
Eden/Citron/Ryujinx cabe ao template validado de cada adapter; assim não se
inventam opções específicas. LSFG só recomenda auto-apply quando o jogo optou
explicitamente, o runtime foi verificado e a amostra está estável perto de 30.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any

from steamzero.core.errors import SteamZeroError

_ENVIRONMENTS = frozenset({"handheld", "dock"})


@dataclass(frozen=True)
class SwitchRuntimeProfile:
    environment: str
    system_mode: str
    resolution_width: int
    resolution_height: int
    render_scale: float
    detected_controllers: int
    active_players: int
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment": self.environment,
            "systemMode": self.system_mode,
            "resolution": {
                "width": self.resolution_width,
                "height": self.resolution_height,
                "label": f"{self.resolution_height}p",
            },
            "renderScale": self.render_scale,
            "controllers": {
                "detected": self.detected_controllers,
                "activePlayers": self.active_players,
                "maximumPlayers": 4,
                "automatic": True,
            },
            "warnings": list(self.warnings),
        }


def resolve_switch_runtime_profile(
    environment: str,
    *,
    connected_controllers: int,
    built_in_controller: bool = False,
    requested_players: int | None = None,
    external_width: int | None = None,
    external_height: int | None = None,
) -> SwitchRuntimeProfile:
    normalized = environment.strip().lower()
    if normalized not in _ENVIRONMENTS:
        raise SteamZeroError("E-API-SCHEMA", detail=f"ambiente Switch inválido: {environment!r}")
    if not 0 <= connected_controllers <= 32:
        raise SteamZeroError("E-API-SCHEMA", detail="número de controles fora do limite")
    detected = connected_controllers + (1 if built_in_controller else 0)
    available_players = min(max(detected, 1), 4)
    if requested_players is None:
        active_players = available_players
    elif not 1 <= requested_players <= 4:
        raise SteamZeroError("E-API-SCHEMA", detail="jogadores precisa estar entre 1 e 4")
    elif requested_players > available_players:
        active_players = available_players
    else:
        active_players = requested_players

    warnings: list[str] = []
    if detected > 4:
        warnings.append("Mais de quatro controles detectados; somente quatro serão ativados.")
    if requested_players is not None and requested_players > available_players:
        warnings.append(
            f"Solicitados {requested_players} jogadores, mas somente "
            f"{available_players} controles estão disponíveis."
        )

    if normalized == "handheld":
        width, height, mode, scale = 1280, 720, "handheld", 1.0
    else:
        width, height = _safe_dock_resolution(external_width, external_height)
        mode, scale = "docked", 1.0
    return SwitchRuntimeProfile(
        normalized,
        mode,
        width,
        height,
        scale,
        detected,
        active_players,
        tuple(warnings),
    )


def _safe_dock_resolution(width: int | None, height: int | None) -> tuple[int, int]:
    if width is None or height is None or width < 640 or height < 480:
        return 1920, 1080
    # O perfil base limita a saída a 1080p; upscale acima disso é decisão por jogo.
    if width > 1920 or height > 1080:
        return 1920, 1080
    return width, height


@dataclass(frozen=True)
class LsfgDecision:
    state: str
    status_label: str
    detail: str
    source_fps: float | None
    target_fps: int | None
    multiplier: int | None
    should_apply: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "statusLabel": self.status_label,
            "detail": self.detail,
            "sourceFps": self.source_fps,
            "targetFps": self.target_fps,
            "multiplier": self.multiplier,
            "shouldApply": self.should_apply,
        }


def evaluate_lsfg_30_to_60(
    samples_fps: list[float],
    *,
    enabled_for_game: bool,
    runtime_ready: bool,
    vulkan_ready: bool,
    display_refresh_hz: float,
) -> LsfgDecision:
    if not enabled_for_game:
        return LsfgDecision(
            "unavailable",
            "Desativado neste jogo",
            "Ative LSFG no perfil do jogo para permitir 30→60 fps.",
            None,
            None,
            None,
            False,
        )
    if not runtime_ready or not vulkan_ready:
        missing = "runtime LSFG" if not runtime_ready else "Vulkan"
        return LsfgDecision(
            "blocked",
            "Pré-requisito ausente",
            f"{missing} não está verificado; nenhuma alteração será aplicada.",
            None,
            None,
            None,
            False,
        )
    if not math.isfinite(display_refresh_hz) or display_refresh_hz < 59.0:
        return LsfgDecision(
            "unavailable",
            "Tela incompatível",
            "A tela precisa operar a pelo menos 59 Hz para o perfil 30→60.",
            None,
            None,
            None,
            False,
        )
    if len(samples_fps) < 5 or any(
        not math.isfinite(value) or value <= 0 or value > 1000 for value in samples_fps
    ):
        return LsfgDecision(
            "unverified",
            "Amostra insuficiente",
            "Colete ao menos cinco amostras FPS válidas antes de automatizar.",
            None,
            None,
            None,
            False,
        )
    median = statistics.median(samples_fps)
    spread = max(samples_fps) - min(samples_fps)
    if not 27.0 <= median <= 33.0 or spread > 4.0:
        return LsfgDecision(
            "attention",
            "30 fps não estável",
            "O frame rate base precisa ficar entre 27-33 fps com variação de até 4 fps.",
            round(median, 1),
            None,
            None,
            False,
        )
    return LsfgDecision(
        "ready",
        "30→60 fps recomendado",
        "Perfil do jogo permite LSFG 2x e os pré-requisitos estão verificados.",
        round(median, 1),
        60,
        2,
        True,
    )
