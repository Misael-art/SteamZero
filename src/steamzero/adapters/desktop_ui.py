# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Central Qt/QML com bridge HTTP efêmera, loopback-only e allowlisted."""

from __future__ import annotations

import contextlib
import importlib.resources
import json
import math
import os
import re
import secrets
import shutil
import subprocess
import threading
from collections.abc import Mapping
from dataclasses import replace
from functools import lru_cache
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
from steamzero.adapters.journey_studio import (
    MAX_PREVIEW_ROWS,
    MAX_PUBLIC_RECORDS,
    JourneyStudioService,
)
from steamzero.adapters.steam_session import readiness as session_readiness
from steamzero.adapters.steam_session import request_target
from steamzero.core import paths, transaction
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
# A central QML precisa continuar disponível mesmo quando o driver gráfico do
# host falha. O backend software é o mesmo caminho certificado pelo gate visual
# e evita que um SIGSEGV do renderer encerre a unidade transitória do Plasma.
_QT_QUICK_BACKEND = "software"
_QT_QUICK_EFFECTS_MINIMUM = (6, 5)
_QML_VERSION_PATTERN = re.compile(r"(?:Qml Runtime|Qt)\s+(\d+)\.(\d+)")

# Status HTTP por código do catálogo. O default é CONFLICT: erro de domínio que
# recusa a operação no estado atual. Só o que é de fato malformado vira 400 e só
# rota inexistente vira 404 — o cliente distingue "corrija o pedido" de
# "o pedido está certo, o estado é que não permite".
_STATUS_BY_CODE = {
    "E-API-SCHEMA": HTTPStatus.BAD_REQUEST,
    "E-API-UNKNOWN-ACTION": HTTPStatus.NOT_FOUND,
}

_PUBLIC_GAME_RECORD_FIELDS = frozenset(
    {
        "sortTitle",
        "aliases",
        "systemId",
        "family",
        "region",
        "language",
        "container",
        "size",
        "developer",
        "publisher",
        "releaseDate",
        "genres",
        "series",
        "franchise",
        "description",
        "rating",
        "ageRating",
        "players",
        "features",
        "runtime",
        "core",
        "emulatorId",
        "availability",
    }
)
_JOURNEY_FIELD_LABELS = {
    "id": "Identificador",
    "gameId": "ID do jogo",
    "title": "Título",
    "name": "Nome",
    "source": "Origem",
    "platformId": "Plataforma",
    "platformName": "Nome da plataforma",
    "shortName": "Nome curto",
    "gameCount": "Quantidade de jogos",
    "state": "Estado publicado",
    "year": "Ano de lançamento",
    "genre": "Gênero principal",
    "sortTitle": "Título para ordenação",
    "aliases": "Outros nomes",
    "systemId": "Sistema",
    "family": "Família de sistemas",
    "region": "Região",
    "language": "Idioma",
    "container": "Formato do arquivo",
    "size": "Tamanho",
    "developer": "Desenvolvedora",
    "publisher": "Publicadora",
    "releaseDate": "Data de lançamento",
    "genres": "Gêneros publicados",
    "series": "Série",
    "franchise": "Franquia",
    "description": "Descrição",
    "rating": "Classificação",
    "ageRating": "Classificação etária",
    "players": "Jogadores",
    "features": "Recursos publicados",
    "runtime": "Runtime publicado",
    "core": "Core de emulação",
    "availability": "Disponibilidade",
    "emulatorId": "Emulador",
}
_JOURNEY_OPERATION_FIELDS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "rename-journey": (frozenset({"name"}), frozenset()),
    "add-menu": (frozenset({"menu"}), frozenset({"organizationId", "parentId"})),
    "duplicate-menu": (
        frozenset({"menuId", "newId", "name"}),
        frozenset({"organizationId", "parentId"}),
    ),
    "rename-menu": (frozenset({"menuId", "name"}), frozenset()),
    "remove-menu": (frozenset({"menuId"}), frozenset({"replacementMenuId"})),
    "reorder-menus": (frozenset({"menuIds"}), frozenset()),
    "set-entry-menu": (frozenset({"menuId"}), frozenset()),
    "set-source": (frozenset({"menuId", "readModelId"}), frozenset()),
    "add-connection": (frozenset({"connection"}), frozenset()),
    "remove-connection": (frozenset({"connectionId"}), frozenset()),
    "set-filters": (frozenset({"menuId", "values"}), frozenset()),
    "set-sort": (frozenset({"menuId", "values"}), frozenset()),
    "set-group-by": (frozenset({"menuId", "values"}), frozenset()),
    "set-menu-appearance": (frozenset({"menuId", "appearance"}), frozenset()),
    "set-stage-appearance": (frozenset({"stageId", "appearance"}), frozenset()),
}


def _effective_theme_coverage_manifest(loaded: Mapping[str, Any]) -> dict[str, Any]:
    """Combine manifest metadata with scene declarations resolved through ``extends``."""
    manifest = loaded.get("manifest")
    if not isinstance(manifest, Mapping):
        return {}
    effective = dict(manifest)
    declared = loaded.get("declared")
    if isinstance(declared, Mapping):
        for field in ("sceneMotion", "sceneLayouts", "sceneSurfaces"):
            value = declared.get(field)
            if isinstance(value, Mapping):
                effective[field] = dict(value)
    return effective


@lru_cache(maxsize=1)
def _game_record_public_field_types() -> dict[str, str]:
    """Use tipos do schema canônico, publicando só campos sem paths/segredos."""
    schema_path = Path(__file__).resolve().parents[1] / "schemas" / "game-record-v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    properties = schema.get("properties") if isinstance(schema, dict) else None
    if not isinstance(properties, dict):
        raise RuntimeError("schema GameRecord sem propriedades públicas")
    types: dict[str, str] = {}
    for field_id in sorted(_PUBLIC_GAME_RECORD_FIELDS):
        definition = properties.get(field_id)
        if not isinstance(definition, dict):
            continue
        field_type = definition.get("type")
        if field_type in {"string", "integer", "number", "boolean"}:
            types[field_id] = str(field_type)
        elif (
            field_type == "array"
            and isinstance(definition.get("items"), dict)
            and definition["items"].get("type") == "string"
        ):
            types[field_id] = "string[]"
    return types


