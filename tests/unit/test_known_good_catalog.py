# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Onda 1: catálogo de perfis conhecidos bons v2 (identidade tipada)."""

from __future__ import annotations

import pytest
from jsonschema import ValidationError

from steamzero.api import contracts
from steamzero.core.errors import SteamZeroError
from steamzero.domain.emulator_config import (
    EmulatorConfigurator,
    KnownGoodProfileCatalog,
)
from steamzero.domain.game_identity import GameIdentity, IdentityScheme

_V2_SCHEMA = "known-good-profile-v2.schema.json"


def _v2_catalog(platform: str = "playstation-2") -> KnownGoodProfileCatalog:
    return KnownGoodProfileCatalog(
        {
            "schemaVersion": 2,
            "platform": platform,
            "entries": [
                {
                    "identity": {"scheme": "ps2-serial", "value": "SLUS-20152"},
                    "label": "generic",
                    "settings": {"Renderer": {"resolution_scale": 2}},
                },
                {
                    "identity": {"scheme": "ps2-serial", "value": "SLUS-20152"},
                    "emulator": "pcsx2",
                    "label": "pcsx2-specific",
                    "settings": {"Renderer": {"resolution_scale": 4}},
                },
                {
                    "identity": {"scheme": "ps2-elf-crc32", "value": "1A2B3C4D"},
                    "label": "crc",
                    "settings": {"Cheats": {"enabled": True}},
                },
            ],
        }
    )


def test_v2_catalog_lookup_by_typed_identity() -> None:
    catalog = _v2_catalog()
    generic = catalog.lookup(GameIdentity("playstation-2", IdentityScheme.PS2_SERIAL, "slus-20152"))
    assert generic is not None
    assert generic["Renderer"]["resolution_scale"] == 2
    specific = catalog.lookup(
        GameIdentity("playstation-2", IdentityScheme.PS2_SERIAL, "slus-20152"),
        emulator="pcsx2",
    )
    assert specific is not None
    assert specific["Renderer"]["resolution_scale"] == 4


def test_v2_catalog_lookup_by_crc32() -> None:
    catalog = _v2_catalog()
    crc = catalog.lookup(GameIdentity("playstation-2", IdentityScheme.PS2_ELF_CRC32, "1a2b3c4d"))
    assert crc is not None
    assert crc["Cheats"]["enabled"] is True


def test_v2_catalog_empty_is_valid() -> None:
    catalog = KnownGoodProfileCatalog.empty("wii-u")
    assert catalog.lookup(GameIdentity("wii-u", IdentityScheme.WIIU_PRODUCT_ID, "WUPPAYME")) is None


def test_v2_entry_identity_must_be_valid_value() -> None:
    with pytest.raises(ValidationError):
        contracts.validate(
            {
                "schemaVersion": 2,
                "platform": "playstation-2",
                "entries": [
                    {
                        "identity": {"scheme": "ps2-serial", "value": "not a serial!!"},
                        "settings": {"A": {"b": 1}},
                    }
                ],
            },
            _V2_SCHEMA,
        )


def test_v2_schema_rejects_unknown_scheme() -> None:
    with pytest.raises(ValidationError):
        contracts.validate(
            {
                "schemaVersion": 2,
                "platform": "switch",
                "entries": [
                    {
                        "identity": {"scheme": "my-scheme", "value": "ABC123"},
                        "settings": {"A": {"b": 1}},
                    }
                ],
            },
            _V2_SCHEMA,
        )


def _v1_payload(platform: str = "switch") -> dict:
    return {
        "schemaVersion": 1,
        "platform": platform,
        "entries": [
            {
                "titleId": "0100000000010000",
                "label": "generic",
                "settings": {"Renderer": {"resolution_scale": 2}},
            }
        ],
    }


def test_migrate_v1_preserves_switch_entries() -> None:
    migrated = KnownGoodProfileCatalog.migrate_v1(_v1_payload())
    assert migrated["schemaVersion"] == 2
    assert migrated["entries"][0]["identity"] == {
        "scheme": "switch-title-id",
        "value": "0100000000010000",
    }
    assert "titleId" not in migrated["entries"][0]


def test_v1_catalog_is_accepted_and_migrated_at_load() -> None:
    catalog = KnownGoodProfileCatalog(_v1_payload())
    assert catalog.platform == "switch"
    result = catalog.lookup("0100000000010000")
    assert result is not None
    assert result["Renderer"]["resolution_scale"] == 2
    result = catalog.lookup(GameIdentity.switch("0100000000010000"))
    assert result is not None


def test_v1_catalog_with_bad_title_id_fails_migration() -> None:
    payload = _v1_payload()
    payload["entries"][0]["titleId"] = "XYZ"
    # A validação do schema v1 pega o primeiro; a migração tem sua própria
    # defesa para dados que passam no shape mas não no padrão.
    with pytest.raises((SteamZeroError, ValidationError)):
        KnownGoodProfileCatalog(payload)
    with pytest.raises(SteamZeroError) as exc:
        KnownGoodProfileCatalog.migrate_v1(payload)
    assert exc.value.code == "E-API-SCHEMA"


def test_legacy_string_lookup_only_for_switch_catalog() -> None:
    catalog = _v2_catalog()
    assert catalog.lookup("SLUS-20152") is None  # string legado só vale p/ Switch


def test_configurator_preview_with_typed_identity() -> None:
    catalog = _v2_catalog()
    cfg = EmulatorConfigurator(catalog)
    diff = cfg.preview(
        GameIdentity("playstation-2", IdentityScheme.PS2_SERIAL, "SLUS-20152"),
        {"Renderer": {"resolution_scale": 1}},
    )
    assert diff.changed["Renderer"]["resolution_scale"] == (1, 2)


def test_configurator_preview_unknown_identity_is_noop() -> None:
    catalog = _v2_catalog()
    cfg = EmulatorConfigurator(catalog)
    diff = cfg.preview(
        GameIdentity("playstation-2", IdentityScheme.PS2_SERIAL, "SLUS-99999"),
        {"Renderer": {"resolution_scale": 1}},
    )
    assert diff.is_empty


def test_v1_schema_still_rejects_bad_title_id() -> None:
    with pytest.raises(ValidationError):
        contracts.validate(
            {
                "schemaVersion": 1,
                "platform": "switch",
                "entries": [{"titleId": "SLUS-20152", "settings": {"a": {"b": 1}}}],
            },
            "known-good-profile-v1.schema.json",
        )
