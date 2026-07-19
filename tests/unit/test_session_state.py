# SPDX-License-Identifier: GPL-3.0-or-later
"""Vocabulário compartilhado do lifecycle de sessões."""

from steamzero.core.session_state import (
    ACTIVE_SESSION_STATES,
    SESSION_STATES,
    can_transition,
    normalize_session_state,
)


def test_canonical_states_and_transitions_cover_runtime_and_suspend() -> None:
    assert {"launching", "running", "suspended", "closing", "closed", "failed"}.issubset(
        SESSION_STATES
    )
    assert "running" in ACTIVE_SESSION_STATES
    assert "closed" not in ACTIVE_SESSION_STATES
    assert can_transition("launching", "running") is True
    assert can_transition("running", "closed") is True
    assert can_transition("closed", "running") is False


def test_legacy_runtime_states_are_normalized_without_masking_unknown() -> None:
    assert normalize_session_state("active") == "running"
    assert normalize_session_state("exited") == "closed"
    assert normalize_session_state("interrupted") == "failed"
    assert normalize_session_state("vendor-new-state") == "vendor-new-state"
