# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Adapter de importação Pegasus (``metadata.pegasus.txt``).

Formato de texto com pares ``chave: valor``, blocos separados por linha em
branco e continuação por indentação. Um jogo começa em ``game:``; o cabeçalho
antes do primeiro ``game:`` descreve a coleção.

Duas armadilhas do formato, ambas tratadas explicitamente:

- **Continuação indentada.** ``description:`` costuma ocupar várias linhas
  indentadas, e uma linha contendo só ``.`` é parágrafo em branco, não fim do
  campo. Cortar no primeiro ``\\n`` truncaria a descrição.
- **``file:`` versus ``files:``.** A forma plural lista vários caminhos, um por
  linha indentada — é multi-disco, não um jogo por linha. O primeiro caminho
  vira ``path`` e os demais entram em ``discSet``, preservando a relação.

Confiança 0,7: Pegasus é curado à mão com mais frequência que gamelist gerado
por scraper, mas segue sem garantia de correção.
"""

from __future__ import annotations

from typing import Any

from steamzero.domain.game_record import GameRecord, GameRecordError
from steamzero.domain.metadata_import._common import (
    MAX_ENTRIES,
    ImportResult,
    PathRefused,
    build_provenance,
    normalized_players,
    require_absolute_root,
    resolve_path,
    slug_id,
)

#: Origem registrada na proveniência de todo campo vindo deste adapter.
SOURCE = "pegasus"

#: Curado à mão com mais frequência que gamelist, mas sem garantia.
CONFIDENCE = 0.7

#: Chaves que iniciam um novo bloco de jogo.
_GAME_KEYS = ("game", "gameentry")


def _parse_blocks(text: str) -> list[dict[str, list[str]]]:
    """Quebra o arquivo em blocos de ``chave -> linhas``.

    A continuação indentada é preservada como linhas separadas para que o
    chamador decida juntá-las (descrição) ou tratá-las como lista (``files``).
    """
    blocks: list[dict[str, list[str]]] = []
    current: dict[str, list[str]] = {}
    last_key: str | None = None

    for raw_line in text.splitlines():
        if not raw_line.strip():
            last_key = None
            continue

        indented = raw_line[:1] in {" ", "\t"}
        line = raw_line.strip()

        if indented and last_key is not None:
            # Linha com apenas "." é parágrafo em branco no Pegasus.
            current[last_key].append("" if line == "." else line)
            continue

        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip().lower()
        value = value.strip()

        if key in _GAME_KEYS:
            if current:
                blocks.append(current)
            current = {}
        last_key = key
        current.setdefault(key, [])
        if value:
            current[key].append(value)

    if current:
        blocks.append(current)
    return blocks


def _joined(block: dict[str, list[str]], key: str) -> str | None:
    lines = block.get(key)
    if not lines:
        return None
    value = "\n".join(lines).strip()
    return value or None


def _first(block: dict[str, list[str]], key: str) -> str | None:
    lines = block.get(key)
    return lines[0].strip() if lines and lines[0].strip() else None


def import_pegasus_metadata(
    text: str,
    *,
    platform_id: str,
    system_root: str,
    retrieved_at: str,
) -> ImportResult:
    """Traduz um ``metadata.pegasus.txt`` em registros canônicos."""
    try:
        require_absolute_root(system_root)
    except ValueError as exc:
        raise GameRecordError(str(exc)) from exc

    records: list[GameRecord] = []
    skipped: list[tuple[str, str]] = []
    seen: set[str] = set()

    blocks = [block for block in _parse_blocks(text) if any(k in block for k in _GAME_KEYS)]

    for index, block in enumerate(blocks):
        if index >= MAX_ENTRIES:
            skipped.append(("<limite>", "pegasus-arquivo-excede-limite"))
            break

        title = next((_first(block, key) for key in _GAME_KEYS if _first(block, key)), None)
        raw_files = block.get("files") or block.get("file") or []
        label = title or "<sem título>"
        if not raw_files:
            skipped.append((label, "pegasus-sem-file"))
            continue

        resolved: list[str] = []
        refused = False
        for raw in raw_files:
            try:
                resolved.append(resolve_path(raw, system_root))
            except PathRefused as exc:
                skipped.append((label, f"pegasus-path-recusado: {exc}"))
                refused = True
                break
        if refused or not resolved:
            continue

        path = resolved[0]
        record_id = slug_id(platform_id, path)
        if record_id in seen:
            skipped.append((label, "pegasus-id-duplicado"))
            continue
        seen.add(record_id)

        warnings: list[str] = []
        payload: dict[str, Any] = {
            "schemaVersion": 1,
            "id": record_id,
            "title": title or path.rsplit("/", 1)[-1].rsplit(".", 1)[0],
            "platformId": platform_id,
            "path": path,
            "availability": "unknown",
            "updatedAt": retrieved_at,
        }

        optional: dict[str, Any] = {
            "description": _joined(block, "description") or _joined(block, "summary"),
            "developer": _first(block, "developer"),
            "publisher": _first(block, "publisher"),
        }
        genre = _first(block, "genre")
        if genre:
            # Pegasus separa gêneros por vírgula na mesma linha.
            optional["genres"] = [part.strip() for part in genre.split(",") if part.strip()][:32]
        players_raw = _first(block, "players")
        if players_raw:
            players = normalized_players(players_raw)
            if players is None:
                warnings.append("pegasus-players-invalido")
            else:
                optional["players"] = players
        release = _first(block, "release")
        if release and len(release) >= 10 and release[4] == "-" and release[7] == "-":
            optional["releaseDate"] = release[:10]
        elif release:
            warnings.append("pegasus-release-invalida")

        # ``files`` com mais de um caminho é multi-disco, não jogos separados.
        if len(resolved) > 1:
            payload["discSet"] = [
                {"disc": number, "path": disc_path}
                for number, disc_path in enumerate(resolved, start=1)
            ][:999]

        payload.update({key: value for key, value in optional.items() if value is not None})
        if warnings:
            payload["warnings"] = warnings

        payload["provenance"] = build_provenance(
            payload, source=SOURCE, retrieved_at=retrieved_at, confidence=CONFIDENCE
        )

        try:
            records.append(GameRecord.from_mapping(payload))
        except GameRecordError as exc:
            skipped.append((label, f"pegasus-registro-invalido: {exc}"))

    return ImportResult(records=tuple(records), skipped=tuple(skipped))
