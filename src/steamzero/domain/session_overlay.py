# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato puro do overlay de sessão do AURA.

O adapter é a autoridade sobre o que a sessão pode fazer. Este módulo apenas
transforma essa declaração em ações semânticas e intents bounded para a Theme
Engine; não fala com processos, não grava saves e não executa comandos.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

ACTIVE_SESSION_STATES = frozenset(
    {"launching", "running", "suspending", "suspended", "resuming", "closing"}
)
OSD_ACTIONS = (
    "volume",
    "mute",
    "brightness",
    "screenshot",
    "saveState",
    "loadState",
    "fastForward",
    "rewind",
    "pause",
    "control",
    "achievement",
    "network",
)
MAX_REASON_LENGTH = 240
MAX_ACTIONS = len(OSD_ACTIONS)
ERROR_FIELDS = ("code", "message", "detail", "impact", "nextAction")

DIAG_NO_SESSION = "AURA-OSD-SESSION-001"
DIAG_UNKNOWN_ACTION = "AURA-OSD-ACTION-002"
DIAG_DISABLED_ACTION = "AURA-OSD-ACTION-003"
DIAG_CRITICAL_ERROR = "AURA-OSD-ERROR-004"


def _text(value: Any, *, fallback: str = "", limit: int = MAX_REASON_LENGTH) -> str:
    if not isinstance(value, str):
        return fallback
    return value.strip()[:limit]


@dataclass(frozen=True)
class OverlayAction:
    """Ação que o tema pode mostrar sem conhecer o adapter concreto."""

    id: str
    label: str
    enabled: bool
    reason: str = ""
    operation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "enabled": self.enabled,
            "reason": self.reason,
            "operation": self.operation or self.id,
        }


@dataclass(frozen=True)
class OverlayIntent:
    """Pedido semântico que outro adapter ainda precisa executar."""

    session_id: str
    game_id: str
    action_id: str
    operation: str

    def to_dict(self) -> dict[str, str]:
        return {
            "sessionId": self.session_id,
            "gameId": self.game_id,
            "actionId": self.action_id,
            "operation": self.operation,
        }


@dataclass(frozen=True)
class OverlayActionResult:
    accepted: bool
    action: OverlayAction | None = None
    intent: OverlayIntent | None = None
    diagnostic: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "action": self.action.to_dict() if self.action is not None else None,
            "intent": self.intent.to_dict() if self.intent is not None else None,
            "diagnostic": self.diagnostic,
        }


@dataclass(frozen=True)
class SessionOverlay:
    session_id: str
    game_id: str
    state: str
    visible: bool
    focused_action: str
    actions: tuple[OverlayAction, ...]
    save_states: Mapping[str, Any] | None = None
    critical_error: Mapping[str, Any] | None = None
    diagnostic: str | None = None

    def to_qml_object(self) -> dict[str, Any]:
        return {
            "sessionId": self.session_id,
            "gameId": self.game_id,
            "state": self.state,
            "visible": self.visible,
            "focusedAction": self.focused_action,
            "actions": [item.to_dict() for item in self.actions],
            "saveStates": dict(self.save_states) if self.save_states is not None else None,
            "criticalError": dict(self.critical_error) if self.critical_error else None,
            "diagnostic": self.diagnostic,
        }


def _capability(raw: Any) -> tuple[bool, str]:
    if isinstance(raw, bool):
        return raw, "" if raw else "O adapter não declarou suporte para esta ação."
    if not isinstance(raw, Mapping):
        return False, "O adapter não declarou suporte para esta ação."
    available = raw.get("available") is True
    reason = _text(raw.get("reason") or raw.get("detail"))
    if not available and not reason:
        reason = "O adapter não declarou suporte para esta ação."
    return available, reason


