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
from steamzero.domain.input_profiles import InputProfileRegistry


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
        "session-environment-v1.schema.json",
        "error-v1.schema.json",
        "event-v1.schema.json",
        "plan-v1.schema.json",
        "platform-manifest-v1.schema.json",
        "retro-input-profile-v1.schema.json",
        "retro-integer-scaling-v1.schema.json",
        "retro-experience-v1.schema.json",
        "feat-playtime-v1.schema.json",
        "feat-operation-history-v1.schema.json",
        "feat-collection-v1.schema.json",
        "feat-bitrot-v1.schema.json",
        "gtool-hud-v1.schema.json",
        "gtool-launch-environment-v1.schema.json",
        "gtool-vkbasalt-v1.schema.json",
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
def test_bundled_input_profile_validates() -> None:
    profile = InputProfileRegistry.bundled().get("standard-gamepad")
    contracts.validate(profile.to_dict(), "retro-input-profile-v1.schema.json")


@pytest.mark.golden
def test_bitrot_sample_validates() -> None:
    contracts.validate(
        {
            "schemaVersion": 1,
            "generatedAt": "2026-07-23T12:00:00+00:00",
            "state": "suspect",
            "lastRun": {
                "startedAt": "2026-07-23T11:59:58+00:00",
                "finishedAt": "2026-07-23T12:00:00+00:00",
                "checked": 1,
                "bytesRead": 1024,
                "suspect": 1,
                "limited": True,
            },
            "counts": {
                "verified": 3,
                "suspect": 1,
                "missing": 0,
                "error": 0,
                "unavailable": 0,
                "unchecked": 2,
            },
            "items": [
                {
                    "assetId": "emulation:game-1",
                    "title": "Synthetic",
                    "platformId": "switch",
                    "state": "suspect",
                    "size": 1024,
                    "checkedAt": "2026-07-23T12:00:00+00:00",
                    "reason": "Hash diverge da baseline; o arquivo não foi alterado.",
                }
            ],
            "activeJobs": [],
            "limits": {"maxFiles": 8, "maxBytes": 2147483648, "maxSeconds": 20},
        },
        "feat-bitrot-v1.schema.json",
    )


@pytest.mark.golden
def test_hud_catalog_validates() -> None:
    from steamzero.domain.hud import hud_catalog

    contracts.validate(hud_catalog(), "gtool-hud-v1.schema.json")


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

    environment_event = {
        "seq": 3,
        "ts": "2026-07-15T00:00:02+00:00",
        "kind": "session.environment",
        "correlationId": "01J000000000000000000000AD",
        "digest": "a" * 64,
        "changes": ["displays", "power"],
    }
    contracts.validate(environment_event, "event-v1.schema.json")

    resume_event = {
        "seq": 4,
        "ts": "2026-07-15T00:00:03+00:00",
        "kind": "session.resume",
        "correlationId": "01J000000000000000000000AE",
        "suspendedSeconds": 42.125,
    }
    contracts.validate(resume_event, "event-v1.schema.json")


@pytest.mark.golden
def test_operation_history_sample_validates() -> None:
    sample = {
        "schemaVersion": 1,
        "generatedAt": "2026-07-23T12:00:00+00:00",
        "items": [
            {
                "operationId": "01J000000000000000000000AA",
                "kind": "emulator.config",
                "title": "Configuração de emulador",
                "state": "committed",
                "timestamp": "2026-07-23T11:59:00+00:00",
                "target": "arquivo:0123456789ab",
                "changeCount": 1,
                "rollback": {
                    "available": True,
                    "guarantee": "G-FULL",
                    "route": "transaction",
                    "reason": "",
                },
            }
        ],
        "page": {"limit": 20, "hasMore": False, "nextCursor": None},
    }
    contracts.validate(sample, "feat-operation-history-v1.schema.json")


@pytest.mark.golden
def test_invalid_instances_rejected() -> None:
    assert not contracts.is_valid({"contract": "2.0"}, "envelope-v2.schema.json")  # faltam campos
    assert not contracts.is_valid({"seq": 1}, "event-v1.schema.json")  # falta ts/kind/correlationId
    assert not contracts.is_valid({"code": "sem-prefixo", "title": "x"}, "error-v1.schema.json")
