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
  desktop status         contexto e perfil Desktop efetivo
  desktop plan           planeja perfil auto|handheld|dock|safe
  desktop apply          aplica plano confirmado
  desktop reset          aplica apenas um plano safe confirmado
  desktop recover        restaura snapshot de operação interrompida
  desktop keyboard       abre o primeiro teclado virtual funcional
  desktop ui             abre a central Qt/QML opcional
  emulation workspace    read model da central de emulação Switch
  emulation launch       abre um jogo escaneado (--game-id ID)

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
    limit = _page_limit(args)
    cursor = _page_cursor(args)
    with StateStore() as store:
        store.migrate()
        rows, has_more = store.list_operations_page(limit=limit, before_id=cursor)
    operations = [
        {
            "id": row["id"],
            "state": row["state"],
        }
        for row in rows
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
                    "hasMore": has_more,
                    "nextCursor": (
                        operations[-1]["id"] if has_more and operations else None
                    ),
                },
            },
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
    data = EmulationController().launch_game(game_id)
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
            sys.stdout.write(
                json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
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
        if (
            domain == "operations"
            and target is not None
            and store.get_operation(target) is None
        ):
            raise SteamZeroError(
                "E-API-SCHEMA", detail=f"operação inexistente: {target}"
            )
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


#: Allowlist de ações. Chave (domínio, ação|None).
HANDLERS: dict[tuple[str, str | None], Handler] = {
    ("doctor", None): _cmd_doctor,
    ("jobs", "list"): _cmd_jobs_list,
    ("operations", "list"): _cmd_operations_list,
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
    ("desktop", "status"): _cmd_desktop_status,
    ("desktop", "plan"): _cmd_desktop_plan,
    ("desktop", "apply"): _cmd_desktop_apply,
    ("desktop", "reset"): _cmd_desktop_reset,
    ("desktop", "recover"): _cmd_desktop_recover,
    ("desktop", "keyboard"): _cmd_desktop_keyboard,
    ("desktop", "ui"): _cmd_desktop_ui,
    ("emulation", "workspace"): _cmd_emulation_workspace,
    ("emulation", "launch"): _cmd_emulation_launch,
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
