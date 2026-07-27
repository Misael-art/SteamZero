# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Ponto de entrada da CLI `steamzero` (CLI-CONTRACT).

Dispatch por **allowlist** de (domínio, ação) -> handler; nunca por nome vindo
de dados (P4/SR-19). ``--json`` emite o envelope v2 em stdout puro (avisos em
stderr). Exit codes estáveis (CLI-CONTRACT §Convenções).
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from steamzero import CONTRACT_VERSION, __version__
from steamzero.api.envelope import build_envelope, status_from_checks
from steamzero.core import ids, log
from steamzero.core.errors import SteamZeroError, build_error
from steamzero.core.state import StateStore
from steamzero.diagnostics.doctor import run_doctor
from steamzero.domain.desktop import ExperienceCoordinator
from steamzero.domain.emulation_workspace import build_switch_workspace

if TYPE_CHECKING:
    from steamzero.adapters.flatpak import FlatpakExecutor
    from steamzero.adapters.registry import AdapterRegistry
    from steamzero.adapters.steam_launcher import SteamGameLauncher
    from steamzero.domain.input_profiles import InputProfileManager
    from steamzero.domain.playtime import PlaytimeCatalog

# Exit codes (CLI-CONTRACT).
EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_BLOCKED = 4

Handler = Callable[[list[str], str], tuple[dict[str, Any], int]]

_USAGE = f"""steamzero <domínio> <ação> [flags]

Domínios (Fase 1):
  doctor                 diagnóstico do núcleo
  jobs list              lista jobs paginados (--limit N --cursor ID --state STATE)
  jobs list --follow     segue eventos em NDJSON (--job-id ID --cursor SEQ)
  operations list        lista operações paginadas (--limit N --cursor ID)
  operations list --follow segue eventos em NDJSON (--operation-id ID --cursor SEQ)
  operations show        detalha uma operação (--operation-id ID)
  operations rollback-plan revisa rollback contextual (--operation-id ID)
  operations rollback-apply aplica rollback confirmado (--plan-id ID --confirm TOKEN)
  events page            lê eventos paginados (--cursor SEQ --limit N)
  state export [--out F] exporta o State Store (JSON)
  component list         lista adapters e deployments Flatpak
  component status      mostra um deployment (--id ADAPTER)
  component plan        planeja install/update pinado (--id ADAPTER)
  component apply       aplica plano (--plan-id ID --confirm TOKEN)
  component rollback    restaura deployment anterior (--operation-id ID)
  component recover     recupera operações Flatpak interrompidas
  admin health          verifica helper e autorização Polkit (read-only)
  session environment    observa sessão, energia, rede, DRM e volumes (read-only)
  session status         mostra lifecycle persistido (--game-id APPID)
  session recover        reconhece sessão interrompida (--game-id APPID)
  playtime list          lista recentes e playtime (--limit N --cursor CURSOR)
  playtime show          mostra um jogo e a última sessão (--game-id ID)
  collections list       lista tags, favoritos e coleções inteligentes
  collections plan       revisa mutação (--action-json JSON)
  collections apply      aplica plano (--plan-id ID --confirm TOKEN)
  health status          mostra saúde e amostragem anti-bitrot da coleção
  health plan            revisa re-hash limitado
  health apply           executa re-hash confirmado (--plan-id ID --confirm TOKEN)
  desktop status         contexto e perfil Desktop efetivo
  desktop plan           planeja perfil auto|handheld|dock|safe
  desktop apply          aplica plano confirmado
  desktop reset          aplica apenas um plano safe confirmado
  desktop recover        restaura snapshot de operação interrompida
  desktop keyboard       abre o primeiro teclado virtual funcional
  desktop ui             abre a central Qt/QML opcional
  emulation workspace    read model da central de emulação Switch
  emulation launch       abre um jogo escaneado (--game-id ID)
  cloud list             lista serviços declarados e estado local
  cloud launch           abre URL allowlisted (--platform ID)
  cloud plan             revisa publicação dos atalhos Steam
  cloud apply            aplica publicação (--plan-id ID --confirm TOKEN)
  hud presets            lista presets e evidência automatizada 1280x800
  controls profiles      lista perfis e seleção ativa (--platform ID)
  controls plan          revisa seleção de perfil (--platform ID --profile ID)
  controls apply         aplica plano confirmado (--plan-id ID --confirm TOKEN)
  controls rollback      desfaz seleção (--operation-id ID)
  theme list             lista temas disponíveis (builtin + usuário)
  theme search           busca temas no marketplace remoto [--query Q] [--refresh]
  theme info             mostra detalhes de um tema do marketplace (--theme-id ID)
  theme install          instala tema de URL, caminho local ou ID do marketplace
  theme status           mostra tema ativo e tokens resolvidos
  theme plan             planeja ativação de tema (--theme-id ID)
  theme apply            aplica plano de tema (--plan-id ID --confirm TOKEN)
  theme rollback         reverte ativação de tema (--operation-id ID)

Flags globais:
  --json                 emite envelope v2 (stdout puro)
  --contract-version     imprime a versão do contrato ({CONTRACT_VERSION})
  --version              imprime a versão
  -h, --help             esta ajuda
"""


