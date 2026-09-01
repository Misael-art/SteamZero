# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Página de jogo e o par lançamento/retorno do AURA Launcher.

Dois contratos moldam este módulo, e os dois vêm da Definition of Done:

* o retorno recai no **mesmo contexto** de onde o jogo foi lançado (item 4);
* o processo do launcher pode reiniciar sem derrubar o jogo (item 5) — logo o
  contexto precisa atravessar processos, não viver só em memória.

A consequência prática é que o foco salvo pode não existir na volta: a
biblioteca muda enquanto o jogo roda, e o jogo lançado pode ter sido removido.
Esse caso degrada para um foco válido com diagnóstico, nunca para ausência de
foco.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from steamzero.launcher.identifiers import is_focus_id, is_identifier
from steamzero.launcher.navigation import FocusMap

DIAG_RETURN_MISSING = "LAUNCHER-RETURN-MISSING-001"
DIAG_RETURN_INVALID = "LAUNCHER-RETURN-INVALID-002"


@dataclass(frozen=True)
class GameSummary:
    id: str
    title: str
    platform: str
    last_played: str | None = None
    playable: bool = True
    blocked_reason: str = ""

    def __post_init__(self) -> None:
        if not is_identifier(self.id):
            raise ValueError(f"game id inválido: {self.id!r}")
        if not self.title:
            raise ValueError("game title vazio")
        if not self.playable and not self.blocked_reason:
            raise ValueError("jogo bloqueado exige motivo")


@dataclass(frozen=True)
class PageAction:
    id: str
    label: str
    enabled: bool = True
    reason: str = ""

    @property
    def focus_id(self) -> str:
        return f"action:{self.id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "focusId": self.focus_id,
            "label": self.label,
            "enabled": self.enabled,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class GamePage:
    game: GameSummary
    actions: tuple[PageAction, ...]
    initial_focus: str

    @property
    def title(self) -> str:
        return self.game.title

    def to_qml_object(self) -> dict[str, Any]:
        return {
            "gameId": self.game.id,
            "title": self.game.title,
            "platform": self.game.platform,
            "lastPlayed": self.game.last_played,
            "initialFocus": self.initial_focus,
            "actions": [action.to_dict() for action in self.actions],
        }


def resolve_game_page(game: GameSummary) -> GamePage:
    """Monta a página com as ações já decididas.

    Jogo não jogável mantém o botão visível **com o motivo**: esconder a ação
    faria o usuário procurar o que não existe, e um botão que não responde sem
    explicação é pior que a ausência dele.
    """
    play = PageAction(
        id="play",
        label="Jogar",
        enabled=game.playable,
        reason="" if game.playable else f"indisponível: {game.blocked_reason}",
    )
    actions = (
        play,
        PageAction(id="favorite", label="Favoritar"),
        PageAction(id="details", label="Detalhes"),
    )
    # O foco nunca começa numa ação desabilitada — o usuário apertaria A e nada
    # aconteceria, sem saber por quê.
    initial = next((item for item in actions if item.enabled), actions[0])
    return GamePage(game=game, actions=actions, initial_focus=initial.focus_id)


@dataclass(frozen=True)
class LaunchContext:
    game_id: str
    focus_id: str

    @classmethod
    def capture(cls, *, game_id: str, focus_id: str) -> LaunchContext:
        if not is_identifier(game_id):
            raise ValueError(f"game id inválido: {game_id!r}")
        if not is_focus_id(focus_id):
            raise ValueError(f"focus id inválido: {focus_id!r}")
        return cls(game_id=game_id, focus_id=focus_id)

    def to_dict(self) -> dict[str, str]:
        return {"gameId": self.game_id, "focusId": self.focus_id}


@dataclass(frozen=True)
class ReturnDiagnostic:
    code: str
    reason: str
    fallback: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "reason": self.reason, "fallback": self.fallback}


def _nearest_in_section(section: str, focus: FocusMap) -> str | None:
    for node_id, node in focus.nodes.items():
        if node.section == section:
            return node_id
    return None


def restore_context(payload: object, focus: FocusMap) -> tuple[str, tuple[ReturnDiagnostic, ...]]:
    """Devolve o foco de retorno e o que se perdeu no caminho.

    Nunca levanta: um contexto corrompido é uma condição esperada entre
    processos, e derrubar o retorno deixaria o usuário fora do launcher depois
    de fechar o jogo.
    """
    if not isinstance(payload, dict):
        return focus.initial, (
            ReturnDiagnostic(
                code=DIAG_RETURN_INVALID,
                reason="contexto de retorno não é objeto",
                fallback=focus.initial,
            ),
        )
    raw_focus = payload.get("focusId")
    if not is_focus_id(raw_focus):
        return focus.initial, (
            ReturnDiagnostic(
                code=DIAG_RETURN_INVALID,
                reason=f"focusId inválido: {raw_focus!r}",
                fallback=focus.initial,
            ),
        )
    if raw_focus in focus.nodes:
        return raw_focus, ()

    # O item saiu da biblioteca enquanto o jogo rodava. Cair na mesma seção
    # preserva a intenção do usuário melhor do que voltar ao topo da home.
    section = raw_focus.split(":", 1)[0]
    nearest = _nearest_in_section(section, focus)
    target = nearest or focus.initial
    return target, (
        ReturnDiagnostic(
            code=DIAG_RETURN_MISSING,
            reason=f"item '{raw_focus}' não está mais na home",
            fallback=target,
        ),
    )
