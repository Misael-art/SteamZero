# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Doctor mínimo (M2). Verifica saúde do núcleo sem mutar estado do usuário.

Cada check tem name/status(pass|warn|fail)/message. O status geral do envelope
deriva dos checks. Evidência antes de afirmação (P10): reporta o que verificou.
"""

from __future__ import annotations

import platform
import sys
from typing import Any

from steamzero import __version__
from steamzero.core import fs as corefs
from steamzero.core import journal, paths
from steamzero.core.state import StateStore


def _check(name: str, status: str, message: str) -> dict[str, str]:
    return {"name": name, "status": status, "message": message}


def _pending_operations() -> int:
    jdir = paths.journal_dir()
    if not jdir.is_dir():
        return 0
    pending = 0
    for entry in jdir.glob("*.jsonl"):
        if not journal.is_terminal(journal.read_records(entry.stem)):
            pending += 1
    return pending


def run_doctor() -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Executa os checks do doctor; retorna (data, checks)."""
    checks: list[dict[str, str]] = []

    py = sys.version_info
    checks.append(
        _check(
            "runtime.python",
            "pass" if py >= (3, 11) else "fail",
            f"Python {platform.python_version()}",
        )
    )

    corefs.ensure_state_layout()
    layout_ok = all(f().is_dir() for f in paths.STATE_SUBDIRS)
    checks.append(_check("state.layout", "pass" if layout_ok else "fail", str(paths.state_home())))

    try:
        with StateStore() as store:
            store.migrate()
            integrity = store.integrity_ok()
            schema_version = store.user_version
        checks.append(
            _check(
                "state.db.integrity",
                "pass" if integrity else "fail",
                "integrity_check ok" if integrity else "integrity_check falhou",
            )
        )
    except Exception as exc:  # doctor nunca deve crashar
        schema_version = -1
        checks.append(_check("state.db.integrity", "fail", f"erro: {exc}"))

    pending = _pending_operations()
    checks.append(
        _check(
            "recovery.pending",
            "pass" if pending == 0 else "warn",
            f"{pending} operação(ões) não-terminal(is) no journal",
        )
    )

    data: dict[str, Any] = {
        "version": __version__,
        "stateHome": str(paths.state_home()),
        "schemaVersion": schema_version,
        "pendingOperations": pending,
    }
    return data, checks
