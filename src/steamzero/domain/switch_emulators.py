# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Catálogo de emuladores de Switch com precedência e disponibilidade (WI-2).

Contém apenas fatos verificáveis: identidade, precedência e o requisito
inequívoco de que a emulação de Switch exige keyset ``prod`` e firmware
importados pelo usuário. **Fontes de instalação (ref Flatpak/commit, sha256 de
AppImage) NÃO são embarcadas** porque não podem ser verificadas offline sem
inventar URL/hash/versão — o que a política proíbe. Enquanto uma fonte pinada e
validada por um mantenedor não existir, a capacidade de instalação fica
``unverified`` e o resolver reporta o estado honestamente (LACUNA registrada).

A disponibilidade real no host é resolvida por um ``probe`` injetável (read-only);
sem probe, o estado é ``unverified`` com motivo — nunca uma suposição de sucesso.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_PLATFORM = "switch"

# Estados de instalação reportados à UI (dados, nunca suposição da UI).
STATE_INSTALLED = "installed"
STATE_NOT_INSTALLED = "not-installed"
STATE_UNVERIFIED = "unverified"

#: Probe read-only: dado um id de emulador, retorna True (instalado), False
#: (ausente) ou None (não foi possível determinar → unverified).
Probe = Callable[[str], bool | None]


@dataclass(frozen=True)
class SwitchEmulator:
    """Descritor de um emulador de Switch — só fatos verificáveis."""

    id: str
    display_name: str
    precedence: int
    keyset: str  # "prod" — fato verificável do domínio Switch
    requires_firmware: bool
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "displayName": self.display_name,
            "precedence": self.precedence,
            "platform": _PLATFORM,
            "requiresKeys": {"platform": _PLATFORM, "keyset": self.keyset},
            "requiresFirmware": {"platform": _PLATFORM} if self.requires_firmware else None,
            "notes": self.notes,
        }


# Precedência: sucessor mais ativo primeiro. É uma decisão de curadoria do
# mantenedor, não um fato técnico — documentada aqui e revisável.
SWITCH_EMULATORS: tuple[SwitchEmulator, ...] = (
    SwitchEmulator(
        id="eden",
        display_name="Eden",
        precedence=1,
        keyset="prod",
        requires_firmware=True,
        notes="Projeto sucessor ativo. Requer keys prod e firmware do próprio usuário.",
    ),
    SwitchEmulator(
        id="citron",
        display_name="Citron",
        precedence=2,
        keyset="prod",
        requires_firmware=True,
        notes="Fork da mesma linhagem. Requer keys prod e firmware do próprio usuário.",
    ),
    SwitchEmulator(
        id="ryujinx",
        display_name="Ryujinx",
        precedence=3,
        keyset="prod",
        requires_firmware=True,
        notes="Projeto original descontinuado; sucessores herdam a base. "
        "Requer keys prod e firmware do próprio usuário.",
    ),
)


class SwitchEmulatorCatalog:
    """Catálogo ordenado por precedência com resolução de disponibilidade honesta."""

    def __init__(self, emulators: tuple[SwitchEmulator, ...] = SWITCH_EMULATORS) -> None:
        self._emulators = tuple(sorted(emulators, key=lambda e: e.precedence))
        precedences = [e.precedence for e in self._emulators]
        if len(precedences) != len(set(precedences)):
            raise ValueError("precedências de emulador duplicadas")

    def emulators(self) -> tuple[SwitchEmulator, ...]:
        return self._emulators

    def by_id(self, emulator_id: str) -> SwitchEmulator | None:
        return next((e for e in self._emulators if e.id == emulator_id), None)

    def preferred(self, *, probe: Probe | None = None) -> str | None:
        """Primeiro emulador instalado por ordem de precedência, se detectável."""
        if probe is None:
            return None
        for emulator in self._emulators:
            if probe(emulator.id) is True:
                return emulator.id
        return None

    def availability(self, *, probe: Probe | None = None) -> list[dict[str, Any]]:
        """Estado por emulador como dados. Sem probe → unverified com motivo."""
        result: list[dict[str, Any]] = []
        for emulator in self._emulators:
            install_state, reason = self._resolve_state(emulator.id, probe)
            entry = emulator.to_dict()
            entry.update(
                {
                    "installState": install_state,
                    # Nenhuma fonte pinada validada é embarcada nesta fase.
                    "sourceState": STATE_UNVERIFIED,
                    "installable": False,
                    "reason": reason,
                }
            )
            result.append(entry)
        return result

    @staticmethod
    def _resolve_state(emulator_id: str, probe: Probe | None) -> tuple[str, str]:
        if probe is None:
            return (
                STATE_UNVERIFIED,
                "Detecção não fornecida; disponibilidade não verificada neste contexto.",
            )
        detected = probe(emulator_id)
        if detected is True:
            return (
                STATE_INSTALLED,
                "Emulador detectado no host. Instalação gerenciada aguarda fonte pinada validada.",
            )
        if detected is False:
            return (
                STATE_NOT_INSTALLED,
                "Não detectado. Instalação gerenciada aguarda fonte pinada validada (lacuna WI-2).",
            )
        return (
            STATE_UNVERIFIED,
            "Detecção inconclusiva; estado não verificado.",
        )