def _journey_field_descriptors(field_types: Mapping[str, str]) -> list[dict[str, str]]:
    combined = {
        "id": "string",
        "gameId": "string",
        "title": "string",
        "name": "string",
        "source": "string",
        "platformId": "string",
        "platformName": "string",
        "shortName": "string",
        "gameCount": "integer",
        "year": "integer",
        "genre": "string",
        **field_types,
    }
    descriptors = []
    for field_id, field_type in combined.items():
        label = _JOURNEY_FIELD_LABELS.get(
            field_id, field_id.replace("Id", " ID").replace("Date", " data").capitalize()
        )
        descriptors.append({"id": field_id, "name": label, "label": label, "type": field_type})
    return descriptors


def _safe_public_value(value: object, field_type: str) -> object:
    if field_type == "string" and isinstance(value, str):
        return value[:4096]
    if field_type == "integer" and isinstance(value, int) and not isinstance(value, bool):
        return value
    if field_type == "number" and isinstance(value, int | float) and not isinstance(value, bool):
        return value if not isinstance(value, float) or math.isfinite(value) else None
    if field_type == "boolean" and isinstance(value, bool):
        return value
    if field_type == "string[]" and isinstance(value, list):
        return [item[:512] for item in value[:64] if isinstance(item, str)]
    return None


def _project_journey_game(
    record: Mapping[str, Any],
    *,
    source: str,
    platform_name_by_id: Mapping[str, str],
    field_types: Mapping[str, str],
    default_platform_id: str | None = None,
) -> dict[str, Any] | None:
    record_id = record.get("id")
    title = record.get("title", record.get("name"))
    if not isinstance(record_id, str) or not record_id or not isinstance(title, str) or not title:
        return None
    row: dict[str, Any] = {
        "id": f"{source}:{record_id}"[:256],
        "gameId": record_id[:128],
        "source": source,
        "title": title[:512],
        "name": title[:512],
    }
    for field_id, field_type in field_types.items():
        value = record.get(field_id)
        if field_id == "platformId" and value is None:
            value = record.get("platform", default_platform_id)
        public_value = _safe_public_value(value, field_type)
        if public_value is not None:
            row[field_id] = public_value
    platform_id = row.get("platformId")
    if isinstance(platform_id, str) and platform_id in platform_name_by_id:
        row["platformName"] = platform_name_by_id[platform_id]
    release_date = row.get("releaseDate")
    if isinstance(release_date, str) and len(release_date) >= 4:
        year = release_date[:4]
        if year.isdecimal() and len(year) == 4:
            row["year"] = int(year)
    genres = row.get("genres")
    if isinstance(genres, list) and genres and isinstance(genres[0], str):
        row["genre"] = genres[0]
    elif isinstance(record.get("genre"), str):
        row["genre"] = str(record["genre"])[:256]
    return row


