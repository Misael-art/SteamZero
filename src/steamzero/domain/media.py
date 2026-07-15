# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Índice/reconciliação local de mídia (F-MD-02, ST-06, RT-11).

O domínio não baixa arte nem fala com provedores. Ele classifica payloads locais
por magic bytes, gera destinos canônicos apenas com IDs/tipos validados e move
itens órfãos/hostis para quarentena lógica dentro da raiz da mídia. Toda mudança
usa o núcleo transacional e, portanto, tem preview, confirmação e rollback.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from steamzero.core import fs, ids, transaction

_KINDS = frozenset({"boxart", "screenshot", "video"})
_BIDI_CONTROLS = frozenset({"LRE", "RLE", "LRO", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI"})
_DEFAULT_MAX_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class MediaAssignment:
    game_id: str
    kind: str
    provider: str
    license: str


class MediaLibrary:
    def __init__(self, *, max_bytes: int = _DEFAULT_MAX_BYTES) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes precisa ser positivo")
        self._max_bytes = max_bytes

    def plan_reconcile(
        self, root: Path, assignments: dict[str, MediaAssignment]
    ) -> transaction.Plan:
        """Planeja canonicalização e quarentena de todos os arquivos em ``root``."""
        normalized = {
            str(fs.validate_relative_entry(name)): assignment
            for name, assignment in assignments.items()
        }
        moves: dict[Path, Path] = {}
        for source in fs.iter_files(root):
            relative = source.relative_to(root)
            if relative.parts and relative.parts[0] == ".quarantine":
                continue
            relname = str(relative)
            assignment = normalized.get(relname)
            extension = _media_extension(source, self._max_bytes)
            if (
                assignment is None
                or extension is None
                or _contains_bidi_control(relname)
                or not _valid_assignment(assignment)
            ):
                target = root / _quarantine_relpath(relname, extension)
            else:
                target = root / "canonical" / assignment.game_id / f"{assignment.kind}{extension}"
            if source != target:
                moves[source] = target
        return transaction.plan_move_files(moves, root=root, kind="media.reconcile")

    @staticmethod
    def apply(
        plan_id: str,
        confirm_token: str,
        *,
        smoke: Callable[[], None] | None = None,
    ) -> transaction.ApplyResult:
        return transaction.apply(plan_id, confirm_token, smoke=smoke)

    @staticmethod
    def rollback(operation_id: str) -> transaction.RollbackResult:
        return transaction.rollback(operation_id, reason="media-reconcile")


def _valid_assignment(assignment: MediaAssignment) -> bool:
    return (
        ids.is_ulid(assignment.game_id)
        and assignment.kind in _KINDS
        and bool(assignment.provider.strip())
        and bool(assignment.license.strip())
    )


def _media_extension(path: Path, max_bytes: int) -> str | None:
    if path.stat().st_size > max_bytes:
        return None
    with open(path, "rb") as stream:
        header = stream.read(16)
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if header.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return ".webp"
    return None


def _contains_bidi_control(value: str) -> bool:
    return any(unicodedata.bidirectional(char) in _BIDI_CONTROLS for char in value)


def _quarantine_relpath(relname: str, extension: str | None) -> Path:
    suffix = extension or ".bin"
    token = fs.hash_bytes(unicodedata.normalize("NFC", relname).encode("utf-8"))[:24]
    return Path(".quarantine") / "orphans" / f"{token}{suffix}"
