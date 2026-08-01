# SPDX-License-Identifier: GPL-3.0-or-later
"""Daemon JSON-RPC user-scoped do SteamZero.

Somente UNIX socket local, peer do mesmo UID e métodos registrados. Não existe
listener TCP, dispatch reflexivo, comando de shell ou dependência do PhaseZero.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import select
import signal
import socket
import socketserver
import struct
import threading
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Any

from steamzero import CONTRACT_VERSION, __version__
from steamzero.api.envelope import build_envelope
from steamzero.api.events import (
    JOB_TERMINAL_STATES,
    OPERATION_TERMINAL_STATES,
    PUBLIC_EVENT_KINDS,
    follow_events,
    parse_event_cursor,
)
from steamzero.core import fs, ids, log, transaction
from steamzero.core.errors import SteamZeroError, build_error
from steamzero.core.identity import runtime_identity
from steamzero.core.state import StateStore
from steamzero.jobs.manager import JobManager
from steamzero.service.methods import METHODS, InvalidParams, capabilities
from steamzero.service.reconciler import SessionEnvironmentReconciler
from steamzero.service.socket_path import safe_socket_path

_MAX_REQUEST = 1 << 20
_MAX_REQUESTS_PER_CONNECTION = 128
_MAX_MUTATIONS_PER_CONNECTION = 16
_MAX_SUBSCRIPTION_FILTERS = 64
_MAX_SUBSCRIPTION_IDLE = 86_400.0


@dataclass(frozen=True)
class EventSubscription:
    request_id: str | int
    cursor: str | None
    kinds: tuple[str, ...]
    entities: tuple[str, ...]
    job_ids: tuple[str, ...]
    operation_ids: tuple[str, ...]
    limit: int
    idle_timeout: float | None
    terminal_states: frozenset[str]


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
            if _request_method(raw) == "events.subscribe":
                self._handle_subscription(raw)
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

    def _handle_subscription(self, raw: bytes) -> None:
        parsed = _parse_subscription(raw)
        if isinstance(parsed, dict):
            self._write(parsed)
            return
        subscription_id = ids.new_ulid()
        try:
            with StateStore() as store:
                store.migrate()
                missing = _missing_subscription_target(store, parsed)
                if missing is not None:
                    self._write(_rpc_error(parsed.request_id, -32602, missing))
                    return
                cursor = str(store.latest_event_seq()) if parsed.cursor is None else parsed.cursor
                self._write(
                    _rpc_result(
                        parsed.request_id,
                        {
                            "subscriptionId": subscription_id,
                            "cursor": cursor,
                            "transport": "json-rpc-notifications",
                        },
                    )
                )
                for event in follow_events(
                    store,
                    cursor=cursor,
                    kinds=parsed.kinds,
                    entities=parsed.entities,
                    limit=parsed.limit,
                    idle_timeout=parsed.idle_timeout,
                    terminal_states=parsed.terminal_states,
                    stop_requested=lambda: (
                        self.server.shutdown_requested.is_set() or _socket_has_input(self.request)
                    ),
                ):
                    cursor = str(event["seq"])
                    self._write(
                        _rpc_notification(
                            "events.event",
                            {
                                "subscriptionId": subscription_id,
                                "cursor": cursor,
                                "event": event,
                            },
                        )
                    )
                self._write(
                    _rpc_notification(
                        "events.complete",
                        {"subscriptionId": subscription_id, "cursor": cursor},
                    )
                )
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return


class CoreServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = False
    block_on_close = True
    request_queue_size = 16

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.shutdown_requested = threading.Event()
        super().__init__(*args, **kwargs)

    def shutdown(self) -> None:
        self.shutdown_requested.set()
        super().shutdown()


def _request_id(raw: bytes) -> str | int | None:
    try:
        request = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(request, dict):
        return None
    value = request.get("id")
    return value if isinstance(value, (str, int)) and not isinstance(value, bool) else None


def _request_method(raw: bytes) -> str | None:
    try:
        request = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(request, dict):
        return None
    method = request.get("method")
    return method if isinstance(method, str) else None


def _socket_has_input(stream: socket.socket) -> bool:
    try:
        readable, _writable, _exceptional = select.select([stream], [], [], 0)
    except (OSError, ValueError):
        return True
    return bool(readable)


def _parse_subscription(raw: bytes) -> EventSubscription | dict[str, Any]:
    try:
        request = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _rpc_error(None, -32700, "JSON inválido")
    if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
        return _rpc_error(None, -32600, "requisição JSON-RPC inválida")
    request_id = request.get("id")
    if not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
        return _rpc_error(None, -32600, "id precisa ser texto ou inteiro")
    params = request.get("params", {})
    if not isinstance(params, dict) or not all(isinstance(key, str) for key in params):
        return _rpc_error(request_id, -32602, "params precisa ser um objeto")
    allowed = {
        "cursor",
        "kinds",
        "jobIds",
        "operationIds",
        "entities",
        "limit",
        "idleTimeout",
        "stopOnTerminal",
    }
    unknown = set(params) - allowed
    if unknown:
        return _rpc_error(
            request_id,
            -32602,
            f"campos desconhecidos: {', '.join(sorted(unknown))}",
        )
    try:
        cursor_value = params.get("cursor")
        if cursor_value is not None and not isinstance(cursor_value, str):
            raise ValueError("cursor precisa ser texto decimal")
        parse_event_cursor(cursor_value)
        kinds = _subscription_text_list(params, "kinds")
        if not kinds:
            kinds = PUBLIC_EVENT_KINDS
        unsupported = set(kinds) - set(PUBLIC_EVENT_KINDS)
        if unsupported:
            raise ValueError(f"kinds não públicos: {', '.join(sorted(unsupported))}")
        job_ids = _subscription_text_list(params, "jobIds")
        operation_ids = _subscription_text_list(params, "operationIds")
        requested_entities = _subscription_text_list(params, "entities")
        entities = tuple(
            dict.fromkeys(
                (
                    *(f"job:{job_id}" for job_id in job_ids),
                    *(f"operation:{operation_id}" for operation_id in operation_ids),
                    *requested_entities,
                )
            )
        )
        limit = params.get("limit", 64)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 256:
            raise ValueError("limit precisa ser inteiro entre 1 e 256")
        idle_value = params.get("idleTimeout")
        idle_timeout: float | None
        if idle_value is None:
            idle_timeout = None
        elif (
            not isinstance(idle_value, (int, float))
            or isinstance(idle_value, bool)
            or not math.isfinite(float(idle_value))
            or not 0 <= float(idle_value) <= _MAX_SUBSCRIPTION_IDLE
        ):
            raise ValueError("idleTimeout precisa estar entre 0 e 86400 segundos")
        else:
            idle_timeout = float(idle_value)
        stop_on_terminal = params.get("stopOnTerminal", False)
        if not isinstance(stop_on_terminal, bool):
            raise ValueError("stopOnTerminal precisa ser booleano")
    except ValueError as exc:
        return _rpc_error(request_id, -32602, str(exc))
    terminal_states = (
        JOB_TERMINAL_STATES | OPERATION_TERMINAL_STATES if stop_on_terminal else frozenset()
    )
    return EventSubscription(
        request_id=request_id,
        cursor=cursor_value,
        kinds=kinds,
        entities=entities,
        job_ids=job_ids,
        operation_ids=operation_ids,
        limit=limit,
        idle_timeout=idle_timeout,
        terminal_states=terminal_states,
    )


def _subscription_text_list(params: dict[str, Any], name: str) -> tuple[str, ...]:
    value = params.get(name, [])
    if (
        not isinstance(value, list)
        or len(value) > _MAX_SUBSCRIPTION_FILTERS
        or any(
            not isinstance(item, str) or not item or len(item) > 256 or "\x00" in item
            for item in value
        )
    ):
        raise ValueError(f"{name} precisa ser uma lista de até {_MAX_SUBSCRIPTION_FILTERS} textos")
    return tuple(dict.fromkeys(value))


def _missing_subscription_target(store: StateStore, subscription: EventSubscription) -> str | None:
    for job_id in subscription.job_ids:
        if store.get_job(job_id) is None:
            return f"job inexistente: {job_id}"
    for operation_id in subscription.operation_ids:
        if store.get_operation(operation_id) is None:
            return f"operação inexistente: {operation_id}"
    return None


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
        # A identidade completa — não só a versão — porque duas releases podem
        # compartilhar packageVersion e divergir em commit. Ver
        # steamzero.core.identity: o valor é carregado do próprio pacote em
        # tempo de build, nunca lido de manifesto ao lado de `current`, que o
        # processo antigo leria como se fosse dele.
        identity = runtime_identity()
        return _rpc_result(
            request_id,
            {
                "contractVersion": CONTRACT_VERSION,
                "daemonVersion": __version__,
                "pid": os.getpid(),
                "transport": "unix-peercred",
                "identity": identity.to_dict(),
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


def _rpc_notification(method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "method": method, "params": params}


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


def _recover_at_boot(store: StateStore) -> None:
    """Recovery pós-reboot best-effort (G25, §8): jobs running -> terminal.

    Primeiro JobManager.recover() resolve jobs "running" herdados (cêntrico em
    jobs); depois transaction.recover_all() resolve journals/óperações não-
    terminais sem job associado (cêntrico em journals). Qualquer falha é
    registrada e o daemon segue o boot — recovery nunca derruba serve_forever.
    """
    logger = log.get_logger()
    try:
        recovered = JobManager(store).recover()
        if recovered:
            logger.info(
                "boot.recovery.jobs",
                count=len(recovered),
                jobs=[
                    {"id": j.id, "state": j.state, "error_code": j.error_code}
                    for j in recovered
                ],
            )
    except Exception as exc:  # recovery é best-effort; §8: nunca trava o boot
        logger.warning("boot.recovery.jobs-failed", error=type(exc).__name__, detail=str(exc))
    try:
        results = transaction.recover_all()
        if results:
            logger.info(
                "boot.recovery.operations",
                count=len(results),
                outcomes=[r.outcome for r in results],
            )
    except Exception as exc:  # pragma: no cover - best-effort
        logger.warning(
            "boot.recovery.operations-failed", error=type(exc).__name__, detail=str(exc)
        )


def serve(*, systemd: bool = False) -> int:
    # Migração serial antes de abrir concorrência entre handlers e reconciliador.
    with StateStore() as store:
        store.migrate()
        # G25: recovery pós-reboot uma única vez no boot. Jobs "running" de um
        # processo anterior (ex.: media.global stalado) são levados a terminal,
        # e journals/óperações não-terminais são resolvidos. Best-effort (§8):
        # falha aqui é registrada, mas nunca impede serve_forever — o daemon
        # precisa subir mesmo que recovery não complete.
        _recover_at_boot(store)
    server = _server_from_systemd() if systemd else None
    owned_path: Path | None = None
    if server is None:
        socket_path = _safe_socket_path()
        if socket_path.exists():
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                probe.settimeout(0.2)
                probe.connect(str(socket_path))
            except OSError:
                probe.close()
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
