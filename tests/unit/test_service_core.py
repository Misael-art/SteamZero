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
from steamzero.service.client import (
    CoreAmbiguousResult,
    CoreProtocolError,
    CoreUnavailable,
    invoke,
    subscribe_events,
)
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


@pytest.mark.parametrize(
    "params",
    [
        {"unknown": True},
        {"cursor": 1},
        {"cursor": "-1"},
        {"kinds": ["private.event"]},
        {"kinds": "job.state"},
        {"jobIds": [""]},
        {"operationIds": ["x"] * 65},
        {"limit": 0},
        {"limit": True},
        {"idleTimeout": float("inf")},
        {"idleTimeout": 86_401},
        {"stopOnTerminal": "yes"},
    ],
)
def test_subscription_parser_rejects_unbounded_or_unknown_params(
    params: dict[str, object],
) -> None:
    raw = (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "events.subscribe",
                "params": params,
            }
        ).encode()
        + b"\n"
    )
    parsed = core._parse_subscription(raw)
    assert isinstance(parsed, dict)
    assert parsed["error"]["code"] == -32602


def test_subscription_parser_builds_exact_bounded_filters() -> None:
    raw = (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": "stream-1",
                "method": "events.subscribe",
                "params": {
                    "cursor": "10",
                    "kinds": ["job.state"],
                    "jobIds": ["J1", "J1"],
                    "entities": ["session:S1"],
                    "limit": 32,
                    "idleTimeout": 1.5,
                    "stopOnTerminal": True,
                },
            }
        ).encode()
        + b"\n"
    )
    parsed = core._parse_subscription(raw)
    assert isinstance(parsed, core.EventSubscription)
    assert parsed.entities == ("job:J1", "session:S1")
    assert parsed.terminal_states


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


def test_serve_recovers_stale_jobs_at_boot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # G25: serve() chama recover() no boot; jobs running de um processo anterior
    # são levados a terminal. Recovery é idempotente e best-effort (§8): serve()
    # retorna 0 mesmo quando há trabalho de recovery a fazer.
    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    from steamzero.core import fs as core_fs
    from steamzero.core import state as core_state
    from steamzero.jobs.manager import JobManager

    core_fs.ensure_state_layout()
    store = core_state.open_state()
    try:
        mgr = JobManager(store)
        stale = mgr.create("media.global")
        # Simula job que ficou "running" após um crash/reboot.
        stale.state = "running"
        store.save_job(stale.to_row())
    finally:
        store.close()

    monkeypatch.setattr(core.CoreServer, "serve_forever", lambda self, **_kwargs: None)
    assert core.serve() == 0  # boot sobe mesmo com recovery pendente

    # O job stalado agora está em estado terminal (cancelled + recovered).
    store = core_state.open_state()
    try:
        row = store.get_job(stale.id)
    finally:
        store.close()
    assert row is not None
    assert row["state"] == "cancelled"
    assert row["error_code"] == "recovered"


def test_serve_boots_even_if_recovery_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # G25/§8: se recovery lança, serve() ainda retorna 0 (falha degrada, nunca
    # trava). Patcheamos JobManager.recover para levantar e confirmamos o boot.
    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    from steamzero.jobs.manager import JobManager

    def boom(self: JobManager) -> list:  # type: ignore[type-arg]
        raise RuntimeError("recovery simulado falhando")

    monkeypatch.setattr(JobManager, "recover", boom)
    monkeypatch.setattr(core.CoreServer, "serve_forever", lambda self, **_kwargs: None)
    assert core.serve() == 0  # §8: daemon sobe apesar da falha de recovery


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


def _slow_daemon_response(
    socket_path: Path, delay: float, response: bytes
) -> tuple[threading.Thread, socket.socket]:
    """Servidor sintético que responde só depois de ``delay`` segundos."""
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    socket_path.chmod(0o600)
    server.listen(1)

    def respond() -> None:
        connection, _address = server.accept()
        connection.recv(65536)
        threading.Event().wait(delay)
        try:
            connection.sendall(response)
        except OSError:
            pass  # cliente desistiu (timeout curto): quem testa é o cliente
        finally:
            connection.close()

    thread = threading.Thread(target=respond)
    thread.start()
    return thread, server


def test_invoke_waits_for_slow_method_beyond_legacy_timeout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """BUG-01: round-trip de 3 s expirava no timeout fixo de 2,0 s.

    Antes do fix, ``invoke`` com ``emulation.workspace`` estourava em 2,0 s e
    virava E-API-CONTRACT na tela principal; o MethodSpec agora carrega o
    timeout da operação (30,0 s), e o round-trip lento completa.
    """
    import time

    from steamzero.service.methods import METHODS

    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    socket_path = safe_socket_path()
    response = b'{"jsonrpc":"2.0","id":1,"result":{"envelope":{"ok":true},"exitCode":0}}\n'
    thread, server = _slow_daemon_response(socket_path, delay=3.0, response=response)
    try:
        spec = METHODS["emulation.workspace"]
        started = time.monotonic()
        result = invoke("emulation.workspace", {}, timeout=spec.timeout)
        elapsed = time.monotonic() - started
    finally:
        thread.join(timeout=10)
        server.close()
    assert result.exit_code == 0
    assert elapsed >= 2.5, "resposta só chega depois do antigo timeout de 2,0 s"


