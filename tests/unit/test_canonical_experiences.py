# SPDX-License-Identifier: GPL-3.0-or-later
"""Contrato do catálogo canônico usado pelo tema."""

from __future__ import annotations

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.canonical_experiences import (
    CanonicalExperience,
    CanonicalExperienceRegistry,
)
from steamzero.domain.platforms import PlatformRegistry


def test_catalog_is_complete_unique_and_truthful() -> None:
    experiences = CanonicalExperienceRegistry.bundled().list()

    assert len(experiences) == 155
    assert len({item.id for item in experiences}) == len(experiences)
    assert {item.kind for item in experiences} == {
        "hardware",
        "expansion",
        "enhancement",
        "arcade-board",
        "computer",
        "engine",
        "store",
        "cloud",
    }
    assert not any(item.status == "certified" for item in experiences)
    assert CanonicalExperienceRegistry.bundled().get("playstation-4").status == "experimental"
    assert CanonicalExperienceRegistry.bundled().get("store-xbox-pc").status == "unavailable"


def test_requested_historical_experiences_are_not_collapsed() -> None:
    registry = CanonicalExperienceRegistry.bundled()
    required = {
        "game-boy",
        "game-boy-color",
        "game-boy-advance",
        "neo-geo-pocket",
        "neo-geo-pocket-color",
        "nintendo-64dd",
        "sega-cd-32x",
        "snes-msu1",
        "mega-drive-enhanced",
        "atari-jaguar-cd",
        "playstation-4",
        "engine-mugen",
        "pc-dos",
        "store-steam",
    }

    assert required <= {item.id for item in registry.list()}
    assert registry.get("game-boy").technical_platform_id == "nintendo-handheld"
    assert registry.get("game-boy-color").technical_platform_id == "nintendo-handheld"
    assert registry.get("game-boy").id != registry.get("game-boy-color").id


def test_every_technical_reference_resolves() -> None:
    technical_ids = {item.id for item in PlatformRegistry.bundled().list()}
    references = {
        item.technical_platform_id
        for item in CanonicalExperienceRegistry.bundled().list()
        if item.technical_platform_id is not None
    }

    assert references <= technical_ids


def test_registry_rejects_duplicate_and_dangling_parent() -> None:
    base = CanonicalExperience(
        id="demo",
        name="Demo",
        kind="hardware",
        group_id="tests",
        group_name="Testes",
        status="planned",
        technical_platform_id=None,
        parent_id=None,
        runtimes=(),
    )
    with pytest.raises(SteamZeroError, match="duplicada"):
        CanonicalExperienceRegistry([base, base])
    with pytest.raises(SteamZeroError, match="pais ausentes"):
        CanonicalExperienceRegistry(
            [CanonicalExperience(**{**base.__dict__, "id": "child", "parent_id": "missing"})]
        )


def test_unknown_experience_fails_closed() -> None:
    with pytest.raises(SteamZeroError, match="experiência canônica desconhecida"):
        CanonicalExperienceRegistry.bundled().get("missing")
