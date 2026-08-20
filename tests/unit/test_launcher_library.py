# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato da biblioteca do AURA Launcher sobre um acervo real de ROMs."""

from __future__ import annotations

from pathlib import Path

from steamzero.launcher.library import (
    DIAG_PLATFORM_UNKNOWN,
    game_id_for,
    scan_library,
)


def _acervo(tmp_path: Path) -> Path:
    root = tmp_path / "roms"
    (root / "switch").mkdir(parents=True)
    (root / "gb").mkdir()
    (root / "sistemainventado").mkdir()
    # Arquivos de estrutura que o ES-DE deixa em cada pasta. Não são jogos.
    for name in (".directory", "metadata.txt", "systeminfo.txt"):
        (root / "gb" / name).write_text("x", encoding="utf-8")
    (root / "switch" / "Hollow Knight Silksong [010013C00E930000][v0].nsp").write_bytes(b"x")
    (root / "gb" / "Tetris (World).gb").write_bytes(b"x")
    (root / "sistemainventado" / "algo.bin").write_bytes(b"x")
    return root


def test_metadata_files_never_become_games(tmp_path: Path) -> None:
    """Sem este filtro a home listaria `systeminfo.txt` como se fosse um jogo."""
    result = scan_library(_acervo(tmp_path))
    titles = {game.title for game in result.games}
    assert "systeminfo" not in titles
    assert "metadata" not in titles
    assert not any(game.title.endswith(".txt") for game in result.games)


def test_real_roms_are_found_with_readable_titles(tmp_path: Path) -> None:
    result = scan_library(_acervo(tmp_path))
    titles = {game.title for game in result.games}
    # O título perde os marcadores técnicos do nome do arquivo.
    assert "Hollow Knight Silksong" in titles
    assert "Tetris" in titles


def test_an_unknown_system_is_reported_not_silently_dropped(tmp_path: Path) -> None:
    """34 sistemas no disco e 6 reconhecidos: a diferença precisa ser visível."""
    result = scan_library(_acervo(tmp_path))
    assert any(
        item.code == DIAG_PLATFORM_UNKNOWN and "sistemainventado" in item.reason
        for item in result.diagnostics
    )


def test_game_ids_are_stable_and_safe_for_focus_nodes(tmp_path: Path) -> None:
    """O id vira nó de foco e argumento de lançamento; precisa ser previsível."""
    first = game_id_for("switch", "Hollow Knight Silksong [010013C00E930000][v0].nsp")
    again = game_id_for("switch", "Hollow Knight Silksong [010013C00E930000][v0].nsp")
    assert first == again
    assert first.replace("-", "").isalnum()
    assert first[0].isalpha()
    # Nomes diferentes não podem colidir num mesmo id.
    other = game_id_for("switch", "Hollow Knight [0100000000000000][v0].nsp")
    assert other != first


def test_an_empty_root_is_not_an_error(tmp_path: Path) -> None:
    empty = tmp_path / "vazio"
    empty.mkdir()
    result = scan_library(empty)
    assert result.games == ()
    assert not any(item.code != DIAG_PLATFORM_UNKNOWN for item in result.diagnostics)


def test_a_missing_root_degrades_instead_of_raising(tmp_path: Path) -> None:
    result = scan_library(tmp_path / "nao-existe")
    assert result.games == ()
    assert result.diagnostics
