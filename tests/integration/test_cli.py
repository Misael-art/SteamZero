# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes da CLL `steamzero` — envelope v2, doctor, exit codes (M2)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from steamzero import CONTRACT_VERSION
from steamzero.api import contracts
from steamzero.cli import main as cli
from steamzero.privileged.protocol import Response


@pytest.fixture(autouse=True)
def state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("STEAMZERO_NO_DAEMON", "1")
    return tmp_path


def test_doctor_json_validates_envelope(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["doctor", "--json"])
    out = capsys.readouterr().out
    # stdout PURO: exatamente um objeto JSON
    env = json.loads(out)
    contracts.validate(env, "envelope-v2.schema.json")
    assert env["module"] == "doctor"
    assert env["contract"] == CONTRACT_VERSION
    assert {c["name"] for c in env["checks"]} >= {"runtime.python", "state.db.integrity"}
    assert code == cli.EXIT_OK


def test_doctor_human_output_has_no_json_envelope(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["doctor"])
    out = capsys.readouterr().out
    assert "doctor run:" in out
    assert "[pass]" in out or "[warn]" in out or "[fail]" in out
    assert code == cli.EXIT_OK
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)  # saída humana não é JSON


def test_contract_version(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["--contract-version"])
    assert capsys.readouterr().out.strip() == CONTRACT_VERSION
    assert code == cli.EXIT_OK


def test_jobs_list_empty(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["jobs", "list", "--json"])
    env = json.loads(capsys.readouterr().out)
    contracts.validate(env, "envelope-v2.schema.json")
    assert env["status"] == "noop"
    assert env["data"]["count"] == 0
    assert code == cli.EXIT_OK


