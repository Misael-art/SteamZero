# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Requisitos de plataforma não podem vazar da fachada Switch."""

from __future__ import annotations

from typing import Any

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.emulation_workspace import (
    build_emulation_workspace,
    build_global_management,
)
from steamzero.domain.platform_composer import EmulatorFacts
from steamzero.domain.platforms import PlatformRegistry, load_platform_manifest


def _installed(adapter_id: str) -> EmulatorFacts:
    return EmulatorFacts(
        adapter_id=adapter_id,
        display_name=adapter_id,
        icon_asset="../assets/retroarch.svg",
        installable=True,
        installed=True,
        version="test",
    )


def _platform(payload: dict[str, Any], platform_id: str) -> dict[str, Any]:
    return next(item for item in payload["platforms"] if item["id"] == platform_id)


def test_manifest_requirements_are_explicit_and_scoped() -> None:
    registry = PlatformRegistry.bundled()

    assert registry.get("switch").requirements == ("keys", "firmware")
    assert registry.get("playstation-3").requirements == ("firmware",)
    assert registry.get("nes-famicom").requirements == ()


def test_placeholder_does_not_publish_keys_or_firmware_for_nes() -> None:
    platform = _platform(build_emulation_workspace(), "nes-famicom")

    assert platform["requirements"] == {}


def test_ps3_publishes_firmware_as_unverified_without_claiming_keys() -> None:
    payload = build_emulation_workspace(emulator_facts=_installed)
    platform = _platform(payload, "playstation-3")

    assert set(platform["requirements"]) == {"firmware"}
    assert platform["requirements"]["firmware"]["status"] == "unverified"
    assert platform["requirements"]["firmware"]["blocksPlay"] is False


def test_global_card_uses_not_applicable_for_nes_and_firmware_for_ps3() -> None:
    payload = build_emulation_workspace(emulator_facts=_installed)
    editorial_platforms = [{"id": item["id"], "games": []} for item in payload["platforms"]]
    management = build_global_management(
        platforms=payload["platforms"],
        editorial_platforms=editorial_platforms,
        canonical_experiences=payload["canonicalExperiences"],
        truth_state=str(payload["truthState"]),
        emulators=[],
        directories=[],
        media_providers=[],
    )
    cards = {card["id"]: card for card in management["platformCards"]}

    assert cards["nes-famicom"]["keysStatus"]["status"] == "not-required"
    assert cards["nes-famicom"]["firmwareStatus"]["status"] == "not-required"
    assert cards["playstation-3"]["keysStatus"]["status"] == "not-required"
    assert cards["playstation-3"]["firmwareStatus"]["status"] == "unverified"


def test_manifest_rejects_unknown_requirement_kind() -> None:
    source = next(item for item in PlatformRegistry.bundled().list() if item.id == "switch")
    data = {
        "schemaVersion": source.schema_version,
        "id": source.id,
        "kind": source.kind,
        "name": source.name,
        "shortName": source.short_name,
        "iconKey": source.icon_key,
        "artworkAsset": source.artwork_asset,
        "systems": list(source.systems),
        "capabilities": [dict(item) for item in source.capabilities],
        "areas": [dict(item) for item in source.areas],
        "emulators": [dict(item) for item in source.emulators],
        "media": dict(source.media),
        "controls": dict(source.controls),
        "timing": dict(source.timing),
        "presets": [dict(item) for item in source.presets],
        "cloud": source.cloud,
        "requirements": ["bios"],
    }

    with pytest.raises(SteamZeroError):
        load_platform_manifest(data)
