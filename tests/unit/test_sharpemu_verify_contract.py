# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato de smoke do SharpEmu no deployment real."""

from __future__ import annotations

import json
from pathlib import Path


def test_sharpemu_help_contract_accepts_documented_exit() -> None:
    manifest_path = (
        Path(__file__).parents[2] / "src/steamzero/adapters/manifests/sharpemu.adapter.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    verify = manifest["verify"]
    assert verify["smokeTest"] == ["--help"]
    assert verify["smokeExitCodes"] == [0, 1]
