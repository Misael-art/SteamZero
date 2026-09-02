"""Contratos transacionais dos atalhos de gestão de armazenamento."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from steamzero.adapters.emulation import EmulationController
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain.switch_roots import root_id


def _controller(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> EmulationController:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return EmulationController(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        which=lambda _command: None,
        spawn=lambda _argv: None,
    )


def _apply(controller: EmulationController, plan: dict[str, Any]) -> dict[str, Any]:
    return controller.apply_action(str(plan["planId"]), str(plan["confirmToken"]))


def _register_root(controller: EmulationController, root: Path) -> None:
    _apply(controller, controller.plan_action({"actionId": "library.root.add", "path": str(root)}))


def test_move_registered_root_updates_config_and_is_reversible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = _controller(tmp_path, monkeypatch)
    source = tmp_path / "roms-source"
    source.mkdir()
    nested = source / "nested"
    nested.mkdir()
    (source / "game.nsp").write_bytes(b"rom-data")
    (nested / "cover.txt").write_bytes(b"metadata")
    destination = tmp_path / "roms-destination"
    destination.mkdir()
    _register_root(controller, source)

    plan = controller.plan_action(
        {"actionId": f"library.root.move:{root_id(source)}", "path": str(destination)}
    )

    assert plan["action"] == f"library.root.move:{root_id(source)}"
    assert "Mover" in str(plan["preview"])
    _apply(controller, plan)

    assert [path for path in source.rglob("*") if path.is_file()] == []
    assert (destination / "game.nsp").read_bytes() == b"rom-data"
    assert (destination / "nested" / "cover.txt").read_bytes() == b"metadata"
    roots_config = json.loads(controller._roots_path.read_text(encoding="utf-8"))  # type: ignore[attr-defined]
    assert str(destination) in roots_config["roots"]
    assert str(source) in roots_config["excludedRoots"]


def test_move_root_stale_source_fails_without_partial_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = _controller(tmp_path, monkeypatch)
    source = tmp_path / "roms-source"
    source.mkdir()
    original = source / "game.nsp"
    original.write_bytes(b"before")
    destination = tmp_path / "roms-destination"
    destination.mkdir()
    _register_root(controller, source)
    plan = controller.plan_action(
        {"actionId": f"library.root.move:{root_id(source)}", "path": str(destination)}
    )
    original.write_bytes(b"changed-after-preview")

    with pytest.raises(SteamZeroError, match="precondição mudou"):
        _apply(controller, plan)

    assert original.read_bytes() == b"changed-after-preview"
    assert not (destination / "game.nsp").exists()


def test_storage_cards_expose_compression_and_uninstall_shortcuts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = _controller(tmp_path, monkeypatch)
    rom = tmp_path / "game.nsp"
    second_rom = tmp_path / "second-game.nsp"
    rom.write_bytes(b"rom")
    second_rom.write_bytes(b"rom-2")
    monkeypatch.setattr(controller._nsz, "status", lambda: {"available": True})  # type: ignore[attr-defined]

    area = controller._area_data(  # type: ignore[attr-defined]
        [
            {
                "installState": "installed",
                "actions": [{"id": "emulator.uninstall:eden", "label": "Desinstalar"}],
            }
        ],
        [
            {
                "id": "switch-1",
                "titleId": "0100ABCDEF123000",
                "name": "Jogo Switch",
                "path": str(rom),
                "platform": "switch",
                "platformId": "switch",
                "state": "ready",
                "statusLabel": "Pronto",
                "mediaSource": "fallback",
                "mediaCandidateCount": 0,
                "mediaErrors": {},
            },
            {
                "id": "switch-2",
                "titleId": "0100ABCDEF123001",
                "name": "Segundo jogo Switch",
                "path": str(second_rom),
                "platform": "switch",
                "platformId": "switch",
                "state": "ready",
                "statusLabel": "Pronto",
                "mediaSource": "fallback",
                "mediaCandidateCount": 0,
                "mediaErrors": {},
            },
        ],
        0,
        [str(tmp_path)],
        [],
        {"validRecords": 0, "missingRecords": [], "state": "ready"},
        False,
        0,
        {"status": "ok", "detail": "Keys validadas", "installed": "rev21"},
        {"status": "unverified", "detail": "Firmware não verificado", "installed": None},
        {
            "state": "unverified",
            "statusLabel": "Nenhum perfil selecionado",
            "active": None,
            "available": [],
        },
    )

    storage_cards = {card["id"]: card for card in area["storage"]["cards"]}
    rom_action = next(
        action
        for action in storage_cards["storage-roms"]["actions"]
        if action["id"] == "nsz.convert"
    )
    assert rom_action["path"] == str(rom)
    batch_action = next(
        action
        for action in storage_cards["storage-roms"]["actions"]
        if action["id"] == "nsz.convert.batch"
    )
    assert batch_action["targetFormat"] == "nsz"
    assert batch_action["paths"] == [str(rom), str(second_rom)]
    management = storage_cards["storage-management"]
    assert management["actions"] == [{"id": "emulator.uninstall:eden", "label": "Desinstalar"}]
