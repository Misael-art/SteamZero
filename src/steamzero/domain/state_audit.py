# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Auditoria do estado do daemon (G25).

Funções puras que inspecionam o State Store e os diretórios de journal/staging/
backups para encontrar inconsistências que o doctor antigo (que só contava
journals não-terminais) deixava passar como falso verde:

- ``stale_jobs``: jobs em estado ``running`` (stalados pós-reboot).
- ``orphan_staging``: árvores de staging sem operação correspondente no banco.
- ``orphan_backups``: backups sem operação correspondente no banco.
- ``orphan_journals``: journals sem operação correspondente no banco.

O doctor consome ``audit()`` para seus checks; a CLI ``state audit`` expõe o
mesmo resultado. A auditoria nunca muta estado — é leitura.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from steamzero.core import fs, ids, paths
from steamzero.core.state import StateStore


@dataclass
class AuditReport:
    """Resultado imutável da auditoria de estado."""

    stale_jobs: list[dict[str, Any]] = field(default_factory=list)
    orphan_staging: list[str] = field(default_factory=list)
    orphan_backups: list[str] = field(default_factory=list)
    orphan_journals: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        """True quando nenhuma inconsistência foi encontrada."""
        return not (
            self.stale_jobs
            or self.orphan_staging
            or self.orphan_backups
            or self.orphan_journals
        )


def _known_operation_ids(store: StateStore) -> set[str]:
    """IDs de operações registradas no banco (qualquer estado)."""
    rows = store.adapter_connection().execute("SELECT id FROM operation").fetchall()
    return {r[0] for r in rows}


def _children(parent: Path) -> list[str]:
    """Nomes das entradas diretas de ``parent`` se o dir existir."""
    if not parent.is_dir():
        return []
    return sorted(entry.name for entry in parent.iterdir())


def audit(store: StateStore) -> AuditReport:
    """Inspeciona o estado e retorna as inconsistências encontradas.

    Leitura pura: não cria/remove/move nada. O doctor e ``state audit`` usam
    este resultado; o cleanup (fase 2) consome a mesma lista para quarentena.
    """
    report = AuditReport()

    # Jobs stalados: running no momento da auditoria é forte indício de processo
    # anterior morto sem recovery (a raiz do G25).
    for row in store.list_jobs(states=["running"]):
        report.stale_jobs.append(
            {
                "id": row["id"],
                "type": row["type"],
                "operationId": row.get("operation_id"),
                "updatedAt": row.get("updated_at"),
            }
        )

    known_ops = _known_operation_ids(store)

    # Órfãos: artefatos em disco sem operação correspondente no banco. Não são
    # necessariamente erro (uma operação pode ter sido limpa), mas acumulam e
    # explicam o acervo de ~1,1 GB observado no diagnóstico do host.
    for name in _children(paths.staging_dir()):
        if name not in known_ops:
            report.orphan_staging.append(name)
    for name in _children(paths.backups_dir()):
        if name not in known_ops:
            report.orphan_backups.append(name)
    for name in _children(paths.journal_dir()):
        # journals são "<op_id>.jsonl"; compara sem o sufixo.
        stem = name[:-6] if name.endswith(".jsonl") else name
        if stem not in known_ops:
            report.orphan_journals.append(name)

    return report


# -- cleanup em 2 fases (G25/A42) ------------------------------------------
# Fase 1 (plan): lista artefatos órfãos e devolve um plano persistido com
# token de confirmação. Fase 2 (apply): move os artefatos para quarentena
# (recoverable — NUNCA deleta). A aplicação no host exige autorização humana
# (AGENTS.md §1); os comandos existem, mas não rodam contra o acervo sem isso.


@dataclass
class CleanupItem:
    """Um artefato órfão candidato à quarentena."""

    kind: str  # "staging" | "backup" | "journal"
    name: str
    source: str

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "name": self.name, "source": self.source}


def plan_cleanup(report: AuditReport) -> dict[str, Any]:
    """Constrói o plano de quarentena a partir de um AuditReport.

    Persiste o plano em ``plans_dir`` com um token de confirmação para que
    ``apply_cleanup`` só execute contra o plano exato revisado pelo operador.
    """
    items: list[CleanupItem] = []
    for name in report.orphan_staging:
        items.append(CleanupItem("staging", name, str(paths.staging_for(name))))
    for name in report.orphan_backups:
        items.append(CleanupItem("backup", name, str(paths.backup_for(name))))
    for name in report.orphan_journals:
        items.append(CleanupItem("journal", name, str(paths.journal_dir() / name)))

    plan_id = ids.new_ulid()
    confirm_token = ids.new_ulid()
    payload = {
        "planId": plan_id,
        "confirmToken": confirm_token,
        "items": [it.to_dict() for it in items],
        "count": len(items),
    }
    fs.ensure_dir(paths.plans_dir())
    fs.write_atomic_text(
        paths.plan_path(plan_id),
        json.dumps(payload, ensure_ascii=False, indent=2),
    )
    return payload


def apply_cleanup(plan_id: str, confirm_token: str) -> dict[str, Any]:
    """Move os artefatos do plano para ``quarantine_dir`` (recoverable).

    Nunca deleta: o operador pode inspecionar/restaurar da quarentena. Requer o
    token exato do plano — proteção contra aplicar um plano desatualizado.
    """
    plan_file = paths.plan_path(plan_id)
    if not plan_file.is_file():
        raise FileNotFoundError(f"plano de cleanup inexistente: {plan_id}")
    payload = json.loads(plan_file.read_text(encoding="utf-8"))
    if payload.get("confirmToken") != confirm_token:
        raise PermissionError("token de confirmação não corresponde ao plano")
    quarantine = paths.quarantine_dir()
    fs.ensure_dir(quarantine)
    quarantined: list[dict[str, str]] = []
    for item in payload["items"]:
        src = Path(item["source"])
        if not src.exists():
            continue
        dest = quarantine / item["kind"] / item["name"]
        fs.ensure_dir(dest.parent)
        fs.move_tree(src, dest)
        quarantined.append({"kind": item["kind"], "name": item["name"], "quarantined": str(dest)})
    return {"planId": plan_id, "quarantined": quarantined, "count": len(quarantined)}
