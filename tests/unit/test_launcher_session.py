# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato da página de jogo e do par lançamento/retorno do AURA Launcher."""

from __future__ import annotations

import pytest

from steamzero.launcher.navigation import HomeSection, resolve_home_focus
from steamzero.launcher.session import (
    DIAG_RETURN_MISSING,
    GameSummary,
    LaunchContext,
    resolve_game_page,
    restore_context,
)


def _sections() -> tuple[HomeSection, ...]:
    return (
        HomeSection(id="continue", title="Continuar", items=("celeste", "hades")),
        HomeSection(id="library", title="Biblioteca", items=("tunic", "axiom")),
    )


def _game() -> GameSummary:
    return GameSummary(
        id="celeste",
        title="Celeste",
        platform="Steam",
        last_played="2026-08-18T21:00:00Z",
        playable=True,
    )


def test_game_page_offers_focusable_actions_and_play_comes_first() -> None:
    page = resolve_game_page(_game())
    assert page.title == "Celeste"
    assert next(action.id for action in page.actions) == "play"
    assert page.initial_focus == "action:play"
    for action in page.actions:
        assert action.enabled is True or action.reason


def test_an_unplayable_game_never_offers_play_without_saying_why() -> None:
    """Botão que não funciona sem explicação é pior que botão ausente."""
    page = resolve_game_page(
        GameSummary(
            id="tunic",
            title="Tunic",
            platform="Steam",
            last_played=None,
            playable=False,
            blocked_reason="instalação incompleta",
        )
    )
    play = next(action for action in page.actions if action.id == "play")
    assert play.enabled is False
    assert "instalação incompleta" in play.reason
    # O foco não pode começar num botão desabilitado.
    assert page.initial_focus != "action:play"


def test_the_launch_context_survives_a_launcher_restart() -> None:
    """O item 5 da DoD exige reiniciar o launcher sem derrubar o jogo.

    Se o contexto morre junto com o processo, o retorno cai na home genérica e
    o usuário perde o lugar.
    """
    focus = resolve_home_focus(_sections())
    context = LaunchContext.capture(game_id="hades", focus_id="continue:hades")
    payload = context.to_dict()

    # Round-trip por serialização, como acontece entre dois processos.
    restored, diagnostics = restore_context(payload, focus)
    assert restored == "continue:hades"
    assert not diagnostics


def test_returning_to_a_game_that_left_the_library_lands_somewhere_valid() -> None:
    """A biblioteca muda enquanto o jogo roda: o foco salvo pode não existir."""
    focus = resolve_home_focus(_sections())
    payload = LaunchContext.capture(game_id="removido", focus_id="library:removido").to_dict()
    restored, diagnostics = restore_context(payload, focus)
    assert restored in focus.nodes
    # Cair na mesma seção preserva a intenção; voltar ao topo da home a perde.
    assert focus.nodes[restored].section == "library"
    assert any(item.code == DIAG_RETURN_MISSING for item in diagnostics)
    assert diagnostics[0].fallback == restored


def test_a_corrupt_context_does_not_crash_the_return() -> None:
    focus = resolve_home_focus(_sections())
    # Inclui payload que nem é objeto: entre processos, o arquivo pode vir
    # truncado, vazio ou com outro tipo.
    for payload in (None, "texto", [], {}, {"focusId": 123}, {"focusId": "", "gameId": None}):
        restored, diagnostics = restore_context(payload, focus)
        assert restored == focus.initial
        assert diagnostics


def test_context_refuses_identifiers_it_cannot_trust() -> None:
    with pytest.raises(ValueError, match="focus"):
        LaunchContext.capture(game_id="celeste", focus_id="../../etc/passwd")
