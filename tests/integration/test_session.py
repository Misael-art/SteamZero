# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do Session Manager (F-SD-01/F-SV-02): suspend/resume, FM-08/FM-09/FI-09."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from steamzero.core import fs, state
from steamzero.domain.session import SessionManager
from steamzero.jobs.manager import JobContext, JobManager
from steamzero.jobs.models import Job


class FakeSessionPort:
    def __init__(
        self, *, launch_ok: bool = True, flush_ok: bool = True, ignore_steps: int = 0
    ) -> None:
        self._launch_ok = launch_ok
        self._flush_ok = flush_ok
        self._ignore = ignore_steps
        self._steps = 0
        self._alive = True
        self.actions: list[str] = []

    def launch(self, game_id: str) -> bool:
        self.actions.append(f"launch:{game_id}")
        return self._launch_ok

    def is_alive(self) -> bool:
        return self._alive

    def flush_save(self) -> bool:
        self.actions.append("flush")
        return self._flush_ok

    def signal_close(self) -> None:
        self.actions.append("signal_close")
        self._step()

    def terminate(self) -> None:
        self.actions.append("terminate")
        self._step()

    def kill(self) -> None:
        self.actions.append("kill")
        self._alive = False

    def _step(self) -> None:
        self._steps += 1
        if self._steps > self._ignore:
            self._alive = False


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[state.StateStore]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    fs.ensure_state_layout()
    s = state.open_state()
    yield s
    s.close()


def test_launch_running(store: state.StateStore) -> None:
    mgr = SessionManager(FakeSessionPort(), store)
    session = mgr.launch("game-1")
    assert session.state == "running"
    assert mgr.is_active() is True
    persisted = store.latest_game_session("game-1")
    assert persisted is not None
    assert persisted["id"] == session.id
    assert persisted["state"] == "running"
    assert [event["kind"] for event in store.events_since(0)] == [
        "session.state",
        "session.state",
        "session.state",
    ]


def test_launch_failure(store: state.StateStore) -> None:
    mgr = SessionManager(FakeSessionPort(launch_ok=False), store)
    session = mgr.launch("game-1")
    assert session.state == "failed"


def test_suspend_resume_with_checkpoint(store: state.StateStore) -> None:
    port = FakeSessionPort()
    mgr = SessionManager(port, store)
    mgr.launch("g")
    s = mgr.suspend()
    assert s.state == "suspended"
    assert len(s.checkpoints) == 1  # AC-SV-02: suspensão dispara checkpoint
    assert "flush" in port.actions
    r = mgr.resume()
    assert r.state == "running"
    assert r.last_warning is None


def test_suspend_flush_timeout_uses_fallback(store: state.StateStore) -> None:
    mgr = SessionManager(FakeSessionPort(flush_ok=False), store)
    mgr.launch("g")
    s = mgr.suspend()
    assert s.state == "suspended"
    assert s.last_warning == "E-SAVES-FLUSH-TIMEOUT"
    assert s.checkpoints[-1]["origin"] == "pre-flush-fallback"


def test_suspend_pauses_running_jobs(store: state.StateStore) -> None:
    # FI-09: suspensão pausa jobs em ponto de segurança
    jobs = JobManager(store)

    def looper(job: Job, ctx: JobContext) -> None:
        for _ in range(3):
            ctx.safepoint()

    jobs.register("loop", looper)
    job = jobs.create("loop")
    # força o job a 'running' no store para a suspensão encontrá-lo
    j = jobs.get(job.id)
    assert j is not None
    j.state = "running"
    store.save_job(j.to_row())

    mgr = SessionManager(FakeSessionPort(), store, job_manager=jobs)
    mgr.launch("g")
    mgr.suspend()
    jobs.request_resume(job.id)  # limpa pausa p/ verificar que foi pausado
    # o controle de pausa foi setado durante a suspensão
    assert job.id in jobs._controls


def test_resume_degraded_when_process_died(store: state.StateStore) -> None:
    port = FakeSessionPort()
    mgr = SessionManager(port, store)
    mgr.launch("g")
    mgr.suspend()
    port._alive = False  # processo morreu durante a suspensão
    r = mgr.resume()
    assert r.state == "failed"
    assert r.last_warning == "E-SESSION-RESUME-DEGRADED"
    persisted = store.latest_game_session("g")
    assert persisted is not None
    assert persisted["failure_code"] == "E-SESSION-RESUME-DEGRADED"


def test_close_cooperative(store: state.StateStore) -> None:
    port = FakeSessionPort(ignore_steps=0)  # morre no signal_close
    mgr = SessionManager(port, store)
    mgr.launch("g")
    s = mgr.close()
    assert s.state == "closed"
    assert "kill" not in port.actions


def test_close_needs_sigterm(store: state.StateStore) -> None:
    port = FakeSessionPort(ignore_steps=1)  # ignora semântico, morre no SIGTERM
    mgr = SessionManager(port, store)
    mgr.launch("g")
    s = mgr.close()
    assert s.state == "closed"
    assert "terminate" in port.actions
    assert "kill" not in port.actions


def test_close_escalates_to_kill_with_confirmation(store: state.StateStore) -> None:
    # FM-08: processo trava; SIGKILL só com confirmação
    port = FakeSessionPort(ignore_steps=5)  # ignora tudo menos kill
    mgr = SessionManager(port, store)
    mgr.launch("g")
    s = mgr.close()  # sem allow_kill
    assert s.state == "closing"
    assert s.needs_kill_confirmation is True
    assert "kill" not in port.actions
    s = mgr.close(allow_kill=True)  # confirmado
    assert s.state == "closed"
    assert "kill" in port.actions


def test_close_preserves_timeline_flush_first(store: state.StateStore) -> None:
    port = FakeSessionPort()
    mgr = SessionManager(port, store)
    mgr.launch("g")
    mgr.close()
    assert port.actions.index("flush") < port.actions.index("signal_close")


def test_playtime_excludes_suspended_interval_and_is_persisted(
    store: state.StateStore,
) -> None:
    ticks = iter((10.0, 40.9, 100.0, 169.8))
    mgr = SessionManager(FakeSessionPort(), store, monotonic=lambda: next(ticks))

    mgr.launch("g")
    mgr.suspend()
    mgr.resume()
    mgr.close()

    session = store.latest_game_session("g")
    assert session is not None
    assert session["played_seconds"] == 100
    assert session["duration_source"] == "observed-monotonic"
