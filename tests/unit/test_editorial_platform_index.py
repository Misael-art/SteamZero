# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from steamzero.adapters.emulation import editorial_platform_index
from steamzero.api import contracts
from steamzero.domain.emulation_workspace import build_switch_workspace
from steamzero.domain.platforms import PlatformRegistry


def test_editorial_index_keeps_every_canonical_platform_and_only_scanned_games() -> None:
    registry = PlatformRegistry.bundled()
    rows = editorial_platform_index(
        registry,
        [
            {"id": "psx-game", "name": "Owned game", "platform": "playstation"},
            {"id": "unknown", "name": "Unclassified"},
        ],
    )

    assert [row["id"] for row in rows] == [item.id for item in registry.list()]
    playstation = next(row for row in rows if row["id"] == "playstation")
    assert [game["id"] for game in playstation["games"]] == ["psx-game"]
    assert playstation["state"] == "ready"
    assert all(
        row["state"] == "unverified" and row["games"] == []
        for row in rows
        if row["id"] != "playstation"
    )
    workspace = build_switch_workspace()
    workspace["editorialPlatforms"] = rows
    contracts.validate(workspace, "emulation-workspace-v1.schema.json")
