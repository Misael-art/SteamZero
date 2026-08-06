# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Central Qt/QML com bridge HTTP efêmera, loopback-only e allowlisted."""

from __future__ import annotations

import importlib.resources
import json
import os
import secrets
import shutil
import subprocess
import threading
from dataclasses import replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

from steamzero.adapters.desktop_contracts import handheld_ui_contracts
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
from steamzero.core.state import StateStore
from steamzero.domain.desktop import (
    DesktopContext,
    DisplayState,
    ExperienceCoordinator,
    automatic_profile,
    profile_for,
)
from steamzero.ports import CaptureConsent

_MAX_BODY = 64 * 1024

# Status HTTP por código do catálogo. O default é CONFLICT: erro de domínio que
# recusa a operação no estado atual. Só o que é de fato malformado vira 400 e só
# rota inexistente vira 404 — o cliente distingue "corrija o pedido" de
# "o pedido está certo, o estado é que não permite".
_STATUS_BY_CODE = {
    "E-API-SCHEMA": HTTPStatus.BAD_REQUEST,
    "E-API-UNKNOWN-ACTION": HTTPStatus.NOT_FOUND,
}


class DesktopControlServer(ThreadingHTTPServer):
    # Long-running mutations must not block status polling or cancellation.
    daemon_threads = True
    token: str
    dashboard: DesktopDashboard | None
    session_plans: dict[str, tuple[str, str]]

    def __init__(
        self,
        coordinator: ExperienceCoordinator,
        token: str,
        dashboard: DesktopDashboard | None = None,
    ) -> None:
        self._coordinator_template = coordinator
        self._request_context = threading.local()
        self.token = token
        self.dashboard = dashboard
        self.session_plans = {}
        super().__init__(("127.0.0.1", 0), DesktopControlHandler)

    @property
    def coordinator(self) -> ExperienceCoordinator:
        coordinator = getattr(self._request_context, "coordinator", None)
        if coordinator is None:
            store = StateStore(self._coordinator_template.store_path)
            store.migrate()
            coordinator = self._coordinator_template.for_store(store)
            self._request_context.coordinator = coordinator
        return cast(ExperienceCoordinator, coordinator)

    def close_request_context(self) -> None:
        coordinator = getattr(self._request_context, "coordinator", None)
        if coordinator is not None:
            coordinator.close()
            del self._request_context.coordinator
        if self.dashboard is not None:
            close = getattr(self.dashboard, "close_request_context", None)
            if callable(close):
                close()


