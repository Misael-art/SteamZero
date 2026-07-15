# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Validação de saídas contra os schemas JSON (JSON-SCHEMAS.md, SR-04).

Carrega os schemas empacotados em ``steamzero.schemas`` num registry
``referencing`` (resolve ``$ref`` entre arquivos) e expõe ``validate``/``is_valid``.
Usado pela CLI/serviço e pelos testes de golden file de contrato.
"""

from __future__ import annotations

import importlib.resources
import json
from functools import cache, lru_cache
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


@lru_cache(maxsize=1)
def _registry() -> Registry[Any]:
    resources: list[tuple[str, Resource[Any]]] = []
    files = importlib.resources.files("steamzero.schemas")
    for entry in files.iterdir():
        if entry.name.endswith(".json"):
            doc = json.loads(entry.read_text(encoding="utf-8"))
            resources.append((doc["$id"], Resource.from_contents(doc)))
    return Registry().with_resources(resources)


@cache
def _validator(schema_id: str) -> Draft202012Validator:
    registry = _registry()
    schema = registry.get_or_retrieve(schema_id).value.contents
    return Draft202012Validator(schema, registry=registry)


def validate(instance: Any, schema_id: str) -> None:
    """Valida ``instance`` contra o schema ``schema_id`` (ex.: envelope-v2.schema.json).

    Levanta ``jsonschema.ValidationError`` na primeira falha.
    """
    _validator(schema_id).validate(instance)


def is_valid(instance: Any, schema_id: str) -> bool:
    return bool(_validator(schema_id).is_valid(instance))


def available_schemas() -> list[str]:
    files = importlib.resources.files("steamzero.schemas")
    return sorted(
        json.loads(e.read_text(encoding="utf-8"))["$id"]
        for e in files.iterdir()
        if e.name.endswith(".json")
    )
