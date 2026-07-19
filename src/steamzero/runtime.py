# SPDX-License-Identifier: GPL-3.0-or-later
"""Composition root das capacidades Linux concretas."""

from __future__ import annotations

from typing import Any

from steamzero.adapters.linux_runtime import LinuxSessionEnvironment
from steamzero.domain.device import classify


def observe_session_environment() -> dict[str, Any]:
    data = LinuxSessionEnvironment().snapshot()
    device = data.get("device")
    if isinstance(device, dict):
        dmi = device.get("dmi")
        signals = device.get("signals")
        device["kind"] = classify(
            dmi if isinstance(dmi, dict) else {},
            signals if isinstance(signals, dict) else {},
        )
    return data
