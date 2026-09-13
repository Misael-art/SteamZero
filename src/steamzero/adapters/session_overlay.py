# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Adapter bounded entre o lifecycle de sessão e o overlay AURA.

Este módulo é a autoridade de execução do overlay. A Theme Engine recebe apenas
um read model e intents semânticos; nunca recebe um processo, argv, caminho ou
objeto de gerenciador para executar por conta própria.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from steamzero.domain.session_overlay import (
    OSD_ACTIONS,
    OverlayIntent,
    request_overlay_action,
)

SESSION_ACTIONS = frozenset({"pause"})
UNSUPPORTED_REASON = "Esta ação ainda não possui adapter de sessão."
DIAG_SESSION_MISMATCH = "AURA-SESSION-ADAPTER-001"
DIAG_SESSION_UNAVAILABLE = "AURA-SESSION-ADAPTER-002"
DIAG_ACTION_FAILED = "AURA-SESSION-ADAPTER-003"
DIAG_INVALID_INTENT = "AURA-SESSION-ADAPTER-004"
MAX_DETAIL_LENGTH = 240


class SessionRecord(Protocol):
    id: str
    game_id: str
    state: str


class SessionControl(Protocol):
    """Parte mínima do SessionManager necessária para o overlay."""

    @property
    def current(self) -> SessionRecord | None: ...

    def suspend(self) -> SessionRecord: ...

    def resume(self) -> SessionRecord: ...


@dataclass(frozen=True)
class SessionActionDispatch:
    """Resultado serializável de uma tentativa de ação sem efeito implícito."""

    accepted: bool
    game_id: str
    session_id: str
    operation: str | None
    state: str
    diagnostic: str | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "gameId": self.game_id,
            "sessionId": self.session_id,
            "operation": self.operation,
            "state": self.state,
            "diagnostic": self.diagnostic,
            "detail": self.detail,
        }


def _text(value: Any, *, fallback: str = "", limit: int = MAX_DETAIL_LENGTH) -> str:
    if not isinstance(value, str):
        return fallback
    return value.strip()[:limit]


