# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Golden files de contrato: toda saída JSON valida contra os schemas (DoD 4.2.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.api import contracts
from steamzero.api.envelope import build_envelope
from steamzero.core import fs, transaction
from steamzero.core.errors import build_error
from steamzero.diagnostics.doctor import run_doctor


@pytest.fixture
def state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    fs.ensure_state_layout()
    return tmp_path


@pytest.mark.golden
def test_registry_loads_all_schemas() -> None:
    got = set(contracts.available_schemas())
    assert {
        "envelope-v2.schema.json",
        "adapter-v1.schema.json",
        "component-lock-v1.schema.json",
        "component-plan-v1.schema.json",
        "error-v1.schema.json",
        "event-v1.schema.json",
        "plan-v1.schema.json",
    } <= got


@pytest.mark.golden
def test_error_object_validates() -> None:
    contracts.validate(build_error("E-TX-STALE-PLAN", detail="x"), "error-v1.schema.json")
    contracts.validate(build_error("E-INTERNAL-UNEXPECTED"), "error-v1.schema.json")


@pytest.mark.golden
def test_envelope_ok_validates() -> None:
    env = build_envelope("doctor", "run", status="ok", data={"a": 1})
    contracts.validate(env, "envelope-v2.schema.json")


@pytest.mark.golden
def test_envelope_with_error_validates_cross_ref() -> None:
    # exercita o $ref envelope -> error-v1 (registry resolve entre arquivos)
    env = build_envelope(
        "component", "update", status="failed", ok=False, error=build_error("E-TX-VERIFY-FAILED")
    )
    contracts.validate(env, "envelope-v2.schema.json")


@pytest.mark.golden
def test_live_doctor_envelope_validates(state: Path) -> None:
    data, checks = run_doctor()
    env = build_envelope("doctor", "run", status="ok", data=data, checks=checks)
    contracts.validate(env, "envelope-v2.schema.json")


@pytest.mark.golden
def test_live_plan_validates(state: Path) -> None:
    sandbox = state / "sandbox"
    sandbox.mkdir()
    plan = transaction.plan_write_files({sandbox / "c.ini": b"[x]\n"}, root=sandbox)
    contracts.validate(plan.to_dict(), "plan-v1.schema.json")


@pytest.mark.golden
def test_live_move_plan_validates(state: Path) -> None:
    sandbox = state / "moves"
    sandbox.mkdir()
    fs.write_atomic(sandbox / "game.nes", b"synthetic")
    plan = transaction.plan_move_files(
        {sandbox / "game.nes": sandbox / "nes" / "game.nes"}, root=sandbox
    )
    contracts.validate(plan.to_dict(), "plan-v1.schema.json")


@pytest.mark.golden
def test_live_symlink_plan_validates(state: Path) -> None:
    central = state / "central.bin"
    consumer = state / "consumer"
    consumer.mkdir()
    fs.write_atomic(central, b"synthetic")
    plan = transaction.plan_symlink_files(
        {central: consumer / "bios.bin"}, root=consumer, kind="bios.link"
    )
    contracts.validate(plan.to_dict(), "plan-v1.schema.json")


@pytest.mark.golden
def test_event_sample_validates() -> None:
    event = {
        "seq": 1,
        "ts": "2026-07-15T00:00:00+00:00",
        "kind": "job.progress",
        "correlationId": "01J000000000000000000000AA",
        "progress": {"stage": "apply", "current": 3, "total": 10, "unit": "items"},
    }
    contracts.validate(event, "event-v1.schema.json")

    session_event = {
        "seq": 2,
        "ts": "2026-07-15T00:00:01+00:00",
        "kind": "session.state",
        "correlationId": "01J000000000000000000000AB",
        "sessionId": "01J000000000000000000000AC",
        "gameId": "10",
        "state": "running",
    }
    contracts.validate(session_event, "event-v1.schema.json")


@pytest.mark.golden
def test_invalid_instances_rejected() -> None:
    assert not contracts.is_valid({"contract": "2.0"}, "envelope-v2.schema.json")  # faltam campos
    assert not contracts.is_valid({"seq": 1}, "event-v1.schema.json")  # falta ts/kind/correlationId
    assert not contracts.is_valid({"code": "sem-prefixo", "title": "x"}, "error-v1.schema.json")
