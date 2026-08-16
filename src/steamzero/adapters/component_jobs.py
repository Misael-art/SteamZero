# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Execução assíncrona e persistente do lifecycle de componentes."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, Protocol

from steamzero.adapters.lifecycle import ComponentLifecycle
from steamzero.adapters.registry import AdapterRegistry
from steamzero.core.errors import SteamZeroError
from steamzero.core.net import transfer_observer
from steamzero.core.state import StateStore
from steamzero.jobs.manager import JobContext, JobManager
from steamzero.jobs.models import Job

_JOB_TYPE = "component.apply"


class LifecyclePort(Protocol):
    def validate_apply(self, plan_id: str, confirm_token: str) -> dict[str, str]: ...

    def apply(self, plan_id: str, confirm_token: str) -> dict[str, Any]: ...


StoreFactory = Callable[[], StateStore]
LifecycleFactory = Callable[[StateStore], LifecyclePort]


class ComponentJobService:
    """Cria um único job por confirmação e executa-o fora da thread HTTP."""

    def __init__(
        self,
        *,
        store_factory: StoreFactory = StateStore,
        lifecycle_factory: LifecycleFactory | None = None,
    ) -> None:
        self._store_factory = store_factory
        self._lifecycle_factory = lifecycle_factory or (
            lambda store: ComponentLifecycle(store, AdapterRegistry.bundled())
        )
        self._background_lock = threading.Lock()
        self._background_runners: dict[str, JobManager] = {}
        self._background_threads: dict[str, threading.Thread] = {}

    def start(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        """Valida, deduplica e devolve antes de executar aquisição/aplicação."""
        with self._store_factory() as store:
            store.migrate()
            manager = JobManager(store)
            existing = self._job_for_plan(manager, plan_id)
            if existing is not None:
                return self._view(existing)
            metadata = self._lifecycle_factory(store).validate_apply(plan_id, confirm_token)
            job = manager.create(
                _JOB_TYPE,
                params={
                    "planId": plan_id,
                    "confirmToken": confirm_token,
                    "adapterId": metadata["adapterId"],
                    "action": metadata["action"],
                    "executor": metadata["executor"],
                },
                priority="interactive",
                created_by="ui",
                constraints={"requiresNetwork": metadata["action"] not in {"uninstall", "stop"}},
            )
            view = self._view(job)
        self._start_background(job.id)
        current = self.get(job.id)
        return current or view

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._store_factory() as store:
            store.migrate()
            job = JobManager(store).get(job_id)
        if job is None or job.type != _JOB_TYPE:
            return None
        return self._view(job)

    def list(self) -> list[dict[str, Any]]:
        with self._store_factory() as store:
            store.migrate()
            jobs = [job for job in JobManager(store).list_jobs() if job.type == _JOB_TYPE]
        return [self._view(job) for job in reversed(jobs)]

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._background_lock:
            runner = self._background_runners.get(job_id)
        if runner is not None:
            runner.request_cancel(job_id)
            current = self.get(job_id)
            if current is None:
                raise SteamZeroError("E-API-SCHEMA", detail=f"job inexistente: {job_id}")
            return current
        with self._store_factory() as store:
            store.migrate()
            manager = JobManager(store)
            job = manager.get(job_id)
            if job is None or job.type != _JOB_TYPE:
                raise SteamZeroError("E-API-SCHEMA", detail=f"job inexistente: {job_id}")
            return self._view(manager.cancel(job_id))

    def retry(self, job_id: str) -> dict[str, Any]:
        with self._store_factory() as store:
            store.migrate()
            manager = JobManager(store)
            previous = manager.get(job_id)
            if previous is None or previous.type != _JOB_TYPE:
                raise SteamZeroError("E-API-SCHEMA", detail=f"job inexistente: {job_id}")
            if previous.state not in {"cancelled", "rolled-back", "rollback-failed"}:
                raise SteamZeroError(
                    "E-API-SCHEMA", detail=f"job não repetível no estado {previous.state}"
                )
            replacement = manager.create(
                _JOB_TYPE,
                params=dict(previous.params),
                priority=previous.priority,
                created_by="ui",
                constraints=dict(previous.constraints),
                correlation_id=previous.correlation_id,
            )
            view = self._view(replacement)
        self._start_background(replacement.id)
        return self.get(replacement.id) or view

    def _start_background(self, job_id: str) -> None:
        with self._background_lock:
            existing = self._background_threads.get(job_id)
            if existing is not None and existing.is_alive():
                return
            thread = threading.Thread(
                target=self._run_background,
                args=(job_id,),
                name=f"steamzero-component-{job_id[:8]}",
                daemon=True,
            )
            self._background_threads[job_id] = thread
            thread.start()

    def _run_background(self, job_id: str) -> None:
        with self._store_factory() as store:
            store.migrate()
            manager = JobManager(store)
            manager.register(_JOB_TYPE, self._handler(self._lifecycle_factory(store)))
            with self._background_lock:
                self._background_runners[job_id] = manager
            try:
                job = manager.get(job_id)
                if job is not None and job.state in {"queued", "paused"}:
                    manager.run(job_id)
            finally:
                with self._background_lock:
                    self._background_runners.pop(job_id, None)
                    self._background_threads.pop(job_id, None)

    @staticmethod
    def _handler(lifecycle: LifecyclePort) -> Callable[[Job, JobContext], dict[str, Any]]:
        def apply_component(job: Job, context: JobContext) -> dict[str, Any]:
            context.safepoint()
            context.set_progress("preparing", current=0, total=1, unit="steps")
            adapter_id = str(job.params["adapterId"])

            def transfer_progress(current: int, total: int | None) -> None:
                context.safepoint()
                context.set_progress(
                    "downloading",
                    current=current,
                    total=total,
                    unit="bytes",
                    current_item=adapter_id,
                )

            with transfer_observer(
                progress=transfer_progress,
                cancel_check=context.safepoint,
            ):
                result = lifecycle.apply(
                    str(job.params["planId"]),
                    str(job.params["confirmToken"]),
                )
            context.safepoint()
            operation_id = result.get("operationId")
            if isinstance(operation_id, str) and operation_id:
                job.operation_id = operation_id
                context.checkpoint({"stage": "applied", "operationId": operation_id})
            context.set_progress("verified", current=1, total=1, unit="steps")
            return result

        return apply_component

    @staticmethod
    def _job_for_plan(manager: JobManager, plan_id: str) -> Job | None:
        matches = [
            job
            for job in manager.list_jobs()
            if job.type == _JOB_TYPE and job.params.get("planId") == plan_id
        ]
        return matches[-1] if matches else None

    @staticmethod
    def _view(job: Job) -> dict[str, Any]:
        state = {
            "created": "queued",
            "queued": "queued",
            "blocked": "queued",
            "paused": "queued",
            "running": "running",
            "cancelling": "running",
            "rolling-back": "running",
            "interrupted": "running",
            "completed": "succeeded",
            "cancelled": "cancelled",
            "failed": "failed",
            "rolled-back": "failed",
            "rollback-failed": "failed",
        }.get(job.state, "failed")
        return {
            "jobId": job.id,
            "type": job.type,
            "state": state,
            "rawState": job.state,
            "priority": job.priority,
            "progress": job.progress,
            "errorCode": job.error_code,
            "result": job.result,
            "canCancel": job.state in {"queued", "blocked", "paused", "running"},
            "canRetry": job.state in {"cancelled", "rolled-back", "rollback-failed"},
            "createdAt": job.created_at,
            "updatedAt": job.updated_at,
        }
