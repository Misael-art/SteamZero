# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Adapter de importação LaunchBox (XML de plataforma).

LaunchBox é um catálogo do Windows, e o formato carrega isso: os caminhos usam
barra invertida e costumam ser relativos à instalação. A conversão para caminho
POSIX é explícita, e a contenção na raiz continua valendo — um XML de terceiro
não vira leitor de arquivo arbitrário só porque veio de outro sistema.

Detalhes que o formato impõe:

- **``CommunityStarRating`` é 0..5 estrelas**, não porcentagem. Vira 0..100
  multiplicando por 20; a escala canônica do contrato é uma só.
- **``ReleaseDate`` é ISO com hora** (``1996-09-09T00:00:00``). Só a data entra.
- **``Broken`` e ``Hide``** marcam entradas que o usuário já sinalizou. Elas não
  são importadas em silêncio: viram ``availability`` explícito em vez de
  aparecer como jogo normal.

Confiança 0,75: LaunchBox costuma ser curado com scraper próprio e revisão
humana, o que o torna melhor que uma playlist, mas ainda não é fonte final.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from steamzero.domain.game_record import GameRecord, GameRecordError
from steamzero.domain.metadata_import._common import (
    MAX_ENTRIES,
    ImportResult,
    PathRefused,
    build_provenance,
    require_absolute_root,
    resolve_path,
    slug_id,
)

#: Origem registrada na proveniência de todo campo vindo deste adapter.
SOURCE = "launchbox"

#: Curado com scraper próprio e revisão humana; melhor que playlist, não final.
CONFIDENCE = 0.75

_DOCTYPE = re.compile(r"<!(DOCTYPE|ENTITY)", re.IGNORECASE)
_TRUE = {"true", "1", "yes"}


def _text(node: ET.Element, tag: str) -> str | None:
    child = node.find(tag)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def _flag(node: ET.Element, tag: str) -> bool:
    raw = _text(node, tag)
    return raw is not None and raw.strip().lower() in _TRUE


def _windows_to_posix(raw: str) -> str:
    """Converte separador do Windows e remove letra de unidade.

    ``C:\\Games\\x.chd`` vira ``Games/x.chd`` — relativo, para que a resolução
    contra a raiz declarada decida onde ele realmente fica. Manter a letra de
    unidade produziria um caminho que não existe no host.
    """
    value = raw.strip().replace("\\", "/")
    if len(value) >= 2 and value[1] == ":" and value[0].isalpha():
        value = value[2:]
    return value.lstrip("/") or value


def _rating(node: ET.Element, warnings: list[str]) -> float | None:
    raw = _text(node, "CommunityStarRating")
    if raw is None:
        return None
    try:
        stars = float(raw)
    except ValueError:
        warnings.append("launchbox-rating-invalido")
        return None
    if not 0.0 <= stars <= 5.0:
        warnings.append("launchbox-rating-fora-de-faixa")
        return None
    # 0..5 estrelas -> 0..100. A escala canônica do contrato é uma só.
    return round(stars * 20, 2)


def import_launchbox_xml(
    xml_text: str,
    *,
    platform_id: str,
    system_root: str,
    retrieved_at: str,
) -> ImportResult:
    """Traduz um XML de plataforma do LaunchBox em registros canônicos."""
    try:
        require_absolute_root(system_root)
    except ValueError as exc:
        raise GameRecordError(str(exc)) from exc

    if _DOCTYPE.search(xml_text):
        raise GameRecordError("XML do LaunchBox com DTD ou entidade não é aceito")

    try:
        root = ET.fromstring(xml_text)  # noqa: S314 - DTD recusado acima
    except ET.ParseError as exc:
        raise GameRecordError(f"XML do LaunchBox malformado: {exc}") from exc

    records: list[GameRecord] = []
    skipped: list[tuple[str, str]] = []
    seen: set[str] = set()

    for index, node in enumerate(root.findall("Game")):
        if index >= MAX_ENTRIES:
            skipped.append(("<limite>", "launchbox-xml-excede-limite"))
            break

        raw_path = _text(node, "ApplicationPath")
        label = _text(node, "Title") or raw_path or f"<jogo {index}>"
        if raw_path is None:
            skipped.append((label, "launchbox-sem-application-path"))
            continue

        try:
            path = resolve_path(_windows_to_posix(raw_path), system_root)
        except PathRefused as exc:
            skipped.append((label, f"launchbox-path-recusado: {exc}"))
            continue

        record_id = slug_id(platform_id, path)
        if record_id in seen:
            skipped.append((label, "launchbox-id-duplicado"))
            continue
        seen.add(record_id)

        warnings: list[str] = []
        # O usuário já marcou esta entrada como quebrada; entrar como jogo
        # normal esconderia um estado que ele mesmo registrou.
        availability = "incompatible" if _flag(node, "Broken") else "unknown"
        if _flag(node, "Hide"):
            warnings.append("launchbox-entrada-oculta-na-origem")

        payload: dict[str, Any] = {
            "schemaVersion": 1,
            "id": record_id,
            "title": _text(node, "Title") or path.rsplit("/", 1)[-1].rsplit(".", 1)[0],
            "platformId": platform_id,
            "path": path,
            "availability": availability,
            "updatedAt": retrieved_at,
        }

        optional: dict[str, Any] = {
            "description": _text(node, "Notes"),
            "developer": _text(node, "Developer"),
            "publisher": _text(node, "Publisher"),
            "rating": _rating(node, warnings),
            "series": _text(node, "Series"),
        }
        genre = _text(node, "Genre")
        if genre:
            # LaunchBox separa gêneros por ";".
            optional["genres"] = [part.strip() for part in genre.split(";") if part.strip()][:32]
        players_raw = _text(node, "MaxPlayers")
        if players_raw:
            try:
                players = int(players_raw)
            except ValueError:
                warnings.append("launchbox-players-invalido")
            else:
                if 1 <= players <= 64:
                    optional["players"] = players
                else:
                    warnings.append("launchbox-players-fora-de-faixa")
        release = _text(node, "ReleaseDate")
        if release and len(release) >= 10 and release[4] == "-" and release[7] == "-":
            optional["releaseDate"] = release[:10]
        elif release:
            warnings.append("launchbox-release-invalida")

        payload.update({key: value for key, value in optional.items() if value is not None})
        if warnings:
            payload["warnings"] = warnings

        payload["provenance"] = build_provenance(
            payload, source=SOURCE, retrieved_at=retrieved_at, confidence=CONFIDENCE
        )

        try:
            records.append(GameRecord.from_mapping(payload))
        except GameRecordError as exc:
            skipped.append((label, f"launchbox-registro-invalido: {exc}"))

    return ImportResult(records=tuple(records), skipped=tuple(skipped))