def test_admin_health_uses_read_only_contract(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = SimpleNamespace(
        available=lambda: True,
        request=lambda action, params: Response(
            ok=True,
            result={
                "healthy": action == "health" and params == {},
                "protocolVersion": 1,
                "effectiveUid": 0,
                "mutationsEnabled": False,
            },
        ),
    )
    monkeypatch.setattr(cli, "_admin_client", lambda: fake)
    assert cli.main(["admin", "health", "--json"]) == cli.EXIT_OK
    envelope = json.loads(capsys.readouterr().out)
    contracts.validate(envelope, "envelope-v2.schema.json")
    assert envelope["data"]["mutationsEnabled"] is False

    from steamzero.service.methods import CLI_METHODS

    assert ("admin", "health") not in CLI_METHODS


def test_session_status_and_recovery_use_stable_contract(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeSessionLauncher:
        def status(self, app_id: str) -> dict[str, object]:
            return {
                "state": "stale",
                "statusLabel": "Sessão interrompida",
                "recoveryRequired": True,
                "runtime": {"sessionId": "S1", "gameId": app_id, "state": "running"},
            }

        def recover(self, app_id: str) -> dict[str, object]:
            return {"status": "recovered", "gameId": app_id}

    monkeypatch.setattr(cli, "_session_launcher", FakeSessionLauncher)
    assert cli.main(["session", "status", "--game-id", "10", "--json"]) == cli.EXIT_BLOCKED
    status = json.loads(capsys.readouterr().out)
    contracts.validate(status, "envelope-v2.schema.json")
    assert status["blockers"][0]["code"] == "E-SESSION-INTERRUPTED"
    assert status["data"]["runtime"]["sessionId"] == "S1"

    assert cli.main(["session", "recover", "--game-id", "10", "--json"]) == cli.EXIT_OK
    recovered = json.loads(capsys.readouterr().out)
    assert recovered["status"] == "ok"
    assert recovered["data"] == {"status": "recovered", "gameId": "10"}


def test_session_environment_is_read_only_and_validates_contract(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = {
        "schemaVersion": 1,
        "observedAt": "2026-07-17T00:00:00+00:00",
        "readOnly": True,
        "device": {
            "dmi": {"sys_vendor": "valve"},
            "signals": {"internal_display_present": "true"},
            "evidenceCount": 2,
            "kind": "deck-lcd",
        },
        "session": {
            "id": "3",
            "type": "wayland",
            "desktop": "KDE",
            "waylandDisplay": "wayland-0",
            "display": None,
        },
        "power": {"onAC": False, "batteries": []},
        "network": {"online": True, "interfaces": []},
        "displays": [],
        "volumes": [],
    }
    monkeypatch.setattr(cli, "_session_environment", lambda: snapshot)

    assert cli.main(["session", "environment", "--json"]) == cli.EXIT_OK
    envelope = json.loads(capsys.readouterr().out)
    contracts.validate(envelope, "envelope-v2.schema.json")
    contracts.validate(envelope["data"], "session-environment-v1.schema.json")
    assert envelope["data"]["readOnly"] is True


def test_state_export_json(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["state", "export", "--json"])
    env = json.loads(capsys.readouterr().out)
    contracts.validate(env, "envelope-v2.schema.json")
    assert "job" in env["data"]["tables"]
    assert code == cli.EXIT_OK


def test_state_export_to_file(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    out_file = tmp_path / "export.json"
    code = cli.main(["state", "export", "--out", str(out_file), "--json"])
    env = json.loads(capsys.readouterr().out)
    assert env["data"]["written"] == str(out_file)
    assert code == cli.EXIT_OK
    loaded = json.loads(out_file.read_text())
    assert "tables" in loaded


def test_unknown_action_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["frobnicate", "now", "--json"])
    env = json.loads(capsys.readouterr().out)
    assert env["error"]["code"] == "E-CLI-USAGE"
    assert code == cli.EXIT_USAGE


def test_no_args_usage(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main([])
    assert code == cli.EXIT_USAGE
    assert "steamzero" in capsys.readouterr().err


def test_help(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["--help"])
    assert code == cli.EXIT_OK
    assert "Domínios" in capsys.readouterr().out


def test_desktop_status_works_without_optional_commands(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "")
    code = cli.main(["desktop", "status", "--json"])
    env = json.loads(capsys.readouterr().out)
    contracts.validate(env, "envelope-v2.schema.json")
    contracts.validate(env["data"], "desktop-status-v1.schema.json")
    assert env["data"]["independentRuntime"] is True
    assert code == cli.EXIT_OK


def test_desktop_plan_and_apply_without_optional_commands(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "")
    assert cli.main(["desktop", "plan", "--profile", "safe", "--json"]) == cli.EXIT_OK
    planned = json.loads(capsys.readouterr().out)
    plan = planned["data"]["plan"]
    contracts.validate(plan, "desktop-plan-v1.schema.json")

    code = cli.main(
        [
            "desktop",
            "reset",
            "--plan-id",
            plan["planId"],
            "--confirm",
            plan["confirmToken"],
            "--json",
        ]
    )
    applied = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK
    assert applied["status"] == "degraded"
    assert applied["data"]["profile"]["id"] == "safe"


def test_desktop_apply_requires_confirm(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["desktop", "apply", "--plan-id", "missing", "--json"])
    env = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_FAILURE
    assert env["error"]["code"] == "E-API-SCHEMA"


def test_desktop_status_surfaces_generic_owner_blocker(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("STEAMZERO_DESKTOP_CONFLICT", "controlador externo em teste")
    code = cli.main(["desktop", "status", "--json"])
    env = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_BLOCKED
    assert env["blockers"] == [
        {"code": "E-DESKTOP-OWNER-CONFLICT", "message": "controlador externo em teste"}
    ]


class _FakeComponentRegistry:
    def list(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(id="demo-flatpak")]


class _FakeComponentExecutor:
    def __init__(self) -> None:
        self.applied: tuple[str, str] | None = None

    def status(self, adapter_id: str) -> dict[str, object]:
        return {"id": adapter_id, "state": "missing", "pinned": False}

    def plan_install(self, adapter_id: str) -> SimpleNamespace:
        data = {
            "schemaVersion": 1,
            "planId": "01J000000000000000000000AA",
            "confirmToken": "confirm",
            "adapterId": adapter_id,
            "ref": "org.example.Emulator",
            "remote": "flathub",
            "targetCommit": "a" * 64,
            "before": {
                "installed": False,
                "ref": "org.example.Emulator",
                "origin": None,
                "commit": None,
            },
            "action": "install",
            "status": "pending",
            "createdAt": "2026-07-15T00:00:00+00:00",
            "expiresAt": "2026-07-15T01:00:00+00:00",
            "rollbackGuarantee": "G-DEPLOYMENT",
            "preview": "install demo",
        }
        return SimpleNamespace(action="install", to_dict=lambda: data)

    def apply(self, plan_id: str, confirm: str) -> SimpleNamespace:
        self.applied = (plan_id, confirm)
        data = {
            "operationId": "01J000000000000000000000AB",
            "status": "ok",
            "adapterId": "demo-flatpak",
            "commit": "a" * 64,
        }
        return SimpleNamespace(
            status="ok",
            operation_id=data["operationId"],
            to_dict=lambda: data,
        )


def test_component_list_and_plan_use_contract_envelopes(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeComponentExecutor()
    monkeypatch.setattr(cli, "_component_runtime", lambda _store: (_FakeComponentRegistry(), fake))

    assert cli.main(["component", "list", "--json"]) == cli.EXIT_OK
    listed = json.loads(capsys.readouterr().out)
    contracts.validate(listed, "envelope-v2.schema.json")
    assert listed["data"]["components"][0]["id"] == "demo-flatpak"

    assert cli.main(["component", "plan", "--id", "demo-flatpak", "--json"]) == cli.EXIT_OK
    planned = json.loads(capsys.readouterr().out)
    contracts.validate(planned["data"]["plan"], "component-plan-v1.schema.json")


def test_component_apply_requires_and_forwards_confirmation(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeComponentExecutor()
    monkeypatch.setattr(cli, "_component_runtime", lambda _store: (_FakeComponentRegistry(), fake))

    code = cli.main(
        [
            "component",
            "apply",
            "--plan-id",
            "01J000000000000000000000AA",
            "--confirm",
            "confirm",
            "--json",
        ]
    )
    env = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK
    assert fake.applied == ("01J000000000000000000000AA", "confirm")
    assert env["operationId"] == "01J000000000000000000000AB"
