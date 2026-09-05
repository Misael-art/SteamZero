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
    cover_url: str = ""
    #: Rota de lançamento: emulation resolve executor/sessão; steam entrega o
    #: AppID ao cliente Steam. A discriminação é por registro, não pelo formato
    #: do id, porque ids canônicos de emulação também podem ser numéricos.
    kind: str = "emulation"

    def to_dict(self) -> dict[str, str]:
        # A seção é a plataforma: a home agrupa por sistema.
        return {
            "id": self.id,
            "title": self.title,
            "section": self.platform,
            "system": self.platform,
            "coverUrl": self.cover_url,
        }


def _platform_of(record: Mapping[str, Any]) -> str:
    platform = record.get("platform") or record.get("platformId")
    if isinstance(platform, str) and platform:
        return platform
    fmt = str(record.get("format") or "").casefold()
    return {"nsp": "switch", "xci": "switch", "nsz": "switch"}.get(fmt, fmt or "outros")


def _cover_of(record: Mapping[str, Any]) -> str:
    """Capa exibível do jogo.

    A biblioteca canônica publica artwork em ``coverUrl``/``artworkUrl`` e
    ``bannerAsset`` quando o scraping/mídia foi concluído. Quando ainda não há
    arte (o caso comum hoje), devolvemos vazio e o cartão usa um placeholder
    honesto — nunca uma imagem de "placeholder" fingindo capa de jogo.
    """
    for key in ("coverUrl", "artworkUrl", "bannerAsset"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


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
        games.append(
            CatalogGame(
                id=identifier,
                title=title,
                platform=_platform_of(record),
                cover_url=_cover_of(record),
            )
        )
    return tuple(games)


def catalog_summary(
    payload: Mapping[str, Any] | None,
    catalog: Sequence[CatalogGame],
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Publica a reconciliação do scan sem transformar arquivo em palpite.

    O resumo vem do envelope da varredura canônica quando disponível. Para uma
    lista crua passada por ``--library``, só fatos observáveis nessa lista são
    publicados; contadores de arquivos não são inventados.
    """
    raw = payload if isinstance(payload, Mapping) else {}
    raw_summary = raw.get("scanSummary")
    summary = dict(raw_summary) if isinstance(raw_summary, Mapping) else {}
    if not summary:
        summary = _summary_from_root_stats(raw)
    if not summary:
        summary = {
            "games": len(catalog),
            "updates": sum(
                1 for record in records if str(record.get("contentKind") or "base") == "update"
            ),
            "dlcs": sum(
                1 for record in records if str(record.get("contentKind") or "base") == "dlc"
            ),
            "incompatibleReasons": {},
            "ignoredReasons": {},
            "platformCounts": {},
            "roots": 0,
        }
    summary["games"] = len(catalog)
    platform_counts: dict[str, int] = {}
    for game in catalog:
        platform_counts[game.platform] = platform_counts.get(game.platform, 0) + 1
    summary["platformCounts"] = platform_counts
    summary.setdefault("updates", 0)
    summary.setdefault("dlcs", 0)
    summary.setdefault("incompatible", 0)
    summary.setdefault("ignored", 0)
    summary.setdefault("incompatibleReasons", {})
    summary.setdefault("ignoredReasons", {})
    # `filesFound` NÃO tem default. Um acervo cujo envelope não conta arquivos é
    # um acervo cuja varredura não os contou; preencher com o número de jogos
    # afirmaria que todo arquivo virou jogo. No cache real do operador isso
    # publicava "231 arquivos, 231 jogos, 0 para revisão" enquanto o rootStats
    # do MESMO arquivo registrava 6724 ignorados e 1061 incompatíveis. A UI
    # oculta o resumo quando o campo está ausente, que é dizer "não sei" em vez
    # de dizer um número errado com ar de fato.
    return summary


def _summary_from_root_stats(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstrói o resumo a partir do ``rootStats`` da própria varredura.

    Caches gravados antes de ``scanSummary`` existir continuam carregando a
    contagem verdadeira em ``rootStats``. Ler dali é a diferença entre a UI
    dizer a verdade e a UI inventar um denominador — os dois números moram no
    mesmo arquivo.
    """
    root_stats = raw.get("rootStats")
    if not isinstance(root_stats, Mapping) or not root_stats:
        return {}
    totals: dict[str, int] = {}
    for entry in root_stats.values():
        counts = entry.get("counts") if isinstance(entry, Mapping) else None
        if not isinstance(counts, Mapping):
            continue
        for key, value in counts.items():
            if isinstance(value, int):
                totals[str(key)] = totals.get(str(key), 0) + value
    if not totals:
        return {}
    # `filesFound` NÃO é reconstruído somando os baldes. Medido no acervo real,
    # a soma dá 8381 para 8016 arquivos e 202 symlinks — 163 a mais, exatamente
    # o total de updates+DLCs, que as duas varreduras (Switch e diretórios)
    # contam cada uma por si. Somar publicaria um total que não fecha com o
    # disco. Os baldes individuais continuam verdadeiros e são o que importa
    # para o usuário entender o que ficou de fora.
    return {
        "updates": totals.get("updates", 0),
        "dlcs": totals.get("dlcs", 0),
        "incompatible": totals.get("incompatible", 0),
        "ignored": totals.get("ignored", 0),
        "incompatibleReasons": {},
        "ignoredReasons": {},
        "platformCounts": {},
        "roots": len(root_stats),
    }
