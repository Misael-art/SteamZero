# SPDX-License-Identifier: GPL-3.0-or-later
"""Cliente pequeno e fail-closed para o socket local do ``steamzero-core``."""

from __future__ import annotations

import json
import os
import socket
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from typing import IO, Any

from steamzero.api import contracts
from steamzero.api.events import parse_event_cursor
from steamzero.service.socket_path import safe_socket_path

_MAX_RESPONSE = 1 << 20


class CoreUnavailable(ConnectionError):
    """Daemon ausente ou transporte local indisponível."""


class CoreProtocolError(RuntimeError):
    """Resposta do daemon não respeita o contrato JSON-RPC."""


@dataclass(frozen=True)
class Invocation:
    envelope: dict[str, Any]
    exit_code: int


def invoke(method: str, params: dict[str, str], *, timeout: float = 2.0) -> Invocation:
    request_id = 1
    request = (
        json.dumps(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    client = _connect(timeout)
    try:
        client.sendall(request)
        payload = _read_line(client)
    except OSError as exc:
        raise CoreProtocolError("resultado da chamada é ambíguo") from exc
    finally:
        client.close()
    try:
        response = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoreProtocolError("resposta JSON inválida") from exc
    if (
        not isinstance(response, dict)
        or response.get("jsonrpc") != "2.0"
        or response.get("id") != request_id
    ):
        raise CoreProtocolError("envelope JSON-RPC inválido")
    error = response.get("error")
    if error is not None:
        raise CoreProtocolError(f"daemon recusou a chamada: {error}")
    result = response.get("result")
    if not isinstance(result, dict):
        raise CoreProtocolError("resultado ausente")
    envelope = result.get("envelope")
    exit_code = result.get("exitCode")
    if not isinstance(envelope, dict) or not isinstance(exit_code, int):
        raise CoreProtocolError("resultado tipado inválido")
    return Invocation(envelope=envelope, exit_code=exit_code)


def subscribe_events(
    params: dict[str, Any],
    *,
    connect_timeout: float = 2.0,
    reconnect_attempts: int = 3,
) -> Iterator[dict[str, Any]]:
    """Segue notificações event-v1 e retoma pelo último cursor confirmado."""
    if reconnect_attempts < 0:
        raise ValueError("reconnect_attempts não pode ser negativo")
    request_id = 1
    current_params = dict(params)
    cursor_value = current_params.get("cursor")
    if cursor_value is not None:
        if not isinstance(cursor_value, str):
            raise CoreProtocolError("cursor da assinatura precisa ser texto")
        try:
            parse_event_cursor(cursor_value)
        except ValueError as exc:
            raise CoreProtocolError(str(exc)) from exc
    current_cursor = cursor_value
    connected = False
    failures = 0
    while True:
        try:
            client = _connect(connect_timeout)
        except CoreUnavailable as exc:
            if not connected:
                raise
            failures += 1
            if failures > reconnect_attempts:
                raise CoreProtocolError("assinatura perdeu o daemon") from exc
            continue
        connected = True
        if current_cursor is not None:
            current_params["cursor"] = current_cursor
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "events.subscribe",
            "params": current_params,
        }
        reader = client.makefile("rb")
        try:
            client.sendall(
                json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                + b"\n"
            )
            acknowledgement = _read_json_line(reader)
            subscription_id, acknowledged_cursor = _subscription_ack(acknowledgement, request_id)
            if current_cursor is not None and acknowledged_cursor != current_cursor:
                raise CoreProtocolError("ack da assinatura alterou o cursor solicitado")
            current_cursor = acknowledged_cursor
            client.settimeout(None)
            while True:
                message = _read_json_line(reader, disconnected=True)
                method = message.get("method")
                notification_params = message.get("params")
                if (
                    message.get("jsonrpc") != "2.0"
                    or not isinstance(notification_params, dict)
                    or notification_params.get("subscriptionId") != subscription_id
                ):
                    raise CoreProtocolError("notificação da assinatura inválida")
                notification_cursor = notification_params.get("cursor")
                if not isinstance(notification_cursor, str):
                    raise CoreProtocolError("cursor da notificação inválido")
                try:
                    parsed_cursor = parse_event_cursor(notification_cursor)
                    previous_cursor = parse_event_cursor(current_cursor)
                except ValueError as exc:
                    raise CoreProtocolError(str(exc)) from exc
                if method == "events.complete":
                    if parsed_cursor != previous_cursor:
                        raise CoreProtocolError("cursor final divergiu do último evento")
                    return
                if method != "events.event":
                    raise CoreProtocolError("método de notificação desconhecido")
                event = notification_params.get("event")
                if (
                    not isinstance(event, dict)
                    or event.get("seq") != parsed_cursor
                    or parsed_cursor <= previous_cursor
                ):
                    raise CoreProtocolError("evento fora de ordem ou duplicado")
                try:
                    contracts.validate(event, "event-v1.schema.json")
                except Exception as exc:
                    raise CoreProtocolError("evento não respeita event-v1") from exc
                current_cursor = notification_cursor
                yield event
        except _StreamDisconnected as exc:
            failures += 1
            if failures > reconnect_attempts:
                raise CoreProtocolError("assinatura interrompida após reconexões") from exc
        except OSError as exc:
            failures += 1
            if failures > reconnect_attempts:
                raise CoreProtocolError("assinatura interrompida após reconexões") from exc
        finally:
            reader.close()
            client.close()


class _StreamDisconnected(ConnectionError):
    pass


def _connect(timeout: float) -> socket.socket:
    try:
        path = safe_socket_path()
    except PermissionError as exc:
        raise CoreProtocolError("socket local possui ownership ou permissões inseguras") from exc
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise CoreUnavailable(str(exc)) from exc
    if (
        path.is_symlink()
        or not stat.S_ISSOCK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_mode & 0o077
    ):
        raise CoreProtocolError("socket local possui ownership ou permissões inseguras")
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(str(path))
    except OSError as exc:
        client.close()
        raise CoreUnavailable(str(exc)) from exc
    return client


def _read_json_line(reader: IO[bytes], *, disconnected: bool = False) -> dict[str, Any]:
    payload = reader.readline(_MAX_RESPONSE + 1)
    if not payload:
        if disconnected:
            raise _StreamDisconnected("conexão encerrada")
        raise CoreProtocolError("resposta incompleta")
    if len(payload) > _MAX_RESPONSE or not payload.endswith(b"\n"):
        raise CoreProtocolError("resposta excede o limite ou está incompleta")
    try:
        response = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoreProtocolError("resposta JSON inválida") from exc
    if not isinstance(response, dict):
        raise CoreProtocolError("mensagem JSON-RPC precisa ser objeto")
    return response


def _subscription_ack(response: dict[str, Any], request_id: str | int) -> tuple[str, str]:
    if response.get("jsonrpc") != "2.0" or response.get("id") != request_id:
        raise CoreProtocolError("ack da assinatura inválido")
    error = response.get("error")
    if error is not None:
        raise CoreProtocolError(f"daemon recusou a assinatura: {error}")
    result = response.get("result")
    if not isinstance(result, dict):
        raise CoreProtocolError("ack da assinatura ausente")
    subscription_id = result.get("subscriptionId")
    cursor = result.get("cursor")
    if (
        not isinstance(subscription_id, str)
        or not subscription_id
        or not isinstance(cursor, str)
        or result.get("transport") != "json-rpc-notifications"
    ):
        raise CoreProtocolError("ack da assinatura tipado inválido")
    try:
        parse_event_cursor(cursor)
    except ValueError as exc:
        raise CoreProtocolError(str(exc)) from exc
    return subscription_id, cursor


def _read_line(client: socket.socket) -> str:
    data = bytearray()
    while len(data) <= _MAX_RESPONSE:
        chunk = client.recv(min(65536, _MAX_RESPONSE + 1 - len(data)))
        if not chunk:
            break
        data.extend(chunk)
        if b"\n" in chunk:
            break
    if len(data) > _MAX_RESPONSE:
        raise CoreProtocolError("resposta excede o limite")
    line, separator, _rest = bytes(data).partition(b"\n")
    if not separator:
        raise CoreProtocolError("resposta incompleta")
    return line.decode("utf-8")
