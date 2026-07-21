# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""WI-2: catálogo de emuladores de Switch — precedência e disponibilidade honesta."""

from __future__ import annotations

import pytest

from steamzero.domain.switch_emulators import (
    STATE_INSTALLED,
    STATE_NOT_INSTALLED,
    STATE_UNVERIFIED,
    SWITCH_EMULATORS,
    SwitchEmulator,
    SwitchEmulatorCatalog,
)


def test_catalog_is_ordered_by_precedence() -> None:
    catalog = SwitchEmulatorCatalog()
    ids = [e.id for e in catalog.emulators()]
    assert ids == ["eden", "citron", "ryubing"]
    precedences = [e.precedence for e in catalog.emulators()]
    assert precedences == sorted(precedences)


def test_every_emulator_requires_prod_keys_and_firmware() -> None:
    for emulator in SWITCH_EMULATORS:
        assert emulator.keyset == "prod"
        assert emulator.requires_firmware is True


def test_to_dict_declares_requirements() -> None:
    entry = SwitchEmulatorCatalog().by_id("eden").to_dict()
    assert entry["requiresKeys"] == {"platform": "switch", "keyset": "prod"}
    assert entry["requiresFirmware"] == {"platform": "switch"}


def test_availability_without_probe_is_unverified() -> None:
    entries = SwitchEmulatorCatalog().availability()
    assert {e["installState"] for e in entries} == {STATE_UNVERIFIED}
    # o catálogo de domínio não resolve fontes; somente o registry pode promovê-las
    assert all(e["installable"] is False for e in entries)
    assert all(e["sourceState"] == STATE_UNVERIFIED for e in entries)
    assert all(e["reason"] for e in entries)


def test_availability_with_probe_reports_real_state() -> None:
    def probe(emulator_id: str) -> bool | None:
        return {"eden": True, "citron": False, "ryubing": None}[emulator_id]

    by_id = {e["id"]: e for e in SwitchEmulatorCatalog().availability(probe=probe)}
    assert by_id["eden"]["installState"] == STATE_INSTALLED
    assert by_id["citron"]["installState"] == STATE_NOT_INSTALLED
    assert by_id["ryubing"]["installState"] == STATE_UNVERIFIED
    # mesmo detectado, instalação gerenciada segue indisponível (sem fonte pinada)
    assert by_id["eden"]["installable"] is False


def test_preferred_returns_first_installed_by_precedence() -> None:
    catalog = SwitchEmulatorCatalog()
    assert catalog.preferred() is None  # sem probe

    def probe(emulator_id: str) -> bool | None:
        return emulator_id in {"citron", "ryubing"}

    assert catalog.preferred(probe=probe) == "citron"


def test_duplicate_precedence_is_rejected() -> None:
    dup = (
        SwitchEmulator("a", "A", 1, "prod", True, ""),
        SwitchEmulator("b", "B", 1, "prod", True, ""),
    )
    with pytest.raises(ValueError, match="precedências"):
        SwitchEmulatorCatalog(dup)


def test_unknown_id_returns_none() -> None:
    assert SwitchEmulatorCatalog().by_id("yuzu") is None
