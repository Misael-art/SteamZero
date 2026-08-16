# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do Job Manager: ciclo de vida, pausa/resume/cancel, recovery (M3)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from steamzero.core import fs, paths, state, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.jobs.manager import JobContext, JobManager
from steamzero.jobs.models import Job


@pytest.fixture
def env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[tuple[JobManager, state.StateStore, Path]]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    fs.ensure_state_layout()
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    store = state.open_state()
    mgr = JobManager(store)
    yield mgr, store, sandbox
    store.close()


def _stepwise(job: Job, ctx: JobContext) -> dict[str, bool]:
    done = int(job.params.get("done", 0))
    for i in range(done, 3):
        ctx.safepoint()
        ctx.set_progress("work", current=i + 1, total=3, unit="items")
        job.params["done"] = i + 1
    return {"ok": True}


def test_create_is_queued(env: tuple[JobManager, state.StateStore, Path]) -> None:
    mgr, _, _ = env
    job = mgr.create("noop")
    assert job.state == "queued"
    assert mgr.get(job.id) is not None


def test_run_happy_path(env: tuple[JobManager, state.StateStore, Path]) -> None:
    mgr, _, _ = env
    mgr.register("step", _stepwise)
    job = mgr.create("step")
    done = mgr.run(job.id)
    assert done.state == "completed"
    assert done.result == {"ok": True}
    assert done.progress["current"] == 3


