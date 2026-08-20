# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Processo do AURA Launcher.

Monta as seções da home, sobe a ponte e abre a cena.

Biblioteca e lançamento vêm inteiros do ``EmulationController``: ele descobre os
roots do acervo, classifica base/update/DLC, aplica o emulador padrão com
fallback para o primary instalado, exige as chaves projetadas no Switch, monta o
argv pela fonte fixada no manifesto e registra a sessão. O Launcher não repete
nenhuma dessas decisões — repeti-las já produziu, nesta mesma frente, um caminho
que teria lançado um update sem chaves e chamado isso de sucesso.

Porta consumida: ``EmulationPort``. O que é do Launcher e não existia antes: o
foco da home, a página de jogo e o contexto de retorno.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from steamzero.adapters.launcher_catalog import CatalogGame, EmulationPort, catalog_games
from steamzero.core import paths
from steamzero.launcher.launch import remember_return, restore_return
from steamzero.launcher.navigation import HomeSection

#: Nome de exibição por plataforma. Sem isto a home mostraria `nes-famicom`, que
#: é identificador e não o jeito como o sistema é conhecido.
_PLATFORM_TITLES = {
    "switch": "Nintendo Switch",
    "nintendo-handheld": "Game Boy / GBA",
    "nintendo-3ds": "Nintendo 3DS",
    "nintendo-console": "Wii / GameCube",
    "nes-famicom": "NES / Famicom",
    "mega-drive": "Mega Drive",
    "master-system": "Master System",
    "game-gear": "Game Gear",
    "dreamcast": "Dreamcast",
    "playstation": "PlayStation",
    "arcade": "Arcade",
    "snes": "Super Nintendo",
}


def platform_title(platform: str) -> str:
    return _PLATFORM_TITLES.get(platform, platform)


def build_sections(games: Sequence[CatalogGame]) -> tuple[HomeSection, ...]:
    """Agrupa por plataforma, preservando a ordem em que a biblioteca chegou.

    Item com id fora do formato aceito pelo foco é descartado sozinho: um
    registro estranho não pode esvaziar a home inteira.
    """
    grouped: dict[str, list[str]] = {}
    for game in games:
        try:
            HomeSection(id=game.platform, title=platform_title(game.platform), items=(game.id,))
        except ValueError:
            continue
        grouped.setdefault(game.platform, []).append(game.id)
    return tuple(
        HomeSection(id=name, title=platform_title(name), items=tuple(items))
        for name, items in grouped.items()
    )


def build_titles(games: Sequence[CatalogGame]) -> dict[str, str]:
    """Mapa id -> título. O foco trabalha com ids; o título viaja à parte."""
    return {game.id: game.title for game in games}


def _context_path() -> Path:
    return paths.state_home() / "launcher" / "return.json"


def _controller() -> EmulationPort:
    from steamzero.adapters.emulation import EmulationController
    from steamzero.adapters.registry import AdapterRegistry
    from steamzero.core.state import StateStore

    controller = EmulationController(
        store_factory=StateStore,
        registry_factory=AdapterRegistry.bundled,
    )
    return controller  # type: ignore[return-value]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", type=Path, default=None)
    args = parser.parse_args(argv)

    from steamzero.adapters.launcher_ui import LauncherBridge, launch_launcher_ui

    context_path = args.context or _context_path()
    # Contexto pendente significa que a sessão anterior lançou algo; consumir
    # aqui evita que um retorno antigo posicione o foco de uma sessão nova.
    restore_return(context_path)

    emulation = _controller()
    games = catalog_games(emulation.library())

    def on_launch(game_id: str, focus_id: str) -> None:
        """Grava o lugar de saída e devolve o pedido para a emulação.

        A ordem importa: gravar depois abriria uma janela em que o jogo já roda
        e o lugar do usuário ainda não foi salvo. Recusa do controller — chaves
        ausentes, conteúdo não-base, emulador indisponível — sobe como está,
        porque é ela que a página tem de mostrar.
        """
        remember_return(context_path, game_id=game_id, focus_id=focus_id)
        emulation.launch_game(game_id)

    bridge = LauncherBridge(
        sections=build_sections(games),
        titles=build_titles(games),
        context_path=context_path,
        on_launch=on_launch,
    )
    return launch_launcher_ui(bridge)


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
