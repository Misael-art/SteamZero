# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Vocabulário canônico do lifecycle de sessões de jogo."""

from __future__ import annotations

SESSION_STATES = frozenset(
    {
        "idle",
        "launching",
        "running",
        "suspending",
        "suspended",
        "resuming",
        "closing",
        "closed",
        "failed",
    }
)

SESSION_OWNER = "steamzero-game-session"

ACTIVE_SESSION_STATES = frozenset(SESSION_STATES - {"closed", "failed"})

VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "idle": frozenset({"launching"}),
    "launching": frozenset({"running", "failed"}),
    "running": frozenset({"suspending", "closing", "closed", "failed"}),
    "suspending": frozenset({"suspended", "failed"}),
    "suspended": frozenset({"resuming", "closing", "failed"}),
    "resuming": frozenset({"running", "failed"}),
    "closing": frozenset({"closed", "failed"}),
    "closed": frozenset(),
    "failed": frozenset(),
}

_LEGACY_STATES = {
    "active": "running",
    "exited": "closed",
    "interrupted": "failed",
}


def normalize_session_state(value: object) -> str:
    """Converte estados M11 antigos sem inventar sucesso para valores desconhecidos."""
    state = str(value or "unknown")
    return _LEGACY_STATES.get(state, state)


def can_transition(current: str, target: str) -> bool:
    return target in VALID_TRANSITIONS.get(current, frozenset())
