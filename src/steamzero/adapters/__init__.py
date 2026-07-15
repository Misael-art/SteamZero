# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Adapters declarativos e engine transacional de componentes."""

from steamzero.adapters.engine import AdapterEngine, ArtifactPort, PreparedComponent
from steamzero.adapters.registry import AdapterManifest, AdapterRegistry, AdapterSource

__all__ = [
    "AdapterEngine",
    "AdapterManifest",
    "AdapterRegistry",
    "AdapterSource",
    "ArtifactPort",
    "PreparedComponent",
]
