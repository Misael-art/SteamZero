# SPDX-License-Identifier: GPL-3.0-or-later
"""Schemas fechados do registro JSON-RPC."""

from __future__ import annotations

import pytest

from steamzero.service.methods import CLI_METHODS, METHOD_SPECS, InvalidParams, capabilities


def _value(field_name: str) -> str:
    values = {
        "id": "dolphin",
        "gameId": "10",
        "planId": "01J000000000000000000000AA",
        "confirmToken": "token",
        "operationId": "01J000000000000000000000AB",
        "profile": "safe",
        "limit": "64",
        "cursor": "0",
        "state": "running",
        "kind": "job.state",
        "entity": "job:J1",
        "platformId": "switch",
        "profileId": "standard-gamepad",
        "scope": "platform",
        "scopeId": "game-1",
        "orientation": "landscape",
        "actionJson": '{"actionId":"favorite.set","gameRef":"steam:10","value":true}',
    }
    return values[field_name]


def test_all_method_specs_roundtrip_cli_and_rpc() -> None:
    assert len(CLI_METHODS) == len(METHOD_SPECS)
    for spec in METHOD_SPECS:
        params = {
            field.rpc_name: _value(field.rpc_name)
            for field in spec.fields
            if field.required or field.rpc_name == "profile"
        }
        params["correlationId"] = "01J000000000000000000000AA"
        args = spec.params_to_args(params)
        assert spec.args_to_params(args, params["correlationId"]) == params

    advertised = capabilities()
    assert {row["method"] for row in advertised} == {
        *(spec.method for spec in METHOD_SPECS),
        "events.subscribe",
    }
    assert {row["authorization"] for row in advertised} == {"read", "mutate"}


def test_method_specs_reject_untyped_unknown_missing_and_duplicate_values() -> None:
    session = next(spec for spec in METHOD_SPECS if spec.method == "session.status")
    with pytest.raises(InvalidParams, match="objeto"):
        session.params_to_args(["10"])
    with pytest.raises(InvalidParams, match="desconhecidos"):
        session.params_to_args({"gameId": "10", "shell": "x"})
    with pytest.raises(InvalidParams, match="obrigatório"):
        session.params_to_args({})
    with pytest.raises(InvalidParams, match="texto"):
        session.params_to_args({"gameId": ""})
    with pytest.raises(InvalidParams, match="duplicada"):
        session.args_to_params(["--game-id", "10", "--game-id", "11"], "correlation")
    with pytest.raises(InvalidParams, match="não suportada"):
        session.args_to_params(["--command", "rm"], "correlation")


def test_params_to_args_accepts_none_and_returns_empty() -> None:
    spec = next(s for s in METHOD_SPECS if s.method == "doctor.run")
    assert spec.params_to_args(None) == []


def test_args_to_params_requires_required_fields() -> None:
    spec = next(s for s in METHOD_SPECS if s.method == "session.status")
    with pytest.raises(InvalidParams, match="obrigatória"):
        spec.args_to_params([], "correlation")


def test_optional_profile_and_choices_are_validated() -> None:
    desktop = next(spec for spec in METHOD_SPECS if spec.method == "desktop.plan")
    assert desktop.params_to_args({}) == []
    with pytest.raises(InvalidParams, match="valor inválido"):
        desktop.params_to_args({"profile": "turbo"})
    with pytest.raises(InvalidParams, match="valor inválido"):
        desktop.args_to_params(["--profile", "turbo"], "correlation")
