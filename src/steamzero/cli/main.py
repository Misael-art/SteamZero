# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Ponto de entrada da CLI `steamzero` (CLI-CONTRACT).

Dispatch por **allowlist** de (domínio, ação) -> handler; nunca por nome vindo
de dados (P4/SR-19). ``--json`` emite o envelope v2 em stdout puro (avisos em
stderr). Exit codes estáveis (CLI-CONTRACT §Convenções).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any

from steamzero import CONTRACT_VERSION, __version__
from steamzero.api.envelope import build_envelope, status_from_checks
from steamzero.core import ids, log
from steamzero.core.errors import build_error
from steamzero.core.state import StateStore
from steamzero.diagnostics.doctor import run_doctor

# Exit codes (CLI-CONTRACT).
EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_BLOCKED = 4

Handler = Callable[[list[str], str], tuple[dict[str, Any], int]]

_USAGE = f"""steamzero <domínio> <ação> [flags]

Domínios (Fase 1):
  doctor                 diagnóstico do núcleo
  jobs list              lista jobs
  state export [--out F] exporta o State Store (JSON)

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


def _cmd_jobs_list(_args: list[str], correlation_id: str) -> tuple[dict[str, Any], int]:
    with StateStore() as store:
        store.migrate()
        jobs = [
            {"id": j["id"], "type": j["type"], "state": j["state"], "priority": j["priority"]}
            for j in store.list_jobs()
        ]
    env = build_envelope(
        "jobs",
        "list",
        status="ok" if jobs else "noop",
        data={"jobs": jobs, "count": len(jobs)},
        correlation_id=correlation_id,
    )
    return env, EXIT_OK


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


def _flag_value(args: list[str], flag: str) -> str | None:
    if flag in args:
        i = args.index(flag)
        if i + 1 < len(args):
            return args[i + 1]
    return None


#: Allowlist de ações. Chave (domínio, ação|None).
HANDLERS: dict[tuple[str, str | None], Handler] = {
    ("doctor", None): _cmd_doctor,
    ("jobs", "list"): _cmd_jobs_list,
    ("state", "export"): _cmd_state_export,
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
    tokens = [a for a in argv if a != "--json"]
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

    try:
        env, code = handler(rest, correlation_id)
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


if __name__ == "__main__":
    raise SystemExit(main())
