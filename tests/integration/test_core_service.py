# SPDX-License-Identifier: GPL-3.0-or-later
"""IPC real do daemon user-scoped (ADR-0004 / SR-18)."""

from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from steamzero.api import contracts
from steamzero.cli import main as cli
from steamzero.core import fs, transaction
from steamzero.core.state import StateStore
from steamzero.service.client import invoke, subscribe_events
from steamzero.service.core import CoreRequestHandler, CoreServer
from steamzero.service.socket_path import safe_socket_path


@pytest.fixture
def core_service(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    root = Path(__file__).resolve().parents[2]
    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("STEAMZERO_NO_DAEMON", raising=False)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root / "src")
    process = subprocess.Popen(
        [sys.executable, "-m", "steamzero.service.core"],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    socket_path = safe_socket_path()
    # O checkout suportado pode viver em microSD; import inicial + SQLite sob
    # pressão de I/O do gate completo não deve produzir um falso negativo.
    deadline = time.monotonic() + 60
    while not socket_path.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    if not socket_path.exists():
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
        pytest.fail(f"daemon não iniciou: stdout={stdout!r} stderr={stderr!r}")
    try:
        yield socket_path
    finally:
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)


def _rpc(socket_path: Path, request: dict[str, object]) -> dict[str, object]:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(10)
    client.connect(str(socket_path))
    client.sendall(json.dumps(request).encode("utf-8") + b"\n")
    payload = bytearray()
    while b"\n" not in payload:
        payload.extend(client.recv(65536))
    client.close()
    response = json.loads(bytes(payload).split(b"\n", 1)[0])
    assert isinstance(response, dict)
    return response


@pytest.fixture
def inprocess_core(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    socket_path = safe_socket_path()
    server = CoreServer(str(socket_path), CoreRequestHandler)
    fs.set_mode(socket_path, 0o600)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield socket_path
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        fs.remove_file(socket_path)


def test_daemon_authenticates_local_transport_and_exposes_closed_capabilities(
    core_service: Path,
) -> None:
    mode = core_service.stat().st_mode
    assert stat.S_IMODE(mode) == 0o600
    assert stat.S_IMODE(core_service.parent.stat().st_mode) == 0o700

    hello = _rpc(
        core_service,
        {"jsonrpc": "2.0", "id": 1, "method": "system.hello", "params": {}},
    )
    assert hello["result"]["transport"] == "unix-peercred"  # type: ignore[index]

    capabilities = _rpc(
        core_service,
        {"jsonrpc": "2.0", "id": 2, "method": "system.capabilities", "params": {}},
    )
    methods = {item["method"] for item in capabilities["result"]["methods"]}  # type: ignore[index,union-attr]
    assert {
        "doctor.run",
        "session.status",
        "playtime.list",
        "playtime.show",
        "desktop.apply",
        "events.subscribe",
    } <= methods
    assert "shell.exec" not in methods


def test_daemon_rejects_unknown_method_and_unknown_parameters(core_service: Path) -> None:
    unknown = _rpc(
        core_service,
        {"jsonrpc": "2.0", "id": 1, "method": "shell.exec", "params": {}},
    )
    assert unknown["error"]["code"] == -32601  # type: ignore[index]

    invalid = _rpc(
        core_service,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "session.status",
            "params": {"gameId": "10", "command": "rm"},
        },
    )
    assert invalid["error"]["code"] == -32602  # type: ignore[index]


def test_daemon_exposes_playtime_without_process_or_command_data(
    inprocess_core: Path,
) -> None:
    with StateStore() as store:
        store.migrate()
        store.create_game_session(
            {
                "id": "RPC-PLAYTIME",
                "game_id": "10",
                "state": "launching",
                "owner": "steamzero-game-session",
                "metadata_json": '{"source":"steam","title":"Portal"}',
            }
        )
        store.transition_game_session("RPC-PLAYTIME", "running", pid=4242)
        store.transition_game_session(
            "RPC-PLAYTIME",
            "closed",
            pid=None,
            finished_at="2026-07-23T12:00:00+00:00",
            played_seconds=120,
            duration_source="observed-monotonic",
        )

    listing = _rpc(
        inprocess_core,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "playtime.list",
            "params": {"limit": "10"},
        },
    )
    game = listing["result"]["envelope"]["data"]["games"][0]  # type: ignore[index]
    assert game["playedSeconds"] == 120
    assert "pid" not in game["latestSession"]

    detail = _rpc(
        inprocess_core,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "playtime.show",
            "params": {"gameId": "10"},
        },
    )
    assert detail["result"]["envelope"]["data"]["game"]["title"] == "Portal"  # type: ignore[index]