def test_invoke_short_timeout_raises_ambiguous_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Timeout de transporte é ambiguidade (CoreAmbiguousResult), degradável."""
    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    socket_path = safe_socket_path()
    response = b'{"jsonrpc":"2.0","id":1,"result":{"envelope":{"ok":true},"exitCode":0}}\n'
    thread, server = _slow_daemon_response(socket_path, delay=3.0, response=response)
    try:
        with pytest.raises(CoreAmbiguousResult, match="ambíguo"):
            invoke("emulation.workspace", {}, timeout=0.5)
    finally:
        thread.join(timeout=10)
        server.close()


def test_try_daemon_uses_method_timeout_for_slow_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """BUG-01 no caminho real: ``_try_daemon`` passa o timeout do MethodSpec.

    O daemon sintético leva 3 s para responder — além do antigo timeout fixo de
    2,0 s. Com o fix, ``_try_daemon("emulation", "workspace")`` completa com o
    envelope do daemon; sem o fix, ``invoke`` usava 2,0 s e devolvia
    E-API-CONTRACT (a tela principal quebrava).
    """
    import time

    from steamzero.service import client as mod

    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    socket_path = safe_socket_path()
    response = b'{"jsonrpc":"2.0","id":1,"result":{"envelope":{"ok":true},"exitCode":0}}\n'
    thread, server = _slow_daemon_response(socket_path, delay=3.0, response=response)
    monkeypatch.setattr(mod, "verify_generation", lambda **kw: {"sourceCommit": "x"})
    monkeypatch.delenv("STEAMZERO_NO_DAEMON", raising=False)
    try:
        started = time.monotonic()
        result = cli._try_daemon("emulation", "workspace", [], "corr-9")
        elapsed = time.monotonic() - started
    finally:
        thread.join(timeout=10)
        server.close()
    assert result is not None, "leitura lenta não pode falhar com timeout fixo"
    envelope, code = result
    assert code == 0
    assert envelope["ok"] is True
    assert elapsed >= 2.5, "resposta só chega depois do antigo timeout de 2,0 s"


def test_subscription_client_reconnects_from_confirmed_cursor_without_duplicates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime = tmp_path / "run"
    runtime.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    socket_path = safe_socket_path()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    socket_path.chmod(0o600)
    server.listen(2)
    requests: list[dict[str, object]] = []
    failures: list[BaseException] = []

    event_one = {
        "seq": 1,
        "ts": "2026-07-23T00:00:00+00:00",
        "kind": "entity.changed",
        "correlationId": "00000000000000000000000000",
    }
    event_two = {
        "seq": 2,
        "ts": "2026-07-23T00:00:01+00:00",
        "kind": "entity.changed",
        "correlationId": "00000000000000000000000000",
    }

    def message(value: dict[str, object]) -> bytes:
        return json.dumps(value, separators=(",", ":")).encode() + b"\n"

    def respond() -> None:
        try:
            first, _address = server.accept()
            first_request = json.loads(first.makefile("rb").readline())
            requests.append(first_request)
            first.sendall(
                message(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {
                            "subscriptionId": "S1",
                            "cursor": "0",
                            "transport": "json-rpc-notifications",
                        },
                    }
                )
                + message(
                    {
                        "jsonrpc": "2.0",
                        "method": "events.event",
                        "params": {
                            "subscriptionId": "S1",
                            "cursor": "1",
                            "event": event_one,
                        },
                    }
                )
            )
            first.close()

            second, _address = server.accept()
            second_request = json.loads(second.makefile("rb").readline())
            requests.append(second_request)
            second.sendall(
                message(
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "result": {
                            "subscriptionId": "S2",
                            "cursor": "1",
                            "transport": "json-rpc-notifications",
                        },
                    }
                )
                + message(
                    {
                        "jsonrpc": "2.0",
                        "method": "events.event",
                        "params": {
                            "subscriptionId": "S2",
                            "cursor": "2",
                            "event": event_two,
                        },
                    }
                )
                + message(
                    {
                        "jsonrpc": "2.0",
                        "method": "events.complete",
                        "params": {"subscriptionId": "S2", "cursor": "2"},
                    }
                )
            )
            second.close()
        except BaseException as exc:
            failures.append(exc)

    thread = threading.Thread(target=respond)
    thread.start()
    try:
        events = list(
            subscribe_events(
                {
                    "cursor": "0",
                    "kinds": ["entity.changed"],
                    "idleTimeout": 0,
                },
                reconnect_attempts=2,
            )
        )
    finally:
        thread.join(timeout=5)
        server.close()

    assert not failures
    assert [event["seq"] for event in events] == [1, 2]
    assert requests[0]["params"]["cursor"] == "0"  # type: ignore[index]
    assert requests[1]["params"]["cursor"] == "1"  # type: ignore[index]


@pytest.mark.parametrize(
    ("ack_cursor", "complete_cursor", "message"),
    [
        ("1", None, "alterou o cursor"),
        ("0", "1", "cursor final divergiu"),
    ],
)
def test_subscription_client_rejects_cursor_divergence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    ack_cursor: str,
    complete_cursor: str | None,
    message: str,
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
        messages = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "subscriptionId": "S1",
                    "cursor": ack_cursor,
                    "transport": "json-rpc-notifications",
                },
            }
        ]
        if complete_cursor is not None:
            messages.append(
                {
                    "jsonrpc": "2.0",
                    "method": "events.complete",
                    "params": {
                        "subscriptionId": "S1",
                        "cursor": complete_cursor,
                    },
                }
            )
        connection.sendall(
            b"".join(json.dumps(item, separators=(",", ":")).encode() + b"\n" for item in messages)
        )
        connection.close()

    thread = threading.Thread(target=respond)
    thread.start()
    try:
        with pytest.raises(CoreProtocolError, match=message):
            list(
                subscribe_events(
                    {"cursor": "0", "kinds": ["entity.changed"]},
                    reconnect_attempts=0,
                )
            )
    finally:
        thread.join(timeout=5)
        server.close()


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