def _project_journey_read_models(
    dashboard: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    field_types = _game_record_public_field_types()
    platform_fields = {
        "id": "string",
        "name": "string",
        "shortName": "string",
        "state": "string",
        "gameCount": "integer",
    }
    if not isinstance(dashboard, Mapping):
        return {
            "library.games": {
                "rows": None,
                "fields": {
                    **field_types,
                    "id": "string",
                    "gameId": "string",
                    "title": "string",
                    "name": "string",
                    "source": "string",
                    "platformId": "string",
                    "platformName": "string",
                    "year": "integer",
                    "genre": "string",
                },
                "state": "unavailable",
            },
            "library.platforms": {"rows": None, "fields": platform_fields, "state": "unavailable"},
        }

    emulation = dashboard.get("emulation")
    editorial_platforms = (
        emulation.get("editorialPlatforms") if isinstance(emulation, Mapping) else None
    )
    emulation_available = isinstance(editorial_platforms, list)
    platforms = editorial_platforms if isinstance(editorial_platforms, list) else []
    platform_name_by_id: dict[str, str] = {}
    platform_rows: list[dict[str, Any]] = []
    raw_games: list[tuple[Mapping[str, Any], str | None]] = []
    raw_game_count = 0
    for platform in platforms:
        if not isinstance(platform, Mapping):
            continue
        platform_id, platform_name = platform.get("id"), platform.get("name")
        if not isinstance(platform_id, str) or not isinstance(platform_name, str):
            continue
        platform_name_by_id[platform_id] = platform_name[:256]
        games = platform.get("games")
        platform_games = (
            [game for game in games if isinstance(game, Mapping)] if isinstance(games, list) else []
        )
        platform_rows.append(
            {
                "id": platform_id[:128],
                "name": platform_name[:256],
                "shortName": str(platform.get("shortName") or platform_name)[:128],
                "state": str(platform.get("state") or "unknown")[:64],
                "gameCount": len(platform_games),
            }
        )
        raw_game_count += len(platform_games)
        remaining = MAX_PUBLIC_RECORDS - len(raw_games)
        raw_games.extend((game, platform_id) for game in platform_games[:remaining])

    rows: list[dict[str, Any]] = []
    for game, platform_id in raw_games:
        projected = _project_journey_game(
            game,
            source="emulation",
            platform_name_by_id=platform_name_by_id,
            field_types=field_types,
            default_platform_id=platform_id,
        )
        if projected is not None:
            rows.append(projected)

    steam_gameplay = dashboard.get("steamGameplay")
    steam_games_value = steam_gameplay.get("games") if isinstance(steam_gameplay, Mapping) else None
    steam_available = isinstance(steam_games_value, list)
    steam_games = steam_games_value if isinstance(steam_games_value, list) else []
    if steam_available:
        raw_game_count += len(steam_games)
        remaining = max(0, MAX_PUBLIC_RECORDS - len(raw_games))
        for game in steam_games[:remaining]:
            if not isinstance(game, Mapping):
                continue
            projected = _project_journey_game(
                game,
                source="steam",
                platform_name_by_id=platform_name_by_id,
                field_types=field_types,
            )
            if projected is not None:
                rows.append(projected)

    game_fields = {
        **field_types,
        "id": "string",
        "gameId": "string",
        "title": "string",
        "name": "string",
        "source": "string",
        "platformId": "string",
        "platformName": "string",
        "year": "integer",
        "genre": "string",
    }
    return {
        "library.games": {
            "rows": (
                None
                if raw_game_count > MAX_PUBLIC_RECORDS
                else rows
                if emulation_available or steam_available
                else None
            ),
            "fields": game_fields,
            "state": (
                "budget-exceeded"
                if raw_game_count > MAX_PUBLIC_RECORDS
                else "ready"
                if rows
                else "empty"
                if emulation_available or steam_available
                else "unavailable"
            ),
            "totalRecordCount": raw_game_count,
        },
        "library.platforms": {
            "rows": platform_rows if emulation_available else None,
            "fields": platform_fields,
            "state": "ready"
            if platform_rows
            else "empty"
            if emulation_available
            else "unavailable",
        },
    }


def _qml_supports_quick_effects(executable: str) -> bool:
    """Detecta a capacidade opcional sem tornar a UI dependente da sonda."""

    try:
        completed = subprocess.run(  # noqa: S603
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    output = f"{completed.stdout}\n{completed.stderr}"
    match = _QML_VERSION_PATTERN.search(output)
    if match is None:
        return False
    return (int(match.group(1)), int(match.group(2))) >= _QT_QUICK_EFFECTS_MINIMUM


class DesktopControlServer(ThreadingHTTPServer):
    # Long-running mutations must not block status polling or cancellation.
    daemon_threads = True
    token: str
    dashboard: DesktopDashboard | None
    session_plans: dict[str, tuple[str, str]]
    bios_source_handles: dict[str, str]
    bios_source_lock: threading.Lock
    journey_studio: JourneyStudioService

    def __init__(
        self,
        coordinator: ExperienceCoordinator,
        token: str,
        dashboard: DesktopDashboard | None = None,
        journey_studio: JourneyStudioService | None = None,
    ) -> None:
        self._coordinator_template = coordinator
        self._request_context = threading.local()
        self.token = token
        self.dashboard = dashboard
        self.journey_studio = journey_studio or JourneyStudioService(paths.data_home() / "journeys")
        self._journey_read_models: dict[str, dict[str, Any]] | None = None
        self._journey_read_models_lock = threading.RLock()
        self._journey_theme_lock = threading.RLock()
        self.session_plans = {}
        # Handles de origem pertencem a esta instância efêmera da bridge. Eles
        # não são paths, não sobrevivem a uma nova lista e não são reutilizáveis
        # por outra sessão Desktop.
        self.bios_source_handles = {}
        self.bios_source_lock = threading.Lock()
        super().__init__(("127.0.0.1", 0), DesktopControlHandler)

    def publish_journey_read_models(self, dashboard_snapshot: Mapping[str, Any]) -> None:
        projected = _project_journey_read_models(dashboard_snapshot)
        with self._journey_read_models_lock:
            self._journey_read_models = projected

    def journey_read_models(self) -> dict[str, dict[str, Any]] | None:
        with self._journey_read_models_lock:
            return self._journey_read_models

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
                    dashboard_snapshot = dashboard.snapshot(status)
                    status["dashboard"] = dashboard_snapshot
                    self._control_server.publish_journey_read_models(dashboard_snapshot)
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
        elif path == "/bios/sources":
            self._send(HTTPStatus.OK, self._issue_bios_source_handles())
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
        elif path == "/journey/studio/list":
            self._send(
                HTTPStatus.OK,
                {"journeys": self._control_server.journey_studio.list()},
            )
        elif path == "/journey/studio/catalog":
            try:
                models = self._refresh_journey_read_models()
                self._send(HTTPStatus.OK, self._journey_catalog(models))
            except SteamZeroError as exc:
                self._send(HTTPStatus.CONFLICT, {"error": exc.to_error_object()})
            except Exception as exc:
                self._send(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": build_error("E-INTERNAL-UNEXPECTED", detail=str(exc))},
                )
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
        if path == "/bios/scan":
            (source_id,) = self._required_exact_strings(payload, "sourceId")
            return self._dashboard().bios_scan_selected(self._bios_source_handle(source_id))
        if path == "/bios/scan/status":
            (scan_id,) = self._required_exact_strings(payload, "scanId")
            return self._dashboard().bios_scan_status(scan_id)
        if path == "/bios/import/plan":
            scan_id, selection = self._bios_import_payload(payload)
            return {"plan": self._dashboard().bios_import_plan(scan_id, selection)}
        if path == "/bios/import/apply":
            self._require_desktop_without_conflicts()
            plan_id, confirm_token = self._required_exact_strings(payload, "planId", "confirmToken")
            return self._dashboard().bios_import_apply(plan_id, confirm_token)
        if path == "/bios/rollback/plan":
            (operation_id,) = self._required_exact_strings(payload, "operationId")
            return {"plan": self._dashboard().plan_bios_import_rollback(operation_id)}
        if path == "/bios/rollback/apply":
            self._require_desktop_without_conflicts()
            plan_id, confirm_token = self._required_exact_strings(payload, "planId", "confirmToken")
            return self._dashboard().apply_bios_import_rollback(plan_id, confirm_token)
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
        # Importação de tema de terceiros. `inspect` é leitura e vem antes de
        # `apply` de propósito: a conversão não é fiel por construção, e o
        # usuário precisa ver `isMonochrome` e `unsupportedSlots` ANTES de
        # importar, não depois de olhar um tema cinza e não entender por quê.
        if path == "/theme/import/package/inspect":
            return self._dashboard().theme_import_zip_inspect(
                self._required_string(payload, "source"),
            )
        if path == "/theme/import/package/apply":
            # `overwrite` é explícito e falso por omissão: importar um tema cujo
            # id já existe SOBRESCREVE o instalado, e isso não pode acontecer
            # por omissão de campo.
            return self._dashboard().theme_import_zip_apply(
                self._required_string(payload, "source"),
                overwrite=payload.get("overwrite") is True,
                as_copy=payload.get("asCopy") is True,
            )
        if path == "/theme/catalog/list":
            return self._dashboard().theme_catalog_list()
        if path == "/theme/catalog/install":
            # `overwrite` explícito e falso por omissão: reinstalar por cima de
            # um tema já presente não pode acontecer por campo ausente.
            return self._dashboard().theme_catalog_install(
                self._required_string(payload, "themeId"),
                overwrite=payload.get("overwrite") is True,
            )
        if path == "/theme/catalog/rollback":
            return self._dashboard().theme_catalog_rollback(
                self._required_string(payload, "themeId"),
                self._required_string(payload, "operationId"),
            )
        if path == "/theme/catalog/uninstall":
            return self._dashboard().theme_catalog_uninstall(
                self._required_string(payload, "themeId"),
            )
        if path == "/theme/store/gc":
            # `apply` explícito: a prévia é o padrão, e apagar blob do usuário
            # exige pedido, não omissão.
            return self._dashboard().theme_store_gc(apply=payload.get("apply") is True)
        if path == "/theme/scene/render":
            # Seleção por campo nomeado, nunca posicional: trocar variante por
            # esquema de cor compilaria um tema diferente sem erro nenhum.
            return self._dashboard().theme_scene_render(
                self._required_string(payload, "themeId"),
                system_id=payload.get("systemId") or None,
                variant=str(payload.get("variant") or ""),
                color_scheme=str(payload.get("colorScheme") or ""),
                font_size=str(payload.get("fontSize") or ""),
                aspect_ratio=str(payload.get("aspectRatio") or ""),
                synthetic=payload.get("synthetic") is True,
            )
        if path == "/theme/scene/render-imported":
            return self._dashboard().theme_imported_scene_render(
                self._required_string(payload, "sceneId"),
                synthetic=payload.get("synthetic") is not False,
            )
        if path == "/theme/import/esde/inspect":
            return self._dashboard().theme_import_esde_inspect(
                self._required_string(payload, "source"),
            )
        if path == "/theme/import/esde/apply":
            return self._dashboard().theme_import_esde_apply(
                self._required_string(payload, "source"),
                self._required_string(payload, "scheme"),
                self._required_string(payload, "name"),
            )
        if path == "/theme/import/retrofe/inspect":
            return self._dashboard().theme_import_retrofe_inspect(
                self._required_string(payload, "source"),
            )
        if path == "/theme/import/retrofe/apply":
            return self._dashboard().theme_import_retrofe_apply(
                self._required_string(payload, "source"),
                self._required_string(payload, "layout"),
                self._required_string(payload, "sceneId"),
                self._required_string(payload, "name"),
                self._required_string(payload, "author"),
                self._required_string(payload, "license"),
                overwrite=payload.get("overwrite") is True,
            )
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
        if path == "/theme/editor/set-layout":
            return self._dashboard().editor_set_layout(
                self._required_string(payload, "sessionId"),
                self._required_string(payload, "layoutId"),
                self._required_string(payload, "field"),
                payload.get("value"),
            )
        if path == "/theme/editor/set-media-recipe":
            return self._dashboard().editor_set_media_recipe(
                self._required_string(payload, "sessionId"),
                self._required_string(payload, "role"),
                self._required_string(payload, "field"),
                payload.get("value"),
            )
        if path == "/theme/editor/edit-effect":
            raw_index = payload.get("index")
            return self._dashboard().editor_edit_effect(
                self._required_string(payload, "sessionId"),
                self._required_string(payload, "stack"),
                self._required_string(payload, "op"),
                index=raw_index if isinstance(raw_index, int) else None,
                effect_type=payload.get("effectType")
                if isinstance(payload.get("effectType"), str)
                else None,
                param=payload.get("param") if isinstance(payload.get("param"), str) else None,
                value=payload.get("value"),
            )
        if path == "/theme/editor/edit-motion":
            raw_index = payload.get("index")
            raw_field = payload.get("field")
            return self._dashboard().editor_edit_motion(
                self._required_string(payload, "sessionId"),
                self._required_string(payload, "op"),
                timeline=self._required_string(payload, "timeline"),
                index=raw_index if isinstance(raw_index, int) else None,
                field=raw_field if isinstance(raw_field, str) else None,
                value=payload.get("value"),
            )
        if path == "/theme/editor/edit-binding":
            raw_binding = payload.get("binding")
            return self._dashboard().editor_edit_binding(
                self._required_string(payload, "sessionId"),
                self._required_string(payload, "layoutId"),
                self._required_string(payload, "prop"),
                binding=raw_binding if isinstance(raw_binding, str) else None,
                fallback=payload.get("fallback"),
            )
        if path == "/theme/editor/undo":
            return self._dashboard().editor_undo(self._required_string(payload, "sessionId"))
        if path == "/theme/editor/redo":
            return self._dashboard().editor_redo(self._required_string(payload, "sessionId"))
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
            return self._dashboard().plan_theme_export(
                self._required_string(payload, "sessionId"),
                Path(self._required_string(payload, "destination")),
            )
        if path == "/theme/editor/export/apply":
            return self._dashboard().apply_theme_export(
                self._required_string(payload, "planId"),
                self._required_string(payload, "confirmToken"),
            )
        if path == "/theme/editor/cancel":
            return self._dashboard().editor_cancel(
                self._required_string(payload, "sessionId"),
            )
        if path == "/journey/studio/create":
            self._require_exact_keys(payload, {"name"})
            name = self._required_string(payload, "name")
            if len(name) > 128:
                raise SteamZeroError("E-API-SCHEMA", detail="nome da jornada excede 128 caracteres")
            return self._control_server.journey_studio.create(name=name)
        if path == "/journey/studio/load":
            self._require_exact_keys(payload, {"journeyId"})
            return self._control_server.journey_studio.load(
                self._required_string(payload, "journeyId")
            )
        if path == "/journey/studio/transact":
            self._require_exact_keys(payload, {"operation", "payload"})
            operation = self._required_string(payload, "operation")
            edit_payload = self._required_dict(payload, "payload")
            self._require_exact_keys(
                edit_payload,
                {"sessionId", "expectedGeneration"},
                optional=_JOURNEY_OPERATION_FIELDS.get(operation, (frozenset(), frozenset()))[0]
                | _JOURNEY_OPERATION_FIELDS.get(operation, (frozenset(), frozenset()))[1],
            )
            generation = edit_payload.get("expectedGeneration")
            if not isinstance(generation, int) or isinstance(generation, bool) or generation < 0:
                raise SteamZeroError("E-API-SCHEMA", detail="expectedGeneration inválida")
            session_id = self._required_string(edit_payload, "sessionId")
            operation_fields = _JOURNEY_OPERATION_FIELDS.get(operation)
            if operation_fields is None:
                raise SteamZeroError("E-API-SCHEMA", detail="operação de Jornada não allowlisted")
            operation_payload = {
                key: value
                for key, value in edit_payload.items()
                if key not in {"sessionId", "expectedGeneration"}
            }
            self._validate_journey_operation(operation, operation_payload)
            return self._control_server.journey_studio.transact(
                session_id,
                operation,
                operation_payload,
                expected_generation=generation,
            )
        if path == "/journey/studio/save":
            self._require_exact_keys(payload, {"sessionId", "overwrite"})
            overwrite = payload.get("overwrite")
            if not isinstance(overwrite, bool):
                raise SteamZeroError("E-API-SCHEMA", detail="overwrite precisa ser booleano")
            return self._control_server.journey_studio.save(
                self._required_string(payload, "sessionId"), overwrite=overwrite
            )
        if path == "/journey/studio/preview":
            self._require_exact_keys(
                payload,
                {"sessionId", "menuId"},
                optional={"contextFilters"},
            )
            session_id = self._required_string(payload, "sessionId")
            menu_id = self._required_string(payload, "menuId")
            context_filters = payload.get("contextFilters", {})
            if not isinstance(context_filters, dict) or any(
                not isinstance(key, str)
                or not key
                or not (
                    value is None
                    or isinstance(value, str | int | bool)
                    or (isinstance(value, float) and math.isfinite(value))
                )
                for key, value in context_filters.items()
            ):
                raise SteamZeroError(
                    "E-API-SCHEMA", detail="contextFilters deve conter campos e valores escalares"
                )
            result, _session, _menu, _model = self._journey_preview_query(
                session_id, menu_id, context_filters=context_filters
            )
            return result
        if path == "/journey/studio/engine-preview":
            self._require_exact_keys(payload, {"sessionId", "menuId", "expectedGeneration"})
            session_id = self._required_string(payload, "sessionId")
            menu_id = self._required_string(payload, "menuId")
            expected_generation = payload.get("expectedGeneration")
            if (
                not isinstance(expected_generation, int)
                or isinstance(expected_generation, bool)
                or expected_generation < 0
            ):
                raise SteamZeroError("E-API-SCHEMA", detail="expectedGeneration inválida")
            journey = self._control_server.journey_studio.snapshot(session_id)
            if journey["generation"] != expected_generation:
                raise SteamZeroError(
                    "E-API-SCHEMA", detail="a jornada mudou; atualize antes de pré-visualizar"
                )
            query, _session, menu, model = self._journey_preview_query(session_id, menu_id)
            if self._control_server.journey_studio.snapshot(session_id)["generation"] != (
                expected_generation
            ):
                raise SteamZeroError(
                    "E-API-SCHEMA", detail="a jornada mudou durante a pré-visualização"
                )
            public_fields = model.get("fields")
            rows = query.get("rows")
            if not isinstance(public_fields, Mapping) or not isinstance(rows, list):
                raise SteamZeroError(
                    "E-COMPONENT-DEGRADED", detail="a projeção pública da Jornada está inválida"
                )
            engine_rows = [
                {key: value for key, value in row.items() if key in public_fields}
                for row in rows
                if isinstance(row, Mapping)
            ]
            theme_read_model = {"preview": {"items": engine_rows}}
            appearance = menu.get("appearance")
            declared_theme_id = (
                str(appearance.get("themeId"))
                if isinstance(appearance, Mapping)
                and appearance.get("mode") == "custom"
                and isinstance(appearance.get("themeId"), str)
                else ""
            )
            dashboard = self._dashboard()
            theme_session_ids: list[str] = []
            try:
                with self._control_server._journey_theme_lock:
                    loaded_by_theme: dict[str, Mapping[str, Any]] = {}
                    manifests: dict[str, dict[str, Any]] = {}
                    aura_id = "org.steamzero.default"
                    loaded_aura = dashboard.editor_load(aura_id)
                    if not isinstance(loaded_aura, Mapping):
                        raise SteamZeroError(
                            "E-COMPONENT-DEGRADED", detail="Theme Engine não abriu o tema AURA"
                        )
                    aura_session_id = str(loaded_aura.get("sessionId") or "")
                    if aura_session_id:
                        theme_session_ids.append(aura_session_id)
                    aura_manifest = loaded_aura.get("manifest")
                    if not isinstance(aura_manifest, Mapping):
                        raise SteamZeroError(
                            "E-COMPONENT-DEGRADED",
                            detail="Theme Engine devolveu o manifesto AURA inválido",
                        )
                    loaded_by_theme[aura_id] = loaded_aura
                    manifests[aura_id] = _effective_theme_coverage_manifest(loaded_aura)

                    if declared_theme_id and declared_theme_id != aura_id:
                        try:
                            loaded_custom = dashboard.editor_load(declared_theme_id)
                        except SteamZeroError as exc:
                            if exc.code != "E-THEME-NOT-FOUND":
                                raise
                        else:
                            if not isinstance(loaded_custom, Mapping):
                                raise SteamZeroError(
                                    "E-COMPONENT-DEGRADED",
                                    detail="Theme Engine não abriu o tema selecionado",
                                )
                            custom_session_id = str(loaded_custom.get("sessionId") or "")
                            if custom_session_id:
                                theme_session_ids.append(custom_session_id)
                            custom_manifest = loaded_custom.get("manifest")
                            if isinstance(custom_manifest, Mapping):
                                loaded_by_theme[declared_theme_id] = loaded_custom
                                manifests[declared_theme_id] = _effective_theme_coverage_manifest(
                                    loaded_custom
                                )

                    coverage = self._control_server.journey_studio.coverage(
                        session_id,
                        used_stages=[f"menu:{menu_id}"],
                        themes=manifests,
                        aura_version=str(aura_manifest.get("version") or "unknown"),
                    )
                    coverage_stage = coverage["stages"][0]
                    theme_id = str(coverage_stage.get("sourceThemeId") or aura_id)
                    resolution_state = str(coverage_stage.get("appearance") or "unknown")
                    resolution_diagnostic = ""
                    if resolution_state == "missing-reference":
                        resolution_diagnostic = (
                            f"O tema {declared_theme_id} não está disponível; "
                            "a prévia usa AURA para esta etapa."
                        )
                    elif resolution_state == "incompatible":
                        missing = coverage_stage.get("missingSceneElements", [])
                        detail = ", ".join(str(value) for value in missing)
                        resolution_diagnostic = (
                            f"O tema {declared_theme_id} não cobre esta etapa; "
                            f"a prévia usa AURA{(': ' + detail) if detail else ''}."
                        )
                    loaded_theme = loaded_by_theme.get(theme_id)
                    if loaded_theme is None:
                        raise SteamZeroError(
                            "E-COMPONENT-DEGRADED",
                            detail=f"Theme Engine não abriu o tema resolvido: {theme_id}",
                        )
                    theme_session_id = str(loaded_theme.get("sessionId") or "")
                    if not theme_session_id:
                        raise SteamZeroError(
                            "E-COMPONENT-DEGRADED",
                            detail="Theme Engine não abriu uma sessão de leitura",
                        )
                    theme_preview = dashboard.editor_preview(
                        theme_session_id,
                        scene_layout_read_model=theme_read_model,
                    )
                    manifest = loaded_theme.get("manifest")
                    declared = loaded_theme.get("declared")
                    preview = theme_preview.get("preview")
                    if not isinstance(manifest, Mapping) or not isinstance(declared, Mapping):
                        raise SteamZeroError(
                            "E-COMPONENT-DEGRADED",
                            detail="Theme Engine devolveu uma declaração inválida",
                        )
                    if not isinstance(preview, Mapping):
                        raise SteamZeroError(
                            "E-COMPONENT-DEGRADED",
                            detail="Theme Engine não materializou a pré-visualização",
                        )
                    return {
                        "journeyGeneration": expected_generation,
                        "query": query,
                        "themeId": theme_id,
                        "declaredThemeId": declared_theme_id or None,
                        "themeResolutionState": resolution_state,
                        "themeResolutionDiagnostic": resolution_diagnostic,
                        "coverage": coverage,
                        "manifest": dict(manifest),
                        "declared": dict(declared),
                        "preview": dict(preview),
                    }
            finally:
                for theme_session_id in theme_session_ids:
                    with contextlib.suppress(SteamZeroError, OSError, ValueError):
                        dashboard.editor_cancel(theme_session_id)
        if path == "/journey/studio/coverage":
            self._require_exact_keys(payload, {"sessionId", "usedStages"})
            session_id = self._required_string(payload, "sessionId")
            used_stages = payload.get("usedStages")
            if not isinstance(used_stages, list) or not all(
                isinstance(value, str) and value for value in used_stages
            ):
                raise SteamZeroError("E-API-SCHEMA", detail="usedStages deve ser lista de IDs")
            session = self._control_server.journey_studio.snapshot(session_id)
            document = session["document"]
            theme_ids = {"org.steamzero.default"}
            for menu in document.get("menus", []):
                appearance = menu.get("appearance", {})
                if appearance.get("mode") == "custom" and isinstance(
                    appearance.get("themeId"), str
                ):
                    theme_ids.add(appearance["themeId"])
            for stage in document.get("sessionStages", []):
                appearance = stage.get("appearance", {})
                if appearance.get("mode") == "custom" and isinstance(
                    appearance.get("themeId"), str
                ):
                    theme_ids.add(appearance["themeId"])
            themes: dict[str, dict[str, Any]] = {}
            versions: dict[str, str] = {}
            dashboard = self._dashboard()
            with self._control_server._journey_theme_lock:
                for entry in dashboard.theme_list():
                    if isinstance(entry, Mapping) and isinstance(entry.get("id"), str):
                        versions[str(entry["id"])] = str(entry.get("version") or "unknown")
                for theme_id in sorted(theme_ids):
                    session_id_for_theme = ""
                    try:
                        loaded = dashboard.editor_load(theme_id)
                        session_id_for_theme = str(loaded.get("sessionId") or "")
                        candidate = loaded.get("manifest")
                        if isinstance(candidate, Mapping):
                            themes[theme_id] = _effective_theme_coverage_manifest(loaded)
                    except (SteamZeroError, OSError, ValueError):
                        pass
                    finally:
                        if session_id_for_theme:
                            with contextlib.suppress(SteamZeroError, OSError, ValueError):
                                dashboard.editor_cancel(session_id_for_theme)
            aura_version = str(
                themes.get("org.steamzero.default", {}).get(
                    "version", versions.get("org.steamzero.default", "unknown")
                )
            )
            result = self._control_server.journey_studio.coverage(
                session_id,
                used_stages=used_stages,
                themes=themes,
                aura_version=aura_version,
                operation_requirements={
                    "gameplay": ["launch"],
                    "entryFade": ["launch"],
                    "pause": ["pause", "resume"],
                    "saves": ["saveState", "loadState"],
                    "bezel": ["bezel"],
                    "exitFade": ["exit"],
                },
            )
            result["operationalSource"] = {
                "state": "unknown",
                "detail": (
                    "A bridge desta sessão ainda não recebe as capabilities do adapter de jogo; "
                    "a aparência resolvida não habilita launch, pausa, saves, bezel ou saída."
                ),
            }
            return result
        if path == "/journey/studio/import":
            self._require_exact_keys(payload, {"source", "copyName"})
            source = Path(self._required_string(payload, "source"))
            if not source.is_absolute():
                raise SteamZeroError(
                    "E-CONTENT-UNSAFE-PATH", detail="origem do pacote precisa ser absoluta"
                )
            copy_name = self._required_string(payload, "copyName")
            if len(copy_name) > 128:
                raise SteamZeroError("E-API-SCHEMA", detail="nome da cópia excede 128 caracteres")
            imported = self._control_server.journey_studio.import_file(source, copy_name=copy_name)
            themes = {
                str(theme.get("id")): theme
                for theme in self._dashboard().theme_list()
                if isinstance(theme, Mapping) and isinstance(theme.get("id"), str)
            }
            dependencies = imported.get("dependencies", [])
            for dependency in dependencies:
                if not isinstance(dependency, dict):
                    continue
                theme = themes.get(str(dependency.get("themeId", "")))
                if theme is None:
                    dependency.update({"state": "missing", "installedVersion": None})
                else:
                    dependency.update(
                        {
                            "state": "available-unpinned",
                            "installedVersion": theme.get("version"),
                        }
                    )
            return imported
        if path == "/journey/studio/export/prepare":
            self._require_exact_keys(payload, {"sessionId", "destination"})
            destination = Path(self._required_string(payload, "destination"))
            if not destination.is_absolute():
                raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="destino precisa ser absoluto")
            if destination.suffix.casefold() != ".zip":
                raise SteamZeroError("E-API-SCHEMA", detail="destino precisa terminar em .zip")
            if not destination.parent.is_dir() or destination.is_symlink():
                raise SteamZeroError(
                    "E-CONTENT-UNSAFE-PATH", detail="destino de exportação inválido"
                )
            if destination.exists() and not destination.is_file():
                raise SteamZeroError(
                    "E-CONTENT-UNSAFE-PATH", detail="destino não é arquivo regular"
                )
            bundle = self._control_server.journey_studio.export_copy(
                self._required_string(payload, "sessionId")
            )
            plan = transaction.plan_write_files(
                {destination: bundle}, root=destination.parent, kind="journey.studio.export"
            )
            return {
                **plan.to_dict(),
                "filename": destination.name,
                "size": len(bundle),
                "packageContents": ["experience.json"],
                "dependenciesIncluded": False,
            }
        if path == "/journey/studio/export/apply":
            self._require_exact_keys(payload, {"planId", "confirmToken"})
            plan_id = self._required_string(payload, "planId")
            plan = transaction.load_plan(plan_id)
            if plan.kind != "journey.studio.export":
                raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não exporta uma jornada")
            apply_result = transaction.apply(
                plan_id, self._required_string(payload, "confirmToken")
            )
            return {"status": apply_result.status, "operationId": apply_result.operation_id}
        if path == "/journey/studio/undo":
            self._require_exact_keys(payload, {"sessionId"})
            return self._control_server.journey_studio.undo(
                self._required_string(payload, "sessionId")
            )
        if path == "/journey/studio/redo":
            self._require_exact_keys(payload, {"sessionId"})
            return self._control_server.journey_studio.redo(
                self._required_string(payload, "sessionId")
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

    def _refresh_journey_read_models(self) -> dict[str, dict[str, Any]]:
        dashboard_snapshot = self._dashboard().snapshot(self._control_server.coordinator.status())
        if not isinstance(dashboard_snapshot, Mapping):
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail="read model público da central indisponível"
            )
        self._control_server.publish_journey_read_models(dashboard_snapshot)
        models = self._control_server.journey_read_models()
        if models is None:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail="read model público da Jornada indisponível"
            )
        return models

    def _journey_sources(self) -> dict[str, dict[str, Any]]:
        models = self._control_server.journey_read_models()
        return models if models is not None else self._refresh_journey_read_models()

    def _journey_preview_query(
        self,
        session_id: str,
        menu_id: str,
        *,
        context_filters: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        models = self._journey_sources()
        session = self._control_server.journey_studio.snapshot(session_id)
        menu = next(
            (item for item in session["document"].get("menus", []) if item.get("id") == menu_id),
            None,
        )
        if menu is None:
            raise SteamZeroError("E-API-SCHEMA", detail=f"menu não existe: {menu_id}")
        source = menu.get("source")
        read_model_id = str(source.get("readModelId", "")) if isinstance(source, Mapping) else ""
        model = models.get(read_model_id)
        if model is None:
            raise SteamZeroError(
                "E-API-SCHEMA", detail=f"read model não publicado: {read_model_id}"
            )
        if model.get("state") == "budget-exceeded":
            total = int(model.get("totalRecordCount", 0))
            result = {
                "menuId": menu_id,
                "readModelId": read_model_id,
                "sourceState": "budget-exceeded",
                "resultState": "budget-exceeded",
                "rows": [],
                "totalCount": total,
                "resultCount": 0,
                "returnedCount": 0,
                "previewLimit": MAX_PREVIEW_ROWS,
                "truncated": False,
                "groups": [],
                "groupsTruncated": False,
                "unknownValueCounts": {},
                "recoveryAction": "choose-smaller-source",
                "diagnosticCode": "JOURNEY-BUDGET-RECORDS",
                "diagnosticMessage": (
                    f"A fonte publicou {total} registros; o limite atual é "
                    f"{MAX_PUBLIC_RECORDS}. Escolha uma fonte menor."
                ),
            }
            return result, session, menu, model
        fields = model.get("fields")
        if not isinstance(fields, Mapping):
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail="campos da fonte pública estão indisponíveis"
            )
        result = self._control_server.journey_studio.preview_menu(
            session_id,
            menu_id,
            rows=cast(list[dict[str, Any]] | None, model.get("rows")),
            published_fields=cast(dict[str, str], fields),
            published_read_models={
                key: value["fields"]
                for key, value in models.items()
                if isinstance(value.get("fields"), Mapping)
            },
            context_filters=context_filters,
        )
        result["sourceState"] = str(model.get("state") or "unavailable")
        return result, session, menu, model

    def _journey_catalog(self, models: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        read_models: list[dict[str, Any]] = []
        labels = {
            "library.games": "Jogos publicados",
            "library.platforms": "Plataformas publicadas",
        }
        for model_id in ("library.games", "library.platforms"):
            model = models.get(model_id, {})
            rows = model.get("rows")
            fields = model.get("fields", {})
            if not isinstance(fields, Mapping):
                fields = {}
            read_models.append(
                {
                    "id": model_id,
                    "name": labels[model_id],
                    "state": str(model.get("state") or "unavailable"),
                    "recordCount": (
                        len(rows)
                        if isinstance(rows, list)
                        else int(model.get("totalRecordCount", 0))
                    ),
                    "fields": _journey_field_descriptors(fields),
                }
            )
        themes: list[dict[str, Any]] = []
        for theme in self._dashboard().theme_list():
            theme_id = theme.get("id")
            if not isinstance(theme_id, str) or not theme_id:
                continue
            themes.append(
                {
                    "id": theme_id,
                    "name": str(theme.get("name") or theme_id),
                    "version": str(theme.get("version") or "unknown"),
                    "state": str(theme.get("state") or "unknown"),
                    "compatible": theme.get("compatible") is True,
                    "origin": str(theme.get("origin") or "unknown"),
                }
            )
        return {
            "schemaVersion": 1,
            "readModels": read_models,
            "themes": themes,
            "limits": {
                "maxRecords": MAX_PUBLIC_RECORDS,
                "previewRows": MAX_PREVIEW_ROWS,
                "maxStringCharacters": 4096,
                "maxArrayValues": 64,
            },
        }

    @staticmethod
    def _require_exact_keys(
        payload: Mapping[str, Any],
        required: set[str],
        *,
        optional: set[str] | frozenset[str] = frozenset(),
    ) -> None:
        keys = set(payload)
        allowed = required | set(optional)
        if not required <= keys or not keys <= allowed:
            missing = sorted(required - keys)
            extra = sorted(keys - allowed)
            detail = []
            if missing:
                detail.append("ausentes: " + ", ".join(missing))
            if extra:
                detail.append("não allowlisted: " + ", ".join(extra))
            raise SteamZeroError(
                "E-API-SCHEMA", detail="propriedades inválidas (" + "; ".join(detail) + ")"
            )

    def _validate_journey_operation(self, operation: str, payload: dict[str, Any]) -> None:
        fields = _JOURNEY_OPERATION_FIELDS.get(operation)
        if fields is None:
            raise SteamZeroError("E-API-SCHEMA", detail="operação de Jornada não allowlisted")
        required, optional = fields
        self._require_exact_keys(payload, set(required), optional=optional)
        string_fields = {
            "name",
            "menuId",
            "newId",
            "organizationId",
            "parentId",
            "replacementMenuId",
            "readModelId",
            "connectionId",
            "stageId",
        }
        for field_id in string_fields.intersection(payload):
            value = payload[field_id]
            if value is None and field_id in {"parentId", "replacementMenuId"}:
                continue
            if not isinstance(value, str) or not value:
                raise SteamZeroError("E-API-SCHEMA", detail=f"{field_id} precisa ser texto")
        if operation == "reorder-menus":
            values = payload.get("menuIds")
            if not isinstance(values, list) or not all(
                isinstance(value, str) and value for value in values
            ):
                raise SteamZeroError("E-API-SCHEMA", detail="menuIds deve ser lista de IDs")
        if operation in {"set-filters", "set-sort", "set-group-by"} and not isinstance(
            payload.get("values"), list
        ):
            raise SteamZeroError("E-API-SCHEMA", detail="values precisa ser uma lista")
        if operation in {"add-menu", "add-connection"} and not isinstance(
            payload.get("menu" if operation == "add-menu" else "connection"), Mapping
        ):
            raise SteamZeroError("E-API-SCHEMA", detail="objeto de edição inválido")
        if operation in {"set-menu-appearance", "set-stage-appearance"}:
            appearance = payload.get("appearance")
            if appearance is not None and not isinstance(appearance, Mapping):
                raise SteamZeroError("E-API-SCHEMA", detail="appearance precisa ser objeto ou null")

    def _issue_bios_source_handles(self) -> dict[str, list[dict[str, str]]]:
        """Publica capabilities efêmeras sem expor a identidade interna da origem."""
        payload = self._dashboard().bios_source_selector()
        raw_sources = payload.get("sources")
        if not isinstance(raw_sources, list):
            raise SteamZeroError("E-API-SCHEMA", detail="seletor de BIOS inválido")
        sources: list[dict[str, str]] = []
        handles: dict[str, str] = {}
        for item in raw_sources:
            if not isinstance(item, dict):
                raise SteamZeroError("E-API-SCHEMA", detail="origem de BIOS inválida")
            internal_id = item.get("sourceId")
            label = item.get("label")
            if not isinstance(internal_id, str) or not internal_id:
                raise SteamZeroError("E-API-SCHEMA", detail="identidade de origem inválida")
            if not isinstance(label, str) or not label:
                raise SteamZeroError("E-API-SCHEMA", detail="rótulo de origem inválido")
            handle = secrets.token_urlsafe(24)
            while handle in handles:
                handle = secrets.token_urlsafe(24)
            handles[handle] = internal_id
            sources.append({"sourceId": handle, "label": label})
        with self._control_server.bios_source_lock:
            self._control_server.bios_source_handles = handles
        return {"sources": sources}

    def _bios_source_handle(self, source_id: str) -> str:
        """Resolve um handle somente na sessão que o emitiu."""
        with self._control_server.bios_source_lock:
            internal_id = self._control_server.bios_source_handles.get(source_id)
        if internal_id is None:
            raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="origem de BIOS não aprovada")
        return internal_id

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

    def _bios_import_payload(self, payload: dict[str, Any]) -> tuple[str, list[str] | None]:
        if set(payload) - {"scanId", "selection"} or "scanId" not in payload:
            raise SteamZeroError(
                "E-API-SCHEMA", detail="propriedades de importação de BIOS inválidas"
            )
        scan_id = self._required_string(payload, "scanId")
        selection = payload.get("selection")
        if selection is None:
            return scan_id, None
        if not isinstance(selection, list) or not all(
            isinstance(item, str) and item for item in selection
        ):
            raise SteamZeroError(
                "E-API-SCHEMA", detail="selection de BIOS precisa ser lista de strings"
            )
        if len(selection) != len(set(selection)):
            raise SteamZeroError("E-API-SCHEMA", detail="selection de BIOS contém duplicatas")
        return scan_id, selection

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
            capability_arguments = (
                ["--steamzero-qtquick-effects"] if _qml_supports_quick_effects(executable) else []
            )
            process = subprocess.Popen(  # noqa: S603
                [
                    executable,
                    str(qml_path),
                    "--",
                    "--steamzero-api",
                    f"http://127.0.0.1:{server.server_port}",
                    "--steamzero-token",
                    token,
                    *capability_arguments,
                ],
                stdin=subprocess.DEVNULL,
                env={
                    **os.environ,
                    "QT_QUICK_BACKEND": _QT_QUICK_BACKEND,
                    "STEAMZERO_CLASS": "ui",
                },
            )
            while process.poll() is None:
                server.handle_request()
            return int(process.returncode or 0)
    finally:
        server.server_close()
