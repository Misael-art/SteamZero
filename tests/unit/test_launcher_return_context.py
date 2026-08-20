# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contexto de retorno: o que o Launcher acrescenta ao que já existe."""

from __future__ import annotations

from pathlib import Path

from steamzero.launcher.launch import remember_return, restore_return


def test_the_context_survives_between_processes(tmp_path: Path) -> None:
    """O launcher pode reiniciar sem derrubar o jogo; o lugar tem de sobreviver."""
    path = tmp_path / "return.json"
    remember_return(path, game_id="0fd1b795", focus_id="switch:0fd1b795")
    restored = restore_return(path)
    assert restored is not None
    assert restored["focusId"] == "switch:0fd1b795"


def test_it_is_consumed_once(tmp_path: Path) -> None:
    path = tmp_path / "return.json"
    remember_return(path, game_id="0fd1b795", focus_id="switch:0fd1b795")
    assert restore_return(path) is not None
    # Um retorno já usado não pode reposicionar o foco de uma sessão nova.
    assert restore_return(path) is None


def test_absence_is_normal_and_corruption_is_not_guessed(tmp_path: Path) -> None:
    assert restore_return(tmp_path / "nunca-existiu.json") is None
    truncated = tmp_path / "meio.json"
    truncated.write_text("{ isso não é json", encoding="utf-8")
    assert restore_return(truncated) is None
    wrong = tmp_path / "outro.json"
    wrong.write_text('{"focusId": 123}', encoding="utf-8")
    assert restore_return(wrong) is None


def test_the_project_game_id_fits_the_focus_format(tmp_path: Path) -> None:
    """Os ids da biblioteca são hashes; o foco precisa aceitá-los como estão."""
    path = tmp_path / "return.json"
    remember_return(
        path, game_id="0fd1b7954e6eaf474f5e8c8c", focus_id="switch:0fd1b7954e6eaf474f5e8c8c"
    )
    assert restore_return(path) is not None