def _cmd_doctor(_args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    data, checks = run_doctor()
    status = status_from_checks(checks)
    env = build_envelope(
        "doctor", "run", status=status, data=data, checks=checks, correlation_id=correlation_id
    )
    return env, EXIT_OK if status != "failed" else EXIT_FAILURE


def _cmd_jobs_list(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    limit = _page_limit(args)
    cursor = _page_cursor(args)
    state = _flag_value(args, "--state")
    with StateStore() as store:
        store.migrate()
        rows, has_more = store.list_jobs_page(
            limit=limit,
            before_id=cursor,
            states=[state] if state is not None else None,
        )
        jobs = [
            {
                "id": row["id"],
                "type": row["type"],
                "state": row["state"],
                "priority": row["priority"],
                "progress": _decoded_json(row.get("progress_json")),
                "operationId": row.get("operation_id"),
                "correlationId": row.get("correlation_id"),
                "errorCode": row.get("error_code"),
                "createdAt": row.get("created_at"),
                "updatedAt": row.get("updated_at"),
            }
            for row in rows
        ]
    env = build_envelope(
        "jobs",
        "list",
        status="ok" if jobs else "noop",
        data={
            "jobs": jobs,
            "count": len(jobs),
            "page": {
                "limit": limit,
                "hasMore": has_more,
                "nextCursor": jobs[-1]["id"] if has_more and jobs else None,
            },
        },
        correlation_id=correlation_id,
    )
    return env, EXIT_OK


def _cmd_operations_list(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    from steamzero.domain.operation_history import OperationHistory

    limit = _page_limit(args)
    cursor = _page_cursor(args)
    history = OperationHistory(component_rollback=_component_rollback_for_history)
    payload = history.list(limit=limit, cursor=cursor)
    operations = [
        {
            **row,
            "id": row["operationId"],
        }
        for row in payload["items"]
    ]
    return (
        build_envelope(
            "operations",
            "list",
            status="ok" if operations else "noop",
            data={
                "operations": operations,
                "count": len(operations),
                "page": {
                    "limit": limit,
                    "hasMore": payload["page"]["hasMore"],
                    "nextCursor": payload["page"]["nextCursor"],
                },
                "schemaVersion": payload["schemaVersion"],
                "generatedAt": payload["generatedAt"],
            },
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _component_rollback_for_history(operation_id: str) -> Any:
    with StateStore() as store:
        store.migrate()
        _registry, executor = _component_runtime(store)
        return executor.rollback(operation_id)


def _operation_history() -> Any:
    from steamzero.domain.operation_history import OperationHistory

    return OperationHistory(component_rollback=_component_rollback_for_history)


def _cmd_operations_show(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    operation_id = _required_flag(args, "--operation-id")
    data = _operation_history().get(operation_id)
    return (
        build_envelope(
            "operations",
            "show",
            status="ok",
            data=data,
            operation_id=operation_id,
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _cmd_operations_rollback_plan(
    args: list[str], correlation_id: str
) -> tuple[dict[str, Any], int]:
    operation_id = _required_flag(args, "--operation-id")
    data = _operation_history().plan_rollback(operation_id)
    return (
        build_envelope(
            "operations",
            "rollback-plan",
            status="ok",
            data=data,
            operation_id=operation_id,
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _cmd_operations_rollback_apply(
    args: list[str], correlation_id: str
) -> tuple[dict[str, Any], int]:
    plan_id = _required_flag(args, "--plan-id")
    confirm_token = _required_flag(args, "--confirm")
    data = _operation_history().apply_rollback(plan_id, confirm_token)
    operation_id = str(data["result"]["operationId"])
    return (
        build_envelope(
            "operations",
            "rollback-apply",
            status="rolled-back",
            data=data,
            operation_id=operation_id,
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _collection_manager() -> Any:
    from steamzero.domain.collections import CollectionManager

    return CollectionManager()


def _cmd_collections_list(_args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    data = _collection_manager().state()
    return (
        build_envelope(
            "collections", "list", status="ok", data=data, correlation_id=correlation_id
        ),
        EXIT_OK,
    )


def _cmd_collections_plan(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    raw = _required_flag(args, "--action-json")
    if len(raw) > 16384:
        raise SteamZeroError("E-CONTENT-LIMIT", detail="ação excede 16 KiB")
    try:
        action = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SteamZeroError("E-API-SCHEMA", detail="actionJson inválido") from exc
    if not isinstance(action, dict):
        raise SteamZeroError("E-API-SCHEMA", detail="actionJson precisa ser objeto")
    data = _collection_manager().plan(action)
    return (
        build_envelope(
            "collections", "plan", status="ok", data=data, correlation_id=correlation_id
        ),
        EXIT_OK,
    )


def _cmd_collections_apply(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    plan_id = _required_flag(args, "--plan-id")
    confirm_token = _required_flag(args, "--confirm")
    data = _collection_manager().apply(plan_id, confirm_token)
    return (
        build_envelope(
            "collections",
            "apply",
            status=str(data["status"]),
            data=data,
            operation_id=str(data["operationId"]),
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _bitrot_controller() -> Any:
    from steamzero.adapters.emulation import EmulationController

    return EmulationController()


def _cmd_health_status(_args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    controller = _bitrot_controller()
    try:
        data = controller.library_health()
    finally:
        controller.close()
    return (
        build_envelope(
            "health", "status", status=str(data["state"]), data=data, correlation_id=correlation_id
        ),
        EXIT_OK,
    )


def _cmd_health_plan(_args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    controller = _bitrot_controller()
    try:
        data = controller.plan_library_health()
    finally:
        controller.close()
    return (
        build_envelope("health", "plan", status="ok", data=data, correlation_id=correlation_id),
        EXIT_OK,
    )


def _cmd_health_apply(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    plan_id = _required_flag(args, "--plan-id")
    confirm_token = _required_flag(args, "--confirm")
    controller = _bitrot_controller()
    try:
        data = controller.apply_action(plan_id, confirm_token)
    finally:
        controller.close()
    return (
        build_envelope(
            "health",
            "apply",
            status=str(data["status"]),
            data=data,
            operation_id=str(data["operationId"]),
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _cmd_events_page(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    from steamzero.api.events import PUBLIC_EVENT_KINDS, event_page

    cursor = _flag_value(args, "--cursor")
    kind = _flag_value(args, "--kind")
    entity = _flag_value(args, "--entity")
    if kind is not None and kind not in PUBLIC_EVENT_KINDS:
        raise SteamZeroError("E-API-SCHEMA", detail=f"kind de evento não público: {kind}")
    with StateStore() as store:
        store.migrate()
        try:
            page = event_page(
                store,
                cursor=cursor,
                limit=_page_limit(args),
                kinds=(kind,) if kind is not None else (),
                entities=(entity,) if entity is not None else (),
            )
        except ValueError as exc:
            raise SteamZeroError("E-API-SCHEMA", detail=str(exc)) from exc
    data = page.to_dict()
    return (
        build_envelope(
            "events",
            "page",
            status="ok" if data["events"] else "noop",
            data=data,
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _cmd_state_export(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    out_path = _flag_value(args, "--out")
    with StateStore() as store:
        store.migrate()
        export = store.export_json()
    if out_path is not None:
        from pathlib import Path

        from steamzero.core import fs

        fs.write_atomic_text(Path(out_path), json.dumps(export, ensure_ascii=False, indent=2))
        data: dict[str, Any] = {"written": out_path, "schemaVersion": export["schemaVersion"]}
    else:
        data = export
    env = build_envelope("state", "export", status="ok", data=data, correlation_id=correlation_id)
    return env, EXIT_OK


def _component_runtime(store: StateStore) -> tuple[AdapterRegistry, FlatpakExecutor]:
    # Imports locais mantêm doctor/state utilizáveis mesmo sem o binário Flatpak.
    from steamzero.adapters.flatpak import FlatpakCLI, FlatpakExecutor
    from steamzero.adapters.registry import AdapterRegistry

    registry = AdapterRegistry.bundled()
    return registry, FlatpakExecutor(store, registry, FlatpakCLI())


def _cmd_component_list(_args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    with StateStore() as store:
        store.migrate()
        registry, executor = _component_runtime(store)
        components = [executor.status(manifest.id) for manifest in registry.list()]
    status = "degraded" if any(item["state"] == "degraded" for item in components) else "ok"
    return (
        build_envelope(
            "component",
            "list",
            status=status,
            data={"components": components, "count": len(components)},
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _cmd_component_status(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    adapter_id = _required_flag(args, "--id")
    with StateStore() as store:
        store.migrate()
        _registry, executor = _component_runtime(store)
        data = executor.status(adapter_id)
    status = "degraded" if data["state"] == "degraded" else "ok"
    return (
        build_envelope(
            "component", "status", status=status, data=data, correlation_id=correlation_id
        ),
        EXIT_OK,
    )


def _cmd_component_plan(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    adapter_id = _required_flag(args, "--id")
    with StateStore() as store:
        store.migrate()
        _registry, executor = _component_runtime(store)
        plan = executor.plan_install(adapter_id)
    return (
        build_envelope(
            "component",
            "plan",
            status="noop" if plan.action == "noop" else "ok",
            data={"plan": plan.to_dict()},
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _cmd_component_apply(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    plan_id = _required_flag(args, "--plan-id")
    confirm_token = _required_flag(args, "--confirm")
    with StateStore() as store:
        store.migrate()
        _registry, executor = _component_runtime(store)
        result = executor.apply(plan_id, confirm_token)
    return (
        build_envelope(
            "component",
            "apply",
            status=result.status,
            data=result.to_dict(),
            operation_id=result.operation_id or None,
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _cmd_component_rollback(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    operation_id = _required_flag(args, "--operation-id")
    with StateStore() as store:
        store.migrate()
        _registry, executor = _component_runtime(store)
        result = executor.rollback(operation_id)
    return (
        build_envelope(
            "component",
            "rollback",
            status=result.status,
            data=result.to_dict(),
            operation_id=result.operation_id,
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _cmd_component_recover(_args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    with StateStore() as store:
        store.migrate()
        _registry, executor = _component_runtime(store)
        recovered = executor.recover()
    data = {"operations": [result.to_dict() for result in recovered], "count": len(recovered)}
    return (
        build_envelope(
            "component",
            "recover",
            status="ok" if recovered else "noop",
            data=data,
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _admin_client() -> Any:
    from steamzero.privileged.client import AdminClient

    return AdminClient.host()


def _cmd_admin_health(_args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    client = _admin_client()
    if not client.available():
        raise SteamZeroError(
            "E-PRIV-HELPER-MISSING",
            detail="steamzero-admin ou pkexec não está instalado no host",
        )
    response = client.request("health", {})
    if response.ok:
        return (
            build_envelope(
                "admin",
                "health",
                status="ok",
                data=response.result,
                correlation_id=correlation_id,
            ),
            EXIT_OK,
        )
    return (
        build_envelope(
            "admin",
            "health",
            status="failed",
            ok=False,
            error=response.error,
            correlation_id=correlation_id,
        ),
        EXIT_FAILURE,
    )


def _desktop_coordinator() -> ExperienceCoordinator:
    # Import local mantém a CLI mínima e permite substituir a composição nos testes.
    from steamzero.adapters.desktop_kde import build_desktop_coordinator

    store = StateStore()
    store.migrate()
    return build_desktop_coordinator(store)


def _session_launcher() -> SteamGameLauncher:
    from steamzero.adapters.steam_launcher import SteamGameLauncher

    return SteamGameLauncher()


def _session_environment() -> dict[str, Any]:
    from steamzero.runtime import observe_session_environment

    return observe_session_environment()


def _cmd_session_environment(_args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    data = _session_environment()
    session = data.get("session")
    session_type = session.get("type") if isinstance(session, dict) else "unknown"
    status = "degraded" if session_type in {None, "", "unknown"} else "ok"
    return (
        build_envelope(
            "session",
            "environment",
            status=status,
            data=data,
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _cmd_session_status(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    app_id = _required_flag(args, "--game-id")
    data = _session_launcher().status(app_id)
    recovery = bool(data.get("recoveryRequired"))
    degraded = data.get("state") in {"stale", "degraded"}
    blockers = (
        [
            {
                "code": "E-SESSION-INTERRUPTED",
                "message": "A sessão anterior precisa ser recuperada antes de outro launch.",
            }
        ]
        if recovery
        else []
    )
    return (
        build_envelope(
            "session",
            "status",
            status="blocked" if recovery else "degraded" if degraded else "ok",
            data=data,
            blockers=blockers,
            correlation_id=correlation_id,
        ),
        EXIT_BLOCKED if recovery else EXIT_OK,
    )


def _cmd_session_recover(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    app_id = _required_flag(args, "--game-id")
    data = _session_launcher().recover(app_id)
    return (
        build_envelope(
            "session",
            "recover",
            status="ok" if data["status"] == "recovered" else "noop",
            data=data,
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _playtime_catalog() -> PlaytimeCatalog:
    from steamzero.domain.playtime import PlaytimeCatalog

    return PlaytimeCatalog()


def _validate_playtime_args(args: list[str], allowed: frozenset[str]) -> None:
    if len(args) % 2:
        raise SteamZeroError("E-API-SCHEMA", detail="flag de playtime sem valor")
    seen: set[str] = set()
    for index in range(0, len(args), 2):
        flag, value = args[index : index + 2]
        if flag not in allowed:
            raise SteamZeroError("E-API-SCHEMA", detail=f"flag de playtime não permitida: {flag}")
        if flag in seen:
            raise SteamZeroError("E-API-SCHEMA", detail=f"flag duplicada: {flag}")
        if not value or value.startswith("-") or "\x00" in value or len(value) > 4096:
            raise SteamZeroError("E-API-SCHEMA", detail=f"valor inválido para {flag}")
        seen.add(flag)


def _cmd_playtime_list(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    _validate_playtime_args(args, frozenset({"--limit", "--cursor"}))
    data = _playtime_catalog().list(limit=_page_limit(args), cursor=_page_cursor(args))
    return (
        build_envelope(
            "playtime",
            "list",
            status="ok" if data["games"] else "noop",
            data=data,
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _cmd_playtime_show(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    _validate_playtime_args(args, frozenset({"--game-id"}))
    data = _playtime_catalog().get(_required_flag(args, "--game-id"))
    return (
        build_envelope(
            "playtime",
            "show",
            status="ok",
            data=data,
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _desktop_blockers(messages: list[str] | tuple[str, ...]) -> list[dict[str, str]]:
    return [
        {
            "code": (
                "E-TX-STALE-PLAN"
                if message.startswith("contexto automático")
                else "E-DESKTOP-OWNER-CONFLICT"
            ),
            "message": message,
        }
        for message in messages
    ]


def _cmd_desktop_status(_args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    with _desktop_coordinator() as coordinator:
        data = coordinator.status()
    conflicts = data["context"].get("conflicts", [])
    capabilities = data["context"].get("capabilities", [])
    if conflicts:
        status = "blocked"
        code = EXIT_BLOCKED
    elif not capabilities:
        status = "degraded"
        code = EXIT_OK
    else:
        status = "ok"
        code = EXIT_OK
    return (
        build_envelope(
            "desktop",
            "status",
            status=status,
            data=data,
            blockers=_desktop_blockers(conflicts),
            correlation_id=correlation_id,
        ),
        code,
    )


def _cmd_desktop_plan(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    requested = _flag_value(args, "--profile") or "auto"
    with _desktop_coordinator() as coordinator:
        plan = coordinator.plan(requested)
    status = "blocked" if plan.blockers else "ok"
    return (
        build_envelope(
            "desktop",
            "plan",
            status=status,
            data={"plan": plan.to_dict()},
            blockers=_desktop_blockers(plan.blockers),
            correlation_id=correlation_id,
        ),
        EXIT_BLOCKED if plan.blockers else EXIT_OK,
    )


def _required_flag(args: list[str], flag: str) -> str:
    value = _flag_value(args, flag)
    if not value:
        raise SteamZeroError("E-API-SCHEMA", detail=f"flag obrigatória ausente: {flag}")
    return value


def _cmd_desktop_apply(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    plan_id = _required_flag(args, "--plan-id")
    confirm = _required_flag(args, "--confirm")
    with _desktop_coordinator() as coordinator:
        result = coordinator.apply(plan_id, confirm)
    return (
        build_envelope(
            "desktop",
            "apply",
            status=result.status,
            data=result.to_dict(),
            operation_id=result.operation_id,
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _cmd_desktop_reset(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    plan_id = _required_flag(args, "--plan-id")
    confirm = _required_flag(args, "--confirm")
    with _desktop_coordinator() as coordinator:
        result = coordinator.reset(plan_id, confirm)
    return (
        build_envelope(
            "desktop",
            "reset",
            status=result.status,
            data=result.to_dict(),
            operation_id=result.operation_id,
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _cmd_desktop_recover(_args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    with _desktop_coordinator() as coordinator:
        data = coordinator.recover()
    return (
        build_envelope(
            "desktop",
            "recover",
            status=data["status"],
            data=data,
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _cmd_desktop_ui(_args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    from steamzero.adapters.desktop_ui import launch_desktop_ui

    with _desktop_coordinator() as coordinator:
        returncode = launch_desktop_ui(coordinator)
    state = "ok" if returncode == 0 else "failed"
    return (
        build_envelope(
            "desktop",
            "ui",
            status=state,
            data={"returnCode": returncode},
            correlation_id=correlation_id,
        ),
        EXIT_OK if returncode == 0 else EXIT_FAILURE,
    )


def _cmd_emulation_workspace(_args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    import shutil

    workspace = build_switch_workspace(
        probe=lambda emulator_id: shutil.which(emulator_id) is not None,
    )
    return (
        build_envelope(
            "emulation",
            "workspace",
            status=workspace["truthState"],
            data=workspace,
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _cmd_emulation_launch(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    from steamzero.adapters.emulation import EmulationController

    game_id = _flag_value(args, "--game-id")
    if game_id is None:
        raise SteamZeroError("E-API-SCHEMA", detail="use --game-id <id>")
    controller = EmulationController()
    try:
        data = controller.launch_game(game_id)
    finally:
        close = getattr(controller, "close", None)
        if callable(close):
            close()
    return (
        build_envelope(
            "emulation",
            "launch",
            status="ok",
            data=data,
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _cmd_cloud_list(_args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    from steamzero.adapters.emulation import EmulationController

    controller = EmulationController()
    try:
        data = {"platforms": controller.cloud_platforms()}
    finally:
        controller.close()
    return (
        build_envelope("cloud", "list", status="ok", data=data, correlation_id=correlation_id),
        EXIT_OK,
    )


def _cmd_cloud_launch(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    from steamzero.adapters.emulation import EmulationController

    platform_id = _flag_value(args, "--platform")
    if platform_id is None:
        raise SteamZeroError("E-API-SCHEMA", detail="use --platform <id>")
    controller = EmulationController()
    try:
        data = controller.launch_cloud(platform_id)
    finally:
        controller.close()
    return (
        build_envelope("cloud", "launch", status="ok", data=data, correlation_id=correlation_id),
        EXIT_OK,
    )


def _cmd_cloud_plan(_args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    from steamzero.adapters.emulation import EmulationController

    controller = EmulationController()
    try:
        data = controller.plan_action({"actionId": "cloud.shortcuts.sync"})
    finally:
        controller.close()
    return (
        build_envelope("cloud", "plan", status="ok", data=data, correlation_id=correlation_id),
        EXIT_OK,
    )


def _cmd_cloud_apply(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    from steamzero.adapters.emulation import EmulationController

    plan_id = _flag_value(args, "--plan-id")
    confirm_token = _flag_value(args, "--confirm")
    if plan_id is None or confirm_token is None:
        raise SteamZeroError("E-API-SCHEMA", detail="use --plan-id <id> --confirm <token>")
    controller = EmulationController()
    try:
        data = controller.apply_action(plan_id, confirm_token)
    finally:
        controller.close()
    return (
        build_envelope(
            "cloud", "apply", status=str(data["status"]), data=data, correlation_id=correlation_id
        ),
        EXIT_OK,
    )


def _cmd_hud_presets(_args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    import shutil

    from steamzero.domain.hud import hud_catalog

    data = hud_catalog(mangohud_available=shutil.which("mangohud") is not None)
    return (
        build_envelope("hud", "presets", status="ok", data=data, correlation_id=correlation_id),
        EXIT_OK,
    )


def _input_profiles_manager() -> InputProfileManager:
    from steamzero.core import paths
    from steamzero.domain.input_profiles import InputProfileManager

    return InputProfileManager(paths.config_home() / "input-profiles")


def _validate_controls_args(args: list[str], allowed: frozenset[str]) -> None:
    if len(args) % 2:
        raise SteamZeroError("E-API-SCHEMA", detail="flag de controls sem valor")
    seen: set[str] = set()
    for index in range(0, len(args), 2):
        flag, value = args[index : index + 2]
        if flag not in allowed:
            raise SteamZeroError("E-API-SCHEMA", detail=f"flag de controls não permitida: {flag}")
        if flag in seen:
            raise SteamZeroError("E-API-SCHEMA", detail=f"flag duplicada: {flag}")
        if not value or value.startswith("-") or "\x00" in value or len(value) > 4096:
            raise SteamZeroError("E-API-SCHEMA", detail=f"valor inválido para {flag}")
        seen.add(flag)


def _cmd_controls_profiles(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    _validate_controls_args(args, frozenset({"--platform"}))
    platform_id = _flag_value(args, "--platform")
    if platform_id is None:
        raise SteamZeroError("E-API-SCHEMA", detail="use --platform <id>")
    manager = _input_profiles_manager()
    data = manager.status(platform_id)
    return (
        build_envelope(
            "controls",
            "profiles",
            status=data["state"],
            data=data,
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _cmd_controls_plan(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    _validate_controls_args(
        args,
        frozenset({"--platform", "--profile", "--scope", "--scope-id", "--orientation"}),
    )
    platform_id = _flag_value(args, "--platform")
    profile_id = _flag_value(args, "--profile")
    if platform_id is None or profile_id is None:
        raise SteamZeroError("E-API-SCHEMA", detail="use --platform <id> --profile <id>")
    manager = _input_profiles_manager()
    plan = manager.plan_activate(
        platform_id=platform_id,
        profile_id=profile_id,
        scope=_flag_value(args, "--scope") or "platform",
        scope_id=_flag_value(args, "--scope-id"),
        orientation=_flag_value(args, "--orientation"),
    )
    data = {
        "planId": plan.plan_id,
        "confirmToken": plan.confirm_token,
        "preview": plan.preview,
        "rollbackGuarantee": plan.rollback_guarantee,
        "requirements": plan.requirements,
        "platformId": platform_id,
        "profileId": profile_id,
    }
    return (
        build_envelope(
            "controls", "plan", status="ready", data=data, correlation_id=correlation_id
        ),
        EXIT_OK,
    )


def _cmd_controls_apply(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    _validate_controls_args(args, frozenset({"--plan-id", "--confirm"}))
    plan_id = _flag_value(args, "--plan-id")
    confirm = _flag_value(args, "--confirm")
    if plan_id is None or confirm is None:
        raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="use --plan-id <id> --confirm <token>")
    result = _input_profiles_manager().apply(plan_id, confirm)
    data = {
        "status": result.status,
        "operationId": result.operation_id,
        "actions": result.actions,
    }
    return (
        build_envelope("controls", "apply", status="ok", data=data, correlation_id=correlation_id),
        EXIT_OK,
    )


def _cmd_controls_rollback(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    _validate_controls_args(args, frozenset({"--operation-id"}))
    operation_id = _flag_value(args, "--operation-id")
    if operation_id is None:
        raise SteamZeroError("E-API-SCHEMA", detail="use --operation-id <id>")
    result = _input_profiles_manager().rollback(operation_id)
    data = {
        "status": result.status,
        "operationId": result.operation_id,
        "restored": result.restored,
    }
    return (
        build_envelope(
            "controls", "rollback", status=result.status, data=data, correlation_id=correlation_id
        ),
        EXIT_OK,
    )


def _cmd_desktop_keyboard(_args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    from steamzero.adapters.desktop_kde import activate_virtual_keyboard, toggle_virtual_keyboard

    toggle = "--toggle" in _args
    language = _flag_value(_args, "--language")
    if toggle:
        result = toggle_virtual_keyboard(language=language)
    else:
        result = {"provider": activate_virtual_keyboard(language=language)}
    return (
        build_envelope(
            "desktop",
            "keyboard",
            status="ok",
            data=result,
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _flag_value(args: list[str], flag: str) -> str | None:
    if flag in args:
        i = args.index(flag)
        if i + 1 < len(args):
            return args[i + 1]
    return None


def _page_limit(args: list[str]) -> int:
    value = _flag_value(args, "--limit")
    if value is None:
        return 64
    try:
        limit = int(value)
    except ValueError as exc:
        raise SteamZeroError("E-API-SCHEMA", detail="--limit precisa ser inteiro") from exc
    if not 1 <= limit <= 256:
        raise SteamZeroError("E-API-SCHEMA", detail="--limit precisa estar entre 1 e 256")
    return limit


def _page_cursor(args: list[str]) -> str | None:
    cursor = _flag_value(args, "--cursor")
    if cursor is not None and (len(cursor) > 128 or "\x00" in cursor):
        raise SteamZeroError("E-API-SCHEMA", detail="cursor inválido")
    return cursor


def _decoded_json(value: object) -> object:
    if not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _follow_timeout(args: list[str]) -> float | None:
    value = _flag_value(args, "--timeout")
    if value is None:
        return None
    try:
        timeout = float(value)
    except ValueError as exc:
        raise SteamZeroError("E-API-SCHEMA", detail="--timeout precisa ser número") from exc
    if not 0 <= timeout <= 86_400:
        raise SteamZeroError(
            "E-API-SCHEMA", detail="--timeout precisa estar entre 0 e 86400 segundos"
        )
    return timeout


def _run_follow(domain: str, args: list[str], *, json_out: bool) -> int:
    from steamzero.api import contracts
    from steamzero.api.events import (
        JOB_EVENT_KINDS,
        JOB_TERMINAL_STATES,
        OPERATION_EVENT_KINDS,
        OPERATION_TERMINAL_STATES,
        follow_events,
        parse_event_cursor,
    )

    cursor = _flag_value(args, "--cursor")
    try:
        parse_event_cursor(cursor)
    except ValueError as exc:
        raise SteamZeroError("E-API-SCHEMA", detail=str(exc)) from exc
    timeout = _follow_timeout(args)
    limit = _page_limit(args)
    kinds: tuple[str, ...]
    if domain == "jobs":
        target = _flag_value(args, "--job-id")
        kinds = JOB_EVENT_KINDS
        entities = (f"job:{target}",) if target is not None else ()
        terminal_states = JOB_TERMINAL_STATES if target is not None else frozenset()
    elif domain == "operations":
        target = _flag_value(args, "--operation-id")
        kinds = OPERATION_EVENT_KINDS
        entities = (f"operation:{target}",) if target is not None else ()
        terminal_states = OPERATION_TERMINAL_STATES if target is not None else frozenset()
    else:
        raise SteamZeroError("E-CLI-USAGE", detail="--follow não é suportado nesta ação")

    def emit_event(event: dict[str, Any]) -> None:
        contracts.validate(event, "event-v1.schema.json")
        if json_out:
            sys.stdout.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        else:
            target_id = event.get("jobId") or event.get("operationId") or "-"
            detail = event.get("state") or event.get("progress") or ""
            sys.stdout.write(
                f"{event['seq']} {event['kind']} {target_id} "
                f"{json.dumps(detail, ensure_ascii=False)}\n"
            )
        sys.stdout.flush()

    if os.environ.get("STEAMZERO_NO_DAEMON") != "1":
        from steamzero.service.client import (
            CoreProtocolError,
            CoreUnavailable,
            subscribe_events,
        )

        params: dict[str, Any] = {
            "kinds": list(kinds),
            "limit": limit,
            "idleTimeout": timeout,
            "stopOnTerminal": bool(terminal_states),
        }
        if cursor is not None:
            params["cursor"] = cursor
        if target is not None:
            params["jobIds" if domain == "jobs" else "operationIds"] = [target]
        try:
            for event in subscribe_events(params):
                emit_event(event)
            return EXIT_OK
        except CoreUnavailable:
            pass
        except CoreProtocolError as exc:
            raise SteamZeroError("E-API-CONTRACT", detail=str(exc)) from exc

    with StateStore() as store:
        store.migrate()
        if domain == "jobs" and target is not None and store.get_job(target) is None:
            raise SteamZeroError("E-API-SCHEMA", detail=f"job inexistente: {target}")
        if domain == "operations" and target is not None and store.get_operation(target) is None:
            raise SteamZeroError("E-API-SCHEMA", detail=f"operação inexistente: {target}")
        try:
            for event in follow_events(
                store,
                cursor=cursor,
                kinds=kinds,
                entities=entities,
                limit=limit,
                idle_timeout=timeout,
                terminal_states=terminal_states,
            ):
                emit_event(event)
        except KeyboardInterrupt:
            return EXIT_OK
    return EXIT_OK


def _theme_catalog_mgr() -> Any:
    from steamzero.adapters.theme_catalog import ThemeCatalog

    return ThemeCatalog()


def _theme_pref_mgr() -> Any:
    from steamzero.domain.theme_preferences import ThemePreferenceManager

    return ThemePreferenceManager()


def _cmd_theme_install(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    import urllib.parse
    from pathlib import Path

    from steamzero.adapters.theme_catalog import validate_theme_directory
    from steamzero.domain.theme_install import ThemeInstaller
    from steamzero.domain.theme_marketplace import ThemeMarketplace

    source = _flag_value(args, "--source")
    if source is None:
        positional = [a for a in args if not a.startswith("-")]
        source = positional[0] if positional else None
    if source is None:
        msg = "use theme install <url-ou-caminho> [--force] [--yes]"
        raise SteamZeroError("E-CLI-USAGE", detail=msg)
    force = "--force" in args
    yes = "--yes" in args
    parsed = urllib.parse.urlparse(source)
    is_url = parsed.scheme in ("http", "https")
    if is_url or Path(source).is_file():
        installer = ThemeInstaller(validate=validate_theme_directory)
        result = installer.install(source, force=force, yes=yes)
    else:
        marketplace = ThemeMarketplace()
        result = marketplace.install(
            source, force=force, yes=yes, validate=validate_theme_directory,
        )
    return (
        build_envelope(
            "theme", "install",
            status="ok",
            data=result,
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _cmd_theme_search(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    from steamzero.domain.theme_marketplace import ThemeMarketplace

    query = _flag_value(args, "--query") or ""
    refresh = "--refresh" in args
    marketplace = ThemeMarketplace()
    results = marketplace.search(query, refresh=refresh)
    data = {
        "query": query,
        "count": len(results),
        "results": [r.to_dict() for r in results],
    }
    return (
        build_envelope("theme", "search", status="ok", data=data, correlation_id=correlation_id),
        EXIT_OK,
    )


def _cmd_theme_info(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    from steamzero.domain.theme_marketplace import ThemeMarketplace

    theme_id = _required_flag(args, "--theme-id")
    marketplace = ThemeMarketplace()
    entry = marketplace.get(theme_id)
    return (
        build_envelope(
            "theme", "info", status="ok", data=entry.to_dict(),
            correlation_id=correlation_id,
        ),
        EXIT_OK,
    )


def _cmd_theme_list(_args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    data = _theme_catalog_mgr().list_catalog()
    return (
        build_envelope("theme", "list", status="ok",
                       data={"themes": data}, correlation_id=correlation_id),
        EXIT_OK,
    )


def _cmd_theme_status(_args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    pref = _theme_pref_mgr()._read_preference()
    active_id = str(pref.get("themeId")) if pref else "org.steamzero.default"
    try:
        resolved = _theme_catalog_mgr().resolve(active_id)
        tokens = resolved.to_dict()
    except Exception:
        tokens = None
    data = {
        "activeId": active_id,
        "activeVersion": str(pref.get("themeVersion", "")) if pref else "",
        "resolved": tokens,
    }
    return (
        build_envelope("theme", "status", status="ok", data=data, correlation_id=correlation_id),
        EXIT_OK,
    )


def _cmd_theme_plan(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    theme_id = _required_flag(args, "--theme-id")
    mgr = _theme_pref_mgr()
    previous = mgr._read_preference()
    version = "1.0.0"
    for entry in _theme_catalog_mgr().list_catalog():
        if entry["id"] == theme_id and entry["compatible"]:
            version = entry["version"]
            break
    else:
        raise SteamZeroError("E-THEME-NOT-FOUND", detail=f"tema {theme_id} não encontrado")
    plan = mgr.plan_activate(theme_id, version, previous=previous)
    data = {
        "planId": plan.plan_id,
        "confirmToken": plan.confirm_token,
        "kind": plan.kind,
        "preview": plan.preview,
        "rollbackGuarantee": plan.rollback_guarantee,
    }
    return (
        build_envelope("theme", "plan", status="ok", data=data, correlation_id=correlation_id),
        EXIT_OK,
    )


def _cmd_theme_apply(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    plan_id = _required_flag(args, "--plan-id")
    confirm_token = _required_flag(args, "--confirm")
    result = _theme_pref_mgr().apply(plan_id, confirm_token)
    data = {"status": result.status, "operationId": result.operation_id}
    return (
        build_envelope("theme", "apply", status=result.status,
                       data=data, correlation_id=correlation_id),
        EXIT_OK,
    )


def _cmd_theme_rollback(args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    operation_id = _required_flag(args, "--operation-id")
    result = _theme_pref_mgr().rollback(operation_id)
    data = {"status": result.status, "operationId": result.operation_id}
    return (
        build_envelope("theme", "rollback", status=result.status,
                       data=data, correlation_id=correlation_id),
        EXIT_OK,
    )


#: Allowlist de ações. Chave (domínio, ação|None).
HANDLERS: dict[tuple[str, str | None], Handler] = {
    ("doctor", None): _cmd_doctor,
    ("jobs", "list"): _cmd_jobs_list,
    ("operations", "list"): _cmd_operations_list,
    ("operations", "show"): _cmd_operations_show,
    ("operations", "rollback-plan"): _cmd_operations_rollback_plan,
    ("operations", "rollback-apply"): _cmd_operations_rollback_apply,
    ("collections", "list"): _cmd_collections_list,
    ("collections", "plan"): _cmd_collections_plan,
    ("collections", "apply"): _cmd_collections_apply,
    ("health", "status"): _cmd_health_status,
    ("health", "plan"): _cmd_health_plan,
    ("health", "apply"): _cmd_health_apply,
    ("events", "page"): _cmd_events_page,
    ("state", "export"): _cmd_state_export,
    ("component", "list"): _cmd_component_list,
    ("component", "status"): _cmd_component_status,
    ("component", "plan"): _cmd_component_plan,
    ("component", "apply"): _cmd_component_apply,
    ("component", "rollback"): _cmd_component_rollback,
    ("component", "recover"): _cmd_component_recover,
    ("admin", "health"): _cmd_admin_health,
    ("session", "environment"): _cmd_session_environment,
    ("session", "status"): _cmd_session_status,
    ("session", "recover"): _cmd_session_recover,
    ("playtime", "list"): _cmd_playtime_list,
    ("playtime", "show"): _cmd_playtime_show,
    ("desktop", "status"): _cmd_desktop_status,
    ("desktop", "plan"): _cmd_desktop_plan,
    ("desktop", "apply"): _cmd_desktop_apply,
    ("desktop", "reset"): _cmd_desktop_reset,
    ("desktop", "recover"): _cmd_desktop_recover,
    ("desktop", "keyboard"): _cmd_desktop_keyboard,
    ("desktop", "ui"): _cmd_desktop_ui,
    ("emulation", "workspace"): _cmd_emulation_workspace,
    ("emulation", "launch"): _cmd_emulation_launch,
    ("cloud", "list"): _cmd_cloud_list,
    ("cloud", "launch"): _cmd_cloud_launch,
    ("cloud", "plan"): _cmd_cloud_plan,
    ("cloud", "apply"): _cmd_cloud_apply,
    ("hud", "presets"): _cmd_hud_presets,
    ("controls", "profiles"): _cmd_controls_profiles,
    ("controls", "plan"): _cmd_controls_plan,
    ("controls", "apply"): _cmd_controls_apply,
    ("controls", "rollback"): _cmd_controls_rollback,
    ("theme", "install"): _cmd_theme_install,
    ("theme", "search"): _cmd_theme_search,
    ("theme", "info"): _cmd_theme_info,
    ("theme", "list"): _cmd_theme_list,
    ("theme", "status"): _cmd_theme_status,
    ("theme", "plan"): _cmd_theme_plan,
    ("theme", "apply"): _cmd_theme_apply,
    ("theme", "rollback"): _cmd_theme_rollback,
}


def _emit(env: dict[str, Any], *, json_out: bool) -> None:
    if json_out:
        # stdout PURO: só o envelope (CLI-CONTRACT).
        sys.stdout.write(json.dumps(env, ensure_ascii=False) + "\n")
        return
    _render_human(env)


def _render_human(env: dict[str, Any]) -> None:
    out = sys.stdout
    out.write(f"{env['module']} {env['action']}: {env['status']}\n")
    for check in env.get("checks", []):
        out.write(f"  [{check['status']}] {check['name']}: {check.get('message', '')}\n")
    if env.get("error"):
        err = env["error"]
        out.write(f"  erro {err['code']}: {err['title']}\n")
        if err.get("detail"):
            out.write(f"    {err['detail']}\n")
        out.write(f"    ação: {err.get('action', '')}\n")
    data = env.get("data") or {}
    if data and not env.get("checks"):
        out.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv:
        sys.stderr.write(_USAGE)
        return EXIT_USAGE
    if argv[0] in ("-h", "--help"):
        sys.stdout.write(_USAGE)
        return EXIT_OK
    if argv[0] == "--contract-version":
        sys.stdout.write(CONTRACT_VERSION + "\n")
        return EXIT_OK
    if argv[0] == "--version":
        sys.stdout.write(__version__ + "\n")
        return EXIT_OK

    json_out = "--json" in argv
    follow = "--follow" in argv
    tokens = [a for a in argv if a not in {"--json", "--follow"}]
    domain = tokens[0]
    action: str | None = tokens[1] if len(tokens) > 1 and not tokens[1].startswith("-") else None
    rest = tokens[2:] if action is not None else tokens[1:]

    correlation_id = ids.new_ulid()
    logger = log.get_logger(correlation_id=correlation_id)

    handler = HANDLERS.get((domain, action))
    if handler is None:
        logger.warning("cli.unknown-action", domain=domain, action=action)
        env = build_envelope(
            domain,
            action or "",
            status="failed",
            ok=False,
            error=build_error("E-CLI-USAGE", detail=f"ação desconhecida: {domain} {action or ''}"),
            correlation_id=correlation_id,
        )
        _emit(env, json_out=json_out)
        if not json_out:
            sys.stderr.write("\n" + _USAGE)
        return EXIT_USAGE

    if follow:
        if (domain, action) not in {("jobs", "list"), ("operations", "list")}:
            env = build_envelope(
                domain,
                action or "",
                status="failed",
                ok=False,
                error=build_error(
                    "E-CLI-USAGE",
                    detail="--follow é aceito somente em jobs list e operations list",
                ),
                correlation_id=correlation_id,
            )
            _emit(env, json_out=json_out)
            return EXIT_USAGE
        try:
            return _run_follow(domain, rest, json_out=json_out)
        except SteamZeroError as exc:
            env = build_envelope(
                domain,
                action or "",
                status="failed",
                ok=False,
                error=exc.to_error_object(),
                correlation_id=correlation_id,
            )
            _emit(env, json_out=json_out)
            return EXIT_FAILURE

    daemon_result = _try_daemon(domain, action, rest, correlation_id)
    if daemon_result is not None:
        env, code = daemon_result
        _emit(env, json_out=json_out)
        return code

    try:
        env, code = handler(rest, correlation_id)
    except SteamZeroError as exc:
        logger.warning("cli.domain-error", domain=domain, action=action, code=exc.code)
        blocked = exc.code in {
            "E-TX-CONFIRM-REQUIRED",
            "E-TX-LOCKED",
            "E-DESKTOP-OWNER-CONFLICT",
        }
        env = build_envelope(
            domain,
            action or "",
            status="blocked" if blocked else "failed",
            ok=False,
            error=exc.to_error_object(),
            correlation_id=correlation_id,
        )
        _emit(env, json_out=json_out)
        return EXIT_BLOCKED if blocked else EXIT_FAILURE
    except Exception as exc:  # nunca vazar stack para o usuário (P7)
        logger.error("cli.handler-error", domain=domain, action=action, error=str(exc))
        env = build_envelope(
            domain,
            action or "",
            status="failed",
            ok=False,
            error=build_error("E-INTERNAL-UNEXPECTED", detail=str(exc)),
            correlation_id=correlation_id,
        )
        _emit(env, json_out=json_out)
        return EXIT_FAILURE

    _emit(env, json_out=json_out)
    return code


def _try_daemon(
    domain: str, action: str | None, args: list[str], correlation_id: str
) -> tuple[dict[str, Any], int] | None:
    """Usa o daemon quando disponível; falha ambígua nunca repete mutação localmente."""
    if os.environ.get("STEAMZERO_NO_DAEMON") == "1":
        return None
    from steamzero.service.client import CoreProtocolError, CoreUnavailable, invoke
    from steamzero.service.methods import CLI_METHODS, InvalidParams

    spec = CLI_METHODS.get((domain, action))
    if spec is None:
        return None
    try:
        params = spec.args_to_params(args, correlation_id)
    except InvalidParams:
        # A CLI local pode ter uma opção deliberadamente não exposta pelo daemon.
        return None
    try:
        invocation = invoke(spec.method, params)
    except CoreUnavailable:
        return None
    except CoreProtocolError as exc:
        return (
            build_envelope(
                domain,
                action or "",
                status="failed",
                ok=False,
                error=build_error("E-API-CONTRACT", detail=str(exc)),
                correlation_id=correlation_id,
            ),
            EXIT_FAILURE,
        )
    return invocation.envelope, invocation.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
