# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Tests for the real-window launcher performance evidence contract."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_tool():
    root = Path(__file__).resolve().parents[2]
    theme_path = root / "tools" / "theme_perf_probe.py"
    theme_spec = importlib.util.spec_from_file_location("theme_perf_probe", theme_path)
    if theme_spec is None or theme_spec.loader is None:
        raise RuntimeError("theme_perf_probe ausente")
    theme_module = importlib.util.module_from_spec(theme_spec)
    sys.modules[theme_spec.name] = theme_module
    theme_spec.loader.exec_module(theme_module)

    probe_path = root / "tools" / "launcher_perf_probe.py"
    probe_spec = importlib.util.spec_from_file_location("launcher_perf_probe", probe_path)
    if probe_spec is None or probe_spec.loader is None:
        raise RuntimeError("launcher_perf_probe ausente")
    probe_module = importlib.util.module_from_spec(probe_spec)
    sys.modules[probe_spec.name] = probe_module
    probe_spec.loader.exec_module(probe_module)
    return probe_module


probe = _load_tool()


def _report(
    *,
    startup: float | None = 932,
    p95: float | None = 16.176,
    frames: int = 375,
    vram: int | None = 123980,
) -> dict[str, object]:
    return {
        "startupMs": startup,
        "frameTime": {"frames": frames, "p95Ms": p95},
        "peakVramKb": vram,
    }


def test_valid_real_window_sample_passes_the_three_budgets() -> None:
    validation = probe.evaluate_budget(_report())

    assert validation["valid"] is True
    assert validation["meetsBudget"] is True
    assert all(item["passed"] for item in validation["checks"].values())


@pytest.mark.parametrize(
    "payload,failed_check",
    [
        (_report(p95=16.701), "frameTimeP95"),
        (_report(startup=2000.001), "startup"),
        (_report(vram=512 * 1024 + 1), "vram"),
    ],
)
def test_budget_failure_is_reported_without_being_hidden(payload, failed_check) -> None:
    validation = probe.evaluate_budget(payload)

    assert validation["valid"] is True
    assert validation["meetsBudget"] is False
    assert validation["checks"][failed_check]["passed"] is False


def test_missing_vram_invalidates_certification_instead_of_becoming_zero() -> None:
    validation = probe.evaluate_budget(_report(vram=None))

    assert validation["valid"] is False
    assert validation["meetsBudget"] is False
    assert validation["checks"]["vram"]["passed"] is False


def test_insufficient_frames_invalidates_the_sample() -> None:
    validation = probe.evaluate_budget(_report(frames=119))

    assert validation["valid"] is False
    assert validation["meetsBudget"] is False
