# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Modelo de atribuição de recursos por classe de processo (GAP-G30).

O escopo systemd agregava UI, daemon, jobs e emuladores num único número, que
não permitia atribuir consumo nem detectar regressão. Este domínio classifica
cada processo observado em uma das seis classes:

- ``ui`` — interface QML (identidade própria da ponte ou marcador);
- ``daemon`` — serviço persistente (PID do hello ou marcador da unit);
- ``media-job`` — job de mídia isolado (marcador; hoje os jobs rodam na
  thread do daemon, então a classe publica zero processos — honesto);
- ``emulator`` — processo de emulador comprovadamente iniciado pelo SteamZero
  (sessão de jogo com PID e start-time, ou marcador no environ);
- ``emulator-child`` — descendente de um emulador via cadeia de PPID;
- ``unknown`` — não atribuível.

Regras duras:

- a identidade é **efêmera** (PID + start-time lidos na observação); command
  line nunca é lida nem persistida; caminho de ROM nunca entra no snapshot;
- processo encerrado não é contado (não existe mais em /proc) e PID
  reutilizado não herda identidade antiga (start-time divergente sem marcador
  vira ``identity-mismatch`` → ``unknown``);
- permission denied vira memória ``unknown`` com causa explícita, e PSS
  indisponível usa fallback explícito para RSS (``rss-fallback``);
- o agregado nunca é chamado de "vazamento": os totais publicam
  "consumo atribuído" e "não atribuível" com rótulos PT-BR estáveis.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

#: Ordem canônica das classes (também a ordem de exibição).
PROCESS_CLASSES: tuple[str, ...] = (
    "ui",
    "daemon",
    "media-job",
    "emulator",
    "emulator-child",
    "unknown",
)

CLASS_LABELS: dict[str, str] = {
    "ui": "Interface",
    "daemon": "Daemon",
    "media-job": "Job de mídia",
    "emulator": "Emulador",
    "emulator-child": "Filho de emulador",
    "unknown": "Não atribuível",
}

#: Estados de ciclo de vida observáveis.
LIFECYCLES: tuple[str, ...] = ("running", "zombie", "stopped", "unknown")

#: Como a classificação foi comprovada (nunca por command line).
EVIDENCE_KINDS: tuple[str, ...] = (
    "own-process",
    "daemon-pid",
    "identity-provider",
    "environ-marker",
    "child-of-emulator",
    "identity-mismatch",
    "unattributable",
)

#: Métricas de memória: PSS nativo, fallback explícito para RSS ou indisponível.
METRICS: tuple[str, ...] = ("pss", "rss-fallback", "unavailable")

#: Causas de leitura falha por processo.
READ_FAILURES: tuple[str, ...] = ("permission-denied", "proc-incomplete")

_LIFECYCLE_LABELS: dict[str, str] = {
    "running": "em execução",
    "zombie": "zumbi",
    "stopped": "parado",
    "unknown": "desconhecido",
}


@dataclass(frozen=True)
class ProcessObservation:
    """Observação read-only de um processo no instante do snapshot.

    Nenhum campo carrega command line, argv ou caminho privado. ``comm`` é o
    nome do processo (limitado pelo kernel, sem barras) e ``start_ticks`` a
    identidade efêmera usada para detectar reutilização de PID.
    """

    pid: int
    process_class: str
    evidence: str
    lifecycle: str
    metric: str
    pss_bytes: int | None
    rss_bytes: int | None
    swap_bytes: int | None
    comm: str | None
    start_ticks: int | None
    read_failure: str | None = None


