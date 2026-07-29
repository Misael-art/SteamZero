# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do catálogo de erros e do objeto error-v1."""

from __future__ import annotations

import pytest

from steamzero import i18n
from steamzero.core import errors

HOST_ERROR_CODES = (
    "E-HOST-RELEASE-MISMATCH",
    "E-HOST-DAEMON-PENDING",
    "E-HOST-CONVERGENCE-TIMEOUT",
    "E-HOST-RESTART-FAILED",
    "E-HOST-CURRENT-UNREADABLE",
)


def test_every_code_has_all_i18n_fields() -> None:
    keys = i18n.all_keys()
    missing = [
        f"error.{code}.{field}"
        for code in errors.ERROR_CATALOG
        for field in errors.REQUIRED_FIELDS
        if f"error.{code}.{field}" not in keys
    ]
    assert not missing, f"chaves i18n ausentes: {missing}"


def test_no_orphan_error_i18n_keys() -> None:
    for key in i18n.all_keys():
        if not key.startswith("error."):
            continue
        parts = key.split(".")
        assert len(parts) == 3, f"chave de erro malformada: {key}"
        _, code, field = parts
        assert code in errors.ERROR_CATALOG, f"texto órfão: código {code} não registrado"
        assert field in errors.REQUIRED_FIELDS, f"campo desconhecido em {key}"


def test_code_area_matches_prefix() -> None:
    # E-<ÁREA>-<NOME>: a área registrada deve ser o segundo segmento do código.
    for code, area in errors.ERROR_CATALOG.items():
        assert code.startswith(f"E-{area}-"), f"{code} não começa com E-{area}-"


def test_build_error_shape() -> None:
    obj = errors.build_error("E-TX-STALE-PLAN", detail="arquivo X mudou", operation_id="OP")
    assert obj["code"] == "E-TX-STALE-PLAN"
    assert obj["title"] == "Plano desatualizado"
    assert obj["detail"] == "arquivo X mudou"
    assert obj["operationId"] == "OP"
    # manualAction e action (alias de compat com envelope) coincidem
    assert obj["action"] == obj["manualAction"]
    for field in ("title", "what", "impact", "probableCause", "manualAction"):
        assert isinstance(obj[field], str) and obj[field]


def test_build_error_rejects_unregistered() -> None:
    with pytest.raises(ValueError):
        errors.build_error("E-NOPE-NOPE")


@pytest.mark.parametrize("code", HOST_ERROR_CODES)
def test_host_diagnostics_build_error_objects(code: str) -> None:
    obj = errors.build_error(code, detail="detalhe observado no host")

    assert obj["code"] == code
    assert obj["detail"] == "detalhe observado no host"
    for field in ("title", "what", "impact", "probableCause", "manualAction"):
        assert isinstance(obj[field], str) and obj[field]


def test_steamzero_error_roundtrip() -> None:
    err = errors.SteamZeroError("E-TX-LOCKED", detail="dono job=X idade=30s")
    obj = err.to_error_object()
    assert obj["code"] == "E-TX-LOCKED"
    assert obj["detail"] == "dono job=X idade=30s"
    assert errors.is_registered(err.code)


def test_steamzero_error_rejects_unregistered() -> None:
    with pytest.raises(ValueError):
        errors.SteamZeroError("E-FAKE")
