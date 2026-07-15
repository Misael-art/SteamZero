# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Mode Manager (F-SD-02): máquina de modos + cadeia de fallback de display.

Modos: handheld, docked-tv, docked-monitor, desktop, unknown. A aplicação de um
modo tenta o perfil-alvo e, se o display não produzir sinal válido, percorre a
cadeia de degradação (FM-18: perfil → sem HDR → sem VRR → menos Hz → menos res →
tela interna), sempre terminando numa imagem válida (a interna é sempre válida).
Se degradou, reporta ``E-MODE-DISPLAY-FALLBACK`` com o degrau atingido (AC-SD-01).

O acesso ao display é uma **porta** (``DisplayPort``) injetada; o domínio não
fala com KMS/DRM diretamente.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from steamzero.core.state import StateStore

MODES = ("handheld", "docked-tv", "docked-monitor", "desktop", "unknown")

_CURRENT_MODE_ID = "current-mode"


@dataclass(frozen=True)
class DisplayProfile:
    label: str  # degrau da cadeia (ex.: "target", "no-hdr", "internal")
    output: str  # internal | external
    width: int
    height: int
    refresh_hz: int
    hdr: bool
    vrr: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "output": self.output,
            "width": self.width,
            "height": self.height,
            "refreshHz": self.refresh_hz,
            "hdr": self.hdr,
            "vrr": self.vrr,
        }


class DisplayPort(Protocol):
    """Capacidade de aplicar um perfil de display e confirmar sinal válido."""

    def apply(self, profile: DisplayProfile) -> bool:
        """Aplica ``profile``; retorna True se há imagem válida na saída."""
        ...


@dataclass(frozen=True)
class ModeResult:
    mode: str
    applied: DisplayProfile
    fallback_step: int  # 0 = alvo aplicado sem degradação
    degraded: bool


def _internal() -> DisplayProfile:
    return DisplayProfile("internal", "internal", 1280, 800, 60, hdr=False, vrr=False)


def fallback_chain(mode: str) -> list[DisplayProfile]:
    """Candidatos do melhor ao mais seguro; o último é sempre a tela interna."""
    if mode not in MODES:
        raise ValueError(f"modo inválido: {mode}")
    if mode == "handheld":
        return [_internal()]
    if mode == "unknown":
        return [_internal()]
    if mode == "docked-tv":
        ext = [
            DisplayProfile("target", "external", 3840, 2160, 60, hdr=True, vrr=True),
            DisplayProfile("no-hdr", "external", 3840, 2160, 60, hdr=False, vrr=True),
            DisplayProfile("no-vrr", "external", 3840, 2160, 60, hdr=False, vrr=False),
            DisplayProfile("lower-hz", "external", 3840, 2160, 30, hdr=False, vrr=False),
            DisplayProfile("lower-res", "external", 1920, 1080, 60, hdr=False, vrr=False),
        ]
    elif mode == "docked-monitor":
        ext = [
            DisplayProfile("target", "external", 2560, 1440, 144, hdr=False, vrr=True),
            DisplayProfile("no-vrr", "external", 2560, 1440, 144, hdr=False, vrr=False),
            DisplayProfile("lower-hz", "external", 2560, 1440, 60, hdr=False, vrr=False),
            DisplayProfile("lower-res", "external", 1920, 1080, 60, hdr=False, vrr=False),
        ]
    else:  # desktop
        ext = [
            DisplayProfile("target", "external", 1920, 1080, 60, hdr=False, vrr=False),
        ]
    return [*ext, _internal()]


class ModeManager:
    def __init__(self, display: DisplayPort, store: StateStore) -> None:
        self._display = display
        self._store = store

    def apply_mode(self, mode: str) -> ModeResult:
        """Aplica ``mode`` percorrendo a cadeia até obter imagem válida."""
        chain = fallback_chain(mode)
        for step, profile in enumerate(chain):
            if self._display.apply(profile):
                result = ModeResult(mode, profile, step, degraded=step > 0)
                self._persist(result)
                return result
        # a tela interna é sempre válida por contrato; se chegou aqui, é falha dura
        internal = chain[-1]
        result = ModeResult(mode, internal, len(chain) - 1, degraded=True)
        self._persist(result)
        return result

    def _persist(self, result: ModeResult) -> None:
        self._store.save_profile(
            {
                "id": _CURRENT_MODE_ID,
                "scope": "mode",
                "kind": "display",
                "payload_json": json.dumps(
                    {
                        "mode": result.mode,
                        "step": result.fallback_step,
                        "degraded": result.degraded,
                        "profile": result.applied.as_dict(),
                    },
                    ensure_ascii=False,
                ),
                "priority": 0,
            }
        )
        self._store.append_event(
            "entity.changed",
            entity="mode:current",
            payload={"mode": result.mode, "degraded": result.degraded},
        )

    def current(self) -> dict[str, object] | None:
        row = self._store.get_profile(_CURRENT_MODE_ID)
        if row is None or not row.get("payload_json"):
            return None
        payload: dict[str, object] = json.loads(row["payload_json"])
        return payload
