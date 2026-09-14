# SPDX-License-Identifier: GPL-3.0-or-later
"""Contracts and concrete boundaries for AURA session peripherals."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.adapters.session_peripherals import RetroArchSessionPeripheral
from steamzero.domain.session_peripherals import resolve_session_peripherals


def test_resolver_bounds_and_hides_private_bezel_paths() -> None:
    model = resolve_session_peripherals(
        {
            "state": "ready",
            "activeDisc": 1,
            "discs": [
                {"id": "disc-0", "label": "A", "available": True},
                {"id": "disc-1", "label": "B", "available": True},
            ],
            "selectedBezel": "crt",
            "bezels": [
                {"id": "crt", "label": "CRT", "assetUrl": "/home/user/private.png"},
                {"id": "safe", "label": "Safe", "assetUrl": "asset://bezels/safe.png"},
            ],
            "fade": {"phase": "return", "progress": 2, "durationMs": 99999},
        },
        reduced_motion=True,
    )
    payload = model.to_dict()
    assert payload["activeDisc"] == 1
    assert payload["discs"][1]["inserted"] is True
    assert payload["bezels"][0]["assetUrl"] == ""
    assert payload["bezels"][0]["available"] is False
    assert payload["bezels"][1]["assetUrl"] == "asset://bezels/safe.png"
    assert payload["fade"] == {
        "phase": "return",
        "progress": 1.0,
        "durationMs": 10000,
        "reducedMotion": True,
    }


def test_retroarch_save_state_slot_zero_waits_for_a_real_file(tmp_path: Path) -> None:
    commands: list[str] = []
    content = tmp_path / "game.zip"
    content.write_bytes(b"content")
    states = tmp_path / "states"
    states.mkdir()

    def send(command: str) -> None:
        commands.append(command)
        (states / "game.state").write_bytes(b"real-state")

    adapter = RetroArchSessionPeripheral(content, states, send_command=send, sleep=lambda _: None)
    result = adapter.save_state(0)
    assert result.state == "running"
    assert commands == ["SAVE_STATE"]
    assert adapter.list_save_states()["entries"][0]["compatibility"] == "native"


def test_retroarch_save_state_backups_the_previous_snapshot_atomically(tmp_path: Path) -> None:
    content = tmp_path / "game.zip"
    content.write_bytes(b"content")
    states = tmp_path / "states"
    states.mkdir()
    previous = states / "game.state"
    previous.write_bytes(b"previous")

    def send(command: str) -> None:
        assert command == "SAVE_STATE"
        previous.write_bytes(b"next")

    adapter = RetroArchSessionPeripheral(content, states, send_command=send, sleep=lambda _: None)
    adapter.save_state(0)

    assert (states / ".backups" / "game.slot0.state").read_bytes() == b"previous"
    assert adapter.list_save_states()["entries"][0]["backupAvailable"] is True


def test_retroarch_rejects_unproven_slots_and_supports_m3u_swap(tmp_path: Path) -> None:
    first = tmp_path / "disc-one.cue"
    second = tmp_path / "disc-two.cue"
    first.write_text("FILE one.bin BINARY\n", encoding="utf-8")
    second.write_text("FILE two.bin BINARY\n", encoding="utf-8")
    playlist = tmp_path / "game.m3u"
    playlist.write_text("disc-one.cue\ndisc-two.cue\n", encoding="utf-8")
    commands: list[str] = []
    adapter = RetroArchSessionPeripheral(
        playlist, tmp_path / "states", send_command=commands.append, sleep=lambda _: None
    )
    with pytest.raises(ValueError, match="somente o slot 0"):
        adapter.save_state(1)
    assert adapter.list_discs()["discs"][1]["label"] == "disc-two.cue"
    adapter.swap_disc("disc-1")
    assert commands == ["DISK_EJECT_TOGGLE", "DISK_NEXT", "DISK_EJECT_TOGGLE"]