class SessionOverlayAdapter:
    """Publica a sessão observada e executa somente operações allowlisted.

    ``observe`` deve ser a leitura canônica da sessão e ``resolve_control``
    deve devolver o gerenciador que já é dono daquele ``sessionId``/``gameId``.
    O adapter não cria outro gerenciador e não faz spawn, kill ou acesso a disco.
    """

    def __init__(
        self,
        observe: Callable[[str], Mapping[str, Any]],
        resolve_control: Callable[[str, str], SessionControl | None],
    ) -> None:
        self._observe = observe
        self._resolve_control = resolve_control

    def read_model(
        self,
        game_id: str,
        *,
        visible: bool = False,
        focused_action: str = "",
    ) -> dict[str, Any]:
        """Converte a observação em um read model completo para a Theme Engine."""

        observed = dict(self._observe(game_id))
        session_game_id = _text(observed.get("gameId"), limit=128)
        session_id = _text(observed.get("sessionId"), limit=128)
        state = _text(observed.get("state"), fallback="unknown", limit=32)
        consistent = session_game_id == game_id and bool(session_id)
        control = self._matching_control(session_id, game_id) if consistent else None
        pause_available = control is not None and state in {"running", "suspended"}
        capabilities: dict[str, dict[str, Any]] = {
            action_id: {
                "available": action_id in SESSION_ACTIONS and pause_available,
                "reason": (
                    "" if action_id in SESSION_ACTIONS and pause_available else UNSUPPORTED_REASON
                ),
            }
            for action_id in OSD_ACTIONS
        }
        if not consistent:
            reason = (
                "A observação da sessão não corresponde ao jogo solicitado."
                if session_id
                else "Nenhuma sessão controlável foi observada."
            )
            capabilities["pause"] = {"available": False, "reason": reason}
        elif not pause_available:
            capabilities["pause"] = {
                "available": False,
                "reason": "A sessão não está em um estado pausável.",
            }
        result_session = {
            "gameId": game_id,
            "sessionId": session_id or None,
            "state": state,
        }
        if observed.get("diagnostic"):
            result_session["diagnostic"] = _text(observed["diagnostic"], limit=64)
        return {
            "session": result_session,
            "osd": {
                "visible": visible,
                "focusedAction": focused_action,
                "capabilities": capabilities,
            },
        }

    def dispatch(
        self,
        game_id: str,
        session_id: str,
        action_id: str,
    ) -> SessionActionDispatch:
        """Valida correlação/capacidade e encaminha pause ou resume ao dono."""

        if not _text(game_id, limit=128) or not _text(session_id, limit=128):
            return SessionActionDispatch(
                accepted=False,
                game_id=_text(game_id, limit=128),
                session_id=_text(session_id, limit=128),
                operation=None,
                state="unknown",
                diagnostic=DIAG_INVALID_INTENT,
                detail="gameId e sessionId são obrigatórios.",
            )
        model = self.read_model(game_id, visible=True)
        session = model["session"]
        observed_id = session.get("sessionId")
        observed_state = _text(session.get("state"), fallback="unknown", limit=32)
        if observed_id != session_id or session.get("gameId") != game_id:
            return SessionActionDispatch(
                accepted=False,
                game_id=game_id,
                session_id=session_id,
                operation=None,
                state=observed_state,
                diagnostic=DIAG_SESSION_MISMATCH,
                detail="A sessão mudou; atualize o overlay antes de tentar novamente.",
            )

        requested = request_overlay_action(model, action_id)
        if not requested.accepted or requested.intent is None:
            return SessionActionDispatch(
                accepted=False,
                game_id=game_id,
                session_id=session_id,
                operation=(requested.action.operation if requested.action else None),
                state=observed_state,
                diagnostic=requested.diagnostic,
                detail=(requested.action.reason if requested.action else "Ação não reconhecida."),
            )

        intent = requested.intent
        control = self._matching_control(session_id, game_id)
        if control is None:
            return SessionActionDispatch(
                accepted=False,
                game_id=game_id,
                session_id=session_id,
                operation=intent.operation,
                state=observed_state,
                diagnostic=DIAG_SESSION_UNAVAILABLE,
                detail="O gerenciador canônico da sessão não está disponível.",
            )
        try:
            updated = self._execute(intent, control)
        except Exception as exc:  # boundary: transforma falha de adapter em estado recuperável
            return SessionActionDispatch(
                accepted=False,
                game_id=game_id,
                session_id=session_id,
                operation=intent.operation,
                state=_text(
                    getattr(control.current, "state", None),
                    fallback=observed_state,
                    limit=32,
                ),
                diagnostic=DIAG_ACTION_FAILED,
                detail=_text(str(exc), fallback="A operação da sessão falhou."),
            )
        state = _text(getattr(updated, "state", None), fallback=observed_state, limit=32)
        return SessionActionDispatch(
            accepted=True,
            game_id=game_id,
            session_id=session_id,
            operation=intent.operation,
            state=state,
        )

    def _matching_control(self, session_id: str, game_id: str) -> SessionControl | None:
        control = self._resolve_control(session_id, game_id)
        if control is None:
            return None
        current = control.current
        if current is None or current.id != session_id or current.game_id != game_id:
            return None
        return control

    @staticmethod
    def _execute(intent: OverlayIntent, control: SessionControl) -> SessionRecord:
        if intent.action_id != "pause" or intent.operation not in {"pause", "resume"}:
            raise ValueError("intent de sessão não allowlisted")
        current = control.current
        if current is None:
            raise RuntimeError("sessão sem estado atual")
        if intent.operation == "pause":
            if current.state != "running":
                raise ValueError("a sessão não está em execução")
            return control.suspend()
        if current.state != "suspended":
            raise ValueError("a sessão não está suspensa")
        return control.resume()


__all__ = ["SessionActionDispatch", "SessionOverlayAdapter"]