class DesktopControlHandler(BaseHTTPRequestHandler):
    server_version = "SteamZeroDesktop/1"

    def do_GET(self) -> None:
        if not self._authorized():
            self._send(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
            return
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/contracts":
            self._send(HTTPStatus.OK, handheld_ui_contracts())
        elif path == "/status":
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
        elif path == "/emulation/jobs":
            self._send(HTTPStatus.OK, {"jobs": self._dashboard().list_emulation_jobs()})
        elif path == "/component/list":
            self._send(HTTPStatus.OK, {"components": self._dashboard().list_components()})
        elif path == "/component/matrix":
            self._send(HTTPStatus.OK, self._dashboard().component_capability_matrix())
        elif path == "/component/open-config/matrix":
            self._send(HTTPStatus.OK, self._dashboard().component_open_config_matrix())
        elif path == "/component/recovery/inspect":
            self._send(HTTPStatus.OK, self._dashboard().component_recovery_inspect())
        elif path == "/bios/status":
            self._send(HTTPStatus.OK, self._dashboard().bios_status())
        elif path == "/bios/audit":
            self._send(HTTPStatus.OK, self._dashboard().bios_audit())
        elif path.startswith("/emulation/job/status/"):
            job_id = path.removeprefix("/emulation/job/status/")
            if not job_id:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "jobId ausente"})
                return
            result = self._dashboard().get_emulation_job_status(job_id)
            if result is None:
                self._send(HTTPStatus.NOT_FOUND, {"error": "job não encontrado"})
                return
            self._send(HTTPStatus.OK, result)
        elif path == "/system/operations":
            query = parse_qs(parsed.query)
            try:
                page = int(query.get("page", ["1"])[0])
                page_size = int(query.get("pageSize", ["20"])[0])
            except ValueError as exc:
                self._send(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._send(
                HTTPStatus.OK,
                self._dashboard().operations_history(page, page_size),
            )
        elif path == "/collections":
            self._send(HTTPStatus.OK, self._dashboard().collection_state())
        elif path == "/library/health":
            self._send(HTTPStatus.OK, self._dashboard().library_health())
        elif path == "/hud/presets":
            self._send(HTTPStatus.OK, self._dashboard().hud_presets())
        elif path == "/system/admin/health":
            self._send(HTTPStatus.OK, self._dashboard().admin_health())
        elif path == "/cast/discover":
            timeout_ms = int(parse_qs(parsed.query).get("timeout", ["5000"])[0])
            self._send(HTTPStatus.OK, {"receivers": self._dashboard().cast_discover(timeout_ms)})
        elif path == "/cast/status":
            self._send(HTTPStatus.OK, self._dashboard().cast_status())
        elif path == "/cast/sessions":
            self._send(HTTPStatus.OK, {"sessions": self._dashboard().cast_sessions()})
        elif path == "/theme/list":
            self._send(HTTPStatus.OK, {"themes": self._dashboard().theme_list()})
        elif path == "/theme/editor/load":
            query = parse_qs(parsed.query)
            vals: list[str] | list[None] = query.get("themeId") or []
            theme_id = vals[0] if vals else None
            if not theme_id:
                self._send(HTTPStatus.BAD_REQUEST, {"error": "themeId ausente"})
                return
            try:
                result = self._dashboard().editor_load(theme_id)
            except SteamZeroError as exc:
                self._send(HTTPStatus.NOT_FOUND, {"error": exc.to_error_object()})
                return
            self._send(HTTPStatus.OK, result)
        else:
            self._send(HTTPStatus.NOT_FOUND, {"error": "not-found"})

    def do_POST(self) -> None:
        if not self._authorized():
            self._send(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
            return
        try:
            payload = self._read_payload()
            result = self._dispatch(urlparse(self.path).path, payload)
        except SteamZeroError as exc:
            status = _STATUS_BY_CODE.get(exc.code, HTTPStatus.CONFLICT)
            self._send(status, {"error": exc.to_error_object()})
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
        try:
            length = int(raw_length)
        except ValueError:
            raise SteamZeroError("E-API-SCHEMA", detail="Content-Length não numérico") from None
        if length < 0 or length > _MAX_BODY:
            raise SteamZeroError("E-API-SCHEMA", detail="corpo fora do limite")
        if length == 0:
            return {}
        loaded = json.loads(self.rfile.read(length))
        if not isinstance(loaded, dict):
            raise SteamZeroError("E-API-SCHEMA", detail="corpo precisa ser objeto JSON")
        return loaded

    def _dispatch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        coordinator = self._control_server.coordinator
        if path == "/plan":
            requested = payload.get("profile", "auto")
            if not isinstance(requested, str):
                raise SteamZeroError("E-API-SCHEMA", detail="profile precisa ser string")
            return {"plan": coordinator.plan(requested).to_dict()}
        if path == "/component/status":
            (component_id,) = self._required_exact_strings(payload, "componentId")
            return self._dashboard().component_status(component_id)
        if path == "/component/verify":
            (component_id,) = self._required_exact_strings(payload, "componentId")
            return self._dashboard().verify_component(component_id)
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
            component_id, component_action = self._required_exact_strings(
                payload, "componentId", "action"
            )
            return {
                "plan": self._dashboard().plan_component(
                    component_id,
                    component_action,
                )
            }
        if path == "/component/apply":
            self._require_desktop_without_conflicts()
            plan_id, confirm_token = self._required_exact_strings(payload, "planId", "confirmToken")
            return self._dashboard().apply_component(
                plan_id,
                confirm_token,
            )
        if path == "/component/launch":
            (component_id,) = self._required_exact_strings(payload, "componentId")
            return self._dashboard().launch_component(component_id)
        if path == "/component/history":
            (component_id,) = self._required_exact_strings(payload, "componentId")
            return self._dashboard().component_operation_history(component_id)
        if path == "/component/rollback/plan":
            component_id, operation_id = self._required_exact_strings(
                payload, "componentId", "operationId"
            )
            return {
                "plan": self._dashboard().plan_component_rollback(
                    component_id,
                    operation_id,
                )
            }
        if path == "/component/rollback/apply":
            self._require_desktop_without_conflicts()
            plan_id, confirm_token = self._required_exact_strings(payload, "planId", "confirmToken")
            return self._dashboard().apply_component_rollback(
                plan_id,
                confirm_token,
            )
        if path == "/component/recovery/plan":
            return {"plan": self._dashboard().plan_component_recovery()}
        if path == "/component/recovery/apply":
            self._require_desktop_without_conflicts()
            plan_id, confirm_token = self._required_exact_strings(payload, "planId", "confirmToken")
            return self._dashboard().apply_component_recovery(
                plan_id,
                confirm_token,
            )
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
        if path == "/emulation/emulator/stop":
            return self._dashboard().stop_emulation_emulator(
                self._required_string(payload, "emulatorId")
            )
        if path == "/emulation/game/launch":
            return self._dashboard().launch_emulation_game(self._required_string(payload, "gameId"))
        if path == "/cloud/launch":
            return self._dashboard().launch_cloud_platform(
                self._required_string(payload, "platformId")
            )
        if path == "/emulation/action/plan":
            return {"plan": self._dashboard().plan_emulation_action(payload)}
        if path == "/emulation/action/apply":
            return self._dashboard().apply_emulation_action(
                self._required_string(payload, "planId"),
                self._required_string(payload, "confirmToken"),
            )
        if path == "/emulation/action/rollback":
            return self._dashboard().rollback_emulation_action(
                self._required_string(payload, "operationId")
            )
        if path == "/emulation/library/scan":
            return self._dashboard().scan_emulation_library()
        if path == "/emulation/job/status":
            job_id = self._required_string(payload, "jobId")
            result = self._dashboard().get_emulation_job_status(job_id)
            if result is None:
                raise SteamZeroError("E-API-SCHEMA", detail="job não encontrado")
            return result
        if path == "/emulation/job/cancel":
            return self._dashboard().cancel_emulation_job(self._required_string(payload, "jobId"))
        if path == "/emulation/job/retry":
            return self._dashboard().retry_emulation_job(self._required_string(payload, "jobId"))
        if path == "/steam/open":
            return self._dashboard().open_steam(self._required_string(payload, "target"))
        if path == "/steam/game/launch":
            return self._dashboard().launch_steam_game(self._required_string(payload, "gameId"))
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
        if path == "/steam/gameplay/rollback":
            return self._dashboard().rollback_steam_gameplay(
                self._required_string(payload, "operationId")
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
                raise SteamZeroError("E-API-SCHEMA", detail="campo obrigatório: categories")
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
        if path == "/system/diagnostics/export/plan":
            return self._dashboard().plan_diagnostics_export(
                Path(self._required_string(payload, "destination")),
                self._required_string(payload, "kind"),
                coordinator.status(),
            )
        if path == "/system/diagnostics/export/apply":
            return self._dashboard().apply_diagnostics_export(
                self._required_string(payload, "planId"),
                self._required_string(payload, "confirmToken"),
            )
        if path == "/system/operations/show":
            return self._dashboard().operation_detail(self._required_string(payload, "operationId"))
        if path == "/system/operations/rollback/plan":
            return self._dashboard().plan_operation_rollback(
                self._required_string(payload, "operationId")
            )
        if path == "/system/operations/rollback/apply":
            return self._dashboard().apply_operation_rollback(
                self._required_string(payload, "planId"),
                self._required_string(payload, "confirmToken"),
            )
        if path == "/collections/plan":
            action = payload.get("action")
            if not isinstance(action, dict):
                raise SteamZeroError("E-API-SCHEMA", detail="campo obrigatório: action")
            return self._dashboard().plan_collection_action(action)
        if path == "/collections/apply":
            return self._dashboard().apply_collection_action(
                self._required_string(payload, "planId"),
                self._required_string(payload, "confirmToken"),
            )
        if path == "/library/health/plan":
            return {"plan": self._dashboard().plan_library_health()}
        if path == "/library/health/apply":
            return self._dashboard().apply_library_health(
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
                raise SteamZeroError(
                    "E-API-SCHEMA", detail="nenhuma configuração de teclado informada"
                )
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
        if path == "/scraping/credential/status":
            return self._dashboard().credential_status()
        if path == "/scraping/credential/save":
            provider = self._required_string(payload, "provider")
            credentials = payload.get("credentials")
            if not isinstance(credentials, dict) or not credentials:
                raise SteamZeroError("E-API-SCHEMA", detail="credentials são obrigatórias")
            values = {
                key: value
                for key, value in credentials.items()
                if isinstance(key, str) and isinstance(value, str)
            }
            if len(values) != len(credentials):
                raise SteamZeroError("E-API-SCHEMA", detail="credentials inválidas")
            return self._dashboard().save_credential(provider, values)
        if path == "/scraping/credential/test":
            provider = self._required_string(payload, "provider")
            return self._dashboard().test_credential(provider)
        if path == "/scraping/credential/delete":
            provider = self._required_string(payload, "provider")
            return self._dashboard().delete_credential(provider)
        if path == "/scraping/provider-link":
            provider = self._required_string(payload, "provider")
            link = self._required_string(payload, "link")
            return self._dashboard().scraping_provider_link(provider, link)
        if path == "/cast/pair":
            receiver_id = self._required_string(payload, "receiverId")
            pin = payload.get("pin")
            if pin is not None and not isinstance(pin, str):
                raise SteamZeroError("E-API-SCHEMA", detail="pin precisa ser string")
            return self._dashboard().cast_pair(receiver_id, pin)
        if path == "/cast/start":
            receiver_id = self._required_string(payload, "receiverId")
            profile = payload.get("profile")
            mode = payload.get("mode")
            if profile is not None and not isinstance(profile, str):
                raise SteamZeroError("E-API-SCHEMA", detail="profile precisa ser string")
            if mode is not None and not isinstance(mode, str):
                raise SteamZeroError("E-API-SCHEMA", detail="mode precisa ser string")
            raw_consent = payload.get("consent")
            if not isinstance(raw_consent, dict):
                raise SteamZeroError(
                    "E-API-SCHEMA",
                    detail="consentimento explícito de captura é obrigatório",
                )
            granted = raw_consent.get("granted")
            scope = raw_consent.get("scope")
            audio = raw_consent.get("audio", False)
            if granted is not True:
                raise SteamZeroError(
                    "E-API-SCHEMA",
                    detail="consent.granted precisa ser true após ação explícita",
                )
            if scope not in {"monitor", "window", "virtual"}:
                raise SteamZeroError(
                    "E-API-SCHEMA",
                    detail="consent.scope precisa ser monitor, window ou virtual",
                )
            if not isinstance(audio, bool):
                raise SteamZeroError("E-API-SCHEMA", detail="consent.audio precisa ser booleano")
            return self._dashboard().cast_start(
                receiver_id,
                profile_id=profile or "balanced",
                mode=mode or "game",
                consent=CaptureConsent(granted=True, scope=scope, audio=audio),
            )
        if path == "/cast/stop":
            return self._dashboard().cast_stop()
        if path == "/theme/editor/create":
            return self._dashboard().editor_create(
                self._required_string(payload, "name"),
                str(payload.get("extends", "org.steamzero.default")),
            )
        if path == "/theme/editor/set-tokens":
            return self._dashboard().editor_set_tokens(
                self._required_string(payload, "sessionId"),
                self._required_string(payload, "category"),
                self._required_dict(payload, "values"),
            )
        if path == "/theme/editor/set-metadata":
            return self._dashboard().editor_set_metadata(
                self._required_string(payload, "sessionId"),
                self._required_string(payload, "field"),
                payload.get("value"),
            )
        if path == "/theme/editor/preview":
            sid = self._required_string(payload, "sessionId")
            hc = bool(payload.get("highContrast", False))
            rm = bool(payload.get("reducedMotion", False))
            return self._dashboard().editor_preview(sid, high_contrast=hc, reduced_motion=rm)
        if path == "/theme/editor/save":
            return self._dashboard().editor_save(
                self._required_string(payload, "sessionId"),
                overwrite=bool(payload.get("overwrite", False)),
            )
        if path == "/theme/editor/export":
            zip_data = self._dashboard().editor_export_zip(
                self._required_string(payload, "sessionId"),
            )
            import base64

            return {
                "zip": base64.b64encode(zip_data).decode("ascii"),
                "filename": f"theme-{payload['sessionId'][:8]}.zip",
            }
        if path == "/theme/editor/cancel":
            return self._dashboard().editor_cancel(
                self._required_string(payload, "sessionId"),
            )
        if path == "/theme/apply":
            return self._dashboard().plan_theme_apply(self._required_string(payload, "themeId"))
        if path == "/theme/apply/confirm":
            return self._dashboard().apply_theme_preference(
                self._required_string(payload, "planId"),
                self._required_string(payload, "confirmToken"),
            )
        if path == "/theme/apply/rollback":
            return self._dashboard().rollback_theme(self._required_string(payload, "operationId"))
        raise SteamZeroError("E-API-UNKNOWN-ACTION", detail=f"ação não permitida: {path}")

    _SESSION_TARGETS = frozenset({"steam", "gamepadui"})

    def _session_select(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Retorno confirmado ao Game Mode: plano + token antes de encerrar a sessão."""
        target = str(payload.get("target", "steam"))
        if target not in self._SESSION_TARGETS:
            raise SteamZeroError(
                "E-API-SCHEMA", detail=f"destino de sessão não permitido: {target}"
            )
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
                "E-TX-CONFIRM-REQUIRED",
                detail="confirmação de troca de sessão inválida ou expirada",
            )
        if stored[1] != target:
            raise SteamZeroError(
                "E-TX-CONFIRM-REQUIRED", detail="alvo divergente do plano confirmado"
            )
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
            raise SteamZeroError("E-API-SCHEMA", detail=f"campo obrigatório: {key}")
        return value

    def _required_exact_strings(self, payload: dict[str, Any], *keys: str) -> tuple[str, ...]:
        """Valida o schema fechado das rotas do lifecycle de componentes."""
        if set(payload) != set(keys):
            raise SteamZeroError("E-API-SCHEMA", detail="propriedades do componente inválidas")
        return tuple(self._required_string(payload, key) for key in keys)

    def _required_dict(self, payload: dict[str, Any], key: str) -> dict[str, Any]:
        value = payload.get(key)
        if not isinstance(value, dict):
            raise SteamZeroError("E-API-SCHEMA", detail=f"campo obrigatório: {key}")
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

    def finish(self) -> None:
        try:
            super().finish()
        finally:
            self._control_server.close_request_context()


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
    resource = importlib.resources.files("steamzero.ui").joinpath("qml/Main.qml")
    try:
        with importlib.resources.as_file(resource) as qml_path:
            process = subprocess.Popen(  # noqa: S603
                [
                    executable,
                    str(qml_path),
                    "--",
                    "--steamzero-api",
                    f"http://127.0.0.1:{server.server_port}",
                    "--steamzero-token",
                    token,
                ],
                stdin=subprocess.DEVNULL,
                env={**os.environ, "STEAMZERO_CLASS": "ui"},
            )
            while process.poll() is None:
                server.handle_request()
            return int(process.returncode or 0)
    finally:
        server.server_close()
