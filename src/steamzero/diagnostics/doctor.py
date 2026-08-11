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
from steamzero.adapters.desktop_kde import detect_deck_input_keys
from steamzero.adapters.release_convergence import ConvergenceState, observe
from steamzero.adapters.service_activation import read_quarantine
from steamzero.adapters.steam_boot import status as boot_status
from steamzero.core import fs as corefs
from steamzero.core import journal, paths
from steamzero.core.identity import runtime_identity
from steamzero.core.state import StateStore
from steamzero.domain import state_audit


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

    # Identidade do código em execução: sem ela não há como confrontar gerações,
    # e foi a ausência dessa comparação que deixou a a37 passar em silêncio.
    identity = runtime_identity()
    checks.append(
        _check(
            "runtime.provenance",
            "pass" if identity.known else "warn",
            f"{identity.release_id or identity.package_version}"
            + (" (árvore alterada)" if identity.source_dirty else "")
            if identity.known
            else "origem do pacote desconhecida; promoção será recusada pelo preflight",
        )
    )

    # C3: quarentena é anunciada, não descoberta.
    quarantine = read_quarantine()
    if quarantine:
        checks.append(
            _check(
                "service.generation",
                "fail",
                str(quarantine.get("reason", "serviço em quarentena")),
            )
        )
    else:
        # G38: comparar current × daemon (read-only). Pass genérico sem esta
        # leitura era falso verde quando a44 estava ativa e o daemon ainda
        # respondia como a42.
        try:
            convergence = observe()
        except Exception as exc:  # doctor nunca deve crashar nem mutar
            checks.append(
                _check(
                    "service.generation",
                    "warn",
                    f"convergência ilegível: {exc}",
                )
            )
        else:
            state = convergence.state
            activated = convergence.activated_release or "?"
            daemon = convergence.daemon_release or "?"
            if state is ConvergenceState.CONVERGED:
                checks.append(
                    _check(
                        "service.generation",
                        "pass",
                        f"daemon na release ativada {activated}",
                    )
                )
            elif state is ConvergenceState.PENDING:
                checks.append(
                    _check(
                        "service.generation",
                        "fail",
                        f"E-HOST-DAEMON-PENDING: current={activated} daemon={daemon}",
                    )
                )
            elif state is ConvergenceState.MISMATCH:
                checks.append(
                    _check(
                        "service.generation",
                        "fail",
                        f"E-HOST-RELEASE-MISMATCH: current={activated} daemon={daemon}",
                    )
                )
            elif state is ConvergenceState.TIMEOUT:
                checks.append(
                    _check(
                        "service.generation",
                        "warn",
                        f"daemon não respondeu; current={activated}",
                    )
                )
            else:
                checks.append(
                    _check(
                        "service.generation",
                        "warn",
                        f"convergência {state.value}: {convergence.detail}",
                    )
                )

    corefs.ensure_state_layout()
    layout_ok = all(f().is_dir() for f in paths.STATE_SUBDIRS)
    checks.append(_check("state.layout", "pass" if layout_ok else "fail", str(paths.state_home())))

    stale_count = 0
    orphan_staging = 0
    orphan_backups = 0
    orphan_journals = 0
    try:
        with StateStore() as store:
            store.migrate()
            integrity = store.integrity_ok()
            schema_version = store.user_version
            # G25: auditoria de estado enquanto o store está aberto. O doctor
            # antigo só contava journals não-terminais; jobs stalados em SQLite
            # e artefatos órfãos passavam despercebidos (falso verde operacional).
            report = state_audit.audit(store)
            stale_count = len(report.stale_jobs)
            orphan_staging = len(report.orphan_staging)
            orphan_backups = len(report.orphan_backups)
            orphan_journals = len(report.orphan_journals)
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

    checks.append(
        _check(
            "jobs.stale",
            "warn" if stale_count else "pass",
            (
                f"{stale_count} job(s) em estado running (stalado pós-reboot)"
                if stale_count
                else "nenhum job stalado"
            ),
        )
    )
    checks.append(
        _check(
            "staging.orphan",
            "warn" if orphan_staging else "pass",
            f"{orphan_staging} árvore(s) de staging sem operação no banco"
            if orphan_staging
            else "nenhum staging órfão",
        )
    )
    checks.append(
        _check(
            "backup.orphan",
            "warn" if orphan_backups else "pass",
            f"{orphan_backups} backup(s) sem operação no banco"
            if orphan_backups
            else "nenhum backup órfão",
        )
    )
    checks.append(
        _check(
            "journal.orphan",
            "warn" if orphan_journals else "pass",
            f"{orphan_journals} journal(is) sem operação no banco"
            if orphan_journals
            else "nenhum journal órfão",
        )
    )

    pending = _pending_operations()
    checks.append(
        _check(
            "recovery.pending",
            "pass" if pending == 0 else "warn",
            f"{pending} operação(ões) não-terminal(is) no journal",
        )
    )

    try:
        deck_keys = detect_deck_input_keys()
        checks.append(
            _check(
                "deck.input.keys",
                "pass" if deck_keys else "warn",
                (
                    "botões do Deck chegam como teclas: sim"
                    if deck_keys
                    else "botões do Deck chegam como teclas: não; considere InputPlumber"
                ),
            )
        )
    except Exception as exc:  # doctor nunca deve crashar
        deck_keys = False
        checks.append(_check("deck.input.keys", "warn", f"não foi possível detectar: {exc}"))

    # Boot direto Game Mode: cadeia GRUB→SDDM→sessão. ``steam_boot.status`` é
    # read-only (lê config/state) e nunca exige root; devolve ``unknown`` com
    # ``permissionDenied`` quando não pode inspecionar — nunca falso verde nem
    # falso negativo (ADR-0020). O doctor só fotografa: não habilita nem remove.
    boot_state = "unknown"
    boot_reason = "não foi possível inspecionar o boot direto"
    boot_backoff = False
    try:
        boot = boot_status()
        boot_state = str(boot.get("state", "unknown"))
        boot_backoff = bool(boot.get("backoff"))
        boot_reason = str(boot.get("reason", boot_reason))
        if boot.get("permissionDenied") or boot_state in {"backoff", "degraded"}:
            boot_level = "warn"
        else:  # ready (ativado e saudável) ou available (não ativado, legítimo)
            boot_level = "pass"
    except Exception as exc:  # doctor nunca deve crashar
        boot_level = "warn"
        boot_reason = f"não foi possível inspecionar o boot direto: {exc}"
    checks.append(_check("boot.direct", boot_level, f"{boot_state}: {boot_reason}"))

    data: dict[str, Any] = {
        "version": __version__,
        "stateHome": str(paths.state_home()),
        "schemaVersion": schema_version,
        "pendingOperations": pending,
        "deckInputKeys": deck_keys,
        "bootDirect": boot_state,
        "bootBackoff": boot_backoff,
        "staleJobs": stale_count,
        "orphanStaging": orphan_staging,
        "orphanBackups": orphan_backups,
        "orphanJournals": orphan_journals,
    }
    return data, checks
