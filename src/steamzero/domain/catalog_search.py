# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Consulta pura para catálogo e mídia da superfície AURA.

O Launcher e o pipeline de mídia precisam concordar sobre o significado de
"buscar". Este módulo mantém esse contrato no domínio, sem conhecer QML,
adapters, disco ou rede:

* texto é comparado sem diferenciar maiúsculas, acentos ou variantes de título;
* ``platformId`` e ``systemId`` são filtros exatos e independentes;
* filtro ausente significa escopo global, nunca ``switch`` por padrão;
* a consulta de mídia pode restringir também o papel (`cover`, `fanart`, etc.);
* os resultados preservam a ordem e os objetos recebidos.

O contrato aceita tanto ``GameRecord`` quanto mapeamentos de borda. Isso permite
que o adapter faça a transição sem transformar o domínio em consumidor da UI.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar, cast

from steamzero.core.title_variants import title_variants
from steamzero.domain.game_record import GameRecord

_SPACE = re.compile(r"\s+")
_TOKEN = re.compile(r"\w+", re.UNICODE)
_T = TypeVar("_T")


def _fold(value: object) -> str:
    """Normaliza texto para uma comparação humana estável."""
    text = unicodedata.normalize("NFKD", str(value)).casefold()
    text = "".join(char for char in text if not unicodedata.combining(char))
    return _SPACE.sub(" ", text).strip()


def _identifier(value: object) -> str:
    return _fold(value).replace("_", "-")


def _optional_string(value: object | None) -> str | None:
    return str(value) if value is not None else None


def _mapping(value: GameRecord | Mapping[str, Any]) -> Mapping[str, Any]:
    return value.payload if isinstance(value, GameRecord) else value


def _first(mapping: Mapping[str, Any], *keys: str) -> object | None:
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return cast(object, value)
    return None


def _values(value: object | None) -> tuple[object, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Mapping):
        return tuple(value.values())
    if isinstance(value, Sequence):
        return tuple(value)
    return (value,)


def _system_ids(mapping: Mapping[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for key in ("systemId", "system_id", "systems", "systemIds", "system_ids"):
        for item in _values(mapping.get(key)):
            if isinstance(item, Mapping):
                item = _first(item, "id", "systemId", "system_id", "name")
            if item is not None and str(item).strip():
                values.append(_identifier(item))
    return tuple(dict.fromkeys(values))


def _media_roles(mapping: Mapping[str, Any]) -> tuple[str, ...]:
    direct_role = _first(mapping, "kind", "role", "mediaKind", "media_kind")
    if direct_role is not None:
        return (_identifier(direct_role),)
    media = mapping.get("media")
    if isinstance(media, Mapping):
        return tuple(_identifier(key) for key, value in media.items() if value)
    if isinstance(media, Sequence) and not isinstance(media, str):
        roles: list[str] = []
        for item in media:
            if isinstance(item, Mapping):
                role = _first(item, "kind", "role", "mediaKind")
                if role is not None:
                    roles.append(_identifier(role))
        return tuple(dict.fromkeys(roles))
    return ()


def _search_text(mapping: Mapping[str, Any]) -> str:
    values: list[str] = []
    for key in (
        "title",
        "canonicalTitle",
        "canonical_title",
        "displayName",
        "display_name",
        "name",
        "id",
        "gameId",
        "game_id",
        "path",
    ):
        value = mapping.get(key)
        if value is not None:
            values.append(str(value))
            if key in {"title", "canonicalTitle", "canonical_title", "displayName"}:
                values.extend(title_variants(str(value)))
    aliases = mapping.get("titleVariants", mapping.get("title_variants"))
    values.extend(str(value) for value in _values(aliases))
    return _fold(" ".join(values))


@dataclass(frozen=True)
class CatalogSearchQuery:
    """Consulta compartilhada pelo catálogo de jogos e de mídia."""

    text: str = ""
    platform_id: str | None = None
    system_id: str | None = None
    media_kind: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", _fold(self.text))
        for field_name in ("platform_id", "system_id", "media_kind"):
            value = getattr(self, field_name)
            object.__setattr__(self, field_name, _identifier(value) if value else None)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> CatalogSearchQuery:
        """Lê o envelope de busca sem permitir nomes de borda divergentes."""
        return cls(
            text=_optional_string(_first(payload, "query", "q", "text")) or "",
            platform_id=_optional_string(_first(payload, "platformId", "platform_id", "platform")),
            system_id=_optional_string(_first(payload, "systemId", "system_id", "system")),
            media_kind=_optional_string(_first(payload, "mediaKind", "media_kind", "kind")),
        )

    @property
    def is_global(self) -> bool:
        return not any((self.platform_id, self.system_id, self.media_kind))


def matches_record(record: GameRecord | Mapping[str, Any], query: CatalogSearchQuery) -> bool:
    """Retorna se um registro satisfaz todos os filtros da consulta."""
    mapping = _mapping(record)
    searchable = _search_text(mapping)
    if query.text and not all(token in searchable for token in _TOKEN.findall(query.text)):
        return False
    platform = _first(mapping, "platformId", "platform_id", "platform")
    if query.platform_id and _identifier(platform) != query.platform_id:
        return False
    if query.system_id and query.system_id not in _system_ids(mapping):
        return False
    return not query.media_kind or query.media_kind in _media_roles(mapping)


def search_records(records: Sequence[_T], query: CatalogSearchQuery) -> tuple[_T, ...]:
    """Filtra registros preservando ordem e identidade dos resultados."""
    return tuple(
        record
        for record in records
        if isinstance(record, (GameRecord, Mapping)) and matches_record(record, query)
    )


def search_media(entries: Sequence[_T], query: CatalogSearchQuery) -> tuple[_T, ...]:
    """Filtra entradas de mídia pelo mesmo contrato de escopo do catálogo."""
    return tuple(
        entry for entry in entries if isinstance(entry, Mapping) and matches_record(entry, query)
    )
