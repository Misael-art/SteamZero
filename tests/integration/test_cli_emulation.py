# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""WI-9: integração do comando CLI ``emulation workspace`` com o read model."""

from __future__ import annotations

import json

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
        "graphicsPerformance",
        "controls",
        "saves",
        "shaderCache",
        "media",
        "storage",
        "advanced",
    }
    assert captured.err == ""