def summarize(
    observations: list[ProcessObservation],
    *,
    complete: bool,
    reason: str | None = None,
) -> dict[str, Any]:
    """Agrega observações por classe e totais atribuídos/não atribuíveis.

    A soma de memória ignora valores ``None`` (desconhecidos) e processos
    zumbi (0 bytes — um zumbi não retém memória e não pode "continuar sendo
    contado"). O resultado nunca usa a palavra "vazamento".
    """
    classes: dict[str, dict[str, Any]] = {}
    for process_class in PROCESS_CLASSES:
        classes[process_class] = {
            "processClass": process_class,
            "displayName": CLASS_LABELS[process_class],
            "processCount": 0,
            "pssBytes": 0,
            "rssBytes": 0,
            "swapBytes": 0,
            "memoryMetric": "pss",
            "lifecycle": {state: 0 for state in LIFECYCLES},
            "readFailures": {failure: 0 for failure in READ_FAILURES},
        }
    attributed_processes = 0
    attributed_pss = 0
    attributed_swap = 0
    attributed_unknown_memory = 0
    unattributable_processes = 0
    unattributable_pss = 0
    unattributable_swap = 0
    unattributable_unknown_memory = 0
    process_rows: list[dict[str, Any]] = []
    for observation in observations:
        process_class = (
            observation.process_class if observation.process_class in classes else "unknown"
        )
        row = classes[process_class]
        row["processCount"] += 1
        row["lifecycle"][observation.lifecycle] += 1
        if observation.read_failure in READ_FAILURES:
            row["readFailures"][observation.read_failure] += 1
        memory = _memory_kind(observation)
        if memory == "none":
            row["memoryMetric"] = _merge_metric(str(row["memoryMetric"]), "unavailable")
        elif memory == "rss":
            row["memoryMetric"] = _merge_metric(str(row["memoryMetric"]), "rss-fallback")
        if observation.metric == "unavailable":
            row["memoryMetric"] = _merge_metric(str(row["memoryMetric"]), "unavailable")
        if observation.pss_bytes is not None:
            row["pssBytes"] += observation.pss_bytes
        if observation.rss_bytes is not None:
            row["rssBytes"] += observation.rss_bytes
        if observation.swap_bytes is not None:
            row["swapBytes"] += observation.swap_bytes
        attributed = process_class != "unknown"
        if attributed:
            attributed_processes += 1
            if observation.pss_bytes is None:
                attributed_unknown_memory += 1
            else:
                attributed_pss += observation.pss_bytes
            if observation.swap_bytes is not None:
                attributed_swap += observation.swap_bytes
        else:
            unattributable_processes += 1
            if observation.pss_bytes is None:
                unattributable_unknown_memory += 1
            else:
                unattributable_pss += observation.pss_bytes
            if observation.swap_bytes is not None:
                unattributable_swap += observation.swap_bytes
        process_rows.append(
            {
                "pid": observation.pid,
                "comm": observation.comm,
                "processClass": process_class,
                "evidence": observation.evidence,
                "lifecycle": observation.lifecycle,
                "metric": observation.metric,
                "pssBytes": observation.pss_bytes,
                "rssBytes": observation.rss_bytes,
                "swapBytes": observation.swap_bytes,
                "startTicks": observation.start_ticks,
                "readFailure": observation.read_failure,
            }
        )
    return {
        "schemaVersion": 1,
        "observedAt": datetime.now(UTC).isoformat(),
        "readOnly": True,
        "complete": complete,
        "reason": reason,
        "classes": [classes[key] for key in PROCESS_CLASSES],
        "totals": {
            "attributed": {
                "displayName": "Consumo atribuído",
                "processCount": attributed_processes,
                "pssBytes": attributed_pss,
                "swapBytes": attributed_swap,
                "processesWithUnknownMemory": attributed_unknown_memory,
            },
            "unattributable": {
                "displayName": "Não atribuível",
                "processCount": unattributable_processes,
                "pssBytes": unattributable_pss,
                "swapBytes": unattributable_swap,
                "processesWithUnknownMemory": unattributable_unknown_memory,
            },
        },
        "processes": process_rows,
    }


def lifecycle_label(state: str) -> str:
    return _LIFECYCLE_LABELS.get(state, state)


def _memory_kind(observation: ProcessObservation) -> str:
    """Classifica a evidência de memória do processo para o rótulo da classe."""
    if observation.metric == "pss" and observation.pss_bytes is not None:
        return "pss"
    if observation.metric == "rss-fallback" and observation.rss_bytes is not None:
        return "rss"
    return "none"


def _merge_metric(current: str, incoming: str) -> str:
    """Merge honesto: qualquer indisponibilidade domina; senão fallback."""
    if current == "unavailable" or incoming == "unavailable":
        return "unavailable"
    if current == "rss-fallback" or incoming == "rss-fallback":
        return "rss-fallback"
    return "pss"
