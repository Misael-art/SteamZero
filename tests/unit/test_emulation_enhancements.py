# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Costura (Onda 6): ações de melhoria e aplicação pré-argv no controlador."""

from __future__ import annotations

from pathlib import Path

import pytest

import steamzero.adapters.emulation as emulation_mod
from steamzero.adapters.emulation import EmulationController
from steamzero.adapters.enhancements.installer import EnhancementTarget
from steamzero.adapters.enhancements.renderers import ENHANCEMENT_MARKER
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain.game_enhancements import EnhancementKind
from steamzero.domain.launch_profile import parse_launch


def _controller(monkeypatch, tmp_path: Path) -> EmulationController:  # type: ignore[no-untyped-def]
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    return EmulationController(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        which=lambda _command: None,
        spawn=lambda _argv: None,
        secret_store=emulation_mod.SessionSecretStore(),
    )


def _apply(controller: EmulationController, plan: dict[str, object]) -> dict[str, object]:
    return controller.apply_action(str(plan["planId"]), str(plan["confirmToken"]))


def _stub_duckstation_target(monkeypatch, tmp_path: Path, *, supplied=()) -> None:
    target = EnhancementTarget(
        emulator_id="duckstation",
        target_dir=tmp_path / "home" / ".config" / "duckstation",
        formats=("cemu-rules", "duckstation-ini"),
        supplied=frozenset(supplied),
    )
    monkeypatch.setattr(
        emulation_mod,
        "resolve_enhancement_target",
        lambda raw_manifest, **_kwargs: (
            target
            if isinstance(raw_manifest, dict) and raw_manifest.get("id") == "duckstation"
            else None
        ),
    )


def _seed_switch_game(controller: EmulationController, tmp_path: Path) -> dict[str, object]:
    roms = tmp_path / "owned-roms"
    roms.mkdir()
    rom = roms / "Example [0100ABCDEF123000].nsp"
    rom.write_bytes(b"owned-game")
    _apply(
        controller,
        controller.plan_action({"actionId": "library.root.add", "path": str(roms)}),
    )
    games, _unidentified = controller._load_library_cache()  # type: ignore[attr-defined]
    if not games:
        raise AssertionError("jogo Switch não foi inventariado")
    return games[0]


def _launch_ready(monkeypatch, controller: EmulationController, tmp_path: Path) -> None:
    monkeypatch.setattr(controller, "_require_launchable_emulator", lambda _id: None)
    monkeypatch.setattr(controller, "_require_key_projection", lambda _id: None)
    monkeypatch.setattr(
        controller,
        "_launch_profile_for",
        lambda _platform_id, adapter_id: parse_launch(
            "switch", adapter_id, {"gameArgs": ["{rom}"]}
        ),
    )
    monkeypatch.setattr(
        "steamzero.adapters.emulation.AdapterEngine.payload_path",
        lambda _self, emulator_id: tmp_path / f"{emulator_id}.AppImage",
    )


