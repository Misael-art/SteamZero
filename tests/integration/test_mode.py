# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do Mode Manager (F-SD-02): cadeia de fallback de display (AC-SD-01/FM-18)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from steamzero.core import state
from steamzero.domain.mode import DisplayProfile, ModeManager, fallback_chain


class FakeDisplayPort:
    """Aplica com sucesso, exceto perfis cujo label está em ``fail_labels``."""

    def __init__(self, fail_labels: set[str] | None = None) -> None:
        self._fail = fail_labels or set()
        self.applied: list[str] = []

    def apply(self, profile: DisplayProfile) -> bool:
        self.applied.append(profile.label)
        return profile.label not in self._fail


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[state.StateStore]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    s = state.open_state()
    yield s
    s.close()


def test_handheld_uses_internal(store: state.StateStore) -> None:
    port = FakeDisplayPort()
    result = ModeManager(port, store).apply_mode("handheld")
    assert result.applied.output == "internal"
    assert result.fallback_step == 0
    assert result.degraded is False


def test_docked_tv_target_applies_clean(store: state.StateStore) -> None:
    port = FakeDisplayPort()
    result = ModeManager(port, store).apply_mode("docked-tv")
    assert result.applied.label == "target"
    assert result.degraded is False
    assert port.applied == ["target"]  # não precisou degradar


def test_docked_tv_falls_back_when_target_fails(store: state.StateStore) -> None:
    # alvo e no-hdr falham -> aplica no-vrr (degrau 2), degradado
    port = FakeDisplayPort(fail_labels={"target", "no-hdr"})
    result = ModeManager(port, store).apply_mode("docked-tv")
    assert result.applied.label == "no-vrr"
    assert result.fallback_step == 2
    assert result.degraded is True


def test_all_external_fail_falls_to_internal(store: state.StateStore) -> None:
    # todos os externos falham -> tela interna, sempre válida
    port = FakeDisplayPort(fail_labels={"target", "no-hdr", "no-vrr", "lower-hz", "lower-res"})
    result = ModeManager(port, store).apply_mode("docked-tv")
    assert result.applied.output == "internal"
    assert result.degraded is True


def test_current_is_none_when_no_mode_applied(store: state.StateStore) -> None:
    cur = ModeManager(FakeDisplayPort(), store).current()
    assert cur is None


def test_current_mode_persisted(store: state.StateStore) -> None:
    ModeManager(FakeDisplayPort(), store).apply_mode("desktop")
    cur = ModeManager(FakeDisplayPort(), store).current()
    assert cur is not None
    assert cur["mode"] == "desktop"


def test_fallback_chain_invalid_mode() -> None:
    with pytest.raises(ValueError):
        fallback_chain("teletransporte")


def test_fallback_chain_ends_in_internal() -> None:
    for mode in ("docked-tv", "docked-monitor", "desktop", "handheld", "unknown"):
        assert fallback_chain(mode)[-1].output == "internal"
