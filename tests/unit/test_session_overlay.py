# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Provas do contrato semântico do overlay de sessão."""

from steamzero.domain.session_overlay import (
    DIAG_CRITICAL_ERROR,
    DIAG_DISABLED_ACTION,
    DIAG_NO_SESSION,
    DIAG_UNKNOWN_ACTION,
    request_overlay_action,
    resolve_session_overlay,
)


def _model(**osd: object) -> dict[str, object]:
    return {
        "session": {"sessionId": "01JSESSION", "gameId": "game-1", "state": "running"},
        "osd": {
            "visible": True,
            "focusedAction": "pause",
            "capabilities": {
                "pause": {"available": True},
                "volume": {"available": True},
                "screenshot": {"available": True},
                "saveState": {"available": False, "reason": "O emulador não oferece save-state."},
            },
            **osd,
        },
    }


def test_overlay_exposes_only_bounded_semantic_actions_and_focus() -> None:
    overlay = resolve_session_overlay(_model())
    assert overlay.visible is True
    assert overlay.focused_action == "pause"
    assert len(overlay.actions) == 13
    assert overlay.actions[0].id == "volume"
    assert next(item for item in overlay.actions if item.id == "saveState").enabled is False
    assert "save-state" in next(item for item in overlay.actions if item.id == "saveState").reason


def test_pause_intent_is_semantic_and_not_an_instruction_to_execute() -> None:
    result = request_overlay_action(_model(), "pause")
    assert result.accepted is True
    assert result.intent is not None
    assert result.intent.to_dict() == {
        "sessionId": "01JSESSION",
        "gameId": "game-1",
        "actionId": "pause",
        "operation": "pause",
    }


def test_suspended_session_changes_pause_label_and_operation_to_resume() -> None:
    model = _model()
    model["session"] = {"sessionId": "01JSESSION", "gameId": "game-1", "state": "suspended"}
    overlay = resolve_session_overlay(model)
    action = next(item for item in overlay.actions if item.id == "pause")
    assert action.label == "Retomar"
    assert action.operation == "resume"
    assert request_overlay_action(model, "pause").intent is not None
    assert request_overlay_action(model, "pause").intent.operation == "resume"  # type: ignore[union-attr]


def test_unavailable_action_is_visible_with_reason_and_cannot_be_dispatched() -> None:
    result = request_overlay_action(_model(), "saveState")
    assert result.accepted is False
    assert result.diagnostic == DIAG_DISABLED_ACTION
    assert result.action is not None
    assert result.action.reason
    assert result.intent is None


def test_critical_error_stays_visible_and_blocks_successful_intents() -> None:
    overlay = resolve_session_overlay(
        _model(
            criticalError={
                "code": "E-SAVE",
                "message": "Falha ao salvar",
                "privatePath": "/nao-publicar",
            }
        )
    )
    assert overlay.visible is True
    assert overlay.diagnostic == DIAG_CRITICAL_ERROR
    assert overlay.critical_error == {"code": "E-SAVE", "message": "Falha ao salvar"}
    result = request_overlay_action(
        _model(criticalError={"code": "E-SAVE", "message": "Falha ao salvar"}), "pause"
    )
    assert result.accepted is False
    assert result.diagnostic == DIAG_DISABLED_ACTION


def test_missing_or_unknown_action_degrades_without_fabricating_session() -> None:
    assert resolve_session_overlay({}).diagnostic == DIAG_NO_SESSION
    result = request_overlay_action(_model(), "secretShellCommand")
    assert result.accepted is False
    assert result.diagnostic == DIAG_UNKNOWN_ACTION