def test_enhancement_seam_applies_before_argv_idempotent_and_managed(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    assert ENHANCEMENT_MARKER.startswith("# SteamZero-Boot-Managed")
    controller = _controller(monkeypatch, tmp_path)
    _stub_duckstation_target(monkeypatch, tmp_path)
    game = _seed_switch_game(controller, tmp_path)
    game_id = str(game["id"])
    _apply(
        controller,
        controller.plan_action(
            {"actionId": "game.emulator.set", "gameId": game_id, "emulatorId": "duckstation"}
        ),
    )
    _apply(
        controller,
        controller.plan_action(
            {
                "actionId": f"game.enhancements.set:{game_id}",
                "emulatorId": "duckstation",
                "kind": "cheat",
                "category": "performance",
                "title": "60 FPS",
                "source": "forum",
                "codes": ["0x12345678 00000000"],
            }
        ),
    )
    [definition] = controller._load_game_settings(strict=True)[game_id][  # type: ignore[attr-defined]
        "enhancements"
    ]
    assert definition["title"] == "60 FPS"

    _launch_ready(monkeypatch, controller, tmp_path)
    launched: list[tuple[str, ...]] = []
    controller._spawn = lambda argv: launched.append(tuple(argv))  # type: ignore[attr-defined]
    first = controller.launch_game(game_id)
    assert first["status"] == "started"
    assert first["enhancementsTried"] == 1
    assert first["enhancementsApplied"] == 1
    assert first["enhancementsSkipped"] == []
    rules = tmp_path / "home" / ".config" / "duckstation" / "rules.txt"
    content = rules.read_text(encoding="ascii")
    assert content.startswith(ENHANCEMENT_MARKER)
    assert "0100ABCDEF123000" in content
    assert "0x12345678 00000000" in content

    second = controller.launch_game(game_id)
    assert second["enhancementsApplied"] == 1
    assert second["enhancementsSkipped"] == []
    assert rules.read_text(encoding="ascii") == content


def test_enhancement_launch_degrades_on_render_failure(monkeypatch, tmp_path: Path) -> None:
    controller = _controller(monkeypatch, tmp_path)
    _stub_duckstation_target(monkeypatch, tmp_path)
    game = _seed_switch_game(controller, tmp_path)
    game_id = str(game["id"])
    _apply(
        controller,
        controller.plan_action(
            {"actionId": "game.emulator.set", "gameId": game_id, "emulatorId": "duckstation"}
        ),
    )
    _apply(
        controller,
        controller.plan_action(
            {
                "actionId": f"game.enhancements.set:{game_id}",
                "emulatorId": "duckstation",
                "kind": "cheat",
                "category": "graphics",
                "title": "Widescreen",
                "source": "forum",
                "codes": ["0x12345678 00000000"],
            }
        ),
    )
    import steamzero.adapters.enhancements.installer as installer_mod

    def boom(*_args, **_kwargs):
        raise SteamZeroError("E-ENHANCEMENT-DENIED", detail="renderer indisponível")

    monkeypatch.setattr(installer_mod, "render_file", boom)
    _launch_ready(monkeypatch, controller, tmp_path)
    controller._spawn = lambda _argv: 4242  # type: ignore[attr-defined]
    result = controller.launch_game(game_id)
    assert result["status"] == "started"
    assert result["enhancementsApplied"] == 0
    assert (
        result["enhancementsSkipped"][0]["reason"] == "E-ENHANCEMENT-DENIED: renderer indisponível"
    )
    assert not (tmp_path / "home" / ".config" / "duckstation" / "rules.txt").exists()


def test_enhancement_set_denies_gameplay_category_and_unmanaged_emulator(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    _stub_duckstation_target(monkeypatch, tmp_path)
    game = _seed_switch_game(controller, tmp_path)
    game_id = str(game["id"])
    _apply(
        controller,
        controller.plan_action(
            {"actionId": "game.emulator.set", "gameId": game_id, "emulatorId": "duckstation"}
        ),
    )
    with pytest.raises(SteamZeroError, match="E-ENHANCEMENT-DENIED"):
        controller.plan_action(
            {
                "actionId": f"game.enhancements.set:{game_id}",
                "emulatorId": "duckstation",
                "kind": "cheat",
                "category": "gameplay",
                "title": "Infinitas vidas",
                "source": "forum",
                "codes": ["0x12345678 00000000"],
            }
        )
    with pytest.raises(SteamZeroError, match="não declara suporte"):
        controller.plan_action(
            {
                "actionId": f"game.enhancements.set:{game_id}",
                "emulatorId": "ryubing",
                "kind": "cheat",
                "category": "performance",
                "title": "60 FPS",
                "source": "forum",
                "codes": ["0x12345678 00000000"],
            }
        )


def test_enhancement_launch_never_touches_foreign_file_and_clear_removes(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    _stub_duckstation_target(monkeypatch, tmp_path)
    game = _seed_switch_game(controller, tmp_path)
    game_id = str(game["id"])
    _apply(
        controller,
        controller.plan_action(
            {"actionId": "game.emulator.set", "gameId": game_id, "emulatorId": "duckstation"}
        ),
    )
    _apply(
        controller,
        controller.plan_action(
            {
                "actionId": f"game.enhancements.set:{game_id}",
                "emulatorId": "duckstation",
                "kind": "cheat",
                "category": "display-only",
                "title": "Widescreen",
                "source": "forum",
                "codes": ["0x12345678 00000000"],
            }
        ),
    )
    rules = tmp_path / "home" / ".config" / "duckstation" / "rules.txt"
    rules.parent.mkdir(parents=True)
    rules.write_text("# feito a mao pelo usuario\n", encoding="ascii")
    _launch_ready(monkeypatch, controller, tmp_path)
    controller._spawn = lambda _argv: 4242  # type: ignore[attr-defined]
    result = controller.launch_game(game_id)
    assert result["status"] == "started"
    assert result["enhancementsApplied"] == 0
    assert result["enhancementsSkipped"][0]["reason"].startswith("arquivo sem marcador")
    assert rules.read_text(encoding="ascii") == "# feito a mao pelo usuario\n"

    _apply(
        controller,
        controller.plan_action(
            {"actionId": f"game.enhancements.clear:{game_id}", "title": "Widescreen"}
        ),
    )
    after = controller.launch_game(game_id)
    assert after["enhancementsTried"] == 0
    assert after["enhancementsApplied"] == 0


def test_enhancement_emulator_supplied_role_is_never_written_by_steamzero(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    _stub_duckstation_target(monkeypatch, tmp_path, supplied=(EnhancementKind.CHEAT,))
    game = _seed_switch_game(controller, tmp_path)
    game_id = str(game["id"])
    _apply(
        controller,
        controller.plan_action(
            {"actionId": "game.emulator.set", "gameId": game_id, "emulatorId": "duckstation"}
        ),
    )
    with pytest.raises(SteamZeroError, match="é dono do arquivo"):
        controller.plan_action(
            {
                "actionId": f"game.enhancements.set:{game_id}",
                "emulatorId": "duckstation",
                "kind": "cheat",
                "category": "performance",
                "title": "60 FPS",
                "source": "forum",
                "codes": ["0x12345678 00000000"],
            }
        )


def test_settings_reject_unknown_enhancement_fields_with_integrity_error(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    controller = _controller(monkeypatch, tmp_path)
    _stub_duckstation_target(monkeypatch, tmp_path)
    game = _seed_switch_game(controller, tmp_path)
    game_id = str(game["id"])
    import json

    controller._game_settings_path.write_text(  # type: ignore[attr-defined]
        json.dumps(
            {"schemaVersion": 1, "games": {game_id: {"enhancements": [{"evil": True}]}}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(SteamZeroError, match="E-STATE-INTEGRITY"):
        controller.launch_game(game_id)
