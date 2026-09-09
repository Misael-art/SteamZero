# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Adapter de importação ES-DE / EmulationStation (``gamelist.xml``).

Traduz ``<game>`` em ``GameRecord`` canônico. O que não existe no formato de
origem fica ausente — inventar campo para preencher a tela é falsear estado.

Decisões que o formato impõe e que o contrato não pode herdar em silêncio:

- **Caminho relativo com ``./``.** ES-DE grava ``./Jogo.chd`` relativo à raiz do
  sistema. A resolução é feita contra a raiz declarada pelo chamador, e um
  caminho que escape dela é recusado, não normalizado: ``../../etc/passwd`` num
  gamelist de terceiro não pode virar leitura fora da biblioteca.
- **Rating 0..1.** ES-DE usa fração; o contrato usa 0..10. A conversão é
  explícita, e valor fora de faixa vira ausência com aviso, não um número
  inventado.
- **``<players>`` livre.** Aceita ``1``, ``1-2``, ``2+``. Só o máximo inteiro é
  aproveitado; texto que não se resolve é descartado com aviso.
- **XML de terceiro é entrada hostil.** Entidades externas e DTD são recusadas.

A confiança é fixa e modesta (0,6): gamelist é curado por humano ou por scraper,
sem garantia de correção. Quem tiver fonte melhor vence pela política de
conflito, não por sobrescrita cega.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from steamzero.domain.game_record import GameRecord, GameRecordError

#: Origem registrada na proveniência de todo campo vindo deste adapter.
SOURCE = "esde"

#: Gamelist é curado, mas sem garantia; não compete com hash nem com o usuário.
CONFIDENCE = 0.6

_DOCTYPE = re.compile(r"<!(DOCTYPE|ENTITY)", re.IGNORECASE)
_ID_SAFE = re.compile(r"[^a-z0-9._-]+")
_PLAYERS = re.compile(r"(\d+)")
_MAX_GAMES = 100_000


@dataclass(frozen=True)
class EsdeImportResult:
    """Registros traduzidos e o que foi recusado, com o motivo.

    Entrada rejeitada nunca desaparece em silêncio: ``skipped`` diz qual jogo e
    por quê, para que a UI possa explicar em vez de mostrar biblioteca menor sem
    justificativa.

    Aviso que não derruba o jogo (rating fora de faixa, mídia de formato
    desconhecido) fica em ``GameRecord.warnings``, junto do registro a que
    pertence — não há lista global aqui, porque aviso solto não diz de quem é.
    """

    records: tuple[GameRecord, ...] = ()
    skipped: tuple[tuple[str, str], ...] = ()


def _text(node: ET.Element, tag: str) -> str | None:
    child = node.find(tag)
    if child is None or child.text is None:
        return None
    value = child.text.strip()
    return value or None


def _slug_id(platform_id: str, path: str) -> str:
    stem = PurePosixPath(path).stem.lower()
    slug = _ID_SAFE.sub("-", f"{platform_id}-{stem}").strip("-._")
    slug = slug or f"{platform_id}-sem-titulo"
    if not slug[0].isalnum():
        slug = f"g{slug}"
    return slug[:128]


def _resolve_path(raw: str, system_root: str) -> str:
    """Resolve o caminho do ES-DE contra a raiz, recusando escape.

    Recusar é deliberado. Normalizar silenciosamente um ``../`` transformaria um
    gamelist de terceiro num leitor de arquivo arbitrário.
    """
    candidate = raw.strip()
    if not candidate:
        raise ValueError("caminho vazio")
    if candidate.startswith("~"):
        raise ValueError("caminho com expansão de home não é aceito")
    root = PurePosixPath(system_root)
    if candidate.startswith("/"):
        resolved = PurePosixPath(candidate)
    else:
        resolved = root / PurePosixPath(candidate)
    # Normaliza ``.`` e ``..`` sem tocar o disco (nada de resolve(), que
    # seguiria symlink), e então exige contenção. A contenção é a única garantia
    # e é o que os testes de mutação provam: guarda extra durante a normalização
    # é código morto que só parece defesa.
    parts: list[str] = []
    for part in resolved.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    final = PurePosixPath(*parts) if parts else root
    if final != root and root not in final.parents:
        raise ValueError("caminho escapa da raiz do sistema")
    return str(final)


def _rating(node: ET.Element, warnings: list[str]) -> float | None:
    raw = _text(node, "rating")
    if raw is None:
        return None
    try:
        fraction = float(raw)
    except ValueError:
        warnings.append("esde-rating-invalido")
        return None
    if not 0.0 <= fraction <= 1.0:
        warnings.append("esde-rating-fora-de-faixa")
        return None
    return round(fraction * 10, 2)


