# SPDX-License-Identifier: GPL-3.0-or-later
"""Branches defensivos do transporte JSON-RPC sem subprocesso."""

from __future__ import annotations

import json
import os
import socket
import threading
from pathlib import Path

import pytest

from steamzero.cli import main as cli
from steamzero.core.errors import SteamZeroError
from steamzero.service import core
from steamzero.service.client import CoreProtocolError, CoreUnavailable, invoke
from steamzero.service.socket_path import safe_socket_path


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b"{\n", -32700),
        (json.dumps([]).encode() + b"\n", -32600),
        (
            json.dumps({"jsonrpc": "2.0", "id": True, "method": "doctor.run"}).encode() + b"\n",
            -32600,
        ),
        (json.dumps({"jsonrpc": "2.0", "id": 1, "method": 7}).encode() + b"\n", -32600),
        (json.dumps({"jsonrpc": "2.0", "id": 1, "method": "missing"}).encode() + b"\n", -32601),
    ],
)
def test_dispatch_rejects_malformed_requests(payload: bytes, code: int) -> None:
    response, mutation = core._dispatch(payload)
    assert response["error"]["code"] == code
    assert mutation is False


def test_dispatch_system_methods_and_parameter_guards() -> None:
    hello, _ = core._dispatch(b'{"jsonrpc":"2.0","id":1,"method":"system.hello","params":{}}\n')
    assert hello["result"]["transport"] == "unix-peercred"
    capabilities, _ = core._dispatch(
        b'{"jsonrpc":"2.0","id":2,"method":"system.capabilities","params":{}}\n'
    )
    assert capabilities["result"]["methods"]
    for method in ("system.hello", "system.capabilities"):
        payload = (
            json.dumps(
                {"jsonrpc": "2.0", "id": 3, "method": method, "params": {"extra": 1}}
            ).encode()
            + b"\n"
        )
        response, _ = core._dispatch(payload)
        assert response["error"]["code"] == -32602


def test_domain_exceptions_are_returned_as_typed_envelopes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def blocked(_args: list[str], _correlation: str) -> tuple[dict[str, object], int]:
        raise SteamZeroError("E-TX-LOCKED", detail="ocupado")

    monkeypatch.setitem(cli.HANDLERS, ("doctor", None), blocked)
    envelope, code = core._invoke_action("doctor", None, [], "correlation")
    assert code == cli.EXIT_BLOCKED
    assert envelope["status"] == "blocked"

    def broken(_args: list[str], _correlation: str) -> tuple[dict[str, object], int]:
        raise RuntimeError("boom")

    monkeypatch.setitem(cli.HANDLERS, ("doctor", None), broken)
    envelope, code = core._invoke_action("doctor", None, [], "correlation")
    assert code == cli.EXIT_FAILURE
    assert envelope["error"]["code"] == "E-INTERNAL-UNEXPECTED"


def test_safe_socket_path_and_direct_serve_cleanup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    path = core._safe_socket_path()
    assert path.parent.stat().st_mode & 0o077 == 0

    monkeypatch.setattr(core.CoreServer, "serve_forever", lambda self, **_kwargs: None)
    assert core.serve() == 0
    assert not path.exists()
    assert core._server_from_systemd() is None


def test_safe_socket_path_rejects_symlinked_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(linked))
    with pytest.raises(PermissionError, match="XDG runtime inseguro"):
        core._safe_socket_path()


def test_client_rejects_unsafe_socket_and_invalid_response(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    regular = safe_socket_path()
    regular.write_text("not a socket", encoding="utf-8")
    with pytest.raises(CoreProtocolError, match="inseguras"):
        invoke("doctor.run", {})
    regular.unlink()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(regular))
    regular.chmod(0o600)
    server.listen(1)

    def respond() -> None:
        connection, _address = server.accept()
        connection.recv(65536)
        connection.sendall(b"not-json\n")
        connection.close()

    thread = threading.Thread(target=respond)
    thread.start()
    try:
        with pytest.raises(CoreProtocolError, match="JSON inválida"):
            invoke("doctor.run", {})
    finally:
        thread.join(timeout=5)
        server.close()


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (b'{"jsonrpc":"1.0","id":1,"result":{}}\n', "envelope"),
        (b'{"jsonrpc":"2.0","id":1,"error":{"code":-1}}\n', "recusou"),
        (b'{"jsonrpc":"2.0","id":1,"result":null}\n', "resultado ausente"),
        (b'{"jsonrpc":"2.0","id":1,"result":{}}\n', "tipado"),
        (b'{"jsonrpc":"2.0","id":1,"result":{} }', "incompleta"),
    ],
)
def test_client_rejects_each_invalid_response_shape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, response: bytes, message: str
) -> None:
    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    socket_path = safe_socket_path()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    socket_path.chmod(0o600)
    server.listen(1)

    def respond() -> None:
        connection, _address = server.accept()
        connection.recv(65536)
        connection.sendall(response)
        connection.close()

    thread = threading.Thread(target=respond)
    thread.start()
    try:
        with pytest.raises(CoreProtocolError, match=message):
            invoke("doctor.run", {})
    finally:
        thread.join(timeout=5)
        server.close()


def test_client_falls_back_only_when_connect_never_happened(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    socket_path = safe_socket_path()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    socket_path.chmod(0o600)
    server.close()
    with pytest.raises(CoreUnavailable):
        invoke("doctor.run", {})


def test_systemd_socket_inheritance_and_stale_socket_recovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    inherited_path = tmp_path / "inherited.sock"
    inherited = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    inherited.bind(str(inherited_path))
    inherited.listen(1)
    monkeypatch.setenv("LISTEN_PID", str(os.getpid()))
    monkeypatch.setenv("LISTEN_FDS", "1")
    monkeypatch.setattr(core.socket, "fromfd", lambda *_args: inherited.dup())
    server = core._server_from_systemd()
    assert server is not None
    server.server_close()
    inherited.close()

    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state-stale"))
    monkeypatch.delenv("LISTEN_PID")
    monkeypatch.delenv("LISTEN_FDS")
    stale_path = safe_socket_path()
    stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stale.bind(str(stale_path))
    stale_path.chmod(0o600)
    stale.close()
    monkeypatch.setattr(core.CoreServer, "serve_forever", lambda self, **_kwargs: None)
    assert core.serve() == 0
    assert not stale_path.exists()


def test_core_main_forwards_systemd_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[bool] = []
    monkeypatch.setattr(
        core,
        "serve",
        lambda *, systemd=False: received.append(systemd) or 0,
    )
    assert core.main(["--systemd"]) == 0
    assert received == [True]
