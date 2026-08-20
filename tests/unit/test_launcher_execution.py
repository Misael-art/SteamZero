# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Como o Launcher decide o que executar para cada plataforma.

O projeto atende dezenas de sistemas, cada um com emulador, core e argumentos
próprios. Um comando fixo serviria a um e quebraria o resto — a decisão vem do
manifesto da plataforma do jogo, e nada aqui inventa alternativa.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.launcher.execution import (
    DIAG_CORE_MISSING,
    DIAG_NO_EMULATOR,
    ExecutionPlan,
    resolve_execution,
)
from steamzero.launcher.library import LibraryGame


def _game(system: str, name: str = "jogo.rom") -> LibraryGame:
    return LibraryGame(id="jogo-1234abcd", title="Jogo", system=system, path=Path(f"/roms/{name}"))


def test_each_platform_brings_its_own_emulator_and_arguments(tmp_path: Path) -> None:
    """Switch e Game Boy não podem receber o mesmo comando."""
    # Game Boy roda em RetroArch, que exige o core da plataforma instalado.
    (tmp_path / "mgba_libretro.so").write_bytes(b"x")
    switch = resolve_execution(_game("switch", "Jogo [0100].nsp"), available={"eden"})
    handheld = resolve_execution(
        _game("nintendo-handheld", "Jogo.gb"), available={"retroarch"}, core_search=tmp_path
    )

    assert isinstance(switch, ExecutionPlan)
    assert switch.emulator_id == "eden"
    assert "{rom}" not in switch.argv
    assert str(switch.game.path) in switch.argv

    assert isinstance(handheld, ExecutionPlan)
    assert handheld.emulator_id == "retroarch"
    # RetroArch atende muitas plataformas: o core é da plataforma, não do emulador.
    assert handheld.core == "mgba"
    assert switch.argv != handheld.argv


def test_precedence_is_respected_and_fallback_only_when_needed() -> None:
    primary_off = resolve_execution(_game("switch"), available={"citron"})
    assert isinstance(primary_off, ExecutionPlan)
    assert primary_off.emulator_id == "citron"

    both = resolve_execution(_game("switch"), available={"citron", "eden"})
    assert isinstance(both, ExecutionPlan)
    assert both.emulator_id == "eden", "primary tem precedência sobre fallback"


def test_no_installed_emulator_refuses_with_a_reason() -> None:
    """Oferecer Jogar sem emulador terminaria em stub — proibido pelo AGENTS."""
    result = resolve_execution(_game("switch"), available=set())
    assert not isinstance(result, ExecutionPlan)
    assert result.code == DIAG_NO_EMULATOR
    assert "switch" in result.reason


def test_an_unknown_platform_is_refused_instead_of_guessed() -> None:
    result = resolve_execution(_game("plataforma-inventada"), available={"retroarch"})
    assert not isinstance(result, ExecutionPlan)
    assert result.reason


def test_a_platform_whose_core_is_missing_says_so(tmp_path: Path) -> None:
    """Core ausente vira "instale o core", não um Jogar que falha depois."""
    result = resolve_execution(
        _game("nintendo-handheld", "Jogo.gb"), available={"retroarch"}, core_search=tmp_path
    )
    assert not isinstance(result, ExecutionPlan)
    assert result.code == DIAG_CORE_MISSING
    assert "mgba" in result.reason


def test_the_rom_stays_an_atomic_argument() -> None:
    """Nome com espaço e aspas não pode virar oportunidade de injeção."""
    game = _game("switch", 'Jogo "com aspas" e espaço [0100].nsp')
    plan = resolve_execution(game, available={"eden"})
    assert isinstance(plan, ExecutionPlan)
    assert str(game.path) in plan.argv
    assert not any(";" in argument or "&&" in argument for argument in plan.argv)


@pytest.mark.parametrize("system", ["switch", "nintendo-handheld", "arcade"])
def test_every_supported_platform_resolves_or_explains(system: str) -> None:
    result = resolve_execution(_game(system), available={"eden", "retroarch"})
    assert isinstance(result, ExecutionPlan) or result.reason


def test_installed_emulators_reads_the_lifecycle_state_not_the_path() -> None:
    """`which(adapterId)` daria falso positivo com binários homônimos.

    No KDE, `dolphin` no PATH é o gerenciador de arquivos; o emulador é
    `dolphin-emu`. E os emuladores chegam por Flatpak ou engine gerenciada, que
    não aparecem no PATH de forma alguma.
    """
    from steamzero.launcher.app import installed_emulators

    statuses = [
        {"id": "eden", "installed": True},
        {"id": "retroarch", "state": "installed"},
        {"id": "dolphin", "installed": False},
        {"id": "citron", "state": "available"},
    ]
    assert installed_emulators(statuses) == {"eden", "retroarch"}


def test_a_game_whose_emulator_is_absent_never_yields_a_plan() -> None:
    from steamzero.launcher.app import installed_emulators

    available = installed_emulators([{"id": "dolphin", "installed": False}])
    result = resolve_execution(_game("nintendo-console", "Jogo.rvz"), available=available)
    assert not isinstance(result, ExecutionPlan)
