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
        "specJson": '{"srm":{"collections":[]},"esde":{"systems":[]}}',
        "target": "esde",
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


def test_method_specs_carry_per_method_transport_timeout() -> None:
    """BUG-01: o round-trip de emulation.workspace mede ~13,3 s no host.

    O timeout do transporte é por método: leituras leves seguem com 2,0 s;
    operações lentas conhecidas declaram teto verificado (30,0 s).
    """
    by_method = {spec.method: spec for spec in METHOD_SPECS}
    assert by_method["emulation.workspace"].timeout == 30.0
    assert by_method["doctor.run"].timeout == 30.0
    fast = ("jobs.list", "session.status", "cloud.launch", "controls.apply")
    for method in fast:
        assert by_method[method].timeout == 2.0
    for method in (
        "frontends.status",
        "frontends.plan",
        "frontends.apply",
        "frontends.verify",
        "frontends.rollback",
    ):
        assert by_method[method].timeout == 2.0
    for spec in METHOD_SPECS:
        assert spec.timeout > 0.0


def test_frontends_specs_are_closed_and_spec_file_stays_local() -> None:
    """O transporte do daemon nunca recebe paths: só a spec JSON fechada."""
    plan = next(spec for spec in METHOD_SPECS if spec.method == "frontends.plan")
    verify = next(spec for spec in METHOD_SPECS if spec.method == "frontends.verify")
    apply = next(spec for spec in METHOD_SPECS if spec.method == "frontends.apply")
    rollback = next(spec for spec in METHOD_SPECS if spec.method == "frontends.rollback")
    status = next(spec for spec in METHOD_SPECS if spec.method == "frontends.status")

    with pytest.raises(InvalidParams, match="obrigatória"):
        plan.args_to_params([], "correlation")
    with pytest.raises(InvalidParams, match="obrigatório"):
        plan.params_to_args({})
    with pytest.raises(InvalidParams, match="desconhecidos"):
        plan.params_to_args({"specJson": "{}", "path": "/etc/passwd"})
    with pytest.raises(InvalidParams, match="não suportada"):
        plan.args_to_params(["--spec", "/home/user/spec.json"], "correlation")
    with pytest.raises(InvalidParams, match="valor inválido"):
        apply.params_to_args({"planId": "p", "confirmToken": "t", "target": "wii"})
    with pytest.raises(InvalidParams, match="valor inválido"):
        apply.args_to_params(["--plan-id", "p", "--confirm", "t", "--target", "wii"], "correlation")

    assert status.params_to_args({}) == []
    assert status.args_to_params([], "correlation") == {"correlationId": "correlation"}
    with pytest.raises(InvalidParams, match="obrigatório"):
        rollback.params_to_args({})
    with pytest.raises(InvalidParams, match="obrigatório"):
        verify.params_to_args({})
    assert rollback.params_to_args({"operationId": "op"}) == ["--operation-id", "op"]
    assert verify.params_to_args({"specJson": "{}"}) == ["--spec-json", "{}"]

    applied = apply.params_to_args(
        {"planId": "p", "confirmToken": "t", "target": "esde", "correlationId": "c"}
    )
    assert applied == ["--plan-id", "p", "--confirm", "t", "--target", "esde"]
    assert apply.args_to_params(applied, "c") == {
        "planId": "p",
        "confirmToken": "t",
        "target": "esde",
        "correlationId": "c",
    }

    assert {key for key in CLI_METHODS if key[0] == "frontends"} == {
        ("frontends", "status"),
        ("frontends", "plan"),
        ("frontends", "apply"),
        ("frontends", "verify"),
        ("frontends", "rollback"),
    }
