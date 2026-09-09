# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato de tradução compartilhado pelos adapters de metadados (frente A1).

Extraído do adapter ES-DE quando o segundo adapter apareceu. A defesa de
caminho, sobretudo, existe uma vez só de propósito: replicada em cada arquivo,
uma cópia acabaria divergindo e viraria a brecha que as outras fecham.

Tudo aqui é puro — nenhuma leitura de disco, nenhuma rede. O adapter recebe
texto já lido e devolve registros; percorrer diretório é do chamador.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from steamzero.domain.game_record import GameRecord

_ID_SAFE = re.compile(r"[^a-z0-9._-]+")

#: Extensões que o contrato aceita por papel de mídia. O que não estiver aqui é
#: descartado com aviso: registrar um formato que a engine não consome faria a
#: UI prometer arte que nunca aparece.
IMAGE_FORMATS: Mapping[str, str] = {
    "png": "png",
    "jpg": "jpeg",
    "jpeg": "jpeg",
    "webp": "webp",
    "svg": "svg",
}
VIDEO_FORMATS: Mapping[str, str] = {"mp4": "mp4", "webm": "webm"}

#: Limite de entradas por arquivo. Biblioteca real grande é legítima; arquivo
#: com mais que isto é entrada hostil ou corrompida.
MAX_ENTRIES = 100_000


class PathRefused(ValueError):
    """Caminho recusado por escapar da raiz ou por forma inaceitável."""


@dataclass(frozen=True)
class ImportResult:
    """Registros traduzidos e o que foi recusado, com o motivo.

    Entrada rejeitada nunca desaparece em silêncio: ``skipped`` diz qual entrada
    e por quê, para que a UI possa explicar em vez de mostrar biblioteca menor
    sem justificativa.

    Aviso que não derruba o jogo fica em ``GameRecord.warnings``, junto do
    registro a que pertence — aviso solto não diz de quem é.
    """

    records: tuple[GameRecord, ...] = ()
    skipped: tuple[tuple[str, str], ...] = ()


def resolve_path(raw: str, system_root: str) -> str:
    """Resolve um caminho externo contra a raiz, recusando escape.

    Recusar é deliberado. Normalizar silenciosamente um ``../`` transformaria um
    arquivo de metadados de terceiro num leitor de arquivo arbitrário.

    A normalização é textual: ``resolve()`` seguiria symlink e tocaria o disco,
    o que este módulo não faz.
    """
    candidate = raw.strip()
    if not candidate:
        raise PathRefused("caminho vazio")
    if candidate.startswith("~"):
        raise PathRefused("caminho com expansão de home não é aceito")
    if "\x00" in candidate:
        raise PathRefused("caminho com byte nulo")

    root = PurePosixPath(system_root)
    resolved = PurePosixPath(candidate) if candidate.startswith("/") else root / candidate

    parts: list[str] = []
    for part in resolved.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    final = PurePosixPath(*parts) if parts else root

    # Contenção por componente, não por prefixo de string: ``startswith`` daria
    # ``/roms/psx-mal`` como interno a ``/roms/psx``.
    if final != root and root not in final.parents:
        raise PathRefused("caminho escapa da raiz do sistema")
    return str(final)


def require_absolute_root(system_root: str) -> None:
    if not system_root.startswith("/"):
        raise ValueError(f"system_root deve ser absoluto: {system_root!r}")


def slug_id(platform_id: str, path: str) -> str:
    """Identificador estável derivado de plataforma e caminho.

    Estável entre execuções para que reimportar funda em vez de duplicar.
    """
    stem = PurePosixPath(path).stem.lower()
    slug = _ID_SAFE.sub("-", f"{platform_id}-{stem}").strip("-._")
    slug = slug or f"{platform_id}-sem-titulo"
    if not slug[0].isalnum():
        slug = f"g{slug}"
    return slug[:128]


def media_asset(path: str, *, role: str) -> dict[str, str] | None:
    """Asset de mídia, ou ``None`` se a extensão não for consumível."""
    suffix = PurePosixPath(path).suffix.lower().lstrip(".")
    table = VIDEO_FORMATS if role == "video" else IMAGE_FORMATS
    fmt = table.get(suffix)
    return None if fmt is None else {"path": path, "format": fmt}


def build_provenance(
    payload: Mapping[str, Any],
    *,
    source: str,
    retrieved_at: str,
    confidence: float,
    conflict_policy: str = "keepRichest",
) -> dict[str, dict[str, Any]]:
    """Proveniência para todo campo de dado do payload.

    ``schemaVersion``, ``provenance`` e ``warnings`` ficam de fora: são
    metadados do próprio registro, não dado vindo da fonte, e reivindicá-los
    inflaria a proveniência com origem falsa.
    """
    excluded = {"schemaVersion", "provenance", "warnings"}
    return {
        key: {
            "source": source,
            "retrievedAt": retrieved_at,
            "confidence": confidence,
            "conflictPolicy": conflict_policy,
        }
        for key in payload
        if key not in excluded
    }


def normalized_players(raw: str) -> int | None:
    """Máximo de jogadores a partir de texto livre (``1``, ``1-2``, ``2+``)."""
    found = re.findall(r"(\d+)", raw)
    return max(int(value) for value in found) if found else None
