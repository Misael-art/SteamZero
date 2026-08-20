# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""O que instalar quando falta emulador ou core para jogar.

A experiência que se quer é: escolher um jogo e jogar. Quando falta a peça, o
sistema resolve — mas **só depois que o operador habilita**. Baixar centenas de
megabytes por conta própria seria decidir pelo usuário o uso do disco e da rede
dele, e num handheld com dados limitados isso não é detalhe.

Enquanto a opção estiver desligada, a recusa continua explicando o que falta,
para a decisão ser informada. Este módulo só monta o pedido: quem instala é o
lifecycle de componentes, e o que instalar vem do manifesto daquela plataforma —
nunca um emulador genérico.
"""

from __future__ import annotations

from dataclasses import dataclass

from steamzero.domain.platforms import PlatformRegistry
from steamzero.launcher.execution import (
    DIAG_CORE_MISSING,
    DIAG_NO_EMULATOR,
    ExecutionRefusal,
)
from steamzero.launcher.library import LibraryGame

DIAG_AUTO_DISABLED = "LAUNCHER-PROVISION-DISABLED-001"
DIAG_NOT_PROVISIONABLE = "LAUNCHER-PROVISION-UNKNOWN-002"


@dataclass(frozen=True)
class ProvisionPlan:
    """Pedido de instalação para tornar um jogo jogável."""

    game: LibraryGame
    platform_id: str
    adapter_id: str
    core: str | None = None

    @property
    def summary(self) -> str:
        parts = [self.adapter_id]
        if self.core:
            parts.append(f"core {self.core}")
        return " + ".join(parts)


@dataclass(frozen=True)
class ProvisionRefusal:
    code: str
    reason: str


def plan_provision(
    game: LibraryGame,
    refusal: ExecutionRefusal,
    *,
    auto_install: bool,
    registry: PlatformRegistry | None = None,
) -> ProvisionPlan | ProvisionRefusal:
    """Monta o pedido de instalação para a plataforma daquele jogo."""
    if refusal.code not in {DIAG_NO_EMULATOR, DIAG_CORE_MISSING}:
        return ProvisionRefusal(
            code=DIAG_NOT_PROVISIONABLE,
            reason=refusal.reason,
        )
    if not auto_install:
        # A recusa original já diz o que falta; repeti-la é o que permite ao
        # usuário decidir habilitar a opção com conhecimento de causa.
        return ProvisionRefusal(code=DIAG_AUTO_DISABLED, reason=refusal.reason)

    catalogue = registry or PlatformRegistry.bundled()
    for manifest in catalogue.list():
        if manifest.id != game.system and game.system not in tuple(
            getattr(manifest, "systems", ()) or ()
        ):
            continue
        entries = [
            dict(entry)
            for entry in (getattr(manifest, "emulators", None) or [])
            if isinstance(entry, dict)
        ]
        if not entries:
            break
        # Precedência do manifesto: instala o emulador que aquela plataforma
        # considera principal, não o primeiro que aparecer na lista.
        first = min(entries, key=lambda item: int(item.get("precedence", 99)))
        adapter_id = str(first.get("adapterId") or first.get("id") or "")
        if not adapter_id:
            break
        launch = first.get("launch")
        core = None
        if isinstance(launch, dict) and launch.get("core"):
            # Emulador multi-sistema sem o core da plataforma abre e não roda o
            # jogo; o core faz parte do mesmo pedido.
            core = str(launch["core"])
        return ProvisionPlan(
            game=game,
            platform_id=str(manifest.id),
            adapter_id=adapter_id,
            core=core,
        )

    return ProvisionRefusal(
        code=DIAG_NOT_PROVISIONABLE,
        reason=f"plataforma '{game.system}' não declara emulador instalável",
    )