def test_progress_events_are_throttled_without_losing_persisted_progress(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    fs.ensure_state_layout()
    store = state.open_state()
    now = [100.0]
    manager = JobManager(store, monotonic=lambda: now[0])

    def burst(_job: Job, context: JobContext) -> None:
        context.set_progress("scan", current=1, total=3, unit="items")
        context.set_progress("scan", current=2, total=3, unit="items")
        now[0] += 0.25
        context.set_progress("scan", current=3, total=3, unit="items")

    manager.register("burst", burst)
    job = manager.create("burst")
    manager.run(job.id)

    progress_events = [event for event in store.events_since(0) if event["kind"] == "job.progress"]
    assert len(progress_events) == 2
    persisted = manager.get(job.id)
    assert persisted is not None
    assert persisted.progress["current"] == 3
    store.close()


def test_cancel_before_run(env: tuple[JobManager, state.StateStore, Path]) -> None:
    mgr, _, _ = env
    mgr.register("step", _stepwise)
    job = mgr.create("step")
    mgr.request_cancel(job.id)
    done = mgr.run(job.id)
    assert done.state == "cancelled"


def test_cancel_queued_job_transitions_immediately(
    env: tuple[JobManager, state.StateStore, Path],
) -> None:
    mgr, _, _ = env
    job = mgr.create("step")
    assert mgr.cancel(job.id).state == "cancelled"


def test_retry_creates_auditable_replacement(
    env: tuple[JobManager, state.StateStore, Path],
) -> None:
    mgr, _, _ = env
    mgr.register("step", _stepwise)
    original = mgr.create("step", params={"source": "ui"})
    mgr.cancel(original.id)

    replacement = mgr.retry(original.id)

    assert replacement.id != original.id
    assert replacement.state == "completed"
    assert replacement.result == {"ok": True}
    assert replacement.params["source"] == "ui"


def test_pause_then_resume(env: tuple[JobManager, state.StateStore, Path]) -> None:
    mgr, _, _ = env
    mgr.register("step", _stepwise)
    job = mgr.create("step")
    mgr.request_pause(job.id)
    paused = mgr.run(job.id)
    assert paused.state == "paused"
    mgr.request_resume(job.id)
    done = mgr.run(job.id)
    assert done.state == "completed"
    assert done.params["done"] == 3


def test_failure_without_operation_rolls_back(
    env: tuple[JobManager, state.StateStore, Path],
) -> None:
    mgr, _, _ = env

    def boom(job: Job, ctx: JobContext) -> None:
        raise RuntimeError("falhou")

    mgr.register("boom", boom)
    job = mgr.create("boom")
    done = mgr.run(job.id)
    assert done.state == "rolled-back"
    assert done.error_code == "E-INTERNAL-UNEXPECTED"


def test_failure_with_operation_triggers_transaction_rollback(
    env: tuple[JobManager, state.StateStore, Path],
) -> None:
    mgr, store, sandbox = env
    target = sandbox / "c"
    fs.write_atomic_text(target, "orig")
    plan = transaction.plan_write_files({target: b"novo"}, root=sandbox)
    result = transaction.apply(plan.plan_id, plan.confirm_token)  # committed

    def failing(job: Job, ctx: JobContext) -> None:
        raise SteamZeroError("E-COMPONENT-DEGRADED", detail="pós-apply falhou")

    mgr.register("op", failing)
    job = mgr.create("op")
    job = mgr.get(job.id)  # type: ignore[assignment]
    job.operation_id = result.operation_id
    store.save_operation(
        result.operation_id, journal_path=str(paths.journal_path(result.operation_id))
    )
    store.save_job(job.to_row())
    done = mgr.run(job.id)
    assert done.state == "rolled-back"
    assert target.read_text() == "orig"  # transação revertida


def test_blocked_by_gameplay(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    fs.ensure_state_layout()
    store = state.open_state()
    mgr = JobManager(store, session_active=lambda: True)
    mgr.register("conv", _stepwise)
    job = mgr.create("conv", constraints={"forbiddenDuringGameplay": True})
    done = mgr.run(job.id)
    assert done.state == "blocked"
    assert done.error_code == "E-JOBS-BLOCKED-GAMEPLAY"
    store.close()


def test_blocked_by_battery(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    fs.ensure_state_layout()
    store = state.open_state()
    mgr = JobManager(store, on_ac_power=lambda: False)
    mgr.register("dl", _stepwise)
    job = mgr.create("dl", constraints={"requiresAC": True})
    done = mgr.run(job.id)
    assert done.state == "blocked"
    assert done.error_code == "E-JOBS-BLOCKED-BATTERY"
    store.close()


def test_unknown_handler(env: tuple[JobManager, state.StateStore, Path]) -> None:
    mgr, _, _ = env
    job = mgr.create("sem-handler")
    with pytest.raises(SteamZeroError) as ei:
        mgr.run(job.id)
    assert ei.value.code == "E-API-UNKNOWN-ACTION"


def test_recover_cancels_running_without_op(
    env: tuple[JobManager, state.StateStore, Path],
) -> None:
    # G25/D1: job running sem operação (media.global stalado) não pode ser
    # reenfileirado — reativaria rede. Termina "cancelled" marcado recuperado.
    mgr, store, _ = env
    job = mgr.create("step")
    job = mgr.get(job.id)  # type: ignore[assignment]
    job.state = "running"
    store.save_job(job.to_row())
    recovered = mgr.recover()
    assert len(recovered) == 1
    assert recovered[0].state == "cancelled"
    assert recovered[0].error_code == "recovered"


def test_recover_committed_op_rolls_forward(env: tuple[JobManager, state.StateStore, Path]) -> None:
    mgr, store, sandbox = env
    target = sandbox / "c"
    fs.write_atomic_text(target, "v0")
    plan = transaction.plan_write_files({target: b"v1"}, root=sandbox)
    result = transaction.apply(plan.plan_id, plan.confirm_token)  # committed
    job = mgr.create("op")
    job = mgr.get(job.id)  # type: ignore[assignment]
    job.state = "running"
    job.operation_id = result.operation_id
    store.save_operation(
        result.operation_id, journal_path=str(paths.journal_path(result.operation_id))
    )
    store.save_job(job.to_row())
    recovered = mgr.recover()
    assert recovered[0].state == "completed"  # roll-forward (kept)


def test_recover_interrupted_op_rolls_back(env: tuple[JobManager, state.StateStore, Path]) -> None:
    mgr, store, sandbox = env
    target = sandbox / "c"
    fs.write_atomic_text(target, "v0")
    plan = transaction.plan_write_files({target: b"v1"}, root=sandbox)

    def hook(stage: str) -> None:
        if stage == "apply.done":
            raise transaction.SimulatedKill

    transaction.set_crash_hook(hook)
    try:
        with pytest.raises(transaction.SimulatedKill):
            transaction.apply(plan.plan_id, plan.confirm_token)
    finally:
        transaction.set_crash_hook(None)
    op_id = next(p.stem for p in paths.journal_dir().glob("*.jsonl"))

    job = mgr.create("op")
    job = mgr.get(job.id)  # type: ignore[assignment]
    job.state = "running"
    job.operation_id = op_id
    store.save_operation(op_id, journal_path=str(paths.journal_path(op_id)))
    store.save_job(job.to_row())
    recovered = mgr.recover()
    assert recovered[0].state == "rolled-back"
    assert target.read_text() == "v0"


def test_recover_is_idempotent(env: tuple[JobManager, state.StateStore, Path]) -> None:
    # G25: chamar recover() duas vezes não tem efeito colateral — a segunda
    # chamada não encontra jobs running e retorna [].
    mgr, store, _ = env
    job = mgr.create("step")
    job = mgr.get(job.id)  # type: ignore[assignment]
    job.state = "running"
    store.save_job(job.to_row())
    first = mgr.recover()
    second = mgr.recover()
    assert len(first) == 1
    assert second == []


def test_recover_filters_job_types_without_touching_other_workers(
    env: tuple[JobManager, state.StateStore, Path],
) -> None:
    mgr, store, _ = env
    component = mgr.create("component.apply")
    media = mgr.create("media.global")
    for job in (component, media):
        job.state = "running"
        store.save_job(job.to_row())

    recovered = mgr.recover(job_types={"component.apply"})

    assert [job.id for job in recovered] == [component.id]
    assert mgr.get(component.id).state == "cancelled"  # type: ignore[union-attr]
    assert mgr.get(media.id).state == "running"  # type: ignore[union-attr]


def test_cancel_runnerless_running_forces_terminal(
    env: tuple[JobManager, state.StateStore, Path],
) -> None:
    # G25/D2: cancel de job "running" sem handler vivo neste processo (caso de
    # job stalado pós-reboot) não pode ser inerte. Deve atingir estado terminal.
    mgr, store, _ = env
    job = mgr.create("step")
    job = mgr.get(job.id)  # type: ignore[assignment]
    job.state = "running"
    store.save_job(job.to_row())
    # Sem registrar handler/executar via run(), _controls não tem o job.
    assert job.id not in mgr._controls
    cancelled = mgr.cancel(job.id)
    assert cancelled.state == "cancelled"
    assert cancelled.error_code == "recovered"


def test_cancel_running_with_live_control_still_requests(
    env: tuple[JobManager, state.StateStore, Path],
) -> None:
    # G25/D2: regressão — quando há handler vivo (_controls presente), cancel
    # mantém o comportamento original (request_cancel, não força terminal).
    mgr, store, _ = env
    job = mgr.create("step")
    job = mgr.get(job.id)  # type: ignore[assignment]
    job.state = "running"
    store.save_job(job.to_row())
    mgr.request_cancel(job.id)  # simula handler vivo solicitando cancelamento
    result = mgr.cancel(job.id)
    # request_cancel apenas sinaliza; o job permanece running até o handler honrar.
    assert result.state == "running"


def test_invalid_transition_raises(env: tuple[JobManager, state.StateStore, Path]) -> None:
    mgr, _, _ = env
    mgr.register("step", _stepwise)
    job = mgr.create("step")
    mgr.run(job.id)  # completed (terminal)
    completed = mgr.get(job.id)
    assert completed is not None and completed.state == "completed"
    with pytest.raises(SteamZeroError) as ei:
        mgr._transition(completed, "running")
    assert ei.value.code == "E-INTERNAL-UNEXPECTED"
