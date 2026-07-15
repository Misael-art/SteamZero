# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Envelope v2 (CLI-CONTRACT). Construção da saída tipada CLI/API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from steamzero import CONTRACT_VERSION
from steamzero.core import ids

Status = str  # ok | degraded | failed | blocked | noop


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def build_envelope(
    module: str,
    action: str,
    *,
    status: Status,
    ok: bool | None = None,
    data: dict[str, Any] | None = None,
    checks: list[dict[str, Any]] | None = None,
    blockers: list[dict[str, Any]] | None = None,
    error: dict[str, Any] | None = None,
    operation_id: str | None = None,
    job_id: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    """Monta um envelope v2. ``ok`` deriva do status quando não informado."""
    if ok is None:
        ok = status in ("ok", "noop", "degraded")
    return {
        "ok": ok,
        "contract": CONTRACT_VERSION,
        "module": module,
        "action": action,
        "status": status,
        "operationId": operation_id,
        "jobId": job_id,
        "correlationId": correlation_id or ids.new_ulid(),
        "data": data or {},
        "checks": checks or [],
        "blockers": blockers or [],
        "error": error,
        "generatedAt": _now_iso(),
    }


def status_from_checks(checks: list[dict[str, Any]]) -> Status:
    """Deriva o status a partir dos checks: fail=>failed, warn=>degraded, senão ok."""
    if any(c.get("status") == "fail" for c in checks):
        return "failed"
    if any(c.get("status") == "warn" for c in checks):
        return "degraded"
    return "ok"
