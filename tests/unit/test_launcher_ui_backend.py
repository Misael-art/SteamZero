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


def test_launcher_defaults_to_basic_render_loop_for_stable_frame_pacing(monkeypatch) -> None:
    monkeypatch.delenv("STEAMZERO_QSG_RENDER_LOOP", raising=False)
    monkeypatch.delenv("QSG_RENDER_LOOP", raising=False)
    assert launcher_ui._resolve_qsg_render_loop() == "basic"


def test_launcher_accepts_bounded_render_loop_override(monkeypatch) -> None:
    monkeypatch.setenv("STEAMZERO_QSG_RENDER_LOOP", "threaded")
    assert launcher_ui._resolve_qsg_render_loop() == "threaded"

    monkeypatch.setenv("STEAMZERO_QSG_RENDER_LOOP", "untrusted")
    assert launcher_ui._resolve_qsg_render_loop() == "basic"


def test_launcher_accepts_only_loopback_performance_report(monkeypatch) -> None:
    monkeypatch.setenv("STEAMZERO_PERF_REPORT_URL", "http://127.0.0.1:1234/report")
    assert launcher_ui._performance_report_url() == "http://127.0.0.1:1234/report"

    monkeypatch.setenv("STEAMZERO_PERF_REPORT_URL", "https://example.test/report")
    assert launcher_ui._performance_report_url() == ""
