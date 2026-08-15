# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Journal write-ahead JSONL por operação (TRANSACTION-MODEL §3, SR-17).

Uma operação = um arquivo ``journal/<opId>.jsonl``, append-only, com **fsync por
registro** (durabilidade — base do recovery determinístico após SIGKILL). Fica
FORA do SQLite (ADR-0005): sobrevive a corrupção do state.db e é a fonte do
recovery. Registros:

    operation.begin {planId, kind}
    stage.enter     {stage}
    action.intent   {actionId, undo}   ← gravado ANTES de mutar
    action.done     {actionId}         ← gravado DEPOIS de mutar
    custody.intent  {actionId, custodyId, target, custody, purpose, expected}
                                      ← intenção durável de tomar a entrada;
                                        custodyId identifica a TENTATIVA (o
                                        mesmo actionId reaparece em ciclos
                                        distintos — apply e rollback): nunca
                                        correlacione ciclos só por actionId
    custody.taken   {actionId, custodyId, target, custody}
                                      ← entrada realmente retirada do lugar
    custody.released {actionId, custodyId, custody, returned, reason}
                                      ← custódia resolvida (devolvida/removida)
    operation.commit
    operation.rollback {reason}
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from steamzero.core import fs, paths

# tipos de registro terminais
COMMIT = "operation.commit"
ROLLBACK = "operation.rollback"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Journal:
    """Escritor de journal de uma operação (append + fsync por linha)."""

    def __init__(self, operation_id: str, *, path: Path | None = None) -> None:
        self.operation_id = operation_id
        self._path = path or paths.journal_path(operation_id)
        existing = read_records(operation_id, path=self._path)
        self._seq = len(existing)
        self._writer = fs.AppendWriter(self._path)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def seq(self) -> int:
        """Sequência do Próximo registro — usado como identidade de tentativa."""
        return self._seq

    def _record(self, type_: str, **fields: Any) -> dict[str, Any]:
        rec: dict[str, Any] = {
            "seq": self._seq,
            "ts": _now_iso(),
            "type": type_,
            "operationId": self.operation_id,
            **fields,
        }
        self._seq += 1
        self._writer.write_line(json.dumps(rec, sort_keys=True, ensure_ascii=False), fsync=True)
        return rec

    def begin(self, *, plan_id: str, kind: str) -> None:
        self._record("operation.begin", planId=plan_id, kind=kind)

    def stage(self, name: str) -> None:
        self._record("stage.enter", stage=name)

    def intent(self, action_id: str, *, undo: dict[str, Any]) -> None:
        self._record("action.intent", actionId=action_id, undo=undo)

    def done(self, action_id: str) -> None:
        self._record("action.done", actionId=action_id)

    def custody_intent(
        self,
        action_id: str,
        *,
        custody_id: str,
        target: str,
        custody: str,
        purpose: str,
        expected: str | None,
    ) -> None:
        """Registra a intenção de tomar ``target`` em custódia (antes do rename).

        ``custody_id`` identifica a TENTATIVA desta custódia (único por ciclo):
        o mesmo ``action_id`` participa de ciclos distintos (apply e rollback)
        e correlacionar apenas por ``actionId`` mistura as tentativas — o P1
        desta série. O nome determinístico da entrada (``custody``) carrega o
        custodyId, para que o recovery encontre a entrada exata pelo journal.

        Este registro é o vínculo durável entre a entrada retirada do lugar e o
        journal: sem ele, um crash entre a tomada e a resolução deixaria a
        entrada órfã e invisível para o recovery.
        """
        self._record(
            "custody.intent",
            actionId=action_id,
            custodyId=custody_id,
            target=target,
            custody=custody,
            purpose=purpose,
            expected=expected,
        )

    def custody_taken(self, action_id: str, *, custody_id: str, target: str, custody: str) -> None:
        self._record(
            "custody.taken",
            actionId=action_id,
            custodyId=custody_id,
            target=target,
            custody=custody,
        )

    def custody_released(
        self,
        action_id: str,
        *,
        custody_id: str,
        custody: str,
        returned: bool,
        reason: str,
    ) -> None:
        self._record(
            "custody.released",
            actionId=action_id,
            custodyId=custody_id,
            custody=custody,
            returned=returned,
            reason=reason,
        )

    def commit(self) -> None:
        self._record(COMMIT)

    def rollback(self, *, reason: str) -> None:
        self._record(ROLLBACK, reason=reason)

    def close(self) -> None:
        self._writer.close()

    def __enter__(self) -> Journal:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def read_records(operation_id: str, *, path: Path | None = None) -> list[dict[str, Any]]:
    """Lê e parseia os registros do journal (lista vazia se inexistente)."""
    p = path or paths.journal_path(operation_id)
    if not p.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def has_type(records: list[dict[str, Any]], type_: str) -> bool:
    return any(r.get("type") == type_ for r in records)


def is_terminal(records: list[dict[str, Any]]) -> bool:
    """True se a operação já foi commitada ou revertida (estado terminal)."""
    return has_type(records, COMMIT) or has_type(records, ROLLBACK)
