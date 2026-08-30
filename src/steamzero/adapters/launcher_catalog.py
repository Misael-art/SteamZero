# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Tradução entre a biblioteca canônica de emulação e a home do AURA Launcher.

O Launcher **não** tem catálogo, resolução de executor nem regra de jogabilidade
própria. Ele lê a biblioteca canônica do projeto (``emulation-library-cache-v1``;
ou o arquivo passado em ``--library``) e publica os itens **base** da home.

Regras desta camada:

* o rótulo vem de ``name`` (a biblioteca canônica publica o nome exibível em
  ``name``; ``title`` não existe no acervo real — medido: 23 chaves por jogo,
  com ``name`` e sem ``title``). ``title`` é aceito como alias, mas nunca o
  fallback para o id, que fazia a home exibir ``ae18c7e53583298461a0edea`` no
  lugar de ``1969 (Homebrew) (SMS)``.
* a seção é a **plataforma**: a home fullscreen agrupa por sistema porque é
  assim que se procura um jogo, e uma seção única com o acervo inteiro tornaria
  a navegação por controle impraticável.
* update e DLC ficam de fora: ``launch_game`` os recusa, e oferecê-los
  produziria um erro que o usuário não teria como prever olhando a tela.

Jogabilidade **não** é decidida aqui. Quem sabe se um jogo pode rodar é o
controller, que combina ajuste por jogo, ``defaultEmulatorId`` global e o
fallback para o primary instalado.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CatalogGame:
    """Item da home. O ``id`` é o da biblioteca do projeto, não um id local.

    Um id próprio quebraria ``launch_game``/``emulation launch --game-id``, que
    resolve o jogo por esse valor.
    """

    id: str
    title: str
    platform: str

    def to_dict(self) -> dict[str, str]:
        # A seção é a plataforma: a home agrupa por sistema.
        return {
            "id": self.id,
            "title": self.title,
            "section": self.platform,
            "system": self.platform,
        }


def _platform_of(record: Mapping[str, Any]) -> str:
    platform = record.get("platform") or record.get("platformId")
    if isinstance(platform, str) and platform:
        return platform
    fmt = str(record.get("format") or "").casefold()
    return {"nsp": "switch", "xci": "switch", "nsz": "switch"}.get(fmt, fmt or "outros")


def catalog_games(records: Sequence[Mapping[str, Any]]) -> tuple[CatalogGame, ...]:
    """Lista o conteúdo base da biblioteca como itens da home.

    Aceita a lista crua (o que ``_read_library`` já normaliza). Update e DLC
    ficam de fora; um registro sem id ou sem rótulo utilizável é descartado com
    o resto intacto (um registro corrompido não pode esvaziar a home inteira).
    """
    games: list[CatalogGame] = []
    for record in records:
        if str(record.get("contentKind") or "base") != "base":
            continue
        identifier = str(record.get("id") or "")
        title = str(record.get("name") or record.get("title") or "")
        if not identifier or not title:
            continue
        games.append(CatalogGame(id=identifier, title=title, platform=_platform_of(record)))
    return tuple(games)
