# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

from steamzero.adapters.launcher_catalog import CatalogGame
from steamzero.adapters.launcher_ui import LauncherBridge
from steamzero.launcher.app import _search_catalog_records
from steamzero.launcher.navigation import HomeSection


def _bridge(tmp_path: Path) -> LauncherBridge:
    return LauncherBridge(
        sections=(HomeSection(id="switch", title="Switch", items=("mario", "zelda")),),
        context_path=tmp_path / "return.json",
        on_launch=lambda game, focus: None,
        titles={
            "mario": "Mário Kart 8 Deluxe (USA).nsp",
            "zelda": "The Legend of Zelda",
        },
        catalog_records=(
            {
                "id": "mario",
                "title": "Mário Kart 8 Deluxe (USA).nsp",
                "platformId": "switch",
                "systemId": "switch-handheld",
            },
            {
                "id": "zelda",
                "title": "The Legend of Zelda",
                "platformId": "switch",
                "systemId": "switch",
            },
        ),
        metadata={"mario": {"fanartUrl": "file:///managed/mario-fanart.jpg"}},
    )


def test_bridge_search_uses_canonical_text_scope_and_media(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)

    result = bridge.search(
        {
            "query": "MARIO KART",
            "platformId": "SWITCH",
            "systemId": "switch-handheld",
            "mediaKind": "fanart",
        }
    )

    assert [game["id"] for game in result["games"]] == ["mario"]
    assert result["games"][0]["fanartUrl"] == "file:///managed/mario-fanart.jpg"


def test_bridge_search_keeps_platform_and_system_filters_independent(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)

    assert [game["id"] for game in bridge.search({"platform": "switch"})["games"]] == [
        "mario",
        "zelda",
    ]
    assert [game["id"] for game in bridge.search({"system": "switch"})["games"]] == ["zelda"]


def test_qml_legacy_search_route_uses_the_same_contract(tmp_path: Path) -> None:
    bridge = _bridge(tmp_path)
    query = urllib.parse.urlencode(
        {
            "q": "mArIo",
            "platform": "switch",
            "systemId": "switch-handheld",
        }
    )

    with bridge.serving() as base:
        request = urllib.request.Request(  # noqa: S310
            f"{base}/search?{query}",
            headers={"X-SteamZero-Token": bridge.token},
        )
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            payload = json.loads(response.read())

    assert payload["query"] == "mArIo"
    assert [game["id"] for game in payload["games"]] == ["mario"]


def test_entrypoint_preserves_source_system_when_building_search_catalog() -> None:
    records = _search_catalog_records(
        (
            CatalogGame(
                id="mario",
                title="Mário Kart",
                platform="switch",
                platform_label="Nintendo Switch",
            ),
        ),
        ({"id": "mario", "platformId": "switch", "systemId": "switch-handheld"},),
    )

    assert records[0]["platformId"] == "switch"
    assert records[0]["systemId"] == "switch-handheld"
