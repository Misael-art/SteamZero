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

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from steamzero.core import paths
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
            self.stale_jobs or self.orphan_staging or self.orphan_backups or self.orphan_journals
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
