from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.adapters.emulation import EmulationController
from steamzero.adapters.preservation import PreservationTarget
from steamzero.core import fs
from steamzero.core.state import StateStore


def _apply(controller: EmulationController, plan: dict[str, object]) -> dict[str, object]:
    return controller.apply_action(str(plan["planId"]), str(plan["confirmToken"]))


def test_handheld_read_model_exposes_only_confirmed_save_operations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda _class: home))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    state_db = tmp_path / "state.db"

    controller = EmulationController(
        store_factory=lambda: StateStore(state_db),
        which=lambda _command: None,
        spawn=lambda _argv: None,
    )
    title_id = "0100ABCDEF123000"
    roms = tmp_path / "roms"
    roms.mkdir()
    (roms / f"Example [{title_id}][v0].nsp").write_bytes(b"rom")
    _apply(
        controller,
        controller.plan_action({"actionId": "library.root.add", "path": str(roms)}),
    )
    game = controller.snapshot({"context": {}})["platforms"][0]["games"][0]
    game_id = str(game["id"])
    _apply(
        controller,
        controller.plan_action(
            {"actionId": "game.emulator.set", "gameId": game_id, "emulatorId": "citron"}
        ),
    )

    active = tmp_path / "citron" / "save" / title_id
    fs.write_atomic(active / "slot.bin", b"first-version")
    target = PreservationTarget(
        kind="save",
        game_id=game_id,
        title_id=title_id,
        emulator_id="citron",
        root=active,
        emulator_version="1.0.0",
    )
    controller = EmulationController(
        store_factory=lambda: StateStore(state_db),
        which=lambda _command: None,
        spawn=lambda _argv: None,
        preservation_targets=[target],
    )
    snapshot = controller.snapshot({"context": {}})
    game = snapshot["platforms"][0]["games"][0]
    assert game["saveTarget"]["confirmed"] is True
    saves_area = snapshot["platforms"][0]["areaData"]["saves"]
    target_card = saves_area["cards"][0]
    assert [action["id"] for action in target_card["actions"]] == [f"game.save.backup:{game_id}"]

    _apply(
        controller,
        controller.plan_action({"actionId": f"game.save.backup:{game_id}"}),
    )
    snapshot = controller.snapshot({"context": {}})
    cards = snapshot["platforms"][0]["areaData"]["saves"]["cards"]
    restore_action = next(
        action
        for card in cards
        for action in card.get("actions", [])
        if str(action["id"]).startswith("game.save.restore:")
    )
    assert restore_action["enabled"] is True

    fs.write_atomic(active / "slot.bin", b"second-version")
    _apply(
        controller,
        controller.plan_action({"actionId": str(restore_action["id"])}),
    )
    assert (active / "slot.bin").read_bytes() == b"first-version"


def test_unconfirmed_destination_has_no_mutation_button(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda _class: home))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    controller = EmulationController(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        which=lambda _command: None,
        spawn=lambda _argv: None,
    )

    cards = controller.snapshot({"context": {}})["platforms"][0]["areaData"]["saves"]["cards"]
    assert cards[0].get("actions", []) == []
