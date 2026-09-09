# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato canônico GameRecord v1 (frente A0 do plano AURA).

Valida o schema empacotado em ``src/steamzero/schemas`` contra as fixtures
sintéticas de exceção em ``tests/fixtures/aura-contracts``. Não importa o
runtime do SteamZero, não acessa rede nem estado XDG.

Contagens normativas: 8 fixtures válidas e 8 inválidas. A ausência de
contrato ou fixture é falha — nunca verde em silêncio.

Cada fixture inválida traz um ``.meta.json`` de forma fechada: ``violates``
nomeia a regra, ``explains`` diz por que ela existe, e ``failsAt``/``failsWith``
ancoram a fixture ao erro que o schema realmente produz. A ausência de arte,
conflito de fontes, multi-disc, BIOS ausente, save conflitante e operação
interrompida são estados representáveis: o contrato precisa aceitá-los como
válidos e deixar a degradação honesta para a UI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "src" / "steamzero" / "schemas" / "game-record-v1.schema.json"
FIXTURES = ROOT / "tests" / "fixtures" / "aura-contracts" / "game-record"

_EXPECTED = {"valid": 8, "invalid": 8}
_META_KEYS = frozenset({"violates", "explains", "failsAt", "failsWith"})


def _pointer(path: object) -> str:
    """JSON Pointer do caminho da instância; a raiz é ``/``."""
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


def test_catalog_totals_are_eight_valid_and_eight_invalid() -> None:
    """Regressão de inventário: suite incompleta não pode passar em silêncio."""
    assert len(_valid_fixtures()) == _EXPECTED["valid"]
    assert len(_invalid_fixtures()) == _EXPECTED["invalid"]


def test_schema_is_draft_2020_12_versioned_and_forward_tolerant() -> None:
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["schemaVersion"]["const"] == 1  # type: ignore[index]
    # Compatibilidade: campos desconhecidos na raiz são preservados, não reprovados.
    assert schema["additionalProperties"] is True
    assert schema["maxProperties"] == 128
    # Roles de mídia são conjunto fechado desta versão.
    assert set(schema["properties"]["media"]["properties"]) == {  # type: ignore[index]
        "cover",
        "fanart",
        "screenshot",
        "marquee",
        "video",
        "icon",
    }


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
    assert set(meta) == _META_KEYS, (
        f"{fixture.name}: meta precisa ter exatamente {sorted(_META_KEYS)}"
    )
    for key in _META_KEYS:
        value = meta[key]
        assert isinstance(value, str) and value.strip(), (
            f"{fixture.name}: meta['{key}'] precisa ser texto não vazio"
        )
    observed = {(_pointer(err.path), err.validator) for err in errors}
    declared = (meta["failsAt"], meta["failsWith"])
    assert declared in observed, (
        f"{fixture.name}: meta declara falha em {declared[0]} por '{declared[1]}', "
        f"mas o schema falhou em {sorted(observed)}"
    )


def test_exception_states_are_representable() -> None:
    """Arte ausente, conflito, multi-disc, BIOS ausente, save conflitante e
    operação interrompida existem como fixtures válidas nomeadas."""
    names = {path.name for path in _valid_fixtures()}
    for expected in (
        "02-missing-artwork.json",
        "03-source-conflict.json",
        "04-multi-disc.json",
        "05-bios-missing.json",
        "06-save-conflict.json",
        "07-interrupted-operation.json",
    ):
        assert expected in names, f"fixture de exceção ausente: {expected}"


def test_unknown_root_fields_are_tolerated_and_preserved() -> None:
    validator = _validator()
    base = json.loads((FIXTURES / "valid" / "02-missing-artwork.json").read_text(encoding="utf-8"))
    base["futureCapabilityField"] = {"enabled": True}
    errors = sorted(validator.iter_errors(base), key=lambda err: list(err.path))
    assert not errors, "campo de versão futura não pode reprovar o registro"
    assert base["futureCapabilityField"] == {"enabled": True}


def test_migration_requires_explicit_schema_version() -> None:
    validator = _validator()
    base = json.loads((FIXTURES / "valid" / "02-missing-artwork.json").read_text(encoding="utf-8"))
    without_version = {key: value for key, value in base.items() if key != "schemaVersion"}
    errors = list(validator.iter_errors(without_version))
    assert any(err.validator == "required" and not err.path for err in errors), (
        "registro sem schemaVersion precisa falhar na raiz"
    )
    bumped = dict(base, schemaVersion=2)
    errors = list(validator.iter_errors(bumped))
    assert any(
        err.validator == "const" and list(err.path) == ["schemaVersion"] for err in errors
    ), "schemaVersion 2 não pode validar sob o schema v1"


def test_limits_are_enforced() -> None:
    validator = _validator()
    base = json.loads((FIXTURES / "valid" / "02-missing-artwork.json").read_text(encoding="utf-8"))

    over_title = dict(base, title="x" * 513)
    assert any(
        err.validator == "maxLength" and list(err.path) == ["title"]
        for err in validator.iter_errors(over_title)
    ), "título acima de 512 caracteres precisa reprovar"

    over_hashes = dict(base, hashes={f"sha1{n:02d}": "a" * 40 for n in range(9)})
    assert any(
        err.validator == "maxProperties" and list(err.path) == ["hashes"]
        for err in validator.iter_errors(over_hashes)
    ), "mais de 8 hashes precisa reprovar"

    over_provenance = dict(
        base,
        provenance={
            f"campo{n:03d}": {
                "source": "es-de",
                "retrievedAt": "2026-09-08T10:00:00Z",
                "confidence": 0.5,
                "conflictPolicy": "keepRichest",
            }
            for n in range(129)
        },
    )
    assert any(
        err.validator == "maxProperties" and list(err.path) == ["provenance"]
        for err in validator.iter_errors(over_provenance)
    ), "provenance acima de 128 campos precisa reprovar"

    over_discs = dict(
        base,
        discSet=[{"disc": n, "path": f"/roms/disc{n}.chd"} for n in range(1, 66)],
    )
    assert any(
        err.validator == "maxItems" and list(err.path) == ["discSet"]
        for err in validator.iter_errors(over_discs)
    ), "discSet acima de 64 discos precisa reprovar"
