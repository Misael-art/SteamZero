# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Processo do AURA Launcher.

Monta as seções da home, sobe a ponte e abre a cena. A biblioteca vem da fonte
canônica do projeto (``emulation-library-cache-v1.json``), achada sozinha
quando ninguém passou ``--library``; o argumento continua valendo para apontar
outro arquivo. O lançamento de cada jogo é delegado à rota de produto
``emulation launch --game-id``, que resolve emulador, chaves e sessão.

Sem biblioteca, o Launcher **abre assim mesmo**, com a home vazia acionável que
o domínio já resolve. Primeira execução sem acervo é o caso comum, não erro.
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from steamzero.adapters.launcher_catalog import CatalogGame, catalog_games
from steamzero.core import paths
from steamzero.launcher.launch import LaunchPlan, Spawn, consume_context, launch_detached
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

    A biblioteca canônica publica o rótulo em ``name``; ``title`` é aceito como
    alias porque outras fontes o usam. Ler só ``title`` fazia o fallback para o
    id disparar em TODO o acervo real, e a home do Launcher exibia
    ``ae18c7e53583298461a0edea`` no lugar de ``1969 (Homebrew) (SMS)`` —
    observado na release 2.0.0rc1-720928250e1a com os 80 jogos do host.
    """
    titles: dict[str, str] = {}
    for game in games:
        identifier = str(game.get("id", ""))
        if identifier:
            label = game.get("name") or game.get("title")
            titles[identifier] = str(label or identifier)
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


def canonical_library_path() -> Path:
    """Onde a varredura publica a biblioteca canônica."""
    return paths.data_home() / "emulation-library-cache-v1.json"


def _read_library(path: Path | None) -> list[Mapping[str, Any]]:
    """Lê o acervo, achando-o sozinho quando ninguém disse onde está.

    Quem abre o Launcher pelo entry point não passa ``--library``, e sem isso a
    home abria vazia mesmo com a biblioteca canônica cheia. O argumento continua
    valendo para apontar outro arquivo; a ausência dele deixou de significar
    "sem acervo".

    Aceita as duas formas: a lista crua que o argumento sempre aceitou, e o
    envelope ``{"games": [...]}`` que a varredura publica. Sem isso, apontar
    ``--library`` para a propria biblioteca canônica devolvia vazio.
    """
    source = path if path is not None else canonical_library_path()
    if not source.is_file():
        return []
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(payload, Mapping):
        payload = payload.get("games")
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, Mapping)]


def _context_path() -> Path:
    return paths.state_home() / "launcher" / "return.json"


class LaunchRouter:
    """Decide a rota de lançamento de cada jogo e delega o spawn ao adapter.

    A home do Launcher é da biblioteca canônica de emulação, então cada item é
    lançado pela rota de produto ``emulation launch --game-id``. A rota por tipo
    de jogo é uma discriminação futura (Steam AppID → wrapper Steam), feita aqui
    pelo ``kind`` do registro — nunca pela mesma chamada genérica.
    """

    def __init__(
        self,
        *,
        on_spawn: Spawn,
        context_path: Path,
        executable: Callable[[], str] | None = None,
    ) -> None:
        self._spawn = on_spawn
        self._context_path = Path(context_path)
        self._executable = executable or _steamzero_executable

    def launch(self, game_id: str, focus_id: str = "") -> None:
        # O antigo `steamzero-launch <game_id>` era o wrapper de jogo Steam
        # (`--appid APPID -- %command%`) e não existe como binário publicado;
        # passava o id canônico de emulação a um comando cujo contrato é outro.
        executable = self._executable()
        argv = (executable, "emulation", "launch", "--game-id", game_id)
        plan = LaunchPlan(
            game_id=game_id,
            argv=argv,
            focus_id=focus_id or f"{_DEFAULT_SECTION}:{game_id}",
            context_path=self._context_path,
        )
        launch_detached(plan, spawn=self._spawn)


def _steamzero_executable() -> str:
    """Caminho absoluto do `steamzero` para lançar o jogo desacoplado.

    O processo nasce em sessão própria (`start_new_session`) e pode não herdar
    o PATH do launcher. ``shutil.which`` resolve o binário publicado; a falha
    em encontrá-lo é uma falha de integração (o instalador publica
    ``/usr/local/bin/steamzero``) e aparece como erro do spawn, que o
    ``launch_detached`` converte em contexto limpo + exceção — nunca sucesso
    vazio.
    """
    resolved = None
    for candidate in ("/usr/local/bin/steamzero", "/usr/bin/steamzero", "steamzero"):
        path = candidate if "/" in candidate else shutil.which(candidate)
        if not path or not Path(path).is_file():
            continue
        resolved = str(Path(path).resolve())
        break
    if resolved is None:
        raise OSError("steamzero CLI não encontrado no PATH do launcher")
    return resolved


def _sections_from_catalog(catalog: Sequence[CatalogGame]) -> tuple[HomeSection, ...]:
    """Agrupa a home por plataforma, preservando a primeira ordem de chegada.

    A home fullscreen agrupa por sistema: sem isso uma seção única com o acervo
    inteiro tornaria a navegação por controle impraticável. Um jogo cuja
    plataforma não tem seção conhecida cai em ``outros``.
    """
    grouped: dict[str, list[str]] = {}
    for game in catalog:
        section = game.platform or "outros"
        try:
            HomeSection(id=section, title=section, items=(game.id,))
        except ValueError:
            section = "outros"
            HomeSection(id=section, title=section, items=(game.id,))
        grouped.setdefault(section, []).append(game.id)
    return tuple(
        HomeSection(id=name, title=_SECTION_TITLES.get(name, name), items=tuple(items))
        for name, items in grouped.items()
    )


def _sections_from_collections(catalog: Sequence[CatalogGame]) -> tuple[HomeSection, ...]:
    """Adiciona uma seção por coleção persistida, com os membros jogáveis.

    Usa o `CollectionManager` do domínio para resolver as regras (tag/favorite)
    — o Launcher não reimplementa a lógica de coleção. Só entram coleções com
    pelo menos um membro presente no acervo; uma coleção vazia não viraria
    uma seção sem jogos na home.
    """
    from steamzero.domain.collections import CollectionManager

    # O gameRef da coleção usa o prefixo `emulation:` (contrato do domínio);
    # o id do Launcher é o id canônico da biblioteca sem o prefixo.
    games = [{"gameRef": f"emulation:{game.id}"} for game in catalog]
    try:
        state = CollectionManager().state(games)
    except Exception:
        return ()
    sections: list[HomeSection] = []
    for collection in state.get("collections", []):
        title = str(collection.get("name") or "")
        members = tuple(
            str(member).removeprefix("emulation:")
            for member in collection.get("members", [])
            if str(member).startswith("emulation:")
        )
        if not title or not members:
            continue
        try:
            sections.append(
                HomeSection(
                    id=f"collection-{collection.get('id', '')}",
                    title=title,
                    items=members,
                )
            )
        except ValueError:
            continue
    return tuple(sections)


def _host_accessibility() -> dict[str, Any]:
    """Herda as preferências de acessibilidade do host (sem mutar nada).

    Usa as MESMAS probes do dashboard desktop, para que o Launcher respeite o
    alto contraste e a redução de movimento que o usuário já configurou no
    Plasma. Em ambiente sem `kreadconfig6` (ex.: sessão sem Plasma) degrada
    para os padrões — nunca quebra o lançamento.
    """
    from steamzero.adapters.desktop_kde import high_contrast_enabled, reduced_motion_enabled

    return {
        "highContrast": high_contrast_enabled(),
        "reducedMotion": reduced_motion_enabled(),
        "visualScale": 1.0,
    }


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
    catalog = catalog_games(library)
    sections = _sections_from_catalog(catalog) + _sections_from_collections(catalog)
    titles = {game.id: game.title for game in catalog}
    covers = {game.id: game.cover_url for game in catalog if game.cover_url}

    router = LaunchRouter(on_spawn=spawn_detached, context_path=context_path)

    accessibility = _host_accessibility()

    bridge = LauncherBridge(
        sections=sections,
        titles=titles,
        covers=covers,
        context_path=context_path,
        on_launch=router.launch,
        accessibility=accessibility,
    )
    return launch_launcher_ui(bridge)


if __name__ == "__main__":  # pragma: no cover - entry point
    raise SystemExit(main())
