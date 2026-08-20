# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Provisão automática de emulador e core, quando o operador habilita."""

from __future__ import annotations

from pathlib import Path

from steamzero.launcher.execution import resolve_execution
from steamzero.launcher.library import LibraryGame
from steamzero.launcher.provisioning import (
    DIAG_AUTO_DISABLED,
    ProvisionPlan,
    plan_provision,
)


def _game(system: str) -> LibraryGame:
    return LibraryGame(id="jogo-1234abcd", title="Jogo", system=system, path=Path("/roms/j.rom"))


def test_nothing_is_installed_without_the_operator_enabling_it() -> None:
    """Instalar por conta própria seria decidir pelo usuário o que baixar."""
    refusal = resolve_execution(_game("switch"), available=set())
    plan = plan_provision(_game("switch"), refusal, auto_install=False)
    assert not isinstance(plan, ProvisionPlan)
    assert plan.code == DIAG_AUTO_DISABLED
    # A recusa continua explicando o que falta, para o usuário poder decidir.
    assert "eden" in plan.reason


def test_enabling_it_provisions_exactly_what_that_platform_declares() -> None:
    refusal = resolve_execution(_game("switch"), available=set())
    plan = plan_provision(_game("switch"), refusal, auto_install=True)
    assert isinstance(plan, ProvisionPlan)
    # O primeiro da precedência, não um emulador genérico.
    assert plan.adapter_id == "eden"
    assert plan.platform_id == "switch"
    assert plan.core is None


def test_a_platform_that_needs_a_core_provisions_the_core_too() -> None:
    """RetroArch instalado sem core não roda o jogo; ambos fazem parte do pedido."""
    refusal = resolve_execution(_game("nintendo-handheld"), available={"retroarch"})
    plan = plan_provision(_game("nintendo-handheld"), refusal, auto_install=True)
    assert isinstance(plan, ProvisionPlan)
    assert plan.core == "mgba"


def test_an_unknown_platform_is_never_provisioned_blindly() -> None:
    refusal = resolve_execution(_game("plataforma-inventada"), available=set())
    plan = plan_provision(_game("plataforma-inventada"), refusal, auto_install=True)
    assert not isinstance(plan, ProvisionPlan)
    assert plan.reason
