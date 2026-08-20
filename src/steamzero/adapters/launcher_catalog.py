# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Tradução entre a emulação do projeto e a home do AURA Launcher.

O Launcher **não** tem catálogo, resolução de executor nem regra de jogabilidade
própria. Ele pergunta ao ``EmulationController`` e devolve o pedido para ele.

Porta consumida: ``EmulationPort`` (``library`` e ``launch_game``).
Contrato publicado: ``CatalogGame``, com o id do projeto preservado.

A primeira versão desta frente tinha caminho próprio e cada peça perdia algo que
estava acoplado: ``scan_library`` classifica base/update/DLC e ignora
auxiliares; ``launch_profile`` monta argv com a ROM atômica e o core como
propriedade da plataforma; ``_settings_for_game_with_global`` aplica o emulador
padrão e ``_resolve_primary_emulator`` já cai no primary instalado quando nada
foi configurado; ``launch_game`` exige chaves projetadas no Switch e registra a
sessão. Decidir qualquer uma dessas coisas aqui reintroduz a divergência.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol


class EmulationPort(Protocol):
    """Superfície mínima da emulação que o Launcher consome."""

    def library(self) -> Mapping[str, Any]: ...

    def launch_game(self, game_id: str) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class CatalogGame:
    """Item da home. O ``id`` é o da biblioteca do projeto, não um id local.

    Um id próprio quebraria ``launch_game``, que resolve o jogo por esse valor.
    """

    id: str
    title: str
    platform: str

    def to_dict(self) -> dict[str, Any]:
        # A seção é a plataforma: a home agrupa por sistema porque é assim que
        # se procura um jogo, e uma seção única com o acervo inteiro tornaria a
        # navegação por controle impraticável.
        return {
            "id": self.id,
            "title": self.title,
            "section": self.platform,
            "system": self.platform,
        }


def _platform_of(record: Mapping[str, Any]) -> str:
    platform = record.get("platformId") or record.get("platform")
    if isinstance(platform, str) and platform:
        return platform
    fmt = str(record.get("format") or "").casefold()
    return {"nsp": "switch", "xci": "switch", "nsz": "switch"}.get(fmt, fmt or "outros")


def catalog_games(library: Mapping[str, Any]) -> tuple[CatalogGame, ...]:
    """Lista o conteúdo base da biblioteca como itens da home.

    Update e DLC ficam de fora: são conteúdo real do acervo, mas ``launch_game``
    os recusa, e oferecê-los produziria um erro que o usuário não teria como
    prever olhando a tela.

    Jogabilidade **não** é decidida aqui. Quem sabe se um jogo pode rodar é o
    controller, que combina ajuste por jogo, ``defaultEmulatorId`` global e o
    fallback para o primary instalado — ler ``emulatorId`` do registro daria
    "não jogável" para um sistema que já sabe qual emulador usar.
    """
    records = library.get("games")
    if not isinstance(records, Sequence) or isinstance(records, str | bytes):
        return ()
    games: list[CatalogGame] = []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        if str(record.get("contentKind") or "base") != "base":
            continue
        identifier = str(record.get("id") or "")
        title = str(record.get("name") or record.get("title") or "")
        if not identifier or not title:
            continue
        games.append(CatalogGame(id=identifier, title=title, platform=_platform_of(record)))
    return tuple(games)
