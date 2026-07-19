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

from steamzero.cli import main as cli
from steamzero.core import fs
from steamzero.service.client import invoke
from steamzero.service.core import CoreRequestHandler, CoreServer


@pytest.fixture
def core_service(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    root = Path(__file__).resolve().parents[2]
    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
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
    socket_path = runtime / "steamzero" / "core.sock"
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
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


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
    socket_path = runtime / "steamzero" / "core.sock"
    socket_path.parent.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
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
    assert {"doctor.run", "session.status", "desktop.apply"} <= methods
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
