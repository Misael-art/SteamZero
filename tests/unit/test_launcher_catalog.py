# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""O Launcher consome a biblioteca da emulação, sem catálogo próprio."""

from __future__ import annotations

from steamzero.adapters.launcher_catalog import catalog_games


def _library() -> dict[str, object]:
    return {
        "games": [
            {
                "id": "0fd1b7954e6eaf474f5e8c8c",
                "name": "Demon Slayer",
                "format": "nsp",
                "contentKind": "base",
                "emulatorId": "eden",
                "identityVerified": True,
            },
            {
                "id": "aaaa1111",
                "name": "Demon Slayer (update)",
                "format": "nsp",
                "contentKind": "update",
                "emulatorId": "eden",
            },
            {
                "id": "bbbb2222",
                "name": "Sem emulador",
                "format": "nsp",
                "contentKind": "base",
                "emulatorId": None,
            },
        ]
    }


def test_the_project_ids_are_preserved_so_launch_can_find_the_game() -> None:
    """Id próprio quebraria `launch_game`, que resolve pelo id da biblioteca."""
    games = catalog_games(_library())
    assert any(game.id == "0fd1b7954e6eaf474f5e8c8c" for game in games)


def test_updates_and_dlc_never_appear_as_playable_items() -> None:
    """Um `.nsp` de update não é jogo; o adapter recusaria depois do clique."""
    titles = {game.title for game in catalog_games(_library())}
    assert "Demon Slayer" in titles
    assert "Demon Slayer (update)" not in titles


def test_playability_is_not_decided_here() -> None:
    """Ler `emulatorId` do registro daria "não jogável" para jogo que roda.

    O controller combina ajuste por jogo, `defaultEmulatorId` global e o
    fallback para o primary instalado. Um jogo com `emulatorId: null` continua
    lançável, e decidir o contrário aqui divergiria de quem realmente sabe.
    """
    games = catalog_games(_library())
    listed = next(game for game in games if game.id == "bbbb2222")
    assert listed.title == "Sem emulador"
    assert not hasattr(listed, "playable")


def test_platform_falls_back_to_the_format_instead_of_one_big_section() -> None:
    games = catalog_games(_library())
    assert all(game.platform == "switch" for game in games)


def test_a_malformed_library_does_not_empty_the_home() -> None:
    assert catalog_games({}) == ()
    assert catalog_games({"games": "nada"}) == ()
    partial = catalog_games({"games": [{"id": "x"}, {"name": "y"}, {"id": "z", "name": "Z"}]})
    assert [game.title for game in partial] == ["Z"]
