# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""The Launcher selects an accelerated, bounded Qt Quick backend."""

from __future__ import annotations

from steamzero.adapters import launcher_ui


def test_launcher_defaults_to_opengl(monkeypatch) -> None:
    monkeypatch.delenv("STEAMZERO_QT_QUICK_BACKEND", raising=False)
    assert launcher_ui._resolve_qt_quick_backend() == "opengl"


def test_launcher_allows_explicit_software_degradation(monkeypatch) -> None:
    monkeypatch.setenv("STEAMZERO_QT_QUICK_BACKEND", "software")
    assert launcher_ui._resolve_qt_quick_backend() == "software"


def test_launcher_rejects_unallowlisted_backend(monkeypatch) -> None:
    monkeypatch.setenv("STEAMZERO_QT_QUICK_BACKEND", "vulkan-experimental")
    assert launcher_ui._resolve_qt_quick_backend() == "opengl"
