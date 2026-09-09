# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato EnhancementEntry v1 do registry de melhorias (frente A0 AURA).

Regras provadas aqui: categoria fechada sem cheats de gameplay, fonte com
checksum verificável e licença, transporte somente https, identificador por
jogo obrigatório e rollback declarado. A política de adoção por emulador
(DuckStation/Dolphin/PCSX2 primeiro, depois RPCS3/Cemu, shadPS4 separado) é
da frente A9 — este contrato não a embute.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "src" / "steamzero" / "schemas" / "enhancement-entry-v1.schema.json"
FIXTURES = ROOT / "tests" / "fixtures" / "aura-contracts" / "enhancement-entry"

_EXPECTED = {"valid": 2, "invalid": 2}
_META_KEYS = frozenset({"violates", "explains", "failsAt", "failsWith"})


def _pointer(path: object) -> str:
    parts = [str(part) for part in path]  # type: ignore[union-attr]
    return "/" + "/".join(parts) if parts else "/"


def _schema() -> dict[str, object]:
    assert SCHEMA_PATH.is_file(), f"schema de contrato ausente: {SCHEMA_PATH}"
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(schema, dict)
    return schema


def _validator() -> Draft202012Validator:
    return Draft202012Validator(_schema(), format_checker=FormatChecker())


def _valid_fixtures() -> list[Path]:
    return sorted((FIXTURES / "valid").glob("*.json"))


def _invalid_fixtures() -> list[Path]:
    return sorted(
        path
        for path in (FIXTURES / "invalid").glob("*.json")
        if not path.name.endswith(".meta.json")
    )


def _meta_for(fixture: Path) -> dict[str, object]:
    meta_path = fixture.with_name(fixture.stem + ".meta.json")
    assert meta_path.is_file(), f"meta ausente para fixture inválida: {meta_path}"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert isinstance(meta, dict)
    return meta


def test_catalog_totals_are_two_valid_and_two_invalid() -> None:
    assert len(_valid_fixtures()) == _EXPECTED["valid"]
    assert len(_invalid_fixtures()) == _EXPECTED["invalid"]


def test_schema_is_draft_2020_12_closed_and_versioned() -> None:
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schemaVersion"]["const"] == 1  # type: ignore[index]


def test_categories_exclude_gameplay_cheats() -> None:
    schema = _schema()
    categories = schema["properties"]["category"]["enum"]  # type: ignore[index]
    assert set(categories) == {
        "performance",
        "compatibility",
        "quality",
        "accessibility",
    }
    assert "cheat" not in categories


def test_source_transport_is_https_only_with_checksum_and_license() -> None:
    schema = _schema()
    source = schema["$defs"]["source"]["properties"]  # type: ignore[index]
    assert source["url"]["pattern"].startswith("^https://")
    for required in ("checksum", "checksumAlgorithm", "license"):
        assert required in schema["$defs"]["source"]["required"]  # type: ignore[index]


def test_identifier_per_game_is_mandatory() -> None:
    schema = _schema()
    identifiers = schema["$defs"]["identifiers"]  # type: ignore[index]
    assert identifiers["minProperties"] >= 1


@pytest.mark.parametrize("fixture", _valid_fixtures(), ids=lambda path: path.name)
def test_valid_fixtures_validate_against_contract(fixture: Path) -> None:
    validator = _validator()
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.path))
    assert not errors, f"{fixture.name} violou o contrato: {errors[0].message}"


@pytest.mark.parametrize("fixture", _invalid_fixtures(), ids=lambda path: path.name)
def test_invalid_fixtures_fail_and_declare_violated_rule(fixture: Path) -> None:
    validator = _validator()
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.path))
    assert errors, f"{fixture.name} deveria falhar o schema"
    meta = _meta_for(fixture)
    assert set(meta) == _META_KEYS
    for key in _META_KEYS:
        value = meta[key]
        assert isinstance(value, str) and value.strip()
    observed = {(_pointer(err.path), err.validator) for err in errors}
    declared = (meta["failsAt"], meta["failsWith"])
    assert declared in observed, (
        f"{fixture.name}: meta declara falha em {declared[0]} por '{declared[1]}', "
        f"mas o schema falhou em {sorted(observed)}"
    )
