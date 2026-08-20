# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Processo do AURA Launcher.

Monta as seções da home, sobe a ponte e abre a cena.

A biblioteca vem do acervo em disco (``--roms``) ou de um arquivo já resolvido
(``--library``), e o que executar vem do manifesto da plataforma de cada jogo.
São duas responsabilidades distintas com uma fonte só: o catálogo de plataformas
decide emulador, core e argumentos, e o Launcher não guarda alternativa própria.

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
from steamzero.launcher.execution import ExecutionPlan, resolve_execution
from steamzero.launcher.launch import LaunchPlan, consume_context, launch_detached
from steamzero.launcher.library import LibraryGame, scan_library
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


def _lifecycle_status() -> list[Mapping[str, Any]]:
    """Estado dos componentes pela mesma fachada que CLI e dashboard usam.

    Falha de sondagem devolve lista vazia em vez de propagar: o Launcher precisa
    abrir mesmo quando o serviço de componentes não responde, e a página de jogo
    já sabe recusar "Jogar" com motivo.
    """
    from steamzero.adapters.lifecycle import ComponentLifecycle
    from steamzero.adapters.registry import AdapterRegistry
    from steamzero.core.state import StateStore

    try:
        with StateStore() as store:
            store.migrate()
            lifecycle = ComponentLifecycle(store, AdapterRegistry.bundled())
            return list(lifecycle.status_all())
    except OSError as exc:
        # Só falha de I/O é tolerada aqui. Engolir qualquer exceção esconderia
        # um import quebrado atrás de "nenhum emulador instalado", que é uma
        # resposta plausível e falsa — foi o que aconteceu na primeira versão.
        raise RuntimeError(f"estado de componentes indisponível: {exc}") from exc


def installed_emulators(statuses: Sequence[Mapping[str, Any]] | None = None) -> set[str]:
    """Emuladores realmente instalados, pela fachada de lifecycle do projeto.

    A primeira versão disto usava ``shutil.which(adapterId)`` e estava errada
    duas vezes. Os emuladores chegam por Flatpak ou por engine gerenciada, não
    como binário no PATH — e ``dolphin`` no PATH é o gerenciador de arquivos do
    KDE, não o emulador, que se chama ``dolphin-emu``. A busca ingênua daria um
    plano para abrir uma ROM de Wii no navegador de arquivos.

    Consultar o estado real antes de montar o plano é o que permite a página
    recusar "Jogar" com motivo, em vez de abrir algo que não existe.
    """
    if statuses is None:
        statuses = _lifecycle_status()
    installed: set[str] = set()
    for entry in statuses:
        adapter = str(entry.get("id") or entry.get("adapterId") or "")
        state = str(entry.get("state") or entry.get("status") or "")
        if adapter and (entry.get("installed") is True or state == "installed"):
            installed.add(adapter)
    return installed


def _context_path() -> Path:
    return paths.state_home() / "launcher" / "return.json"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, default=None)
    parser.add_argument("--roms", type=Path, default=None)
    parser.add_argument("--context", type=Path, default=None)
    args = parser.parse_args(argv)

    from steamzero.adapters.launcher_process import spawn_detached
    from steamzero.adapters.launcher_ui import LauncherBridge, launch_launcher_ui

    context_path = args.context or _context_path()
    # Um contexto pendente significa que a sessão anterior lançou algo. Consumir
    # aqui evita que um retorno antigo posicione o foco de uma sessão nova.
    consume_context(context_path)

    scanned: tuple[LibraryGame, ...] = ()
    library = _read_library(args.library)
    if not library and args.roms is not None:
        scan = scan_library(args.roms)
        scanned = scan.games
        library = [game.to_dict() for game in scan.games]
    sections = build_sections(library)
    titles = build_titles(library)

    by_id = {game.id: game for game in scanned}

    def on_launch(game_id: str, focus_id: str) -> None:
        """Executa o que o manifesto da plataforma daquele jogo declara.

        A versão anterior montava ``steamzero-launch <id>``, que é o caminho de
        jogos Steam e falharia para qualquer ROM. Cada plataforma traz o próprio
        emulador, core e argumentos, e é o manifesto que decide — um comando
        fixo atenderia uma e quebraria as outras.
        """
        game = by_id.get(game_id)
        if game is None:
            return
        decision = resolve_execution(game, available=installed_emulators())
        if not isinstance(decision, ExecutionPlan):
            # Recusa com motivo já resolvida; a página de jogo mostra o texto e
            # não oferece "Jogar" que falharia depois.
            return
        plan = LaunchPlan(
            game_id=game_id,
            argv=decision.argv,
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
