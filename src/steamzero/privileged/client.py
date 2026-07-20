# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Cliente único da fronteira privilegiada, in-process ou Polkit host.

O transporte externo usa argv totalmente fixo e, neste incremento, publica
somente ``health``. Ações mutáveis são recusadas antes de criar um processo.
Nunca há fallback silencioso para sudo (FM-20).
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steamzero.core.errors import SteamZeroError, build_error
from steamzero.privileged.helper import AdminHelper
from steamzero.privileged.protocol import PROTOCOL_VERSION, Request, Response

_PKEXEC = Path("/usr/bin/pkexec")
_HELPER = Path("/usr/local/libexec/steamzero-admin")
_MAX_RESPONSE = 64 * 1024


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes


Runner = Callable[[tuple[str, ...], float], ProcessResult]


def _run_fixed(argv: tuple[str, ...], timeout: float) -> ProcessResult:
    completed = subprocess.run(  # noqa: S603 - argv fixo, sem entrada do chamador
        argv,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    return ProcessResult(completed.returncode, completed.stdout, completed.stderr)


class PkexecHealthTransport:
    """Transporte Polkit mínimo; não aceita parâmetros nem ações mutáveis."""

    def __init__(
        self,
        *,
        pkexec: Path = _PKEXEC,
        helper: Path = _HELPER,
        runner: Runner = _run_fixed,
        timeout: float = 90.0,
    ) -> None:
        self._pkexec = pkexec
        self._helper = helper
        self._runner = runner
        self._timeout = max(5.0, min(timeout, 120.0))

    def available(self) -> bool:
        return all(
            path.is_file() and os.access(path, os.X_OK) for path in (self._pkexec, self._helper)
        )

    def request(self, action: str, params: dict[str, Any]) -> Response:
        if action != "health" or params:
            return Response(
                ok=False,
                error=build_error(
                    "E-PRIV-DENIED",
                    detail="o transporte Polkit atual publica somente health sem parâmetros",
                ),
            )
        if not self.available():
            raise SteamZeroError(
                "E-PRIV-HELPER-MISSING",
                detail="steamzero-admin ou pkexec não está instalado no host",
            )
        argv = (str(self._pkexec), str(self._helper), "--health")
        try:
            completed = self._runner(argv, self._timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SteamZeroError(
                "E-PRIV-DENIED",
                detail="autorização Polkit indisponível ou expirou",
            ) from exc
        if len(completed.stdout) > _MAX_RESPONSE or len(completed.stderr) > _MAX_RESPONSE:
            raise SteamZeroError(
                "E-PRIV-PROTO-MISMATCH",
                detail="resposta do helper excedeu o limite",
            )
        try:
            payload = json.loads(completed.stdout)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            if completed.returncode != 0:
                return Response(
                    ok=False,
                    error=build_error("E-PRIV-DENIED", detail="autorização Polkit recusada"),
                )
            raise SteamZeroError(
                "E-PRIV-PROTO-MISMATCH",
                detail="helper retornou JSON inválido",
            ) from exc
        return _parse_response(payload, completed.returncode)


def _parse_response(payload: object, returncode: int) -> Response:
    if not isinstance(payload, dict) or set(payload) != {"ok", "result", "error"}:
        raise SteamZeroError("E-PRIV-PROTO-MISMATCH", detail="envelope do helper inválido")
    ok = payload.get("ok")
    result = payload.get("result")
    error = payload.get("error")
    if not isinstance(ok, bool):
        raise SteamZeroError("E-PRIV-PROTO-MISMATCH", detail="campo ok inválido")
    if ok:
        if returncode != 0 or not isinstance(result, dict) or error is not None:
            raise SteamZeroError("E-PRIV-PROTO-MISMATCH", detail="sucesso inconsistente")
        return Response(ok=True, result=result)
    if returncode == 0 or result is not None or not isinstance(error, dict):
        raise SteamZeroError("E-PRIV-PROTO-MISMATCH", detail="falha inconsistente")
    return Response(ok=False, error=error)


class AdminClient:
    def __init__(
        self,
        helper: AdminHelper | None,
        *,
        caller: str = "steamzero-core",
        transport: PkexecHealthTransport | None = None,
    ) -> None:
        self._helper = helper
        self._caller = caller
        self._transport = transport

    @classmethod
    def host(cls) -> AdminClient:
        return cls(None, transport=PkexecHealthTransport())

    def available(self) -> bool:
        return self._helper is not None or (
            self._transport is not None and self._transport.available()
        )

    def request(self, action: str, params: dict[str, Any]) -> Response:
        """Envia uma ação privilegiada; levanta E-PRIV-* em falha de fronteira."""
        if self._helper is not None:
            return self._helper.handle(
                Request(
                    action=action,
                    params=params,
                    protocol_version=PROTOCOL_VERSION,
                    caller=self._caller,
                )
            )
        if self._transport is not None:
            return self._transport.request(action, params)
        else:
            raise SteamZeroError(
                "E-PRIV-HELPER-MISSING",
                detail="steamzero-admin não instalado; instale o helper para ações privilegiadas",
            )
