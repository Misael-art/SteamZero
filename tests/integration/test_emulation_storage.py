# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Integração do resumo de armazenamento no workspace da emulação."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.adapters.emulation import EmulationController
from steamzero.core.state import StateStore


def _apply(controller: EmulationController, plan: dict[str, object]) -> None:
    controller.apply_action(str(plan["planId"]), str(plan["confirmToken"]))


def test_workspace_exposes_storage_statistics_without_mutating_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    roms = tmp_path / "roms"
    roms.mkdir()
    (roms / "game.nsp").write_bytes(b"rom")
    data = tmp_path / "data" / "steamzero"
    (data / "saves").mkdir(parents=True)
    (data / "saves" / "slot.bin").write_bytes(b"save")
    (data / "media").mkdir(parents=True)
    (data / "media" / "cover.png").write_bytes(b"cover")

    controller = EmulationController(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        which=lambda _command: None,
        spawn=lambda _argv: None,
    )
    _apply(
        controller,
        controller.plan_action({"actionId": "library.root.add", "path": str(roms)}),
    )
    monkeypatch.setattr(
        controller,
        "_load_library_cache",
        lambda: (
            [
                {
                    "id": "switch-1",
                    "titleId": "0100ABCDEF123000",
                    "name": "Jogo Switch",
                    "state": "ready",
                    "statusLabel": "Pronto",
                    "path": str(roms / "game.nsp"),
                    "platform": "switch",
                    "platformId": "switch",
                }
            ],
            0,
        ),
    )
    monkeypatch.setattr(controller, "_enrich_games", lambda games, *_args: games)
    monkeypatch.setattr(controller, "_enrich_preservation", lambda games: games)
    monkeypatch.setattr(controller, "_enrich_controls", lambda games: games)

    tracked = {
        path: path.read_bytes()
        for path in (roms / "game.nsp", data / "saves" / "slot.bin", data / "media" / "cover.png")
    }
    platform = controller.snapshot({"context": {}})["platforms"][0]
    storage = platform["areaData"]["storage"]
    summary = storage["storageSummary"]
    buckets = {bucket["id"]: bucket for bucket in summary["buckets"]}

    assert buckets["roms"]["files"] == 1
    assert buckets["saves"]["bytes"] == 4
    assert buckets["media"]["bytes"] == 5
    assert storage["primaryAction"]["id"] == "storage.recover"
    rom_card = next(card for card in storage["cards"] if card["id"] == "storage-roms")
    assert rom_card["actions"][0]["id"] == "library.scan"
    assert {path: path.read_bytes() for path in tracked} == tracked
