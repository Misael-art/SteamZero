# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""WI-0: fundação de schema para keys/firmware/tool/DAT e requisitos de adapter.

Cobre retrocompatibilidade dos manifestos existentes, os campos aditivos
``requiresKeys``/``requiresFirmware`` e a validação estrita dos bancos de hashes
sintéticos (nunca conteúdo real).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import ValidationError

from steamzero.adapters.registry import AdapterRegistry, load_manifest
from steamzero.api import contracts
from steamzero.core.errors import SteamZeroError

_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "switch"


def _fixture(name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _switch_manifest(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schemaVersion": 1,
        "id": "demo-switch",
        "kind": "emulator",
        "platforms": ["switch"],
        "capabilities": ["detect", "status", "install", "update", "verify"],
        "sources": [
            {
                "type": "flatpak",
                "ref": "org.demo.Switch",
                "remote": "flathub",
                "version": "a" * 64,
                "priority": 1,
            }
        ],
        "verify": {"smokeTest": ["--version"]},
        "license": "GPL-3.0-or-later",
        "upstream": "https://example.invalid/demo-switch",
    }
    base.update(overrides)
    return base


# --- Retrocompatibilidade -------------------------------------------------


def test_existing_bundled_manifests_still_load_without_new_fields() -> None:
    registry = AdapterRegistry.bundled()
    for manifest in registry.list():
        assert manifest.requires_keys is None
        assert manifest.requires_firmware is None


def test_manifest_without_new_fields_is_still_valid() -> None:
    manifest = load_manifest(_switch_manifest())
    assert manifest.requires_keys is None
    assert manifest.requires_firmware is None


# --- requiresKeys / requiresFirmware --------------------------------------


def test_manifest_parses_key_and_firmware_requirements() -> None:
    manifest = load_manifest(
        _switch_manifest(
            requiresKeys={"platform": "switch", "keyset": "prod", "minimumKeyRevision": 18},
            requiresFirmware={"platform": "switch", "minimumVersion": "17.0.0"},
        )
    )
    assert manifest.requires_keys is not None
    assert manifest.requires_keys.keyset == "prod"
    assert manifest.requires_keys.minimum_key_revision == 18
    assert manifest.requires_firmware is not None
    assert manifest.requires_firmware.minimum_version == "17.0.0"


def test_key_requirement_platform_must_be_declared() -> None:
    with pytest.raises(SteamZeroError) as exc:
        load_manifest(_switch_manifest(requiresKeys={"platform": "psx", "keyset": "prod"}))
    assert "requiresKeys" in exc.value.detail


def test_firmware_requirement_platform_must_be_declared() -> None:
    with pytest.raises(SteamZeroError) as exc:
        load_manifest(
            _switch_manifest(requiresFirmware={"platform": "psx", "minimumVersion": "1.0.0"})
        )
    assert "requiresFirmware" in exc.value.detail


def test_manifest_rejects_unknown_keyset() -> None:
    with pytest.raises(SteamZeroError):
        load_manifest(_switch_manifest(requiresKeys={"platform": "switch", "keyset": "pirate"}))


def test_manifest_rejects_extra_field_in_key_requirement() -> None:
    with pytest.raises(SteamZeroError):
        load_manifest(
            _switch_manifest(requiresKeys={"platform": "switch", "keyset": "prod", "blob": "AAAA"})
        )


# --- Bancos de hashes: aceitam sintético, rejeitam conteúdo/malformado ----


def test_keys_db_schema_accepts_synthetic_fixture() -> None:
    contracts.validate(_fixture("keys-db.json"), "keys-db-v1.schema.json")


def test_firmware_db_schema_accepts_synthetic_fixture() -> None:
    contracts.validate(_fixture("firmware-db.json"), "firmware-db-v1.schema.json")


def test_dat_index_schema_accepts_synthetic_fixture() -> None:
    contracts.validate(_fixture("dat-index.json"), "dat-index-v1.schema.json")


def test_tool_manifest_schema_accepts_synthetic_fixture() -> None:
    contracts.validate(_fixture("nsz-tool-manifest.json"), "tool-manifest-v1.schema.json")


def test_keys_db_rejects_content_field() -> None:
    data = _fixture("keys-db.json")
    data["entries"][0]["blob"] = "AAAA"  # conteúdo de key jamais é aceito
    with pytest.raises(ValidationError):
        contracts.validate(data, "keys-db-v1.schema.json")


def test_keys_db_rejects_bad_hash() -> None:
    data = _fixture("keys-db.json")
    data["entries"][0]["sha256"] = "xyz"
    with pytest.raises(ValidationError):
        contracts.validate(data, "keys-db-v1.schema.json")


def test_firmware_db_rejects_bad_version() -> None:
    data = _fixture("firmware-db.json")
    data["entries"][0]["version"] = "notaversion"
    with pytest.raises(ValidationError):
        contracts.validate(data, "firmware-db-v1.schema.json")


def test_dat_index_requires_local_import_source() -> None:
    data = _fixture("dat-index.json")
    data["source"] = "https://example.invalid/redistributed.dat"
    with pytest.raises(ValidationError):
        contracts.validate(data, "dat-index-v1.schema.json")


def test_dat_index_rejects_bad_title_id() -> None:
    data = _fixture("dat-index.json")
    data["entries"][0]["titleId"] = "XYZ"
    with pytest.raises(ValidationError):
        contracts.validate(data, "dat-index-v1.schema.json")


def test_tool_manifest_requires_pinned_hash() -> None:
    data = _fixture("nsz-tool-manifest.json")
    del data["sources"][0]["sha256"]
    with pytest.raises(ValidationError):
        contracts.validate(data, "tool-manifest-v1.schema.json")


def test_new_schemas_are_registered() -> None:
    available = set(contracts.available_schemas())
    assert {
        "keys-db-v1.schema.json",
        "firmware-db-v1.schema.json",
        "tool-manifest-v1.schema.json",
        "dat-index-v1.schema.json",
    } <= available
