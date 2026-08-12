# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Valida contratos documentais e fixtures das capacidades P2P, RA e cast remoto.

Carrega somente JSON Schema draft 2020-12 e arquivos em ``docs/contracts`` e
``docs/fixtures``. Nao importa o runtime do SteamZero e nao acessa rede,
keyring, host ou estado XDG.

Contagens normativas (ADR-0024/0025/0026): 29 fixtures validas e 39 invalidas.
A ausencia de contrato ou fixture e falha — nunca verde em silencio.

Cada fixture invalida traz um ``.meta.json`` de forma fechada: ``violates``
nomeia a regra, ``explains`` diz por que ela existe, e ``failsAt``/``failsWith``
ancoram a fixture ao erro que o schema realmente produz (JSON Pointer da
instancia e palavra-chave do validador).

A ancoragem existe porque a versao anterior deste teste so exigia que a fixture
falhasse de ALGUM jeito e que ``violates`` fosse texto nao vazio. Isso passava
com duas coisas erradas: uma fixture quebrada por engano em outro campo, e um
``.meta.json`` que fosse copia do payload com ``violates`` pendurado — o estado
real das catorze fixtures de remote-cast quando este teste foi revisado. Ambos
os casos foram reproduzidos por mutacao antes de a asercao ser escrita.
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

# Contagens exatas: evita verde em suite incompleta e regrede se fixtures sumirem.
_EXPECTED = {
    "p2p": {"valid": 8, "invalid": 12},
    "retroachievements": {"valid": 10, "invalid": 13},
    "remote-cast": {"valid": 11, "invalid": 14},
}
_TOTAL_VALID = sum(spec["valid"] for spec in _EXPECTED.values())
_TOTAL_INVALID = sum(spec["invalid"] for spec in _EXPECTED.values())

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
_CAPABILITIES = tuple(_EXPECTED)

# `violates` nomeia a regra, `explains` diz por que ela existe, e o par
# `failsAt`/`failsWith` ancora a fixture ao erro que o schema de fato produz.
_META_KEYS = frozenset({"violates", "explains", "failsAt", "failsWith"})


def _pointer(path: object) -> str:
    """JSON Pointer do caminho da instancia; a raiz e ``/``."""
    parts = [str(part) for part in path]  # type: ignore[union-attr]
    return "/" + "/".join(parts) if parts else "/"


def _require_dir(path: Path) -> Path:
    assert path.is_dir(), f"diretorio de contrato/fixture ausente: {path.relative_to(ROOT)}"
    return path


def _schema_for(capability: str) -> dict[str, object]:
    contract_dir = _require_dir(CONTRACTS / capability)
    schemas = sorted(contract_dir.glob("*.schema.json"))
    assert len(schemas) == 1, (
        f"{capability}: esperado exatamente 1 schema, encontrado {len(schemas)}"
    )
    schema = json.loads(schemas[0].read_text(encoding="utf-8"))
    assert isinstance(schema, dict)
    return schema


def _validator(schema: dict[str, object]) -> Draft202012Validator:
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _valid_fixtures(capability: str) -> list[Path]:
    valid_dir = _require_dir(FIXTURES / capability / "valid")
    return sorted(valid_dir.glob("*.json"))


def _invalid_fixtures(capability: str) -> list[Path]:
    invalid_dir = _require_dir(FIXTURES / capability / "invalid")
    return sorted(
        path for path in invalid_dir.glob("*.json") if not path.name.endswith(".meta.json")
    )


def _meta_for(fixture: Path) -> dict[str, object]:
    # 01-foo.json -> 01-foo.meta.json
    meta_path = fixture.with_name(fixture.stem + ".meta.json")
    assert meta_path.is_file(), f"meta ausente para fixture invalida: {meta_path.relative_to(ROOT)}"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert isinstance(meta, dict)
    return meta


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


def test_catalog_totals_are_twenty_nine_valid_and_thirty_nine_invalid() -> None:
    """Regressao de inventario: suite incompleta nao pode passar em silencio."""
    assert _TOTAL_VALID == 29
    assert _TOTAL_INVALID == 39
    assert CONTRACTS.is_dir(), "docs/contracts ausente"
    assert FIXTURES.is_dir(), "docs/fixtures ausente"
    valid = 0
    invalid = 0
    for capability in _CAPABILITIES:
        valid += len(_valid_fixtures(capability))
        invalid += len(_invalid_fixtures(capability))
    assert valid == 29, f"esperadas 29 fixtures validas, encontradas {valid}"
    assert invalid == 39, f"esperadas 39 fixtures invalidas, encontradas {invalid}"