def _critical_error(raw: Any) -> Mapping[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    value = raw.get("criticalError")
    if not isinstance(value, Mapping):
        return None
    safe = {
        field: _text(value[field])
        for field in ERROR_FIELDS
        if field in value and isinstance(value[field], str) and _text(value[field])
    }
    return safe or None


def _actions(
    capabilities: Mapping[str, Any],
    *,
    state: str,
    critical_error: Mapping[str, Any] | None,
) -> tuple[OverlayAction, ...]:
    result: list[OverlayAction] = []
    for action_id in OSD_ACTIONS:
        available, reason = _capability(capabilities.get(action_id))
        operation = action_id
        label = action_id
        if action_id == "pause":
            label = "Retomar" if state == "suspended" else "Pausar"
            operation = "resume" if state == "suspended" else "pause"
        elif action_id == "saveState":
            label = "Galeria de saves"
        elif action_id == "loadState":
            label = "Carregar save"
        # A critical error stays visible, but cannot be reported as a
        # successful action. Recovery controls remain declarative.
        if critical_error is not None and available:
            reason = "Erro crítico visível; confirme a recuperação na sessão."
        result.append(
            OverlayAction(
                id=action_id,
                label=label,
                enabled=available and critical_error is None,
                reason=reason,
                operation=operation,
            )
        )
    return tuple(result[:MAX_ACTIONS])


def resolve_session_overlay(read_model: Mapping[str, Any]) -> SessionOverlay:
    """Resolve um read model de sessão em uma superfície segura e bounded."""

    session = read_model.get("session")
    if not isinstance(session, Mapping):
        return SessionOverlay(
            session_id="",
            game_id="",
            state="unknown",
            visible=False,
            focused_action="",
            actions=(),
            diagnostic=DIAG_NO_SESSION,
        )
    session_id = _text(session.get("sessionId") or session.get("id"), limit=128)
    game_id = _text(session.get("gameId"), limit=128)
    state = _text(session.get("state"), fallback="unknown", limit=32)
    osd = read_model.get("osd")
    osd = osd if isinstance(osd, Mapping) else {}
    critical_error = _critical_error(osd)
    raw_capabilities = osd.get("capabilities")
    capabilities = raw_capabilities if isinstance(raw_capabilities, Mapping) else {}
    actions = _actions(capabilities, state=state, critical_error=critical_error)
    raw_gallery = read_model.get("saveStates")
    save_states = raw_gallery if isinstance(raw_gallery, Mapping) else None
    requested_focus = _text(osd.get("focusedAction"), limit=32)
    enabled_ids = {item.id for item in actions if item.enabled}
    focused = (
        requested_focus
        if requested_focus in enabled_ids
        else next((item.id for item in actions if item.enabled), "")
    )
    active = bool(session_id and game_id and state in ACTIVE_SESSION_STATES)
    diagnostic = None if active else DIAG_NO_SESSION
    if critical_error is not None:
        diagnostic = DIAG_CRITICAL_ERROR
    return SessionOverlay(
        session_id=session_id,
        game_id=game_id,
        state=state,
        visible=active and osd.get("visible") is True,
        focused_action=focused,
        actions=actions,
        save_states=save_states,
        critical_error=critical_error,
        diagnostic=diagnostic,
    )


def request_overlay_action(read_model: Mapping[str, Any], action_id: str) -> OverlayActionResult:
    """Converte uma ação habilitada em intent; nunca executa o efeito."""

    overlay = resolve_session_overlay(read_model)
    action = next((item for item in overlay.actions if item.id == action_id), None)
    if action is None:
        return OverlayActionResult(False, diagnostic=DIAG_UNKNOWN_ACTION)
    if not overlay.visible or not action.enabled:
        return OverlayActionResult(False, action=action, diagnostic=DIAG_DISABLED_ACTION)
    intent = OverlayIntent(
        session_id=overlay.session_id,
        game_id=overlay.game_id,
        action_id=action.id,
        operation=action.operation or action.id,
    )
    return OverlayActionResult(True, action=action, intent=intent)
