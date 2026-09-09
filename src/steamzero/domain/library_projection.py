# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Projeção de ``GameRecord`` para o catálogo da home (frente A1).

Este é o **consumidor** do modelo canônico: até aqui existiam tradutores de
formatos externos e nenhum leitor, e um modelo que ninguém lê não move nada para
o usuário. A projeção liga a metadata importada à home que o Launcher já
desenha, produzindo exatamente o payload que
``adapters.launcher_catalog.catalog_games`` consome — sem reescrever a UI e sem
tocar o QML.

Duas regras dão a forma do módulo, e as duas vêm de não falsear estado:

1. **Jogo indisponível não entra no catálogo como jogo normal.** ``missing``,
   ``incompatible`` e ``permissionDenied`` são estados que alguém já registrou;
   listá-los junto dos jogáveis faria a home prometer o que não abre. Eles saem
   em ``omitted``, com o motivo, para a superfície explicar em vez de esconder.
2. **Ausência de arte é ausência, não placeholder.** Sem capa, ``coverUrl`` fica
   vazio e o cartão usa o fallback honesto que já existe — nunca uma imagem
   fingindo ser capa de jogo.

Domínio puro: não lê disco, não acessa rede e não importa adapters. O formato de
saída é o que o adapter já entende, e não o contrário — inverter a dependência
faria o domínio conhecer a UI.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote

from steamzero.domain.game_record import GameRecord, MediaRole

#: Estados em que o jogo não abre. Listá-los como jogáveis seria prometer o que
#: não cumpre; ficam de fora do catálogo e são devolvidos com o motivo.
UNPLAYABLE = frozenset({"missing", "incompatible", "permissionDenied"})


@dataclass(frozen=True)
class CatalogProjection:
    """Entradas exibíveis e as que ficaram de fora, com o motivo.

    Espelha o contrato dos adapters de importação de propósito: o que é
    descartado nunca desaparece em silêncio, para que a superfície possa
    explicar em vez de mostrar uma biblioteca menor sem justificativa.
    """

    entries: tuple[dict[str, Any], ...] = ()
    omitted: tuple[tuple[str, str], ...] = ()


def _cover_url(record: GameRecord) -> str:
    """URL da capa, ou vazio quando não há arte utilizável.

    Só caminho absoluto vira ``file://``: um caminho relativo dependeria do
    diretório de trabalho de quem renderiza, e resolvê-lo aqui seria inventar
    uma âncora que o registro não declara.
    """
    asset = record.media(MediaRole.COVER)
    if asset is None:
        return ""
    path = str(asset.get("path") or "")
    if not path.startswith("/"):
        return ""
    return "file://" + quote(str(PurePosixPath(path)))


def project_records(records: Sequence[GameRecord]) -> CatalogProjection:
    """Projeta registros canônicos no payload do catálogo da home.

    O resultado alimenta ``catalog_games`` sem conversão adicional: ``id``,
    ``title`` e ``platformId`` já são os nomes que ele lê, e ``contentKind``
    marca conteúdo base — update e DLC não são jogos da home.
    """
    entries: list[dict[str, Any]] = []
    omitted: list[tuple[str, str]] = []
    seen: set[str] = set()

    for record in records:
        availability = record.availability
        if availability in UNPLAYABLE:
            omitted.append((record.id, f"indisponivel-{availability}"))
            continue
        if record.id in seen:
            omitted.append((record.id, "duplicado-na-projecao"))
            continue
        seen.add(record.id)

        entry: dict[str, Any] = {
            "id": record.id,
            "title": record.title,
            "platformId": record.platform_id,
            "contentKind": "base",
            "coverUrl": _cover_url(record),
        }
        # ``warnings`` do registro seguem para a superfície poder degradar com
        # a causa à mão, em vez de mostrar um cartão mudo.
        if record.warnings:
            entry["warnings"] = list(record.warnings)
        entries.append(entry)

    return CatalogProjection(entries=tuple(entries), omitted=tuple(omitted))
