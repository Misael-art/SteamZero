# SPDX-License-Identifier: GPL-3.0-or-later
"""Daemon JSON-RPC user-scoped do SteamZero.

Somente UNIX socket local, peer do mesmo UID e métodos registrados. Não existe
listener TCP, dispatch reflexivo, comando de shell ou dependência do PhaseZero.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import socketserver
import struct
import threading
from pathlib import Path
from types import FrameType
from typing import Any

from steamzero import CONTRACT_VERSION, __version__
from steamzero.api.envelope import build_envelope
from steamzero.core import fs, ids
from steamzero.core.errors import SteamZeroError, build_error
from steamzero.service.methods import METHODS, InvalidParams, capabilities
from steamzero.service.reconciler import SessionEnvironmentReconciler
from steamzero.service.socket_path import safe_socket_path

_MAX_REQUEST = 1 << 20
_MAX_REQUESTS_PER_CONNECTION = 128
_MAX_MUTATIONS_PER_CONNECTION = 16


class CoreRequestHandler(socketserver.StreamRequestHandler):
    """Atende uma conexão autenticada, com limites por conexão."""

    server: CoreServer

    def setup(self) -> None:
        super().setup()
        credentials = self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        _pid, uid, _gid = struct.unpack("3i", credentials)
        if uid != os.getuid():
            raise PermissionError("peer UID não autorizado")

    def handle(self) -> None:
        mutations = 0
        for _number in range(_MAX_REQUESTS_PER_CONNECTION):
            raw = self.rfile.readline(_MAX_REQUEST + 1)
            if not raw:
                return
            if len(raw) > _MAX_REQUEST or not raw.endswith(b"\n"):
                self._write(_rpc_error(None, -32600, "requisição excede o limite"))
                return
            response, is_mutation = _dispatch(raw)
            if is_mutation:
                mutations += 1
                if mutations > _MAX_MUTATIONS_PER_CONNECTION:
                    self._write(_rpc_error(_request_id(raw), -32029, "limite de mutações excedido"))
                    return
            self._write(response)

    def _write(self, response: dict[str, Any]) -> None:
        payload = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.wfile.write(payload + b"\n")
        self.wfile.flush()


class CoreServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = False
    block_on_close = True
    request_queue_size = 16


def _request_id(raw: bytes) -> str | int | None:
    try:
        request = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(request, dict):
        return None
    value = request.get("id")
    return value if isinstance(value, (str, int)) and not isinstance(value, bool) else None


def _dispatch(raw: bytes) -> tuple[dict[str, Any], bool]:
    try:
        request = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _rpc_error(None, -32700, "JSON inválido"), False
    if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
        return _rpc_error(None, -32600, "requisição JSON-RPC inválida"), False
    request_id = request.get("id")
    if not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
        return _rpc_error(None, -32600, "id precisa ser texto ou inteiro"), False
    method = request.get("method")
    if not isinstance(method, str):
        return _rpc_error(request_id, -32600, "method inválido"), False
    params = request.get("params", {})
    if method == "system.hello":
        if params not in ({}, None):
            return _rpc_error(request_id, -32602, "system.hello não aceita parâmetros"), False
        return _rpc_result(
            request_id,
            {
                "contractVersion": CONTRACT_VERSION,
                "daemonVersion": __version__,
                "pid": os.getpid(),
                "transport": "unix-peercred",
            },
        ), False
    if method == "system.capabilities":
        if params not in ({}, None):
            return (
                _rpc_error(request_id, -32602, "system.capabilities não aceita parâmetros"),
                False,
            )
        return _rpc_result(request_id, {"methods": capabilities()}), False
    spec = METHODS.get(method)
    if spec is None:
        return _rpc_error(request_id, -32601, "método não registrado"), False
    try:
        args = spec.params_to_args(params)
    except InvalidParams as exc:
        return _rpc_error(request_id, -32602, str(exc)), spec.mutation
    correlation_id = params.get("correlationId") if isinstance(params, dict) else None
    correlation = correlation_id if isinstance(correlation_id, str) else ids.new_ulid()
    envelope, exit_code = _invoke_action(spec.domain, spec.action, args, correlation)
    return _rpc_result(request_id, {"envelope": envelope, "exitCode": exit_code}), spec.mutation


def _invoke_action(
    domain: str, action: str | None, args: list[str], correlation_id: str
) -> tuple[dict[str, Any], int]:
    # Import tardio evita ciclo: a CLI importa o cliente somente ao tentar IPC.
    from steamzero.cli.main import EXIT_BLOCKED, EXIT_FAILURE, HANDLERS

    handler = HANDLERS[(domain, action)]
    try:
        return handler(args, correlation_id)
    except SteamZeroError as exc:
        blocked = exc.code in {
            "E-TX-CONFIRM-REQUIRED",
            "E-TX-LOCKED",
            "E-DESKTOP-OWNER-CONFLICT",
        }
        return (
            build_envelope(
                domain,
                action or "",
                status="blocked" if blocked else "failed",
                ok=False,
                error=exc.to_error_object(),
                correlation_id=correlation_id,
            ),
            EXIT_BLOCKED if blocked else EXIT_FAILURE,
        )
    except Exception as exc:
        return (
            build_envelope(
                domain,
                action or "",
                status="failed",
                ok=False,
                error=build_error("E-INTERNAL-UNEXPECTED", detail=str(exc)),
                correlation_id=correlation_id,
            ),
            EXIT_FAILURE,
        )


def _rpc_result(request_id: str | int, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _rpc_error(request_id: str | int | None, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _safe_socket_path() -> Path:
    return safe_socket_path()


def _server_from_systemd() -> CoreServer | None:
    listen_pid = os.environ.get("LISTEN_PID")
    listen_fds = os.environ.get("LISTEN_FDS")
    if listen_pid != str(os.getpid()) or listen_fds != "1":
        return None
    inherited = socket.fromfd(3, socket.AF_UNIX, socket.SOCK_STREAM)
    inherited_type = inherited.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE)
    if inherited.family != socket.AF_UNIX or inherited_type != socket.SOCK_STREAM:
        inherited.close()
        raise RuntimeError("socket herdado do systemd possui tipo inválido")
    server = CoreServer("", CoreRequestHandler, bind_and_activate=False)
    server.socket.close()
    server.socket = inherited
    server.server_address = inherited.getsockname()
    server.server_activate()
    return server


def serve(*, systemd: bool = False) -> int:
    # Migração serial antes de abrir concorrência entre handlers e reconciliador.
    from steamzero.core.state import StateStore

    with StateStore() as store:
        store.migrate()
    server = _server_from_systemd() if systemd else None
    owned_path: Path | None = None
    if server is None:
        socket_path = _safe_socket_path()
        if socket_path.exists():
            try:
                probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                probe.settimeout(0.2)
                probe.connect(str(socket_path))
            except OSError:
                fs.remove_file(socket_path)
            else:
                probe.close()
                raise RuntimeError("steamzero-core já está ativo")
        server = CoreServer(str(socket_path), CoreRequestHandler)
        fs.set_mode(socket_path, 0o600)
        owned_path = socket_path

    reconcile_stop = threading.Event()
    reconcile_thread = threading.Thread(
        target=SessionEnvironmentReconciler().run,
        args=(reconcile_stop,),
        name="steamzero-environment-reconciler",
        daemon=True,
    )
    reconcile_thread.start()

    def stop(_signum: int, _frame: FrameType | None) -> None:
        # shutdown precisa ocorrer fora da thread serve_forever.
        import threading

        threading.Thread(target=server.shutdown, daemon=True).start()

    previous_term = signal.signal(signal.SIGTERM, stop)
    previous_int = signal.signal(signal.SIGINT, stop)
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        reconcile_stop.set()
        reconcile_thread.join(timeout=6.0)
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGINT, previous_int)
        server.server_close()
        if owned_path is not None:
            fs.remove_file(owned_path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daemon local user-scoped do SteamZero")
    parser.add_argument("--systemd", action="store_true", help="aceita socket herdado do systemd")
    args = parser.parse_args(argv)
    return serve(systemd=args.systemd)


if __name__ == "__main__":
    raise SystemExit(main())
