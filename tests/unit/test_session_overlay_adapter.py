# SPDX-License-Identifier: GPL-3.0-or-later
"""Provas do adapter AURA entre read model e SessionManager."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from steamzero.adapters.session_overlay import (
    DIAG_SESSION_MISMATCH,
    SessionOverlayAdapter,
)


@dataclass
class FakeSession:
    id: str = "session-1"
    game_id: str = "game-1"
    state: str = "running"


class FakeControl:
    def __init__(self, session: FakeSession) -> None:
        self.current = session
        self.calls: list[str] = []
        self.fail = False

    def suspend(self) -> FakeSession:
        self.calls.append("suspend")
        if self.fail:
            raise RuntimeError("flush indisponível")
        self.current.state = "suspended"
        return self.current

    def resume(self) -> FakeSession:
        self.calls.append("resume")
        self.current.state = "running"
        return self.current


def make_adapter(control: FakeControl) -> SessionOverlayAdapter:
    def observe(_game_id: str) -> dict[str, Any]:
        return {
            "gameId": control.current.game_id,
            "sessionId": control.current.id,
            "state": control.current.state,
        }

    return SessionOverlayAdapter(
        observe,
        lambda session_id, game_id: (
            control
            if (session_id, game_id) == (control.current.id, control.current.game_id)
            else None
        ),
    )


def test_read_model_declares_real_pause_and_explicit_unsupported_actions() -> None:
    control = FakeControl(FakeSession())
    model = make_adapter(control).read_model("game-1", visible=True)

    capabilities = model["osd"]["capabilities"]
    assert model["session"] == {
        "gameId": "game-1",
        "sessionId": "session-1",
        "state": "running",
    }
    assert capabilities["pause"] == {"available": True, "reason": ""}
    assert capabilities["saveState"]["available"] is False
    assert capabilities["saveState"]["reason"]


def test_dispatch_pause_and_resume_use_the_same_canonical_control() -> None:
    control = FakeControl(FakeSession())
    adapter = make_adapter(control)

    paused = adapter.dispatch("game-1", "session-1", "pause")
    resumed = adapter.dispatch("game-1", "session-1", "pause")

    assert paused.accepted is True
    assert paused.operation == "pause"
    assert paused.state == "suspended"
    assert resumed.accepted is True
    assert resumed.operation == "resume"
    assert resumed.state == "running"
    assert control.calls == ["suspend", "resume"]


def test_dispatch_rejects_stale_session_before_calling_control() -> None:
    control = FakeControl(FakeSession())
    result = make_adapter(control).dispatch("game-1", "old-session", "pause")

    assert result.accepted is False
    assert result.diagnostic == DIAG_SESSION_MISMATCH
    assert control.calls == []


def test_dispatch_keeps_unsupported_action_visible_without_side_effect() -> None:
    control = FakeControl(FakeSession())
    result = make_adapter(control).dispatch("game-1", "session-1", "saveState")

    assert result.accepted is False
    assert result.diagnostic == "AURA-OSD-ACTION-003"
    assert control.calls == []


def test_dispatch_returns_recoverable_error_when_session_operation_fails() -> None:
    control = FakeControl(FakeSession())
    control.fail = True
    result = make_adapter(control).dispatch("game-1", "session-1", "pause")

    assert result.accepted is False
    assert result.diagnostic == "AURA-SESSION-ADAPTER-003"
    assert result.state == "running"
    assert "flush indisponível" in result.detail
