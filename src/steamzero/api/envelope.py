# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Envelope v2 (CLI-CONTRACT). Construção da saída tipada CLI/API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from steamzero import CONTRACT_VERSION
from steamzero.core import ids

Status = str

# Os dez status abaixo foram MEDIDOS instrumentando ``build_envelope`` na suíte
# inteira — não deduzidos do comentário que existia aqui, que listava cinco.
#
# ``ok`` responde "a operação fez o que foi pedido", não "o mundo está bom".
# ``degraded`` já estabelecia essa leitura: degradar é um resultado, não um erro.
# Pela mesma régua são sucesso um plano pronto (``ready``), uma transação
# desfeita a pedido (``rolled-back``), um commit aplicado (``committed``) e um
# estado que apenas ainda não foi conferido (``unchecked``, ``unverified``).
#
# Só ``failed`` e ``blocked`` dizem que a operação não aconteceu.
_FAILURE_STATUSES = frozenset({"failed", "blocked"})
_SUCCESS_STATUSES = frozenset(
    {
        "ok",
        "noop",
        "degraded",
        "ready",
        "already-active",
        "rolled-back",
        "committed",
        "unchecked",
        "unverified",
    }
)
KNOWN_STATUSES = _FAILURE_STATUSES | _SUCCESS_STATUSES


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
    """Monta um envelope v2. ``ok`` deriva do status quando não informado.

    Um status desconhecido degrada para ``ok=False`` em vez de levantar: a
    saída da CLI não pode virar exceção no host por causa de um status novo
    (AGENTS.md §8). O que impede a deriva silenciosa é o gate
    ``test_every_literal_status_is_declared_in_the_contract``, que reprova
    quando um literal novo aparece sem ser classificado aqui.
    """
    if ok is None:
        ok = status in _SUCCESS_STATUSES
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
