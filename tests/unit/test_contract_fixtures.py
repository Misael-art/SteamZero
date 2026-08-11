# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Valida contratos documentais e fixtures das capacidades P2P, RetroAchievements e cast remoto.

Carrega somente JSON Schema draft 2020-12 e arquivos em ``docs/contracts`` e
``docs/fixtures``. Nao importa o runtime do SteamZero e nao acessa rede,
keyring, host ou estado XDG.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "docs" / "contracts"
FIXTURES = ROOT / "docs" / "fixtures"

_MIN_FIXTURES = {
    "p2p": {"valid": 8, "invalid": 12},
    "retroachievements": {"valid": 10, "invalid": 13},
    "remote-cast": {"valid": 9, "invalid": 13},
}

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def _capabilities() -> list[str]:
    return sorted(
        entry.name
        for entry in CONTRACTS.iterdir()
        if entry.is_dir() and any(entry.glob("*.schema.json"))
    )


def _schema_for(capability: str) -> dict[str, object]:
    schema_path = next((CONTRACTS / capability).glob("*.schema.json"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert isinstance(schema, dict)
    return schema


def _validator(schema: dict[str, object]) -> Draft202012Validator:
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _walk_strings(value: object) -> list[str]:
    strings: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            strings.extend(_walk_strings(item))
    elif isinstance(value, list):
        for item in value:
            strings.extend(_walk_strings(item))
    elif isinstance(value, str):
        strings.append(value)
    return strings


def test_every_contract_envelope_is_draft_2020_12_closed_and_versioned() -> None:
    for capability in _capabilities():
        schema = _schema_for(capability)
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["additionalProperties"] is False
        assert schema["properties"]["schemaVersion"]["const"] == 1


@pytest.mark.parametrize("capability", _capabilities())
def test_valid_fixtures_validate_against_contract(capability: str) -> None:
    validator = _validator(_schema_for(capability))
    fixtures = sorted((FIXTURES / capability / "valid").glob("*.json"))
    assert len(fixtures) >= _MIN_FIXTURES[capability]["valid"]
    for fixture in fixtures:
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        assert validator.is_valid(payload), f"{fixture.name} violou o contrato"


@pytest.mark.parametrize("capability", _capabilities())
def test_invalid_fixtures_fail_and_declare_violated_rule(capability: str) -> None:
    validator = _validator(_schema_for(capability))
    invalid_dir = FIXTURES / capability / "invalid"
    fixtures = sorted(
        path for path in invalid_dir.glob("*.json") if not path.name.endswith(".meta.json")
    )
    assert len(fixtures) >= _MIN_FIXTURES[capability]["invalid"]
    for fixture in fixtures:
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        assert not validator.is_valid(payload), f"{fixture.name} deveria falhar"
        meta = json.loads(fixture.with_suffix(".meta.json").read_text(encoding="utf-8"))
        assert isinstance(meta, dict)
        assert isinstance(meta.get("violates"), str) and meta["violates"]


def test_valid_fixtures_use_utc_timestamps() -> None:
    for capability in _capabilities():
        for fixture in (FIXTURES / capability / "valid").glob("*.json"):
            for value in _walk_strings(json.loads(fixture.read_text(encoding="utf-8"))):
                if _ISO_RE.match(value):
                    assert value.endswith("Z"), f"{fixture.name}: timestamp sem UTC: {value}"


def test_retroachievements_idempotency_key_reused_across_sync() -> None:
    offline_path = FIXTURES / "retroachievements" / "valid" / "06-unlock-offline-pending.json"
    if not offline_path.exists():
        return
    offline = json.loads(offline_path.read_text(encoding="utf-8"))
    completed = json.loads(
        (FIXTURES / "retroachievements" / "valid" / "07-sync-completed.json").read_text(
            encoding="utf-8"
        )
    )
    duplicate = json.loads(
        (FIXTURES / "retroachievements" / "valid" / "08-duplicate-idempotent.json").read_text(
            encoding="utf-8"
        )
    )
    key = offline["idempotencyKey"]
    assert completed["idempotencyKey"] == key
    assert duplicate["eventId"] == offline["eventId"]
    assert duplicate == offline
