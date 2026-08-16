# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Job Manager (ADR-0010, JOB-LIFECYCLE).

Fila persistida no State Store; executor síncrono no daemon. Cada job executa um
handler registrado por tipo; o handler coopera com pausa/cancelamento chamando
``ctx.safepoint()`` em pontos de segurança (fim de item/arquivo) e reporta
progresso medido (P11). Recuperação pós-reboot: jobs ``running`` viram
``interrupted`` e são revertidos/roll-forward conforme o journal da operação.

Concorrência real (threads/cgroup) fica para além da Fase 1; aqui o executor é
determinístico e testável. 1 job mutável por recurso é garantido por core.lock
no handler (não reimplementado aqui).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from steamzero.core import ids, log, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.jobs.models import PRIORITIES, Job, can_transition


class JobCancelled(Exception):
    """Sinal interno: cancelamento solicitado em ponto de segurança."""


class JobPaused(Exception):
    """Sinal interno: pausa solicitada em ponto de segurança."""


@dataclass
class _Control:
    pause_requested: bool = False
    cancel_requested: bool = False


class JobContext:
    """Interface do handler com o manager: progresso, checkpoints, safepoints."""

    def __init__(self, job: Job, manager: JobManager, control: _Control) -> None:
        self._job = job
        self._manager = manager
        self._control = control

    def safepoint(self) -> None:
        """Ponto de segurança: honra cancel/pause. Chame entre itens/arquivos."""
        if self._control.cancel_requested:
            raise JobCancelled
        if self._control.pause_requested:
            raise JobPaused

    def set_progress(
        self,
        stage: str,
        *,
        current: float | None = None,
        total: float | None = None,
        unit: str | None = None,
        current_item: str | None = None,
    ) -> None:
        self._job.progress = {
            "stage": stage,
            "current": current,
            "total": total,
            "unit": unit,
            "currentItem": current_item,
        }
        self._manager._persist(self._job)
        self._manager._emit(self._job, "job.progress")

    def checkpoint(self, data: Any) -> None:
        self._job.checkpoints.append(data)
        self._manager._persist(self._job)

    @property
    def job(self) -> Job:
        return self._job


Handler = Callable[[Job, JobContext], Any]


