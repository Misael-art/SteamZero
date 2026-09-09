# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Adapter de importação RetroArch (playlist ``.lpl``).

Playlist do RetroArch é um índice, não um catálogo: traz caminho, rótulo, core
e às vezes CRC32, e **nada** de descrição, gênero, arte ou data. O registro
resultante é propositalmente magro — preencher o que a fonte não tem seria
inventar dado.

Por isso a confiança é a mais baixa dos adapters (0,4): o rótulo costuma ser o
nome do arquivo, não o título real. Numa fusão com ES-DE ou LaunchBox, a
política ``keepRichest`` faz a fonte melhor vencer sem que este adapter precise
saber que ela existe.

Dois formatos existem no mundo real. O JSON (RetroArch ≥ 1.6) é suportado; o
antigo, de seis linhas por entrada, é **recusado com mensagem explícita** em vez
de interpretado por adivinhação — parsear errado um índice de biblioteca
produziria caminhos falsos silenciosamente.
"""

from __future__ import annotations

import json
import re
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
SOURCE = "retroarch"

#: Playlist é índice: o rótulo costuma ser o nome do arquivo, não o título.
CONFIDENCE = 0.4

#: CRC32 do RetroArch vem como ``ABCDEF01|crc``; só o hexadecimal interessa.
_CRC_SUFFIX = "|crc"


def _core_name(item: dict[str, Any]) -> str | None:
    """Identificador de core, no alfabeto que o contrato aceita.

    RetroArch grava o nome de exibição ("Beetle PSX HW"), mas ``core`` é um
    identificador (``^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$``) e não aceita espaço.
    O espaço vira ``-``; o que sobrar fora do alfabeto é descartado, porque um
    identificador inventado é pior que campo ausente.
    """
    raw = item.get("core_name")
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    # RetroArch grava "DETECT" quando não há core fixado. Não é um core.
    if not value or value.upper() == "DETECT":
        return None
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return slug[:128] if slug and slug[0].isalnum() else None


def _crc32(item: dict[str, Any]) -> str | None:
    raw = item.get("crc32")
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if value.lower().endswith(_CRC_SUFFIX):
        value = value[: -len(_CRC_SUFFIX)]
    value = value.strip().lower()
    if len(value) != 8 or any(char not in "0123456789abcdef" for char in value):
        return None
    # CRC32 tudo-zero é o placeholder do RetroArch para "não calculado".
    return None if value == "00000000" else value


def import_retroarch_playlist(
    text: str,
    *,
    platform_id: str,
    system_root: str,
    retrieved_at: str,
) -> ImportResult:
    """Traduz uma playlist ``.lpl`` em registros canônicos.

    ``availability`` fica ``unknown``: o adapter não lê disco, e a playlist é
    um índice que pode apontar para arquivo já removido.
    """
    try:
        require_absolute_root(system_root)
    except ValueError as exc:
        raise GameRecordError(str(exc)) from exc

    stripped = text.strip()
    if not stripped:
        return ImportResult()
    if not stripped.startswith("{"):
        raise GameRecordError(
            "playlist .lpl no formato antigo de seis linhas não é suportada; "
            "interpretá-la por adivinhação produziria caminhos falsos"
        )

    try:
        document = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise GameRecordError(f"playlist .lpl malformada: {exc}") from exc
    if not isinstance(document, dict):
        raise GameRecordError("playlist .lpl malformada: raiz não é objeto")

    items = document.get("items")
    if items is None:
        return ImportResult()
    if not isinstance(items, list):
        raise GameRecordError("playlist .lpl malformada: 'items' não é lista")

    records: list[GameRecord] = []
    skipped: list[tuple[str, str]] = []
    seen: set[str] = set()

    for index, item in enumerate(items):
        if index >= MAX_ENTRIES:
            skipped.append(("<limite>", "retroarch-playlist-excede-limite"))
            break
        if not isinstance(item, dict):
            skipped.append((f"<item {index}>", "retroarch-item-nao-e-objeto"))
            continue

        raw_path = item.get("path")
        label = item.get("label") if isinstance(item.get("label"), str) else None
        display = (label or raw_path or f"<item {index}>") if isinstance(raw_path, str) else "?"
        if not isinstance(raw_path, str) or not raw_path.strip():
            skipped.append((str(display), "retroarch-sem-path"))
            continue

        # Entrada de arquivo comprimido vem como "arquivo.zip#interno.rom"; o
        # caminho real é o container, e o membro não é um caminho de disco.
        container_member = None
        candidate = raw_path
        if "#" in candidate:
            candidate, _, container_member = candidate.partition("#")

        try:
            path = resolve_path(candidate, system_root)
        except PathRefused as exc:
            skipped.append((str(display), f"retroarch-path-recusado: {exc}"))
            continue

        record_id = slug_id(platform_id, path)
        if record_id in seen:
            skipped.append((str(display), "retroarch-id-duplicado"))
            continue
        seen.add(record_id)

        payload: dict[str, Any] = {
            "schemaVersion": 1,
            "id": record_id,
            "title": (label or "").strip() or path.rsplit("/", 1)[-1].rsplit(".", 1)[0],
            "platformId": platform_id,
            "path": path,
            "availability": "unknown",
            "updatedAt": retrieved_at,
        }

        core = _core_name(item)
        if core:
            payload["core"] = core
        crc = _crc32(item)
        if crc:
            payload["hashes"] = {"crc32": crc}
        if container_member:
            payload["container"] = "archive"

        payload["provenance"] = build_provenance(
            payload, source=SOURCE, retrieved_at=retrieved_at, confidence=CONFIDENCE
        )

        try:
            records.append(GameRecord.from_mapping(payload))
        except GameRecordError as exc:
            skipped.append((str(display), f"retroarch-registro-invalido: {exc}"))

    return ImportResult(records=tuple(records), skipped=tuple(skipped))
