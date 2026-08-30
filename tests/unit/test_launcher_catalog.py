# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Tradução biblioteca canônica -> home do AURA Launcher.

O catálogo que a home mostra deve ser o conteúdo BASE, com o rótulo exibível
correto (``name``, nunca o id) e agrupado por plataforma. Um algoritmo que
perde essas três coisas devolve uma home que abre, mas que não serve.
"""

from __future__ import annotations

from steamzero.adapters.launcher_catalog import catalog_games


def test_base_games_are_listed_with_the_canonical_label() -> None:
    games = catalog_games(
        [
            {"id": "a1", "name": "1969 (Homebrew) (SMS)", "platform": "master-system"},
            {"id": "b2", "name": "Ridge Racer", "platform": "playstation"},
        ]
    )
    assert [g.title for g in games] == ["1969 (Homebrew) (SMS)", "Ridge Racer"]
    assert [g.platform for g in games] == ["master-system", "playstation"]


def test_update_and_dlc_are_excluded() -> None:
    """Update/DLC são conteúdo real, mas `launch_game` os recusa: oferecê-los
    produziria um erro que o usuário não teria como prever olhando a tela."""
    games = catalog_games(
        [
            {"id": "base", "name": "Base", "contentKind": "base", "platform": "switch"},
            {"id": "upd", "name": "Update", "contentKind": "update", "platform": "switch"},
            {"id": "dlc", "name": "DLC", "contentKind": "dlc", "platform": "switch"},
        ]
    )
    assert [g.id for g in games] == ["base"]


def test_title_fallback_never_shows_the_identifier() -> None:
    """A biblioteca canônica publica o rótulo em `name`; o fallback para o id
    fazia a home exibir `ae18c7e53583298461a0edea` no lugar de um título."""
    games = catalog_games([{"id": "ae18c7e53583298461a0edea", "name": "1969 (Homebrew) (SMS)"}])
    assert games[0].title == "1969 (Homebrew) (SMS)"


def test_a_broken_record_does_not_clear_the_home() -> None:
    """Um registro corrompido (sem id ou sem rótulo) é descartado; os demais
    permanecem — a home não pode esvaziar por causa de uma entrada ruim."""
    games = catalog_games(
        [
            {"id": "", "name": "sem id"},
            {"id": "ok", "name": "Válido", "platform": "snes"},
            {"id": "sem-nome"},
        ]
    )
    assert [g.id for g in games] == ["ok"]


def test_platform_is_derived_for_switch_formats() -> None:
    """Formato de ROM Switch sem `platform` mapeia para `switch`; formato
    desconhecido cai na extensão normalizada."""
    games = catalog_games(
        [
            {"id": "nsp", "name": "NSP", "format": "NSP"},
            {"id": "gb", "name": "GB", "format": "gb"},
        ]
    )
    assert [g.platform for g in games] == ["switch", "gb"]
