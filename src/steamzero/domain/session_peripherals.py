# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Read model for the non-generic parts of an AURA game session.

The theme receives facts that a concrete emulator adapter has observed.  It
never receives a path, argv or an instruction to simulate a capability.  An
emulator that does not expose a surface remains visibly unavailable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

MAX_DISCS = 16
MAX_BEZELS = 8
MAX_TEXT_LENGTH = 240
_ASSET_PREFIXES = ("asset://", "qrc:/", "data:image/")


def _text(value: Any, *, fallback: str = "", limit: int = MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str):
        return fallback
    return value.strip()[:limit]


def _asset(value: Any) -> str:
    candidate = _text(value, limit=4096)
    return candidate if candidate.startswith(_ASSET_PREFIXES) else ""


@dataclass(frozen=True)
class DiscEntry:
    id: str
    label: str
    index: int
    inserted: bool
    available: bool
    compatible: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "index": self.index,
            "inserted": self.inserted,
            "available": self.available,
            "compatible": self.compatible,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class BezelEntry:
    id: str
    label: str
    asset_url: str
    available: bool
    selected: bool
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "assetUrl": self.asset_url,
            "available": self.available,
            "selected": self.selected,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class FadeState:
    phase: str
    progress: float
    duration_ms: int
    reduced_motion: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "progress": self.progress,
            "durationMs": self.duration_ms,
            "reducedMotion": self.reduced_motion,
        }


@dataclass(frozen=True)
class SessionPeripherals:
    state: str
    discs: tuple[DiscEntry, ...]
    active_disc: int | None
    bezels: tuple[BezelEntry, ...]
    fade: FadeState
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "state": self.state,
            "available": bool(self.discs or self.bezels),
            "discs": [entry.to_dict() for entry in self.discs],
            "activeDisc": self.active_disc,
            "bezels": [entry.to_dict() for entry in self.bezels],
            "fade": self.fade.to_dict(),
            "reason": self.reason,
        }


def _disc(raw: Any, index: int, active: int | None) -> DiscEntry | None:
    if not isinstance(raw, Mapping):
        return None
    identifier = _text(raw.get("id"), limit=64)
    label = _text(raw.get("label"), limit=128)
    if not identifier or not label:
        return None
    return DiscEntry(
        id=identifier,
        label=label,
        index=index,
        inserted=raw.get("inserted") is True or active == index,
        available=raw.get("available", True) is True,
        compatible=raw.get("compatible", True) is True,
        reason=_text(raw.get("reason") or raw.get("detail")),
    )


def _bezel(raw: Any, index: int, selected: str) -> BezelEntry | None:
    if not isinstance(raw, Mapping):
        return None
    identifier = _text(raw.get("id"), limit=64)
    label = _text(raw.get("label"), limit=128)
    if not identifier or not label:
        return None
    asset_url = _asset(raw.get("assetUrl"))
    available = raw.get("available", bool(asset_url)) is True and bool(asset_url)
    reason = _text(raw.get("reason") or raw.get("detail"))
    if not available and not reason:
        reason = "Esta moldura não está disponível para a sessão."
    return BezelEntry(
        id=identifier,
        label=label,
        asset_url=asset_url,
        available=available,
        selected=identifier == selected,
        reason=reason,
    )


def resolve_session_peripherals(raw: Any, *, reduced_motion: bool = False) -> SessionPeripherals:
    """Sanitize the adapter projection for the Theme Engine."""

    source = raw if isinstance(raw, Mapping) else {}
    active_raw = source.get("activeDisc")
    active = (
        active_raw if isinstance(active_raw, int) and not isinstance(active_raw, bool) else None
    )
    discs: list[DiscEntry] = []
    raw_discs = source.get("discs")
    if isinstance(raw_discs, Sequence) and not isinstance(raw_discs, (str, bytes, bytearray)):
        for index, candidate in enumerate(raw_discs[:MAX_DISCS]):
            parsed_disc = _disc(candidate, index, active)
            if parsed_disc is not None:
                discs.append(parsed_disc)

    selected = _text(source.get("selectedBezel"), limit=64)
    bezels: list[BezelEntry] = []
    raw_bezels = source.get("bezels")
    if isinstance(raw_bezels, Sequence) and not isinstance(raw_bezels, (str, bytes, bytearray)):
        for index, candidate in enumerate(raw_bezels[:MAX_BEZELS]):
            parsed_bezel = _bezel(candidate, index, selected)
            if parsed_bezel is not None:
                bezels.append(parsed_bezel)

    raw_fade_value = source.get("fade")
    raw_fade: Mapping[str, Any] = raw_fade_value if isinstance(raw_fade_value, Mapping) else {}
    phase = _text(raw_fade.get("phase"), fallback="idle", limit=16)
    if phase not in {"idle", "in", "out", "return", "error"}:
        phase = "error"
    progress_raw = raw_fade.get("progress", 0.0)
    progress = float(progress_raw) if isinstance(progress_raw, (int, float)) else 0.0
    progress = min(1.0, max(0.0, progress))
    duration_raw = raw_fade.get("durationMs", 180)
    duration = duration_raw if isinstance(duration_raw, int) and duration_raw >= 0 else 180
    fade = FadeState(phase, progress, min(duration, 10_000), reduced_motion)
    state = _text(source.get("state"), fallback="unavailable", limit=16)
    if state not in {"unavailable", "ready", "degraded", "error"}:
        state = "degraded"
    reason = _text(source.get("reason") or source.get("detail"))
    if state == "unavailable" and not reason:
        reason = "O adapter desta sessão não oferece periféricos de mídia."
    return SessionPeripherals(state, tuple(discs), active, tuple(bezels), fade, reason)


def unavailable_peripherals(reason: str) -> SessionPeripherals:
    return resolve_session_peripherals({"state": "unavailable", "reason": reason})


__all__ = [
    "MAX_BEZELS",
    "MAX_DISCS",
    "BezelEntry",
    "DiscEntry",
    "FadeState",
    "SessionPeripherals",
    "resolve_session_peripherals",
    "unavailable_peripherals",
]
