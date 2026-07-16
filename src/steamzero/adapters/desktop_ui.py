# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Central Qt/QML com bridge HTTP efêmera, loopback-only e allowlisted."""

from __future__ import annotations

import importlib.resources
import json
import secrets
import shutil
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, cast
from urllib.parse import urlparse

from steamzero.adapters.desktop_kde import activate_virtual_keyboard
from steamzero.core.errors import SteamZeroError, build_error
from steamzero.domain.desktop import ExperienceCoordinator

_MAX_BODY = 64 * 1024


class DesktopControlServer(HTTPServer):
    coordinator: ExperienceCoordinator
    token: str

    def __init__(self, coordinator: ExperienceCoordinator, token: str) -> None:
        self.coordinator = coordinator
        self.token = token
        super().__init__(("127.0.0.1", 0), DesktopControlHandler)


class DesktopControlHandler(BaseHTTPRequestHandler):
    server_version = "SteamZeroDesktop/1"

    def do_GET(self) -> None:
        if not self._authorized():
            self._send(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
            return
        if urlparse(self.path).path != "/status":
            self._send(HTTPStatus.NOT_FOUND, {"error": "not-found"})
            return
        try:
            status = self._control_server.coordinator.status()
        except SteamZeroError as exc:
            self._send(HTTPStatus.CONFLICT, {"error": exc.to_error_object()})
            return
        except Exception as exc:
            self._send(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": build_error("E-INTERNAL-UNEXPECTED", detail=str(exc))},
            )
            return
        self._send(HTTPStatus.OK, status)

    def do_POST(self) -> None:
        if not self._authorized():
            self._send(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
            return
        try:
            payload = self._read_payload()
            result = self._dispatch(urlparse(self.path).path, payload)
        except SteamZeroError as exc:
            self._send(HTTPStatus.CONFLICT, {"error": exc.to_error_object()})
            return
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        except Exception as exc:
            self._send(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": build_error("E-INTERNAL-UNEXPECTED", detail=str(exc))},
            )
            return
        self._send(HTTPStatus.OK, result)

    @property
    def _control_server(self) -> DesktopControlServer:
        return cast(DesktopControlServer, self.server)

    def _authorized(self) -> bool:
        supplied = self.headers.get("X-SteamZero-Token", "")
        return secrets.compare_digest(supplied, self._control_server.token)

    def _read_payload(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        length = int(raw_length)
        if length < 0 or length > _MAX_BODY:
            raise ValueError("corpo fora do limite")
        if length == 0:
            return {}
        loaded = json.loads(self.rfile.read(length))
        if not isinstance(loaded, dict):
            raise TypeError("corpo precisa ser objeto JSON")
        return loaded

    def _dispatch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        coordinator = self._control_server.coordinator
        if path == "/plan":
            requested = payload.get("profile", "auto")
            if not isinstance(requested, str):
                raise TypeError("profile precisa ser string")
            return {"plan": coordinator.plan(requested).to_dict()}
        if path == "/conflict/plan":
            return {
                "plan": coordinator.plan_conflict_release(
                    self._required_string(payload, "actionId")
                ).to_dict()
            }
        if path == "/conflict/apply":
            return coordinator.apply_conflict_release(
                self._required_string(payload, "planId"),
                self._required_string(payload, "confirmToken"),
            )
        if path == "/apply":
            return coordinator.apply(
                self._required_string(payload, "planId"),
                self._required_string(payload, "confirmToken"),
            ).to_dict()
        if path == "/reset":
            return coordinator.reset(
                self._required_string(payload, "planId"),
                self._required_string(payload, "confirmToken"),
            ).to_dict()
        if path == "/recover":
            return coordinator.recover()
        if path == "/keyboard":
            return {"provider": activate_virtual_keyboard()}
        raise ValueError(f"ação não permitida: {path}")

    def _required_string(self, payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"campo obrigatório: {key}")
        return value

    def _send(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        # A bridge local não grava URLs/tokens no log HTTP padrão.
        return


def launch_desktop_ui(coordinator: ExperienceCoordinator) -> int:
    executable = shutil.which("qml6") or shutil.which("qml")
    if executable is None:
        raise SteamZeroError(
            "E-DESKTOP-VERIFY", detail="runtime Qt/QML ausente; backend e CLI continuam disponíveis"
        )
    token = secrets.token_urlsafe(32)
    server = DesktopControlServer(coordinator, token)
    server.timeout = 0.2
    initial_status = coordinator.status()
    resource = importlib.resources.files("steamzero.ui").joinpath("qml/Main.qml")
    try:
        with importlib.resources.as_file(resource) as qml_path:
            process = subprocess.Popen(  # noqa: S603
                [
                    executable,
                    str(qml_path),
                    "--",
                    "--steamzero-status",
                    json.dumps(initial_status, separators=(",", ":"), ensure_ascii=False),
                    "--steamzero-api",
                    f"http://127.0.0.1:{server.server_port}",
                    "--steamzero-token",
                    token,
                ],
                stdin=subprocess.DEVNULL,
            )
            while process.poll() is None:
                server.handle_request()
            return int(process.returncode or 0)
    finally:
        server.server_close()