def _players(node: ET.Element, warnings: list[str]) -> int | None:
    raw = _text(node, "players")
    if raw is None:
        return None
    found = _PLAYERS.findall(raw)
    if not found:
        warnings.append("esde-players-invalido")
        return None
    return max(int(value) for value in found)


def _iter_games(root: ET.Element) -> Iterator[ET.Element]:
    yield from root.findall("game")


def import_esde_gamelist(
    xml_text: str,
    *,
    platform_id: str,
    system_root: str,
    retrieved_at: str,
) -> EsdeImportResult:
    """Traduz um ``gamelist.xml`` em registros canônicos.

    ``system_root`` é a raiz absoluta do sistema, contra a qual os caminhos
    relativos do ES-DE são resolvidos. ``retrieved_at`` é o timestamp UTC da
    leitura, registrado na proveniência de cada campo.

    Não lê disco: a existência dos arquivos apontados não é verificada aqui, e
    por isso ``availability`` fica ``unknown`` — afirmar ``available`` sem olhar
    o arquivo seria inventar estado.
    """
    if not system_root.startswith("/"):
        raise GameRecordError(f"system_root deve ser absoluto: {system_root!r}")

    # XML de terceiro é entrada hostil: DTD/entidade abrem porta para expansão
    # de entidade e leitura de arquivo externo. Recusar é mais barato e mais
    # verificável do que tentar desarmar o parser.
    if _DOCTYPE.search(xml_text):
        raise GameRecordError("gamelist.xml com DTD ou entidade não é aceito")

    try:
        root = ET.fromstring(xml_text)  # noqa: S314 - DTD recusado acima
    except ET.ParseError as exc:
        raise GameRecordError(f"gamelist.xml malformado: {exc}") from exc

    records: list[GameRecord] = []
    skipped: list[tuple[str, str]] = []
    seen: set[str] = set()

    for index, node in enumerate(_iter_games(root)):
        if index >= _MAX_GAMES:
            skipped.append(("<limite>", "esde-gamelist-excede-limite"))
            break

        raw_path = _text(node, "path")
        label = _text(node, "name") or raw_path or f"<jogo {index}>"
        if raw_path is None:
            skipped.append((label, "esde-sem-path"))
            continue
        try:
            path = _resolve_path(raw_path, system_root)
        except ValueError as exc:
            skipped.append((label, f"esde-path-recusado: {exc}"))
            continue

        title = _text(node, "name") or PurePosixPath(path).stem
        record_id = _slug_id(platform_id, path)
        if record_id in seen:
            skipped.append((label, "esde-id-duplicado"))
            continue
        seen.add(record_id)

        warnings: list[str] = []
        payload: dict[str, Any] = {
            "schemaVersion": 1,
            "id": record_id,
            "title": title,
            "platformId": platform_id,
            "path": path,
            "availability": "unknown",
            "updatedAt": retrieved_at,
        }

        optional: dict[str, Any] = {
            "description": _text(node, "desc"),
            "developer": _text(node, "developer"),
            "publisher": _text(node, "publisher"),
            "rating": _rating(node, warnings),
            "players": _players(node, warnings),
        }
        genre = _text(node, "genre")
        if genre:
            optional["genres"] = [genre]
        release = _text(node, "releasedate")
        if release and len(release) >= 8:
            optional["releaseDate"] = f"{release[0:4]}-{release[4:6]}-{release[6:8]}"

        media: dict[str, Any] = {}
        for tag, role in (("image", "cover"), ("marquee", "marquee"), ("video", "video")):
            raw_media = _text(node, tag)
            if raw_media is None:
                continue
            try:
                media_path = _resolve_path(raw_media, system_root)
            except ValueError:
                warnings.append(f"esde-media-recusada-{role}")
                continue
            suffix = PurePosixPath(media_path).suffix.lower().lstrip(".")
            fmt = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(suffix)
            if role == "video":
                fmt = {"mp4": "mp4", "webm": "webm"}.get(suffix)
            if fmt is None:
                warnings.append(f"esde-media-formato-desconhecido-{role}")
                continue
            media[role] = {"path": media_path, "format": fmt}

        payload.update({key: value for key, value in optional.items() if value is not None})
        if media:
            payload["media"] = media
        if warnings:
            payload["warnings"] = warnings

        tracked = [key for key in payload if key not in {"schemaVersion", "provenance", "warnings"}]
        payload["provenance"] = {
            key: {
                "source": SOURCE,
                "retrievedAt": retrieved_at,
                "confidence": CONFIDENCE,
                "conflictPolicy": "keepRichest",
            }
            for key in tracked
        }

        try:
            records.append(GameRecord.from_mapping(payload))
        except GameRecordError as exc:
            skipped.append((label, f"esde-registro-invalido: {exc}"))

    return EsdeImportResult(records=tuple(records), skipped=tuple(skipped))
