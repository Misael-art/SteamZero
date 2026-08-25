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
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.jobs.manager import JobContext, JobManager
from steamzero.jobs.models import Job
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


def test_component_rollback_reports_rolled_back_as_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Lifecycle:
        def rollback(self, operation_id: str) -> dict[str, str]:
            return {"operationId": operation_id, "status": "rolled-back"}

    monkeypatch.setattr(cli, "_component_lifecycle", lambda _store: Lifecycle())
    envelope, exit_code = cli._cmd_component_rollback(
        ["--operation-id", "01J000000000000000000000ZZ"], "correlation"
    )

    assert exit_code == cli.EXIT_OK
    assert envelope["status"] == "rolled-back"
    assert envelope["ok"] is True


def test_jobs_list_empty(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["jobs", "list", "--json"])
    env = json.loads(capsys.readouterr().out)
    contracts.validate(env, "envelope-v2.schema.json")
    assert env["status"] == "noop"
    assert env["data"]["count"] == 0
    assert code == cli.EXIT_OK


def test_jobs_and_operations_list_are_paginated(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with StateStore() as store:
        store.migrate()
        for identifier in (
            "01J0000000000000000000000A",
            "01J0000000000000000000000B",
            "01J0000000000000000000000C",
        ):
            store.save_job(
                {
                    "id": identifier,
                    "type": "scan",
                    "priority": "background",
                    "state": "queued",
                }
            )
            store.save_operation(identifier, state="committed")

    assert cli.main(["jobs", "list", "--limit", "2", "--json"]) == cli.EXIT_OK
    jobs = json.loads(capsys.readouterr().out)["data"]
    assert [row["id"] for row in jobs["jobs"]] == [
        "01J0000000000000000000000C",
        "01J0000000000000000000000B",
    ]
    assert jobs["page"] == {
        "limit": 2,
        "hasMore": True,
        "nextCursor": "01J0000000000000000000000B",
    }

    assert (
        cli.main(
            [
                "operations",
                "list",
                "--limit",
                "2",
                "--cursor",
                jobs["page"]["nextCursor"],
                "--json",
            ]
        )
        == cli.EXIT_OK
    )
    operations = json.loads(capsys.readouterr().out)["data"]
    assert [row["id"] for row in operations["operations"]] == ["01J0000000000000000000000A"]
    assert operations["page"]["hasMore"] is False


def test_playtime_list_and_show_use_versioned_read_model(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with StateStore() as store:
        store.migrate()
        store.create_game_session(
            {
                "id": "PLAYTIME-SESSION",
                "game_id": "10",
                "state": "launching",
                "owner": "steamzero-game-session",
                "metadata_json": '{"source":"steam","title":"Portal"}',
            }
        )
        store.transition_game_session("PLAYTIME-SESSION", "running")
        store.transition_game_session(
            "PLAYTIME-SESSION",
            "closed",
            finished_at="2026-07-23T12:00:00+00:00",
            played_seconds=3661,
            duration_source="observed-monotonic",
        )

    assert cli.main(["playtime", "list", "--limit", "10", "--json"]) == cli.EXIT_OK
    listing = json.loads(capsys.readouterr().out)
    assert listing["module"] == "playtime"
    assert listing["data"]["games"][0]["playedSeconds"] == 3661

    assert cli.main(["playtime", "show", "--game-id", "10", "--json"]) == cli.EXIT_OK
    detail = json.loads(capsys.readouterr().out)
    assert detail["data"]["game"]["title"] == "Portal"


@pytest.mark.parametrize(
    "args",
    [
        ["playtime", "list", "--limit", "101"],
        ["playtime", "list", "--cursor"],
        ["playtime", "show", "--game-id", "10", "--game-id", "20"],
        ["playtime", "show", "--shell", "x"],
    ],
)
def test_playtime_cli_rejects_unbounded_or_ambiguous_flags(
    capsys: pytest.CaptureFixture[str], args: list[str]
) -> None:
    assert cli.main([*args, "--json"]) == cli.EXIT_FAILURE
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "E-API-SCHEMA"


def test_jobs_follow_emits_reconnectable_event_v1_ndjson(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with StateStore() as store:
        store.migrate()
        jobs = JobManager(store)

        def work(_job: Job, context: JobContext) -> dict[str, bool]:
            context.set_progress("scan", current=1, total=1, unit="catalogs")
            return {"ok": True}

        jobs.register("scan", work)
        job = jobs.create(
            "scan",
            correlation_id="01J000000000000000000000AA",
        )
        jobs.run(job.id)

    assert (
        cli.main(
            [
                "jobs",
                "list",
                "--follow",
                "--job-id",
                job.id,
                "--cursor",
                "0",
                "--timeout",
                "0",
                "--limit",
                "2",
                "--json",
            ]
        )
        == cli.EXIT_OK
    )
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert [event["seq"] for event in events] == sorted(event["seq"] for event in events)
    assert events[-1]["state"] == "completed"
    assert all(event["jobId"] == job.id for event in events)
    assert any(event.get("progress", {}).get("unit") == "catalogs" for event in events)
    for event in events:
        contracts.validate(event, "event-v1.schema.json")


def test_operations_follow_emits_state_events_without_internal_paths(
    capsys: pytest.CaptureFixture[str],
) -> None:
    operation_id = "01J000000000000000000000AB"
    with StateStore() as store:
        store.migrate()
        store.save_operation(
            operation_id,
            state="applying",
            journal_path="/private/journal.jsonl",
            backup_path="/private/backup",
        )
        store.save_operation(
            operation_id,
            state="committed",
            journal_path="/private/journal.jsonl",
            backup_path="/private/backup",
        )

    assert (
        cli.main(
            [
                "operations",
                "list",
                "--follow",
                "--operation-id",
                operation_id,
                "--cursor",
                "0",
                "--timeout",
                "0",
                "--json",
            ]
        )
        == cli.EXIT_OK
    )
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [event["state"] for event in events] == ["applying", "committed"]
    assert all(event["operationId"] == operation_id for event in events)
    assert all("journalPath" not in event and "backupPath" not in event for event in events)


@pytest.mark.parametrize(
    ("argv", "detail"),
    [
        (["jobs", "list", "--limit", "nope", "--json"], "--limit precisa ser inteiro"),
        (["jobs", "list", "--limit", "0", "--json"], "--limit precisa estar"),
        (
            ["jobs", "list", "--cursor", "x" * 129, "--json"],
            "cursor inválido",
        ),
        (
            [
                "jobs",
                "list",
                "--follow",
                "--cursor",
                "-1",
                "--timeout",
                "0",
                "--json",
            ],
            "cursor de evento inválido",
        ),
        (
            [
                "jobs",
                "list",
                "--follow",
                "--timeout",
                "nope",
                "--json",
            ],
            "--timeout precisa ser número",
        ),
        (
            [
                "jobs",
                "list",
                "--follow",
                "--timeout",
                "86401",
                "--json",
            ],
            "--timeout precisa estar",
        ),
        (
            [
                "jobs",
                "list",
                "--follow",
                "--job-id",
                "missing",
                "--timeout",
                "0",
                "--json",
            ],
            "job inexistente",
        ),
        (
            [
                "operations",
                "list",
                "--follow",
                "--operation-id",
                "missing",
                "--timeout",
                "0",
                "--json",
            ],
            "operação inexistente",
        ),
    ],
)
def test_paginated_cli_rejects_invalid_limits_cursors_and_follow_targets(
    capsys: pytest.CaptureFixture[str], argv: list[str], detail: str
) -> None:
    assert cli.main(argv) == cli.EXIT_FAILURE
    envelope = json.loads(capsys.readouterr().out)
    assert detail in envelope["error"]["detail"]


def test_follow_rejects_unrelated_actions_and_has_human_stream(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["doctor", "--follow", "--json"]) == cli.EXIT_USAGE
    rejected = json.loads(capsys.readouterr().out)
    assert rejected["error"]["code"] == "E-CLI-USAGE"

    with StateStore() as store:
        store.migrate()
        jobs = JobManager(store)
        job = jobs.create("noop")
        jobs.cancel(job.id)
    assert (
        cli.main(
            [
                "jobs",
                "list",
                "--follow",
                "--job-id",
                job.id,
                "--cursor",
                "0",
                "--timeout",
                "0",
            ]
        )
        == cli.EXIT_OK
    )
    human = capsys.readouterr().out
    assert "job.state" in human
    assert job.id in human


def test_follow_helpers_cover_default_timeout_interrupt_and_invalid_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert cli._follow_timeout([]) is None  # type: ignore[attr-defined]
    with pytest.raises(SteamZeroError, match="não é suportado"):
        cli._run_follow("invalid", [], json_out=True)  # type: ignore[attr-defined]

    from steamzero.api import events

    def interrupted(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise KeyboardInterrupt
        yield

    monkeypatch.setattr(events, "follow_events", interrupted)
    assert cli._run_follow("jobs", [], json_out=True) == cli.EXIT_OK  # type: ignore[attr-defined]


def test_jobs_list_degrades_corrupt_private_progress_payload(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with StateStore() as store:
        store.migrate()
        store.save_job(
            {
                "id": "01J000000000000000000000AB",
                "type": "scan",
                "priority": "background",
                "state": "queued",
                "progress_json": "{",
            }
        )

    assert cli.main(["jobs", "list", "--json"]) == cli.EXIT_OK
    job = json.loads(capsys.readouterr().out)["data"]["jobs"][0]
    assert job["progress"] is None


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


def test_desktop_gamemode_status_is_read_only_with_validated_plan(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "")
    code = cli.main(["desktop", "gamemode-status", "--json"])
    env = json.loads(capsys.readouterr().out)
    contracts.validate(env, "envelope-v2.schema.json")
    assert env["module"] == "desktop"
    assert env["action"] == "gamemode-status"
    assert code == cli.EXIT_OK
    gamemode = env["data"]["gamemode"]
    for key in (
        "binaryState",
        "daemonState",
        "authorizationState",
        "capabilityState",
        "activityState",
        "effects",
        "condition",
        "state",
        "statusLabel",
        "cause",
        "remediation",
        "requiresOperator",
    ):
        assert key in gamemode
    assert gamemode["state"] in {"ready", "degraded", "missing", "unknown"}
    plan = env["data"]["adminPlan"]
    contracts.validate(plan, "gamemode-admin-plan-v1.schema.json")
    assert plan["executesHostChanges"] is False


def test_system_resources_is_read_only_with_class_attribution(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "")
    code = cli.main(["system", "resources", "--json"])
    env = json.loads(capsys.readouterr().out)
    contracts.validate(env, "envelope-v2.schema.json")
    assert env["module"] == "system"
    assert env["action"] == "resources"
    assert code == cli.EXIT_OK
    resources = env["data"]["resources"]
    assert resources["schemaVersion"] == 1
    assert resources["readOnly"] is True
    assert isinstance(resources["complete"], bool)
    assert [row["processClass"] for row in resources["classes"]] == [
        "ui",
        "daemon",
        "media-job",
        "emulator",
        "emulator-child",
        "unknown",
    ]
    totals = resources["totals"]
    assert "attributed" in totals
    assert "unattributable" in totals
    assert "leak" not in json.dumps(env).lower()
    assert "cmdline" not in json.dumps(env)


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


def test_cloud_cli_uses_closed_controller_contracts(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from steamzero.adapters import emulation

    calls: list[tuple[str, ...]] = []

    class Controller:
        def cloud_platforms(self) -> list[dict[str, object]]:
            calls.append(("list",))
            return [{"id": "geforce-now", "cloud": {"serviceAvailability": "unverified"}}]

        def launch_cloud(self, platform_id: str) -> dict[str, object]:
            calls.append(("launch", platform_id))
            return {"status": "started", "platformId": platform_id}

        def plan_action(self, payload: dict[str, object]) -> dict[str, object]:
            calls.append(("plan", str(payload["actionId"])))
            return {"planId": "cloud-plan", "confirmToken": "cloud-confirm"}

        def apply_action(self, plan_id: str, confirm_token: str) -> dict[str, object]:
            calls.append(("apply", plan_id, confirm_token))
            return {"status": "committed", "operationId": "cloud-operation"}

        def close(self) -> None:
            calls.append(("close",))

    monkeypatch.setattr(emulation, "EmulationController", Controller)

    assert cli.main(["cloud", "list", "--json"]) == cli.EXIT_OK
    listed = json.loads(capsys.readouterr().out)
    assert listed["data"]["platforms"][0]["id"] == "geforce-now"

    assert cli.main(["cloud", "launch", "--platform", "xbox-cloud-gaming", "--json"]) == cli.EXIT_OK
    launched = json.loads(capsys.readouterr().out)
    assert launched["data"]["platformId"] == "xbox-cloud-gaming"

    assert cli.main(["cloud", "plan", "--json"]) == cli.EXIT_OK
    planned = json.loads(capsys.readouterr().out)
    assert planned["data"]["planId"] == "cloud-plan"

    assert (
        cli.main(
            [
                "cloud",
                "apply",
                "--plan-id",
                "cloud-plan",
                "--confirm",
                "cloud-confirm",
                "--json",
            ]
        )
        == cli.EXIT_OK
    )
    applied = json.loads(capsys.readouterr().out)
    assert applied["data"]["operationId"] == "cloud-operation"
    assert calls == [
        ("list",),
        ("close",),
        ("launch", "xbox-cloud-gaming"),
        ("close",),
        ("plan", "cloud.shortcuts.sync"),
        ("close",),
        ("apply", "cloud-plan", "cloud-confirm"),
        ("close",),
    ]


def test_hud_cli_publishes_versioned_offscreen_evidence(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", "")

    assert cli.main(["hud", "presets", "--json"]) == cli.EXIT_OK
    envelope = json.loads(capsys.readouterr().out)
    contracts.validate(envelope["data"], "gtool-hud-v1.schema.json")
    assert envelope["data"]["runtime"]["state"] == "unavailable"
    assert envelope["data"]["evidence"]["humanReview"]["state"] == "PENDING-HUMAN"


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


class _FakeComponentLifecycle:
    def __init__(self) -> None:
        self.applied: tuple[str, str] | None = None
        self.recovery_applied: tuple[str, str] | None = None

    def verify(self, adapter_id: str) -> dict[str, object]:
        self.verified = adapter_id
        return {"id": adapter_id, "state": "degraded", "verified": False, "repairable": True}

    def launch(self, adapter_id: str) -> dict[str, object]:
        self.launched = adapter_id
        return {"status": "started", "componentId": adapter_id, "pid": 4242}

    def stop(self, adapter_id: str) -> dict[str, object]:
        self.stopped = adapter_id
        return {"status": "not-supported", "componentId": adapter_id}

    def open_config(self, adapter_id: str) -> dict[str, object]:
        self.configured = adapter_id
        return {"status": "started", "componentId": adapter_id, "pid": 77}

    def status_all(self) -> list[dict[str, object]]:
        return [
            {
                "id": "demo-flatpak",
                "state": "missing",
                "installed": False,
                "installable": True,
                "executor": "flatpak",
                "sourceType": "flatpak",
                "version": None,
                "targetVersion": "a" * 64,
                "origin": None,
                "detail": None,
                "endOfLife": False,
            }
        ]

    def plan(self, adapter_id: str, action: str = "install") -> SimpleNamespace:
        data = {
            "schemaVersion": 2,
            "planId": "01J000000000000000000000AA",
            "confirmToken": "confirm",
            "adapterId": adapter_id,
            "executor": "flatpak",
            "action": action,
            "sourceFingerprint": {"type": "flatpak"},
            "delegated": {"flatpakPlanId": "01J000000000000000000000AA"},
            "status": "pending",
            "createdAt": "2026-07-15T00:00:00+00:00",
            "expiresAt": "2026-07-15T01:00:00+00:00",
            "rollbackGuarantee": "G-DEPLOYMENT",
            "preview": "install demo",
        }
        return SimpleNamespace(action=action, to_dict=lambda: data)

    def apply(self, plan_id: str, confirm: str) -> dict[str, object]:
        self.applied = (plan_id, confirm)
        return {
            "operationId": "01J000000000000000000000AB",
            "status": "ok",
            "adapterId": "demo-flatpak",
            "commit": "a" * 64,
        }

    def recovery_inspect(self) -> list[dict[str, object]]:
        return [{"operationId": "pending", "adapterId": "demo-flatpak", "state": "applying"}]

    def plan_recovery(self) -> dict[str, object]:
        return {"planId": "recovery-plan", "confirmToken": "recovery-confirm"}

    def apply_recovery(self, plan_id: str, confirm: str) -> dict[str, object]:
        self.recovery_applied = (plan_id, confirm)
        return {"status": "ok", "operationId": "recovery-operation", "operations": []}


def test_component_list_and_plan_use_contract_envelopes(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeComponentLifecycle()
    monkeypatch.setattr(cli, "_component_lifecycle", lambda _store: fake)

    assert cli.main(["component", "list", "--json"]) == cli.EXIT_OK
    listed = json.loads(capsys.readouterr().out)
    contracts.validate(listed, "envelope-v2.schema.json")
    assert listed["data"]["components"][0]["id"] == "demo-flatpak"

    assert cli.main(["component", "plan", "--id", "demo-flatpak", "--json"]) == cli.EXIT_OK
    planned = json.loads(capsys.readouterr().out)
    contracts.validate(planned["data"]["plan"], "component-plan-v2.schema.json")


def test_component_recover_requires_an_explicit_plan_confirmation(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeComponentLifecycle()
    monkeypatch.setattr(cli, "_component_lifecycle", lambda _store: fake)

    assert cli.main(["component", "recover", "--json"]) == cli.EXIT_OK
    reviewed = json.loads(capsys.readouterr().out)
    assert reviewed["data"] == {
        "operations": [
            {"operationId": "pending", "adapterId": "demo-flatpak", "state": "applying"}
        ],
        "count": 1,
        "plan": {"planId": "recovery-plan", "confirmToken": "recovery-confirm"},
    }
    assert fake.recovery_applied is None

    assert (
        cli.main(
            [
                "component",
                "recover",
                "--plan-id",
                "recovery-plan",
                "--confirm",
                "recovery-confirm",
                "--json",
            ]
        )
        == cli.EXIT_OK
    )
    applied = json.loads(capsys.readouterr().out)
    assert applied["data"]["operationId"] == "recovery-operation"
    assert fake.recovery_applied == ("recovery-plan", "recovery-confirm")


def test_component_lifecycle_builder_imports_adapter_registry_at_runtime(
    tmp_path: Path,
) -> None:
    """Regressão G27/G31: `AdapterRegistry` vive só sob `if TYPE_CHECKING:` no
    topo do módulo; `_component_lifecycle` precisa importá-lo no próprio escopo,
    senão `component list` quebra em runtime com NameError (visto em release
    instalada e confirmado no fonte da main)."""
    store = StateStore(tmp_path / "state.db")
    store.migrate()
    lifecycle = cli._component_lifecycle(store)
    assert lifecycle is not None
    store.close()


def test_component_apply_starts_a_durable_job_without_waiting_for_the_download(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeComponentJobs:
        def __init__(self) -> None:
            self.started: tuple[str, str] | None = None

        def start(self, plan_id: str, confirm_token: str) -> dict[str, object]:
            self.started = (plan_id, confirm_token)
            return {
                "jobId": "01J000000000000000000000AB",
                "state": "queued",
                "rawState": "queued",
                "planId": plan_id,
            }

    jobs = FakeComponentJobs()
    monkeypatch.setattr(cli, "_component_job_service", lambda: jobs)

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
    assert jobs.started == ("01J000000000000000000000AA", "confirm")
    assert env["jobId"] == "01J000000000000000000000AB"
    assert env["operationId"] is None
    assert env["data"]["state"] == "queued"


def test_state_audit_reports_clean(capsys: pytest.CaptureFixture[str]) -> None:
    # G25: state audit read-only; estado limpo -> status ok, clean True.
    code = cli.main(["state", "audit", "--json"])
    env = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK
    assert env["module"] == "state"
    assert env["status"] == "ok"
    assert env["data"]["clean"] is True


def test_state_audit_flags_orphan_staging(capsys: pytest.CaptureFixture[str]) -> None:
    # G25: staging órfão faz state audit reportar degraded com o órfão listado.
    from steamzero.core import fs as core_fs
    from steamzero.core import paths as core_paths

    core_fs.ensure_state_layout()
    (core_paths.staging_dir() / "op-sem-banco").mkdir(parents=True, exist_ok=True)
    code = cli.main(["state", "audit", "--json"])
    env = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK
    assert env["status"] == "degraded"
    assert env["data"]["clean"] is False
    assert "op-sem-banco" in env["data"]["orphanStaging"]


def test_state_cleanup_plan_and_apply_roundtrip(capsys: pytest.CaptureFixture[str]) -> None:
    # G25/A42: cleanup-plan gera plano com token; cleanup-apply move para
    # quarentena (recoverable) usando --plan-id + --confirm. Não deleta.
    from steamzero.core import fs as core_fs
    from steamzero.core import paths as core_paths

    core_fs.ensure_state_layout()
    orphan = core_paths.staging_dir() / "orphan-tree"
    orphan.mkdir(parents=True, exist_ok=True)
    (orphan / "marker.txt").write_text("x")

    # Fase 1: plano.
    code = cli.main(["state", "cleanup-plan", "--json"])
    env = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK
    plan = env["data"]
    plan_id = plan["planId"]
    confirm = plan["confirmToken"]
    assert plan["count"] >= 1

    # Fase 2: aplicar move o órfão para a quarentena; a fonte some.
    code = cli.main(
        ["state", "cleanup-apply", "--plan-id", plan_id, "--confirm", confirm, "--json"]
    )
    env = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK
    assert env["data"]["count"] >= 1
    assert not orphan.exists()  # movido, não deletado
    # Recuperável: está na quarentena.
    quarantined = list(core_paths.quarantine_dir().rglob("marker.txt"))
    assert quarantined, "artefato deve estar na quarentena (recoverable)"


def test_state_cleanup_apply_rejects_wrong_token(capsys: pytest.CaptureFixture[str]) -> None:
    # G25/A42: token incorreto não aplica — proteção contra plano desatualizado.
    from steamzero.core import fs as core_fs
    from steamzero.core import paths as core_paths

    core_fs.ensure_state_layout()
    (core_paths.staging_dir() / "op-sem-banco").mkdir(parents=True, exist_ok=True)
    cli.main(["state", "cleanup-plan", "--json"])
    capsys.readouterr()  # descarta saída do plano

    # A aplicação com confirm errado falha sem mover nada.
    code = cli.main(
        [
            "state",
            "cleanup-apply",
            "--plan-id",
            "01J000000000000000000000AA",
            "--confirm",
            "errado",
            "--json",
        ]
    )
    assert code == cli.EXIT_FAILURE


def test_component_verify_is_read_only_and_reports_degraded_without_failing(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verificar não pede token e não é erro quando encontra problema.

    O envelope sai `degraded` com exit 0: o comando cumpriu seu papel — dizer a
    verdade sobre o deployment. Sair diferente de zero faria script de operador
    tratar "verifiquei e está ruim" como "não consegui verificar".
    """
    fake = _FakeComponentLifecycle()
    monkeypatch.setattr(cli, "_component_lifecycle", lambda _store: fake)

    code = cli.main(["component", "verify", "--id", "demo-flatpak", "--json"])
    env = json.loads(capsys.readouterr().out)

    assert code == cli.EXIT_OK
    contracts.validate(env, "envelope-v2.schema.json")
    assert env["status"] == "degraded"
    assert env["data"]["verified"] is False
    assert fake.verified == "demo-flatpak"


def test_component_launch_stop_and_open_config_are_reachable_from_the_cli(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeComponentLifecycle()
    monkeypatch.setattr(cli, "_component_lifecycle", lambda _store: fake)

    assert cli.main(["component", "launch", "--id", "demo-flatpak", "--json"]) == cli.EXIT_OK
    launched = json.loads(capsys.readouterr().out)
    contracts.validate(launched, "envelope-v2.schema.json")
    assert launched["data"]["pid"] == 4242

    # Flatpak gerencia o próprio processo: `not-supported` é resposta honesta,
    # publicada como degraded, e não uma falha do comando.
    assert cli.main(["component", "stop", "--id", "demo-flatpak", "--json"]) == cli.EXIT_OK
    stopped = json.loads(capsys.readouterr().out)
    assert stopped["status"] == "degraded"
    assert stopped["data"]["status"] == "not-supported"

    assert cli.main(["component", "open-config", "--id", "demo-flatpak", "--json"]) == cli.EXIT_OK
    opened = json.loads(capsys.readouterr().out)
    assert opened["data"] == {"status": "started", "componentId": "demo-flatpak", "pid": 77}

    assert (fake.launched, fake.stopped, fake.configured) == (
        "demo-flatpak",
        "demo-flatpak",
        "demo-flatpak",
    )
