# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Modelo de job e máquina de estados (JOB-LIFECYCLE)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# Estados terminais.
TERMINAL = frozenset({"completed", "cancelled", "rolled-back", "rollback-failed"})

# Transições permitidas. "interrupted -> completed" = roll-forward pós-recovery
# (texto do JOB-LIFECYCLE §Recuperação: "tenta completar o commit"); registrado
# no WORKLOG como interpretação do diagrama.
VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "created": frozenset({"queued"}),
    "queued": frozenset({"running", "blocked", "cancelled"}),
    "blocked": frozenset({"queued", "cancelled"}),
    "running": frozenset({"completed", "paused", "cancelling", "failed", "interrupted"}),
    "paused": frozenset({"running", "cancelling"}),
    "cancelling": frozenset({"cancelled"}),
    "failed": frozenset({"rolling-back"}),
    "rolling-back": frozenset({"rolled-back", "rollback-failed"}),
    "interrupted": frozenset({"queued", "rolling-back", "completed"}),
    # terminais não transicionam
    "completed": frozenset(),
    "cancelled": frozenset(),
    "rolled-back": frozenset(),
    "rollback-failed": frozenset(),
}

PRIORITIES = ("interactive", "maintenance", "background")


def can_transition(src: str, dst: str) -> bool:
    return dst in VALID_TRANSITIONS.get(src, frozenset())


@dataclass
class Job:
    id: str
    type: str
    priority: str
    state: str
    params: dict[str, Any] = field(default_factory=dict)
    progress: dict[str, Any] | None = None
    operation_id: str | None = None
    correlation_id: str | None = None
    created_by: str = "cli"
    constraints: dict[str, Any] = field(default_factory=dict)
    checkpoints: list[Any] = field(default_factory=list)
    result: Any = None
    error_code: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def to_row(self) -> dict[str, Any]:
        """Serializa para as colunas do State Store (campos ricos em JSON)."""
        return {
            "id": self.id,
            "type": self.type,
            "priority": self.priority,
            "state": self.state,
            "params_json": json.dumps(self.params, ensure_ascii=False),
            "progress_json": json.dumps(self.progress, ensure_ascii=False)
            if self.progress is not None
            else None,
            "operation_id": self.operation_id,
            "correlation_id": self.correlation_id,
            "created_by": self.created_by,
            "constraints_json": json.dumps(self.constraints, ensure_ascii=False),
            "checkpoints_json": json.dumps(self.checkpoints, ensure_ascii=False),
            "result_json": json.dumps(self.result, ensure_ascii=False)
            if self.result is not None
            else None,
            "error_code": self.error_code,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_row(row: dict[str, Any]) -> Job:
        return Job(
            id=row["id"],
            type=row["type"],
            priority=row["priority"],
            state=row["state"],
            params=json.loads(row["params_json"]) if row.get("params_json") else {},
            progress=json.loads(row["progress_json"]) if row.get("progress_json") else None,
            operation_id=row.get("operation_id"),
            correlation_id=row.get("correlation_id"),
            created_by=row.get("created_by") or "cli",
            constraints=json.loads(row["constraints_json"]) if row.get("constraints_json") else {},
            checkpoints=json.loads(row["checkpoints_json"]) if row.get("checkpoints_json") else [],
            result=json.loads(row["result_json"]) if row.get("result_json") else None,
            error_code=row.get("error_code"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
