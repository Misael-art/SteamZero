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


class SaveStateControl(FakeControl):
    def __init__(self, session: FakeSession) -> None:
        super().__init__(session)
        self.save_states = [
            {
                "slot": 2,
                "timestamp": "2026-09-13T20:00:00Z",
                "playtimeSeconds": 120,
                "thumbnailUrl": "asset://save-states/slot-2.png",
                "compatibility": "native",
                "backupAvailable": True,
            }
        ]

    def list_save_states(self) -> list[dict[str, Any]]:
        return self.save_states

    def save_state(self, slot: int) -> FakeSession:
        self.calls.append(f"save:{slot}")
        return self.current

    def load_state(self, slot: int) -> FakeSession:
        self.calls.append(f"load:{slot}")
        return self.current


class DiscControl(FakeControl):
    def list_discs(self) -> dict[str, Any]:
        return {
            "state": "ready",
            "activeDisc": 0,
            "discs": [
                {"id": "disc-0", "label": "Disco 1", "inserted": True},
                {"id": "disc-1", "label": "Disco 2", "inserted": False},
            ],
        }

    def swap_disc(self, disc_id: str) -> FakeSession:
        self.calls.append(f"disc:{disc_id}")
        return self.current


class PeripheralControl(DiscControl):
    def list_peripherals(self) -> dict[str, Any]:
        return {
            "state": "ready",
            "activeDisc": 0,
            "discs": [
                {"id": "disc-0", "label": "Disco 1", "inserted": True},
                {"id": "disc-1", "label": "Disco 2", "inserted": False},
            ],
            "selectedBezel": "aura-default",
            "bezels": [
                {
                    "id": "aura-default",
                    "label": "AURA Cinema",
                    "assetUrl": "asset://bezels/aura-bezel.svg",
                    "available": True,
                    "selected": True,
                }
            ],
            "fade": {"phase": "idle", "progress": 0.0, "durationMs": 180},
        }


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


def test_read_model_publishes_save_state_gallery_and_declares_real_operations() -> None:
    control = SaveStateControl(FakeSession())
    model = make_adapter(control).read_model("game-1", visible=True)

    assert model["osd"]["capabilities"]["saveState"] == {"available": True, "reason": ""}
    assert model["osd"]["capabilities"]["loadState"] == {"available": True, "reason": ""}
    assert model["saveStates"]["state"] == "ready"
    assert model["saveStates"]["entries"][0]["slot"] == 2
    assert model["saveStates"]["entries"][0]["backupAvailable"] is True


def test_save_and_load_dispatch_requires_a_bounded_slot_and_same_session() -> None:
    control = SaveStateControl(FakeSession())
    adapter = make_adapter(control)

    saved = adapter.dispatch("game-1", "session-1", "saveState", slot=2)
    loaded = adapter.dispatch("game-1", "session-1", "loadState", slot=2)

    assert saved.accepted is True
    assert saved.operation == "saveState"
    assert saved.slot == 2
    assert loaded.accepted is True
    assert loaded.operation == "loadState"
    assert loaded.slot == 2
    assert control.calls == ["save:2", "load:2"]


def test_dispatch_returns_recoverable_error_when_session_operation_fails() -> None:
    control = FakeControl(FakeSession())
    control.fail = True
    result = make_adapter(control).dispatch("game-1", "session-1", "pause")

    assert result.accepted is False
    assert result.diagnostic == "AURA-SESSION-ADAPTER-003"
    assert result.state == "running"
    assert "flush indisponível" in result.detail


def test_disc_surface_is_available_only_from_a_multi_disc_adapter() -> None:
    control = DiscControl(FakeSession())
    adapter = make_adapter(control)

    model = adapter.read_model("game-1", visible=True)
    result = adapter.dispatch("game-1", "session-1", "disc", disc_id="disc-1")

    assert model["osd"]["capabilities"]["disc"] == {"available": True, "reason": ""}
    assert model["peripherals"]["discs"][1]["id"] == "disc-1"
    assert result.accepted is True
    assert result.disc_id == "disc-1"
    assert control.calls == ["disc:disc-1"]


def test_read_model_projects_declared_bezel_and_fade_from_complete_adapter() -> None:
    control = PeripheralControl(FakeSession())
    model = make_adapter(control).read_model("game-1", visible=True)

    assert model["peripherals"]["bezels"] == [
        {
            "id": "aura-default",
            "label": "AURA Cinema",
            "assetUrl": "asset://bezels/aura-bezel.svg",
            "available": True,
            "selected": True,
            "reason": "",
        }
    ]
    assert model["peripherals"]["fade"] == {
        "phase": "idle",
        "progress": 0.0,
        "durationMs": 180,
        "reducedMotion": False,
    }