def test_every_contract_envelope_is_draft_2020_12_closed_and_versioned() -> None:
    for capability in _CAPABILITIES:
        schema = _schema_for(capability)
        Draft202012Validator.check_schema(schema)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["additionalProperties"] is False
        assert schema["properties"]["schemaVersion"]["const"] == 1  # type: ignore[index]


@pytest.mark.parametrize("capability", _CAPABILITIES)
def test_valid_fixtures_validate_against_contract(capability: str) -> None:
    validator = _validator(_schema_for(capability))
    fixtures = _valid_fixtures(capability)
    assert len(fixtures) == _EXPECTED[capability]["valid"], (
        f"{capability}: esperadas {_EXPECTED[capability]['valid']} validas, "
        f"encontradas {len(fixtures)}"
    )
    for fixture in fixtures:
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        errors = sorted(validator.iter_errors(payload), key=lambda err: err.path)
        assert not errors, f"{fixture.name} violou o contrato: {errors[0].message}"


@pytest.mark.parametrize("capability", _CAPABILITIES)
def test_invalid_fixtures_fail_and_declare_violated_rule(capability: str) -> None:
    validator = _validator(_schema_for(capability))
    fixtures = _invalid_fixtures(capability)
    assert len(fixtures) == _EXPECTED[capability]["invalid"], (
        f"{capability}: esperadas {_EXPECTED[capability]['invalid']} invalidas, "
        f"encontradas {len(fixtures)}"
    )
    for fixture in fixtures:
        payload = json.loads(fixture.read_text(encoding="utf-8"))
        errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.path))
        assert errors, f"{fixture.name} deveria falhar o schema"
        meta = _meta_for(fixture)

        # Forma fechada. Sem isto, um meta que fosse copia do payload com um
        # 'violates' pendurado passaria — foi exatamente o que aconteceu com as
        # catorze fixtures de remote-cast.
        assert set(meta) == _META_KEYS, (
            f"{fixture.name}: meta precisa ter exatamente {sorted(_META_KEYS)}, tem {sorted(meta)}"
        )
        for key in _META_KEYS:
            value = meta[key]
            assert isinstance(value, str) and value.strip(), (
                f"{fixture.name}: meta['{key}'] precisa ser texto nao vazio"
            )

        # A ancoragem e o que separa "invalida pela regra declarada" de
        # "invalida por um erro de digitacao em qualquer campo". Sem ela, mexer
        # numa fixture ate quebra-la por outro motivo continuaria verde, e a
        # fixture deixaria de provar a regra que diz provar.
        observed = {(_pointer(err.path), err.validator) for err in errors}
        declared = (meta["failsAt"], meta["failsWith"])
        assert declared in observed, (
            f"{fixture.name}: meta declara falha em {declared[0]} por '{declared[1]}', "
            f"mas o schema falhou em {sorted(observed)}"
        )


def test_valid_fixtures_use_utc_timestamps() -> None:
    for capability in _CAPABILITIES:
        for fixture in _valid_fixtures(capability):
            for value in _walk_strings(json.loads(fixture.read_text(encoding="utf-8"))):
                if _ISO_RE.match(value):
                    assert value.endswith("Z"), f"{fixture.name}: timestamp sem UTC: {value}"


def test_retroachievements_idempotency_key_reused_across_sync() -> None:
    """RA offline→sync→duplicate reutiliza a mesma chave; fixtures obrigatorias."""
    base = FIXTURES / "retroachievements" / "valid"
    offline_path = base / "06-unlock-offline-pending.json"
    completed_path = base / "07-sync-completed.json"
    duplicate_path = base / "08-duplicate-idempotent.json"
    for path in (offline_path, completed_path, duplicate_path):
        assert path.is_file(), f"fixture RA obrigatoria ausente: {path.relative_to(ROOT)}"
    offline = json.loads(offline_path.read_text(encoding="utf-8"))
    completed = json.loads(completed_path.read_text(encoding="utf-8"))
    duplicate = json.loads(duplicate_path.read_text(encoding="utf-8"))
    key = offline["idempotencyKey"]
    assert completed["idempotencyKey"] == key
    assert duplicate["eventId"] == offline["eventId"]
    assert duplicate == offline
