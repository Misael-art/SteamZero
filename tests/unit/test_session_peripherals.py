# SPDX-License-Identifier: GPL-3.0-or-later
"""Contracts and concrete boundaries for AURA session peripherals."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.adapters.session_peripherals import (
    RetroArchSessionPeripheral,
    prepare_retroarch_session_config,
)
from steamzero.core import paths
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


def test_retroarch_session_config_publishes_managed_aura_bezel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(paths, "config_home", lambda: tmp_path / "config")
    monkeypatch.setattr(paths, "saves_dir", lambda: tmp_path / "saves")

    config = prepare_retroarch_session_config()
    text = config.read_text(encoding="utf-8")
    bezel_config = config.parent / "aura-bezel-overlay.cfg"
    bezel_asset = config.parent / "aura-bezel.png"

    assert "SteamZero-Session-Managed: true" in text
    assert 'input_overlay_enable = "true"' in text
    assert f'input_overlay = "{bezel_config}"' in text
    bezel_text = bezel_config.read_text(encoding="utf-8")
    assert bezel_text.startswith("# SteamZero-Session-Managed: true")
    assert 'overlays = "1"' in bezel_text
    assert bezel_asset.is_file()
    assert bezel_asset.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_retroarch_session_config_creates_managed_state_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(paths, "config_home", lambda: tmp_path / "config")
    monkeypatch.setattr(paths, "saves_dir", lambda: tmp_path / "saves")

    prepare_retroarch_session_config()

    state_root = tmp_path / "saves" / "states"
    assert state_root.is_dir()
    assert state_root.stat().st_mode & 0o777 == 0o700


def test_retroarch_complete_peripheral_projection_uses_logical_bezel_asset(
    tmp_path: Path,
) -> None:
    content = tmp_path / "game.sfc"
    content.write_bytes(b"content")
    projection = RetroArchSessionPeripheral(content, tmp_path / "states").list_peripherals()

    assert projection["state"] == "ready"
    assert projection["selectedBezel"] == "aura-default"
    assert projection["bezels"] == [
        {
            "id": "aura-default",
            "label": "AURA Cinema",
            "assetUrl": "asset://bezels/aura-bezel.svg",
            "available": True,
            "compatible": True,
            "selected": True,
        }
    ]
    assert projection["fade"] == {"phase": "idle", "progress": 0.0, "durationMs": 180}


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


def test_retroarch_gallery_saves_and_loads_a_bounded_nonzero_slot(tmp_path: Path) -> None:
    content = tmp_path / "game.zip"
    content.write_bytes(b"content")
    states = tmp_path / "states"
    states.mkdir()
    commands: list[str] = []

    def send(command: str) -> None:
        commands.append(command)
        if command == "SAVE_STATE":
            (states / "game.state2").write_bytes(b"slot-two")

    adapter = RetroArchSessionPeripheral(content, states, send_command=send, sleep=lambda _: None)
    adapter.save_state(2)
    assert commands == ["STATE_SLOT_PLUS", "STATE_SLOT_PLUS", "SAVE_STATE"]
    assert adapter.load_state(2).state == "running"
    assert commands[-1] == "LOAD_STATE_SLOT 2"


def test_retroarch_session_cursor_starts_from_per_content_runtime_log(tmp_path: Path) -> None:
    content = tmp_path / "game.zip"
    content.write_bytes(b"content")
    states = tmp_path / "states"
    (states / "Core Name").mkdir(parents=True)
    logs = tmp_path / "logs" / "Core Name"
    logs.mkdir(parents=True)
    (logs / "game.lrtl").write_text('{"state_slot":"1"}', encoding="utf-8")
    commands: list[str] = []

    def send(command: str) -> None:
        commands.append(command)
        if command == "SAVE_STATE":
            (states / "Core Name" / "game.state3").write_bytes(b"slot-three")

    adapter = RetroArchSessionPeripheral(
        content,
        states,
        send_command=send,
        sleep=lambda _: None,
        runtime_log_root=tmp_path / "logs",
    )
    adapter.save_state(3)

    assert commands == ["STATE_SLOT_PLUS", "STATE_SLOT_PLUS", "SAVE_STATE"]


def test_retroarch_invalid_runtime_log_falls_back_to_slot_zero(tmp_path: Path) -> None:
    content = tmp_path / "game.zip"
    content.write_bytes(b"content")
    logs = tmp_path / "logs" / "Core Name"
    logs.mkdir(parents=True)
    (logs / "game.lrtl").write_text("not-json", encoding="utf-8")

    adapter = RetroArchSessionPeripheral(
        content,
        tmp_path / "states",
        send_command=lambda _: None,
        sleep=lambda _: None,
        runtime_log_root=tmp_path / "logs",
    )

    assert adapter._state_slot == 0


def test_retroarch_slot_commands_are_settled_before_the_next_command(tmp_path: Path) -> None:
    content = tmp_path / "game.zip"
    content.write_bytes(b"content")
    states = tmp_path / "states"
    states.mkdir()
    commands: list[str] = []
    settles: list[float] = []

    def send(command: str) -> None:
        commands.append(command)
        if command == "SAVE_STATE":
            (states / "game.state3").write_bytes(b"slot-three")

    adapter = RetroArchSessionPeripheral(
        content,
        states,
        send_command=send,
        sleep=settles.append,
    )
    adapter.save_state(3)

    assert commands == ["STATE_SLOT_PLUS", "STATE_SLOT_PLUS", "STATE_SLOT_PLUS", "SAVE_STATE"]
    assert settles[:3] == [0.05, 0.05, 0.05]
    assert settles[-1] == 0.05


def test_retroarch_bounds_save_slots_and_supports_m3u_swap(tmp_path: Path) -> None:
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
    with pytest.raises(ValueError, match=r"limite 0\.\.31"):
        adapter.save_state(32)
    assert adapter.list_discs()["discs"][1]["label"] == "disc-two.cue"
    adapter.swap_disc("disc-1")
    assert commands == ["DISK_EJECT_TOGGLE", "DISK_NEXT", "DISK_EJECT_TOGGLE"]
