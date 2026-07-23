# SPDX-License-Identifier: GPL-3.0-or-later
"""Cliente pequeno e fail-closed para o socket local do ``steamzero-core``."""

from __future__ import annotations

import json
import os
import socket
import stat
from dataclasses import dataclass
from typing import Any

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
