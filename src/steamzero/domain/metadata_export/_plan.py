# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato de plano de exportação (frente A1).

Exportar mexe em arquivo **do usuário**, não do projeto — um `gamelist.xml` pode
ter anos de curadoria manual. Por isso nada aqui escreve: o domínio produz um
**plano** que diz o que mudaria, e quem aplica decide com o plano à mão.

Três invariantes, todas por não destruir dado alheio:

1. **Preview antes de escrever.** O plano carrega o conteúdo que seria gravado,
   para que a superfície mostre o diff real em vez de prometer.
2. **Backup obrigatório ao sobrescrever.** Criar arquivo novo não exige; mexer
   em arquivo existente sim, e o plano declara isso em vez de deixar implícito.
3. **Recusar vale mais que adivinhar.** Alvo que não conseguimos interpretar é
   recusado, nunca sobrescrito: um parser que falha pode estar diante de um
   arquivo válido que ele não entende, e sobrescrever apagaria a curadoria.

Idempotência é consequência, não enfeite: reexportar o mesmo conteúdo devolve
``UNCHANGED``, e aplicar um plano assim não toca o disco.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum


class ExportAction(Enum):
    """O que aconteceria com o arquivo alvo."""

    #: Alvo não existe; seria criado. Não exige backup.
    CREATE = "create"
    #: Alvo existe e mudaria. **Exige backup.**
    UPDATE = "update"
    #: Alvo existe e já tem exatamente este conteúdo. Aplicar não toca o disco.
    UNCHANGED = "unchanged"
    #: Alvo existe e não pôde ser interpretado. Nada será escrito.
    REFUSED = "refused"


@dataclass(frozen=True)
class ExportPlan:
    """O que a exportação faria, sem ter feito nada ainda.

    ``preview`` é o conteúdo final proposto — não um resumo — para que quem
    aplica possa comparar com o arquivo atual antes de confirmar.
    """

    action: ExportAction
    target: str
    preview: str = ""
    #: Digest do conteúdo atual do alvo, quando ele existe. Permite a quem
    #: aplica detectar que o arquivo mudou entre planejar e aplicar, em vez de
    #: sobrescrever uma edição feita nesse intervalo.
    current_digest: str = ""
    proposed_digest: str = ""
    #: Motivo da recusa, ou aviso relevante. Vazio quando não há o que dizer.
    reason: str = ""
    #: Campos do arquivo alvo que o GameRecord não modela e que o plano
    #: preservou. Registrados para que o usuário veja que não foram perdidos.
    preserved: tuple[str, ...] = ()
    #: Registros que não entraram no arquivo, com o motivo.
    skipped: tuple[tuple[str, str], ...] = ()

    @property
    def requires_backup(self) -> bool:
        """Sobrescrever arquivo existente exige backup; criar não."""
        return self.action is ExportAction.UPDATE

    @property
    def writes(self) -> bool:
        """Se aplicar este plano tocaria o disco."""
        return self.action in {ExportAction.CREATE, ExportAction.UPDATE}


def digest(text: str) -> str:
    """Digest estável do conteúdo, para comparação e detecção de deriva."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def decide(target: str, current: str | None, proposed: str) -> tuple[ExportAction, str, str]:
    """Escolhe a ação comparando o conteúdo atual com o proposto."""
    proposed_hash = digest(proposed)
    if current is None:
        return ExportAction.CREATE, "", proposed_hash
    current_hash = digest(current)
    if current_hash == proposed_hash:
        return ExportAction.UNCHANGED, current_hash, proposed_hash
    return ExportAction.UPDATE, current_hash, proposed_hash


def refusal(target: str, current: str, reason: str) -> ExportPlan:
    """Plano que recusa tocar o alvo, preservando o digest do que está lá."""
    return ExportPlan(
        action=ExportAction.REFUSED,
        target=target,
        current_digest=digest(current),
        reason=reason,
    )


def summarize(plans: Sequence[ExportPlan]) -> dict[str, int]:
    """Contagem por ação, para a superfície resumir sem recontar."""
    counts = {action.value: 0 for action in ExportAction}
    for plan in plans:
        counts[plan.action.value] += 1
    return counts
