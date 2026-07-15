# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Adapters declarativos e engine transacional de componentes."""

from steamzero.adapters.engine import AdapterEngine, ArtifactPort, PreparedComponent
from steamzero.adapters.flatpak import (
    FlatpakApplyResult,
    FlatpakCLI,
    FlatpakExecutor,
    FlatpakPlan,
    FlatpakPort,
    FlatpakState,
)
from steamzero.adapters.lockfile import (
    ComponentLock,
    LockedComponent,
    LockedSource,
    bundled_component_lock,
)
from steamzero.adapters.registry import AdapterManifest, AdapterRegistry, AdapterSource

__all__ = [
    "AdapterEngine",
    "AdapterManifest",
    "AdapterRegistry",
    "AdapterSource",
    "ArtifactPort",
    "ComponentLock",
    "FlatpakApplyResult",
    "FlatpakCLI",
    "FlatpakExecutor",
    "FlatpakPlan",
    "FlatpakPort",
    "FlatpakState",
    "LockedComponent",
    "LockedSource",
    "PreparedComponent",
    "bundled_component_lock",
]
