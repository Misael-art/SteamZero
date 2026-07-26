# SPDX-License-Identifier: GPL-3.0-or-later
"""Contrato e registry declarativo de plataformas (F5)."""

from __future__ import annotations

import copy
import json
from contextlib import suppress
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from steamzero.adapters.registry import AdapterRegistry
from steamzero.api import contracts
from steamzero.core.errors import SteamZeroError
from steamzero.domain.platforms import (
    PlatformRegistry,
    load_platform_manifest,
    platform_placeholder,
)

MANIFESTS = Path("src/steamzero/platform_manifests")
ASSETS = Path("src/steamzero/ui/assets")
QML = Path("src/steamzero/ui/qml")


def _raw(name: str) -> dict[str, Any]:
    value = json.loads((MANIFESTS / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_bundled_registry_covers_required_platforms_with_unique_artwork() -> None:
    registry = PlatformRegistry.bundled()
    manifests = registry.list()

    assert [manifest.id for manifest in manifests] == [
        "switch",
        "nintendo-handheld",
        "nes-famicom",
        "snes",
        "mega-drive",
        "arcade",
        "playstation",
        "geforce-now",
        "xbox-cloud-gaming",
        "amazon-luna",
        "nintendo-console",
        "master-system",
        "game-gear",
        "pc-engine-turbografx",
        "atari-classics",
        "neo-geo-pocket",
        "wonderswan",
        "msx",
        "zx-spectrum",
        "commodore-64",
        "amiga",
        "colecovision",
        "intellivision",
        "virtual-boy",
        "three-do",
        "sega-cd-32x",
        "nintendo-64",
        "playstation-2",
        "playstation-portable",
        "dreamcast",
        "nintendo-ds",
        "nintendo-3ds",
        "wii-u",
        "playstation-3",
        "xbox",
        "xbox-360",
    ]
    artwork = [manifest.artwork_asset for manifest in manifests]
    shared_artwork = {asset for asset in artwork if artwork.count(asset) > 1}
    assert shared_artwork == {"../assets/retroarch.svg"}
    assert all((ASSETS / Path(asset).name).is_file() for asset in artwork)
    adapter_ids = {manifest.id for manifest in AdapterRegistry.bundled().list()}
    referenced_adapters = {
        str(emulator["adapterId"])
        for manifest in manifests
        for emulator in manifest.emulators
        if emulator["adapterId"] is not None
    }
    assert referenced_adapters <= adapter_ids
    assert registry.get("switch").systems == ("switch",)
    assert "zip" in registry.get("switch").media["extensions"]
    with pytest.raises(SteamZeroError, match="plataforma desconhecida"):
        registry.get("missing")


def test_retroarch_group_one_is_fully_declarative() -> None:
    registry = PlatformRegistry.bundled()
    group_ids = [
        "master-system",
        "game-gear",
        "pc-engine-turbografx",
        "atari-classics",
        "neo-geo-pocket",
        "wonderswan",
        "msx",
        "zx-spectrum",
        "commodore-64",
        "amiga",
        "colecovision",
        "intellivision",
        "virtual-boy",
        "three-do",
        "sega-cd-32x",
        "nintendo-64",
    ]

    manifests = [registry.get(platform_id) for platform_id in group_ids]
    assert all(manifest.artwork_asset == "../assets/retroarch.svg" for manifest in manifests)
    assert all(
        [(emulator["id"], emulator["adapterId"]) for emulator in manifest.emulators]
        == [("retroarch", "retroarch")]
        for manifest in manifests
    )
    assert all(
        manifest.controls["profiles"] == ["retroarch-classic-gamepad"] for manifest in manifests
    )
    assert all(manifest.media["extensions"] for manifest in manifests)
    assert "sms" in registry.get("master-system").media["extensions"]
    assert "gg" in registry.get("game-gear").media["extensions"]
    assert "pce" in registry.get("pc-engine-turbografx").media["extensions"]
    assert "j64" in registry.get("atari-classics").media["extensions"]
    assert "z64" in registry.get("nintendo-64").media["extensions"]


def test_emulation_ui_has_no_switch_specific_routing_or_copy() -> None:
    source = "\n".join(
        (QML / name).read_text(encoding="utf-8") for name in ("Emulation.qml", "Main.qml")
    )

    assert "switch" not in source.casefold()


def test_manifests_publish_all_capability_dimensions_and_safe_cloud_hosts() -> None:
    manifests = PlatformRegistry.bundled().list()
    for manifest in manifests:
        assert manifest.capabilities
        assert manifest.areas
        assert manifest.media["artworkKinds"]
        assert manifest.controls["profiles"]
        assert manifest.timing["unknownFallback"] == "unknown-explicit"
        assert manifest.presets
        if manifest.kind == "cloud":
            assert manifest.cloud is not None
            assert manifest.cloud["launchUrl"].startswith("https://")
            assert manifest.emulators == ()
        else:
            assert manifest.cloud is None
            assert manifest.emulators

    assert PlatformRegistry.bundled().get("arcade").controls["specialized"] == [
        "trackball",
        "spinner",
        "light-gun",
        "twin-stick",
        "wheel",
        "paddle",
        "fight-stick",
    ]


def test_placeholder_is_contract_valid_and_actions_remain_disabled() -> None:
    manifest = PlatformRegistry.bundled().get("xbox-cloud-gaming")
    platform = platform_placeholder(manifest)
    payload = {
        "schemaVersion": 1,
        "truthState": "planned",
        "contextLabel": "Catálogo",
        "platforms": [platform],
    }

    contracts.validate(payload, "emulation-workspace-v1.schema.json")
    assert platform["cloud"]["allowedHosts"] == ["www.xbox.com"]
    assert platform["areas"][1]["id"] == "advanced"
    action = platform["areaData"]["advanced"]["primaryAction"]
    assert action["id"] == "cloud.launch"
    assert action["enabled"] is False
    assert action["reason"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda data: data["capabilities"].append(copy.deepcopy(data["capabilities"][0])),
        lambda data: data["areas"].append(copy.deepcopy(data["areas"][0])),
        lambda data: data["emulators"].append(copy.deepcopy(data["emulators"][0])),
        lambda data: data["presets"].append(copy.deepcopy(data["presets"][0])),
        lambda data: data["emulators"].append(
            {
                **copy.deepcopy(data["emulators"][0]),
                "id": "other",
            }
        ),
        lambda data: data["areas"][0].update({"capabilityId": "missing"}),
        lambda data: data["capabilities"][1].update(
            {"action": copy.deepcopy(data["capabilities"][0]["action"])}
        ),
    ],
)
def test_manifest_rejects_duplicate_or_dangling_references(mutate) -> None:  # type: ignore[no-untyped-def]
    data = _raw("01-switch.platform.json")
    mutate(data)
    with pytest.raises(SteamZeroError, match=r"duplicad|ausentes"):
        load_platform_manifest(data)


@pytest.mark.parametrize(
    "launch_url",
    [
        "http://play.geforcenow.com/",
        "https://evil.example/",
        "https://user@play.geforcenow.com/",
        "https://play.geforcenow.com:444/",
        "https://play.geforcenow.com:99999/",
    ],
)
def test_cloud_launch_url_fails_closed_outside_exact_https_allowlist(
    launch_url: str,
) -> None:
    data = _raw("08-geforce-now.platform.json")
    data["cloud"]["launchUrl"] = launch_url
    with pytest.raises(SteamZeroError, match="E-API-SCHEMA"):
        load_platform_manifest(data)


def test_kind_and_payload_cannot_cross_cloud_boundary() -> None:
    emulated = _raw("01-switch.platform.json")
    emulated["cloud"] = {
        "launchUrl": "https://play.geforcenow.com/",
        "allowedHosts": ["play.geforcenow.com"],
        "requiresSubscription": True,
    }
    with pytest.raises(SteamZeroError, match="não pode declarar cloud"):
        load_platform_manifest(emulated)

    cloud = _raw("08-geforce-now.platform.json")
    cloud["emulators"] = [
        {
            "id": "fake",
            "name": "Fake",
            "adapterId": None,
            "precedence": 1,
            "role": "primary",
        }
    ]
    with pytest.raises(SteamZeroError, match="não aceita emuladores"):
        load_platform_manifest(cloud)


def test_registry_rejects_duplicate_platform_ids() -> None:
    manifest = load_platform_manifest(_raw("01-switch.platform.json"))
    with pytest.raises(SteamZeroError, match="plataforma duplicada"):
        PlatformRegistry([manifest, manifest])


@settings(max_examples=50, deadline=None)
@given(
    st.dictionaries(
        st.text(max_size=24),
        st.one_of(
            st.none(),
            st.booleans(),
            st.integers(),
            st.text(max_size=80),
            st.lists(st.text(max_size=30), max_size=8),
        ),
        max_size=24,
    )
)
def test_manifest_parser_never_leaks_untyped_exception(data: dict[str, Any]) -> None:
    with suppress(SteamZeroError):
        load_platform_manifest(data)
