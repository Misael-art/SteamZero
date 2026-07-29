# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""WI-9: integração do comando CLI ``emulation workspace`` com o read model."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero.cli.main import main


def test_emulation_workspace_cli_emits_versioned_envelope(
    capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STEAMZERO_NO_DAEMON", "1")
    code = main(["emulation", "workspace", "--json"])
    assert code == 0

    captured = capsys.readouterr()
    envelope = json.loads(captured.out)
    assert envelope["module"] == "emulation"
    assert envelope["action"] == "workspace"
    assert envelope["status"] in {"ready", "attention", "blocked", "unverified", "unavailable"}
    assert envelope["data"]["schemaVersion"] == 1
    platform = envelope["data"]["platforms"][0]
    assert platform["id"] == "switch"
    assert {scope["id"] for scope in platform["scopes"]} == {
        "global",
        "emulator",
        "game",
        "handheld",
        "dock",
    }
    assert {area["id"] for area in platform["areas"]} == {
        "overview",
        "keysFirmware",
        "updatesDlc",
        "modsCheats",
        "graphicsPerformance",
        "controls",
        "saves",
        "shaderCache",
        "media",
        "storage",
        "advanced",
    }
    assert captured.err == ""


def test_emulation_launch_cli_uses_local_controller(
    monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:  # type: ignore[no-untyped-def]
    launched: list[str] = []

    class FakeController:
        def launch_game(self, game_id: str) -> dict[str, str]:
            launched.append(game_id)
            return {"status": "started", "gameId": game_id, "emulatorId": "ryubing"}

    monkeypatch.setattr("steamzero.adapters.emulation.EmulationController", FakeController)
    code = main(["emulation", "launch", "--game-id", "game-1", "--json"])
    envelope = json.loads(capsys.readouterr().out)

    assert code == 0
    assert launched == ["game-1"]
    assert envelope["data"]["emulatorId"] == "ryubing"


def test_controls_cli_plan_apply_status_and_rollback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("STEAMZERO_NO_DAEMON", "1")
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(
        "steamzero.core.transaction.secrets.token_urlsafe",
        lambda _size: "-zfAF68ralrhqGIdv1zKbFSCRDyofMsy",
    )

    assert (
        main(
            [
                "controls",
                "plan",
                "--platform",
                "switch",
                "--profile",
                "standard-gamepad",
                "--orientation",
                "portrait-left",
                "--json",
            ]
        )
        == 0
    )
    planned = json.loads(capsys.readouterr().out)["data"]
    assert planned["rollbackGuarantee"] == "G-FULL"
    assert planned["confirmToken"] == "-zfAF68ralrhqGIdv1zKbFSCRDyofMsy"

    assert (
        main(
            [
                "controls",
                "apply",
                "--plan-id",
                planned["planId"],
                "--confirm",
                planned["confirmToken"],
                "--json",
            ]
        )
        == 0
    )
    applied = json.loads(capsys.readouterr().out)["data"]

    assert main(["controls", "profiles", "--platform", "switch", "--json"]) == 0
    status = json.loads(capsys.readouterr().out)["data"]
    assert status["active"]["id"] == "standard-gamepad"
    assert status["active"]["orientation"] == "portrait-left"

    assert (
        main(
            [
                "controls",
                "rollback",
                "--operation-id",
                applied["operationId"],
                "--json",
            ]
        )
        == 0
    )
    rolled_back = json.loads(capsys.readouterr().out)["data"]
    assert rolled_back["status"] == "rolled-back"
    assert main(["controls", "profiles", "--platform", "switch", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["active"] is None


@pytest.mark.parametrize(
    "args",
    [
        ["controls", "profiles", "--platform"],
        ["controls", "profiles", "--platform", "-switch"],
        ["controls", "profiles", "--platform", "switch", "--shell", "x"],
        ["controls", "profiles", "--platform", "switch", "--platform", "arcade"],
    ],
)
def test_controls_cli_rejects_open_ended_or_ambiguous_flags(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    args: list[str],
) -> None:
    monkeypatch.setenv("STEAMZERO_NO_DAEMON", "1")
    assert main([*args, "--json"]) == 1
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["error"]["code"] == "E-API-SCHEMA"
