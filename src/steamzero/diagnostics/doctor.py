# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Doctor mínimo (M2). Verifica saúde do núcleo sem mutar estado do usuário.

Cada check mantém ``name/status/message`` para compatibilidade e acrescenta
guidance estruturado: o que foi observado, impacto, orientação e ação segura.
Isso permite que a superfície Sistema seja orientada à recuperação sem fazer o
Doctor executar mutações por conta própria.
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

_READ_ONLY_ACTIONS: dict[str, dict[str, object]] = {
    "operations": {
        "kind": "navigate",
        "target": "system.operations",
        "label": "Abrir tarefas",
        "enabled": True,
        "requiresConfirmation": False,
    },
    "diagnostics": {
        "kind": "navigate",
        "target": "system.diagnostics.export",
        "label": "Exportar diagnóstico",
        "enabled": True,
        "requiresConfirmation": True,
    },
}


_CHECK_GUIDANCE: dict[str, dict[str, object]] = {
    "runtime.python": {
        "what": "A versão de Python disponível para o SteamZero.",
        "impact": "Uma versão incompatível impede executar componentes do aplicativo.",
        "manualAction": (
            "Atualize o runtime pelo pacote aprovado e execute o diagnóstico novamente."
        ),
    },
    "runtime.provenance": {
        "what": "A identidade e a origem da release em execução.",
        "impact": (
            "Sem proveniência, a versão ativa não pode ser comparada com o daemon com segurança."
        ),
        "manualAction": (
            "Confirme a release instalada com o operador antes de qualquer atualização."
        ),
        "action": "diagnostics",
    },
    "service.generation": {
        "what": "A convergência entre a release ativa e o daemon.",
        "impact": (
            "Divergência pode fazer a interface e o serviço responderem com estados diferentes."
        ),
        "manualAction": (
            "Não reinicie nem instale manualmente; registre o diagnóstico e siga o "
            "fluxo governado de release."
        ),
        "action": "diagnostics",
    },
    "state.layout": {
        "what": "A existência das pastas de estado exigidas pelo aplicativo.",
        "impact": "Uma pasta ausente pode impedir tarefas, rollback ou recuperação persistente.",
        "manualAction": (
            "Exporte o diagnóstico e peça reparo pelo fluxo aprovado; esta leitura "
            "não altera o estado."
        ),
        "action": "diagnostics",
    },
    "state.db.integrity": {
        "what": "A integridade lógica do banco de estado.",
        "impact": "Falha pode tornar catálogos, tarefas ou rollbacks indisponíveis.",
        "manualAction": "Exporte o diagnóstico antes de qualquer reparo para preservar evidência.",
        "action": "diagnostics",
    },
    "jobs.stale": {
        "what": "Operações que ficaram em execução sem concluir após uma interrupção.",
        "impact": "A tarefa pode não ter aplicado tudo e não deve ser repetida às cegas.",
        "manualAction": (
            "Abra Tarefas, confira o detalhe e use somente a recuperação disponível "
            "para aquela operação."
        ),
        "action": "operations",
    },
    "staging.orphan": {
        "what": "Árvores temporárias sem operação correspondente no banco.",
        "impact": (
            "O espaço pode estar ocupado por dados que não pertencem a uma tarefa recuperável."
        ),
        "manualAction": (
            "Abra Tarefas e exporte o diagnóstico; não apague a árvore sem "
            "confirmação de ownership."
        ),
        "action": "operations",
    },
    "backup.orphan": {
        "what": "Backups sem operação correspondente no banco.",
        "impact": (
            "O backup pode ser necessário para recuperação e não pode ser tratado "
            "como lixo automaticamente."
        ),
        "manualAction": "Abra Tarefas, preserve o backup e solicite revisão antes de removê-lo.",
        "action": "operations",
    },
    "journal.orphan": {
        "what": "Journals sem operação correspondente no banco.",
        "impact": "A trilha de uma operação pode estar incompleta para auditoria ou rollback.",
        "manualAction": (
            "Exporte o diagnóstico e peça reconciliação; o Doctor não modifica journals."
        ),
        "action": "diagnostics",
    },
    "recovery.pending": {
        "what": "Operações não terminais registradas no journal.",
        "impact": "Aplicar outra ação antes da recuperação pode aumentar o risco de duplicação.",
        "manualAction": (
            "Abra Tarefas, revise a operação e aguarde ou confirme a recuperação indicada."
        ),
        "action": "operations",
    },
    "deck.input.keys": {
        "what": "Se os botões do Deck chegam ao sistema como teclas reconhecíveis.",
        "impact": "Sem um caminho de entrada, a navegação por controle pode não responder.",
        "manualAction": (
            "Verifique o provider de entrada no host; nenhum ajuste é aplicado pelo Doctor."
        ),
    },
    "boot.direct": {
        "what": "O estado observado da cadeia de boot direto do SteamZero.",
        "impact": (
            "Backoff, degradação ou permissão negada podem impedir a entrada no modo de jogo."
        ),
        "manualAction": (
            "Siga a validação de boot com o operador; esta tela somente observa e "
            "não altera o host."
        ),
    },
}


def _check(name: str, status: str, message: str) -> dict[str, Any]:
    guidance = _CHECK_GUIDANCE.get(name, {})
    action_key = guidance.get("action")
    action = _READ_ONLY_ACTIONS.get(action_key) if isinstance(action_key, str) else None
    return {
        "name": name,
        "status": status,
        "message": message,
        "severity": {"pass": "ok", "warn": "warning", "fail": "error"}.get(status, "unknown"),
        "what": guidance.get("what", "Verificação do estado do sistema."),
        "impact": guidance.get("impact", "O estado requer atenção antes de prosseguir."),
        "manualAction": guidance.get(
            "manualAction", "Nenhuma ação automática é executada por esta verificação."
        ),
        "action": dict(action) if action is not None else None,
    }


def _pending_operations() -> int:
    jdir = paths.journal_dir()
    if not jdir.is_dir():
        return 0
    pending = 0
    for entry in jdir.glob("*.jsonl"):
        if not journal.is_terminal(journal.read_records(entry.stem)):
            pending += 1
    return pending


def run_doctor() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Executa os checks do doctor; retorna (data, checks)."""
    checks: list[dict[str, Any]] = []

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
        # G38: comparar current vs daemon (read-only). Pass generico sem esta
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
