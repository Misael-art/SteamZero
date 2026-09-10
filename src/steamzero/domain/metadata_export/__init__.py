# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Exportação do modelo canônico para formatos externos (frente A1).

Exportar mexe em arquivo **do usuário**. Por isso nada aqui escreve: o domínio
produz um plano com preview e exigência de backup, e quem aplica decide com o
plano à mão. Reexportar o mesmo conteúdo devolve ``UNCHANGED``, e aplicar um
plano assim não toca o disco.

Suportado neste ciclo: ES-DE (``gamelist.xml``).
"""

from __future__ import annotations

from steamzero.domain.metadata_export._plan import (
    ExportAction,
    ExportPlan,
    digest,
    summarize,
)
from steamzero.domain.metadata_export.esde import OWNED_TAGS, plan_esde_export

__all__ = [
    "OWNED_TAGS",
    "ExportAction",
    "ExportPlan",
    "digest",
    "plan_esde_export",
    "summarize",
]