def test_cli_prefers_daemon_and_preserves_contract(
    core_service: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_local(_args: list[str], _correlation_id: str) -> tuple[dict[str, object], int]:
        raise AssertionError("handler local não deveria ser chamado")

    monkeypatch.setitem(cli.HANDLERS, ("doctor", None), fail_local)
    code = cli.main(["doctor", "--json"])
    envelope = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK
    assert envelope["module"] == "doctor"
    assert envelope["status"] in {"ok", "degraded"}

    invocation = invoke(
        "session.status",
        {"gameId": "10", "correlationId": "01J000000000000000000000AA"},
    )
    assert invocation.envelope["module"] == "session"


def test_daemon_exposes_paginated_jobs_through_same_cli_contract(
    core_service: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with StateStore() as store:
        store.migrate()
        store.save_job(
            {
                "id": "J-PAGED",
                "type": "catalog.search",
                "priority": "interactive",
                "state": "queued",
                "correlation_id": "01J000000000000000000000AA",
            }
        )

    def fail_local(_args: list[str], _correlation_id: str) -> tuple[dict[str, object], int]:
        raise AssertionError("handler local não deveria ser chamado")

    monkeypatch.setitem(cli.HANDLERS, ("jobs", "list"), fail_local)
    assert cli.main(["jobs", "list", "--limit", "1", "--json"]) == cli.EXIT_OK
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["data"]["jobs"][0]["id"] == "J-PAGED"
    assert envelope["data"]["page"]["limit"] == 1


def test_inprocess_server_covers_rpc_errors_and_domain_dispatch(inprocess_core: Path) -> None:
    malformed = _rpc(inprocess_core, {"jsonrpc": "1.0", "id": 1, "method": "doctor.run"})
    assert malformed["error"]["code"] == -32600  # type: ignore[index]

    bad_params = _rpc(
        inprocess_core,
        {"jsonrpc": "2.0", "id": 2, "method": "desktop.plan", "params": {"profile": "turbo"}},
    )
    assert bad_params["error"]["code"] == -32602  # type: ignore[index]

    doctor = invoke("doctor.run", {"correlationId": "01J000000000000000000000AA"}, timeout=10)
    assert doctor.envelope["module"] == "doctor"
    status = invoke(
        "session.status",
        {"gameId": "10", "correlationId": "01J000000000000000000000AB"},
        timeout=10,
    )
    assert status.envelope["module"] == "session"


@pytest.mark.parametrize("_repetition", range(5))
def test_daemon_controls_profile_roundtrip_is_closed_and_reversible(
    inprocess_core: Path,
    tmp_path: Path,
    _repetition: int,
) -> None:
    del _repetition
    planned = invoke(
        "controls.plan",
        {
            "platformId": "switch",
            "profileId": "standard-gamepad",
            "orientation": "portrait-right",
            "correlationId": "01J000000000000000000000AC",
        },
    ).envelope["data"]
    applied = invoke(
        "controls.apply",
        {
            "planId": planned["planId"],
            "confirmToken": planned["confirmToken"],
            "correlationId": "01J000000000000000000000AD",
        },
    ).envelope["data"]
    assert len(applied["actions"]) == 1
    target = (
        tmp_path
        / "config"
        / "steamzero"
        / "input-profiles"
        / "active"
        / "switch"
        / "platform-default.json"
    )
    assert target.is_file(), {"applied": applied, "target": str(target)}
    activation = json.loads(target.read_text(encoding="utf-8"))
    assert activation["profile"]["id"] == "standard-gamepad"
    assert activation["orientation"] == "portrait-right"

    observed = invoke(
        "controls.profiles",
        {
            "platformId": "switch",
            "correlationId": "01J000000000000000000000AE",
        },
    ).envelope["data"]
    assert observed["state"] == "ready", observed
    active = observed["active"]
    assert isinstance(active, dict), observed
    assert active["id"] == "standard-gamepad"
    assert active["orientation"] == "portrait-right"

    rolled_back = invoke(
        "controls.rollback",
        {
            "operationId": applied["operationId"],
            "correlationId": "01J000000000000000000000AF",
        },
    ).envelope["data"]
    assert rolled_back["status"] == "rolled-back"


def test_daemon_operation_history_previews_and_confirms_rollback(
    inprocess_core: Path,
    tmp_path: Path,
) -> None:
    del inprocess_core
    managed = tmp_path / "managed"
    target = managed / "settings.ini"
    fs.write_atomic(target, b"before")
    plan = transaction.plan_write_files(
        {target: b"after"},
        root=managed,
        kind="emulator.config",
    )
    applied = transaction.apply(plan.plan_id, plan.confirm_token)

    detail = invoke(
        "operations.show",
        {
            "operationId": applied.operation_id,
            "correlationId": "01J000000000000000000000AG",
        },
    ).envelope["data"]["operation"]
    assert detail["rollback"]["available"] is True

    rollback_plan = invoke(
        "operations.rollback.plan",
        {
            "operationId": applied.operation_id,
            "correlationId": "01J000000000000000000000AH",
        },
    ).envelope["data"]["plan"]
    result = invoke(
        "operations.rollback.apply",
        {
            "planId": rollback_plan["planId"],
            "confirmToken": rollback_plan["confirmToken"],
            "correlationId": "01J000000000000000000000AJ",
        },
    ).envelope["data"]["result"]
    assert result["verified"] is True
    assert target.read_bytes() == b"before"


def test_daemon_collections_roundtrip_is_closed_and_reversible(
    inprocess_core: Path,
) -> None:
    del inprocess_core
    action = json.dumps(
        {"actionId": "favorite.set", "gameRef": "steam:10", "value": True},
        separators=(",", ":"),
    )
    plan = invoke(
        "collections.plan",
        {
            "actionJson": action,
            "correlationId": "01J000000000000000000000AK",
        },
    ).envelope["data"]
    applied = invoke(
        "collections.apply",
        {
            "planId": plan["planId"],
            "confirmToken": plan["confirmToken"],
            "correlationId": "01J000000000000000000000AM",
        },
    ).envelope["data"]
    state = invoke(
        "collections.list",
        {"correlationId": "01J000000000000000000000AN"},
    ).envelope["data"]
    assert state["favorites"] == ["steam:10"]

    rollback = invoke(
        "operations.rollback.plan",
        {
            "operationId": applied["operationId"],
            "correlationId": "01J000000000000000000000AP",
        },
    ).envelope["data"]["plan"]
    invoke(
        "operations.rollback.apply",
        {
            "planId": rollback["planId"],
            "confirmToken": rollback["confirmToken"],
            "correlationId": "01J000000000000000000000AQ",
        },
    )
    state = invoke(
        "collections.list",
        {"correlationId": "01J000000000000000000000AR"},
    ).envelope["data"]
    assert state["favorites"] == []


def test_daemon_library_health_roundtrip_uses_bounded_job(
    inprocess_core: Path,
    tmp_path: Path,
) -> None:
    del inprocess_core
    rom = tmp_path / "Game.nsp"
    rom.write_bytes(b"synthetic" * 256)
    cache = tmp_path / "data" / "steamzero" / "emulation-library-cache-v1.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "unidentified": 0,
                "games": [
                    {
                        "id": "game-health",
                        "name": "Game",
                        "state": "ready",
                        "path": str(rom),
                        "size": rom.stat().st_size,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    before = invoke(
        "health.status",
        {"correlationId": "01J000000000000000000000AS"},
    ).envelope["data"]
    assert before["counts"]["unchecked"] == 1
    plan = invoke(
        "health.plan",
        {"correlationId": "01J000000000000000000000AT"},
    ).envelope["data"]
    result = invoke(
        "health.apply",
        {
            "planId": plan["planId"],
            "confirmToken": plan["confirmToken"],
            "correlationId": "01J000000000000000000000AV",
        },
    ).envelope["data"]
    assert result["job"]["rawState"] == "completed"
    assert result["health"]["state"] == "healthy"


def test_event_subscription_streams_valid_events_and_completes(
    inprocess_core: Path,
) -> None:
    with StateStore() as store:
        store.migrate()
        store.save_job(
            {
                "id": "J-STREAM",
                "type": "catalog.search",
                "priority": "interactive",
                "state": "running",
                "correlation_id": "01J000000000000000000000AA",
            }
        )
        store.append_event(
            "job.progress",
            entity="job:J-STREAM",
            payload={"stage": "download", "current": 1, "total": 2, "unit": "items"},
        )
        store.append_event(
            "job.state",
            entity="job:J-STREAM",
            payload={"state": "completed"},
        )

    events = list(
        subscribe_events(
            {
                "cursor": "0",
                "kinds": ["job.progress", "job.state"],
                "jobIds": ["J-STREAM"],
                "limit": 1,
                "idleTimeout": 0,
                "stopOnTerminal": True,
            }
        )
    )
    assert [event["seq"] for event in events] == sorted(event["seq"] for event in events)
    assert events[-1]["state"] == "completed"
    assert all(event["jobId"] == "J-STREAM" for event in events)
    for event in events:
        contracts.validate(event, "event-v1.schema.json")


def test_cli_follow_prefers_daemon_subscription(
    inprocess_core: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with StateStore() as store:
        store.migrate()
        store.save_job(
            {
                "id": "J-CLI-STREAM",
                "type": "catalog.search",
                "priority": "interactive",
                "state": "running",
                "correlation_id": "01J000000000000000000000AB",
            }
        )
        store.append_event(
            "job.state",
            entity="job:J-CLI-STREAM",
            payload={"state": "completed"},
        )

    class FailLocalStore:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            raise AssertionError("fallback local não deveria ser aberto")

    monkeypatch.setattr(cli, "StateStore", FailLocalStore)
    assert (
        cli.main(
            [
                "jobs",
                "list",
                "--follow",
                "--job-id",
                "J-CLI-STREAM",
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
    assert events[-1]["state"] == "completed"
    assert all(event["jobId"] == "J-CLI-STREAM" for event in events)


def test_inprocess_server_rate_limits_mutations_per_connection(inprocess_core: Path) -> None:
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(2)
    client.connect(str(inprocess_core))
    for request_id in range(1, 18):
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "desktop.plan",
            "params": {"unknown": "value"},
        }
        client.sendall(json.dumps(request).encode() + b"\n")
        payload = bytearray()
        while b"\n" not in payload:
            payload.extend(client.recv(65536))
        response = json.loads(bytes(payload).split(b"\n", 1)[0])
    client.close()
    assert response["error"]["code"] == -32029