class JobManager:
    """Gerencia o ciclo de vida dos jobs (JOB-LIFECYCLE)."""

    def __init__(
        self,
        store: StateStore,
        *,
        logger: log.StructuredLogger | None = None,
        session_active: Callable[[], bool] | None = None,
        on_ac_power: Callable[[], bool] | None = None,
        network_available: Callable[[], bool] | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self._store = store
        self._log = logger or log.get_logger()
        self._handlers: dict[str, Handler] = {}
        self._controls: dict[str, _Control] = {}
        self._session_active = session_active or (lambda: False)
        self._on_ac_power = on_ac_power or (lambda: True)
        self._network_available = network_available or (lambda: True)
        self._monotonic = monotonic or time.monotonic
        self._last_progress_event: dict[str, float] = {}

    # -- registro / criação -------------------------------------------------
    def register(self, job_type: str, handler: Handler) -> None:
        self._handlers[job_type] = handler

    def create(
        self,
        job_type: str,
        *,
        params: dict[str, Any] | None = None,
        priority: str = "background",
        created_by: str = "cli",
        constraints: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> Job:
        if priority not in PRIORITIES:
            raise SteamZeroError("E-API-SCHEMA", detail=f"prioridade inválida: {priority}")
        job = Job(
            id=ids.new_ulid(),
            type=job_type,
            priority=priority,
            state="created",
            params=params or {},
            constraints=constraints or {},
            created_by=created_by,
            correlation_id=correlation_id or log.new_correlation_id(),
        )
        self._persist(job)
        self._transition(job, "queued")
        return job

    # -- persistência / eventos --------------------------------------------
    def _persist(self, job: Job) -> None:
        self._store.save_job(job.to_row())

    def _emit(self, job: Job, kind: str) -> None:
        if kind == "job.progress":
            now = self._monotonic()
            previous = self._last_progress_event.get(job.id)
            if previous is not None and now - previous < 0.25:
                return
            self._last_progress_event[job.id] = now
        self._store.append_event(kind, entity=f"job:{job.id}", payload=job.progress or {})

    def _transition(self, job: Job, new_state: str) -> None:
        if not can_transition(job.state, new_state):
            raise SteamZeroError(
                "E-INTERNAL-UNEXPECTED",
                detail=f"transição inválida de job: {job.state} -> {new_state}",
            )
        job.state = new_state
        self._persist(job)
        self._store.append_event("job.state", entity=f"job:{job.id}", payload={"state": new_state})
        if new_state in {"completed", "cancelled", "rolled-back", "rollback-failed"}:
            self._last_progress_event.pop(job.id, None)
        self._log.bind(jobId=job.id, correlationId=job.correlation_id or "").info(
            "job.transition", state=new_state
        )

    def get(self, job_id: str) -> Job | None:
        row = self._store.get_job(job_id)
        return Job.from_row(row) if row is not None else None

    def _require(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job is None:
            raise SteamZeroError("E-API-SCHEMA", detail=f"job inexistente: {job_id}")
        return job

    def list_jobs(self, *, states: list[str] | None = None) -> list[Job]:
        return [Job.from_row(r) for r in self._store.list_jobs(states=states)]

    # -- controle -----------------------------------------------------------
    def request_pause(self, job_id: str) -> None:
        self._controls.setdefault(job_id, _Control()).pause_requested = True

    def request_resume(self, job_id: str) -> None:
        ctrl = self._controls.setdefault(job_id, _Control())
        ctrl.pause_requested = False

    def request_cancel(self, job_id: str) -> None:
        self._controls.setdefault(job_id, _Control()).cancel_requested = True

    def cancel(self, job_id: str) -> Job:
        """Cancela imediatamente quando seguro ou sinaliza um handler ativo."""
        job = self._require(job_id)
        if job.state in {"queued", "blocked"}:
            self._transition(job, "cancelled")
        elif job.state == "paused":
            self._transition(job, "cancelling")
            self._transition(job, "cancelled")
        elif job.state == "running":
            # G25/D2: cancel de job "running" só é útil se houver um handler
            # vivo neste processo consumindo o controle. _controls é populado
            # apenas por request_cancel/run; um job "running" recuperado de um
            # reboot anterior não tem controle aqui — request_cancel seria
            # inerte. Sem runner, forçamos o caminho terminal via recover().
            if job_id not in self._controls:
                stale = self.get(job_id)
                if stale is not None and stale.state == "running":
                    self._transition(stale, "interrupted")
                    if stale.operation_id:
                        result = transaction.recover_operation(stale.operation_id)
                        terminal = "completed" if result.outcome == "kept" else "rolled-back"
                        self._transition(stale, terminal)
                    else:
                        self._transition(stale, "cancelled")
                        stale.error_code = "recovered"
                        self._persist(stale)
            else:
                self.request_cancel(job_id)
        elif job.state != "cancelling":
            raise SteamZeroError("E-API-SCHEMA", detail=f"job não cancelável no estado {job.state}")
        return self._require(job_id)

    def retry(self, job_id: str, *, created_by: str = "ui") -> Job:
        """Cria nova execução auditável sem reabrir o registro anterior."""
        previous = self._require(job_id)
        if previous.state not in {"cancelled", "rolled-back", "rollback-failed"}:
            raise SteamZeroError(
                "E-API-SCHEMA", detail=f"job não repetível no estado {previous.state}"
            )
        replacement = self.create(
            previous.type,
            params=dict(previous.params),
            priority=previous.priority,
            created_by=created_by,
            constraints=dict(previous.constraints),
            correlation_id=previous.correlation_id,
        )
        return self.run(replacement.id)

    # -- bloqueio por constraints ------------------------------------------
    def blocked_reason(self, job: Job) -> str | None:
        if job.constraints.get("forbiddenDuringGameplay") and self._session_active():
            return "gameplay"
        if job.constraints.get("requiresAC") and not self._on_ac_power():
            return "battery"
        if job.constraints.get("requiresNetwork") and not self._network_available():
            return "network"
        return None

    # -- execução -----------------------------------------------------------
    def run(self, job_id: str) -> Job:
        """Executa um job (queued/paused) até um estado terminal ou pausa."""
        job = self._require(job_id)
        if job.state not in ("queued", "paused"):
            raise SteamZeroError("E-API-SCHEMA", detail=f"job não executável no estado {job.state}")

        reason = self.blocked_reason(job)
        if reason is not None:
            code = {
                "gameplay": "E-JOBS-BLOCKED-GAMEPLAY",
                "battery": "E-JOBS-BLOCKED-BATTERY",
                "network": "E-SUPPLY-OFFLINE",
            }[reason]
            job.error_code = code
            if job.state == "queued":
                self._transition(job, "blocked")
            return self._require(job_id)

        handler = self._handlers.get(job.type)
        if handler is None:
            raise SteamZeroError("E-API-UNKNOWN-ACTION", detail=f"sem handler para {job.type}")

        self._transition(job, "running")
        control = self._controls.setdefault(job_id, _Control())
        ctx = JobContext(job, self, control)
        try:
            job.result = handler(job, ctx)
        except JobPaused:
            self._transition(job, "paused")
            return self._require(job_id)
        except JobCancelled:
            self._transition(job, "cancelling")
            self._transition(job, "cancelled")
            return self._require(job_id)
        except SteamZeroError as exc:
            job.error_code = exc.code
            self._fail_and_rollback(job)
            return self._require(job_id)
        except Exception as exc:  # handler de terceiros: qualquer falha => rollback
            self._log.error("job.handler-error", jobId=job.id, error=str(exc))
            job.error_code = "E-INTERNAL-UNEXPECTED"
            self._fail_and_rollback(job)
            return self._require(job_id)
        self._transition(job, "completed")
        return self._require(job_id)

    def _fail_and_rollback(self, job: Job) -> None:
        self._transition(job, "failed")
        self._transition(job, "rolling-back")
        if job.operation_id:
            result = transaction.rollback(job.operation_id, reason="job-failed")
            terminal = "rolled-back" if result.status == "rolled-back" else "rollback-failed"
        else:
            terminal = "rolled-back"  # nada a reverter
        self._transition(job, terminal)

    # -- recuperação pós-reboot --------------------------------------------
    def recover(self, *, job_types: set[str] | None = None) -> list[Job]:
        """Jobs 'running' viram 'interrupted' e são resolvidos (JOB-LIFECYCLE §Recuperação)."""
        recovered: list[Job] = []
        for job in self.list_jobs(states=["running", "cancelling"]):
            if job_types is not None and job.type not in job_types:
                continue
            if job.state == "cancelling":
                self._transition(job, "cancelled")
                job.error_code = "recovered"
                self._persist(job)
                recovered.append(self._require(job.id))
                continue
            self._transition(job, "interrupted")
            if job.operation_id:
                result = transaction.recover_operation(job.operation_id)
                if result.outcome == "kept":
                    self._transition(job, "completed")  # roll-forward
                elif result.outcome == "rollback-failed":
                    self._transition(job, "rolling-back")
                    self._transition(job, "rollback-failed")
                else:
                    self._transition(job, "rolling-back")
                    self._transition(job, "rolled-back")
            else:
                # G25/D1: job running sem operação (ex.: media.global stalado) não
                # pode ser reenfileirado — reativaria rede no próximo request. Em
                # vez de "queued", termina "cancelled" marcado como recuperado.
                self._transition(job, "cancelled")
                job.error_code = "recovered"
                self._persist(job)
            recovered.append(self._require(job.id))
        return recovered
