# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato público e sanitizado da galeria de save-states do AURA.

O domínio só resolve dados para renderização. Captura, backup e restauração
continuam pertencendo ao adapter da sessão que já é dono do emulador.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

MAX_SAVE_STATE_ENTRIES = 32
MAX_TEXT_LENGTH = 240
SAVE_STATE_COMPATIBILITIES = frozenset({"native", "emulated", "unknown"})
SAVE_STATE_STATUS = frozenset({"unavailable", "empty", "ready", "degraded", "error"})
_THUMBNAIL_PREFIXES = ("asset://", "qrc:/", "data:image/")


def _text(value: Any, *, fallback: str = "", limit: int = MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str):
        return fallback
    return value.strip()[:limit]


def _non_negative_int(value: Any, *, fallback: int = 0, maximum: int = 2**31 - 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        return fallback
    return value


def _thumbnail(value: Any) -> tuple[str, bool]:
    """Return only a package-safe thumbnail URL, never a private filesystem path."""

    candidate = _text(value, limit=4096)
    if candidate.startswith(_THUMBNAIL_PREFIXES):
        return candidate, False
    return "", True


@dataclass(frozen=True)
class SaveStateEntry:
    """One renderable slot; no adapter path or process detail crosses the boundary."""

    slot: int
    timestamp: str
    playtime_seconds: int
    thumbnail_url: str
    thumbnail_fallback: bool
    compatibility: str
    available: bool
    backup_available: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "timestamp": self.timestamp,
            "playtimeSeconds": self.playtime_seconds,
            "thumbnailUrl": self.thumbnail_url,
            "thumbnailFallback": self.thumbnail_fallback,
            "compatibility": self.compatibility,
            "available": self.available,
            "backupAvailable": self.backup_available,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class SaveStateGallery:
    """Bounded read model consumed by Theme Engine/QML."""

    state: str
    available: bool
    save_available: bool
    load_available: bool
    reason: str
    entries: tuple[SaveStateEntry, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "state": self.state,
            "available": self.available,
            "saveAvailable": self.save_available,
            "loadAvailable": self.load_available,
            "reason": self.reason,
            "entries": [entry.to_dict() for entry in self.entries],
        }


def unavailable_gallery(reason: str) -> SaveStateGallery:
    return SaveStateGallery(
        state="unavailable",
        available=False,
        save_available=False,
        load_available=False,
        reason=_text(reason, fallback="O adapter não oferece save-state."),
        entries=(),
    )


def _entry(raw: Any) -> SaveStateEntry | None:
    if not isinstance(raw, Mapping):
        return None
    slot = _non_negative_int(raw.get("slot"), maximum=999)
    timestamp = _text(raw.get("timestamp"), limit=32)
    if not timestamp:
        return None
    thumbnail_url, thumbnail_fallback = _thumbnail(raw.get("thumbnailUrl", raw.get("thumbnail")))
    compatibility = _text(raw.get("compatibility"), fallback="unknown", limit=16)
    if compatibility not in SAVE_STATE_COMPATIBILITIES:
        compatibility = "unknown"
    available = raw.get("available", True) is True
    reason = _text(raw.get("reason") or raw.get("detail"))
    if not available and not reason:
        reason = "Este slot não está disponível para restauração."
    return SaveStateEntry(
        slot=slot,
        timestamp=timestamp,
        playtime_seconds=_non_negative_int(raw.get("playtimeSeconds"), maximum=2**31 - 1),
        thumbnail_url=thumbnail_url,
        thumbnail_fallback=thumbnail_fallback,
        compatibility=compatibility,
        available=available,
        backup_available=raw.get("backupAvailable") is True,
        reason=reason,
    )


def resolve_save_state_gallery(
    raw: Any, *, save_available: bool, load_available: bool
) -> SaveStateGallery:
    """Sanitize an adapter result into a deterministic, bounded gallery."""

    if not isinstance(raw, Mapping):
        raw = {"entries": raw}
    raw_state = _text(raw.get("state"), fallback="ready", limit=16)
    if raw_state not in SAVE_STATE_STATUS - {"unavailable"}:
        raw_state = "degraded"
    raw_entries = raw.get("entries")
    entries: list[SaveStateEntry] = []
    if isinstance(raw_entries, Sequence) and not isinstance(raw_entries, (str, bytes, bytearray)):
        for candidate in raw_entries[:MAX_SAVE_STATE_ENTRIES]:
            parsed = _entry(candidate)
            if parsed is not None:
                entries.append(parsed)
    entries.sort(key=lambda item: (item.slot, item.timestamp), reverse=False)
    reason = _text(raw.get("reason") or raw.get("detail"))
    if not entries and raw_state == "ready":
        raw_state = "empty"
    if raw_state == "empty" and not reason:
        reason = "Nenhum save-state foi criado para esta sessão."
    available = raw_state in {"ready", "degraded"}
    return SaveStateGallery(
        state=raw_state,
        available=available,
        save_available=save_available,
        load_available=load_available and any(entry.available for entry in entries),
        reason=reason,
        entries=tuple(entries),
    )


__all__ = [
    "MAX_SAVE_STATE_ENTRIES",
    "SAVE_STATE_COMPATIBILITIES",
    "SaveStateEntry",
    "SaveStateGallery",
    "resolve_save_state_gallery",
    "unavailable_gallery",
]
