# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Processo do AURA Launcher.

Monta as seções da home, sobe a ponte e abre a cena. A fonte da biblioteca é
injetada: hoje vem de um arquivo passado por ``--library``, porque a varredura
real do acervo roda por jobs assíncronos e ligá-la aqui seria integração de
fachada.

Sem biblioteca, o Launcher **abre assim mesmo**, com a home vazia acionável que
o domínio já resolve. Primeira execução sem acervo é o caso comum, não erro.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from steamzero.core import paths
from steamzero.launcher.launch import LaunchPlan, consume_context, launch_detached
from steamzero.launcher.navigation import HomeSection

_DEFAULT_SECTION = "library"
_SECTION_TITLES = {
    "continue": "Continuar",
    "library": "Biblioteca",
    "collections": "Coleções",
}


def build_titles(games: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Mapa id -> título exibível.

    O domínio de foco trabalha só com ids; o título viaja à parte para a home
    não acabar mostrando `celeste` onde o usuário espera `Celeste`.
    """
    titles: dict[str, str] = {}
    for game in games:
        identifier = str(game.get("id", ""))
        if identifier:
            titles[identifier] = str(game.get("title") or identifier)
    return titles


def build_sections(games: Sequence[Mapping[str, Any]]) -> tuple[HomeSection, ...]:
    """Agrupa jogos em seções, preservando a ordem de chegada.

    Jogo sem id utilizável é descartado com o resto intacto: um registro
    corrompido na biblioteca não pode esvaziar a home inteira.
    """
    grouped: dict[str, list[str]] = {}
    for game in games:
        identifier = str(game.get("id", ""))
        section = str(game.get("section", _DEFAULT_SECTION)) or _DEFAULT_SECTION
        try:
            HomeSection(
                id=section,
                title=_SECTION_TITLES.get(section, section),
                items=(identifier,),
            )
        except ValueError:
            continue
        grouped.setdefault(section, []).append(identifier)
    return tuple(
        HomeSection(id=name, title=_SECTION_TITLES.get(name, name), items=tuple(items))
        for name, items in grouped.items()
    )


def _read_library(path: Path | None) -> list[Mapping[str, Any]]:
    if path is None or not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, Mapping)]


def _context_path() -> Path:
    return paths.state_home() / "launcher" / "return.json"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, default=None)
    parser.add_argument("--context", type=Path, default=None)
    args = parser.parse_args(argv)

    from steamzero.adapters.launcher_process import spawn_detached
    from steamzero.adapters.launcher_ui import LauncherBridge, launch_launcher_ui

    context_path = args.context or _context_path()
    # Um contexto pendente significa que a sessão anterior lançou algo. Consumir
    # aqui evita que um retorno antigo posicione o foco de uma sessão nova.
    consume_context(context_path)

    library = _read_library(args.library)
    sections = build_sections(library)
    titles = build_titles(library)

    def on_launch(game_id: str, focus_id: str) -> None:
        plan = LaunchPlan(
            game_id=game_id,
            argv=("steamzero-launch", game_id),
            focus_id=focus_id or f"{_DEFAULT_SECTION}:{game_id}",
            context_path=context_path,
        )
        launch_detached(plan, spawn=spawn_detached)

    bridge = LauncherBridge(
        sections=sections,
        titles=titles,
        context_path=context_path,
        on_launch=on_launch,
    )
    return launch_launcher_ui(bridge)


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
