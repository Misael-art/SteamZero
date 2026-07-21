# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Central Qt/QML com bridge HTTP efêmera, loopback-only e allowlisted."""

from __future__ import annotations

import importlib.resources
import json
import secrets
import shutil
import subprocess
from dataclasses import replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from steamzero.adapters.desktop_dashboard import DesktopDashboard
from steamzero.adapters.desktop_kde import (
    KDEPanelEffect,
    activate_virtual_keyboard,
    apply_maliit_comfort,
    launch_ashyterm,
    logout_desktop_session,
    toggle_virtual_keyboard,
)
from steamzero.adapters.steam_session import readiness as session_readiness
from steamzero.adapters.steam_session import request_target
from steamzero.core.errors import SteamZeroError, build_error
from steamzero.domain.desktop import (
    DesktopContext,
    DisplayState,
    ExperienceCoordinator,
    automatic_profile,
    profile_for,
)

_MAX_BODY = 64 * 1024


class DesktopControlServer(HTTPServer):
    coordinator: ExperienceCoordinator
    token: str
    dashboard: DesktopDashboard | None
    session_plans: dict[str, tuple[str, str]]

    def __init__(
        self,
        coordinator: ExperienceCoordinator,
        token: str,
        dashboard: DesktopDashboard | None = None,
    ) -> None:
        self.coordinator = coordinator
        self.token = token
        self.dashboard = dashboard
        self.session_plans = {}
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
            dashboard = self._control_server.dashboard
            if dashboard is not None:
                status["dashboard"] = dashboard.snapshot(status)
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
        if path == "/component/plan":
            return {
                "plan": self._dashboard().plan_component(
                    self._required_string(payload, "componentId")
                )
            }
        if path == "/component/apply":
            self._require_desktop_without_conflicts()
            return self._dashboard().apply_component(
                self._required_string(payload, "planId"),
                self._required_string(payload, "confirmToken"),
            )
        if path == "/component/launch":
            return self._dashboard().launch_component(self._required_string(payload, "componentId"))
        if path == "/emulation/emulator/plan":
            return {
                "plan": self._dashboard().plan_emulation_emulator(
                    self._required_string(payload, "emulatorId"),
                    self._required_string(payload, "action"),
                )
            }
        if path == "/emulation/emulator/apply":
            self._require_desktop_without_conflicts()
            return self._dashboard().apply_emulation_emulator(
                self._required_string(payload, "planId"),
                self._required_string(payload, "confirmToken"),
            )
        if path == "/emulation/emulator/launch":
            return self._dashboard().launch_emulation_emulator(
                self._required_string(payload, "emulatorId")
            )
        if path == "/emulation/action/plan":
            return {"plan": self._dashboard().plan_emulation_action(payload)}
        if path == "/emulation/action/apply":
            return self._dashboard().apply_emulation_action(
                self._required_string(payload, "planId"),
                self._required_string(payload, "confirmToken"),
            )
        if path == "/emulation/library/scan":
            return self._dashboard().scan_emulation_library()
        if path == "/steam/open":
            return self._dashboard().open_steam(self._required_string(payload, "target"))
        if path == "/steam/input/open":
            return self._dashboard().open_steam_input(self._required_string(payload, "gameId"))
        if path == "/steam/gameplay/plan":
            return {"plan": self._dashboard().plan_steam_gameplay(payload, coordinator.status())}
        if path == "/steam/gameplay/apply":
            self._require_desktop_without_conflicts()
            return self._dashboard().apply_steam_gameplay(
                self._required_string(payload, "planId"),
                self._required_string(payload, "confirmToken"),
                coordinator.status(),
            )
        if path == "/steam/gameplay/recover":
            return self._dashboard().recover_steam_gameplay(
                self._required_string(payload, "gameId")
            )
        if path == "/steam/gameplay/launch-options/plan":
            return {
                "plan": self._dashboard().plan_steam_launch_options(
                    self._required_string(payload, "gameId")
                )
            }
        if path == "/steam/gameplay/launch-options/apply":
            self._require_desktop_without_conflicts()
            return self._dashboard().apply_steam_launch_options(
                self._required_string(payload, "planId"),
                self._required_string(payload, "confirmToken"),
                self._required_string(payload, "gameId"),
            )
        if path == "/steam/gameplay/launch-options/rollback":
            return self._dashboard().rollback_steam_launch_options(
                self._required_string(payload, "operationId")
            )
        if path == "/steam/maintenance/plan":
            raw_categories = payload.get("categories")
            if not isinstance(raw_categories, list) or not all(
                isinstance(value, str) for value in raw_categories
            ):
                raise ValueError("campo obrigatório: categories")
            return self._dashboard().plan_steam_maintenance(
                self._required_string(payload, "gameId"), raw_categories
            )
        if path == "/steam/maintenance/apply":
            return self._dashboard().apply_steam_maintenance(
                self._required_string(payload, "planId"),
                self._required_string(payload, "confirmToken"),
                self._required_string(payload, "confirmPhrase"),
            )
        if path == "/steam/maintenance/recover":
            return self._dashboard().recover_steam_maintenance()
        if path == "/steam/media/plan":
            return self._dashboard().plan_steam_media(
                self._required_string(payload, "gameId"),
                self._required_string(payload, "accountId"),
                Path(self._required_string(payload, "packagePath")),
            )
        if path == "/steam/media/apply":
            return self._dashboard().apply_steam_media(
                self._required_string(payload, "planId"),
                self._required_string(payload, "confirmToken"),
            )
        if path == "/steam/media/rollback":
            return self._dashboard().rollback_steam_media(
                self._required_string(payload, "operationId")
            )
        if path == "/system/lsfg/plan":
            return {"plan": self._dashboard().plan_lsfg_install()}
        if path == "/system/lsfg/apply":
            return self._dashboard().apply_lsfg_install(
                self._required_string(payload, "planId"),
                self._required_string(payload, "confirmToken"),
            )
        if path == "/system/lsfg/rollback":
            return self._dashboard().rollback_lsfg_install(
                self._required_string(payload, "operationId")
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
            action = payload.get("action", "activate")
            language = payload.get("language")
            if action == "toggle":
                return toggle_virtual_keyboard(language=language)
            return {"provider": activate_virtual_keyboard(language=language)}
        if path == "/keyboard/settings":
            settings = {
                name: value
                for name, value in payload.items()
                if name in {"sound", "haptic", "theme"} and isinstance(value, bool | str)
            }
            if not settings:
                raise ValueError("nenhuma configuração de teclado informada")
            return apply_maliit_comfort(settings)
        if path == "/session/select":
            return self._session_select(payload)
        if path == "/ashyterm":
            return launch_ashyterm()
        if path == "/panel/autohide":
            enable = bool(payload.get("enable", True))
            effect = KDEPanelEffect()
            status = self._control_server.coordinator.status()
            context = status.get("context")
            if not isinstance(context, dict):
                raise SteamZeroError("E-DESKTOP-VERIFY", detail="contexto Desktop indisponível")
            ctx = self._context_from_dict(context)
            if not effect.available(ctx):
                raise SteamZeroError(
                    "E-COMPONENT-DEGRADED",
                    detail="controle de painel indisponível nesta sessão",
                )
            prof = profile_for(automatic_profile(ctx), ctx)
            effect.apply(replace(prof, panel_auto_hide=enable), ctx)
            return {"status": "ok", "autoHide": enable}
        raise ValueError(f"ação não permitida: {path}")

    _SESSION_TARGETS = frozenset({"steam", "gamepadui"})

    def _session_select(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Retorno confirmado ao Game Mode: plano + token antes de encerrar a sessão."""
        target = str(payload.get("target", "steam"))
        if target not in self._SESSION_TARGETS:
            raise ValueError(f"destino de sessão não permitido: {target}")
        plan_id = payload.get("planId")
        confirm = payload.get("confirmToken")
        plans = self._control_server.session_plans
        if not plan_id or not confirm:
            status = session_readiness()
            if status.get("state") != "ready":
                raise SteamZeroError(
                    "E-COMPONENT-DEGRADED",
                    detail=str(status.get("statusLabel", "Game Mode indisponível")),
                )
            new_plan_id = secrets.token_urlsafe(8)
            token = secrets.token_urlsafe(16)
            plans.clear()
            plans[new_plan_id] = (token, target)
            return {
                "planId": new_plan_id,
                "confirmToken": token,
                "target": target,
                "readiness": status,
            }
        stored = plans.pop(str(plan_id), None)
        if stored is None or not secrets.compare_digest(stored[0], str(confirm)):
            raise SteamZeroError(
                "E-API-SCHEMA", detail="confirmação de troca de sessão inválida ou expirada"
            )
        if stored[1] != target:
            raise SteamZeroError("E-API-SCHEMA", detail="alvo divergente do plano confirmado")
        result = request_target(target)
        logged_out = logout_desktop_session()
        return {**result, "logout": logged_out}

    def _context_from_dict(self, context: dict[str, Any]) -> DesktopContext:
        displays = [
            DisplayState(
                name=str(d.get("name", "")),
                connected=bool(d.get("connected")),
                internal=bool(d.get("internal")),
                width=int(d["width"]) if d.get("width") is not None else None,
                height=int(d["height"]) if d.get("height") is not None else None,
                refresh_hz=float(d["refreshHz"]) if d.get("refreshHz") is not None else None,
                scale=float(d["scale"]) if d.get("scale") is not None else None,
            )
            for d in context.get("displays", [])
            if isinstance(d, dict)
        ]
        return DesktopContext(
            device_kind=str(context.get("deviceKind", "unknown")),
            session_type=str(context.get("sessionType", "unknown")),
            displays=tuple(displays),
            physical_dock=bool(context.get("physicalDock")),
            external_keyboard=bool(context.get("externalKeyboard")),
            external_mouse=bool(context.get("externalMouse")),
            capabilities=frozenset(context.get("capabilities", [])),
            conflicts=tuple(context.get("conflicts", [])),
        )

    def _dashboard(self) -> DesktopDashboard:
        dashboard = self._control_server.dashboard
        if dashboard is None:
            raise SteamZeroError("E-COMPONENT-DEGRADED", detail="dashboard Desktop indisponível")
        return dashboard

    def _require_desktop_without_conflicts(self) -> None:
        status = self._control_server.coordinator.status()
        context = status.get("context")
        conflicts = context.get("conflicts", []) if isinstance(context, dict) else []
        if conflicts:
            raise SteamZeroError(
                "E-DESKTOP-OWNER-CONFLICT",
                detail="resolva o owner concorrente antes de aplicar alterações",
            )

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
    dashboard = DesktopDashboard()
    server = DesktopControlServer(coordinator, token, dashboard)
    server.timeout = 0.2
    initial_status = coordinator.status()
    initial_status["dashboard"] = dashboard.snapshot(initial_status)
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
