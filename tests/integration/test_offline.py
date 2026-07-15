# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes offline-first (F-SD-04, AC-OF-01): operações remotas ficam blocked."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from steamzero.core import fs, state
from steamzero.diagnostics.doctor import run_doctor
from steamzero.jobs.manager import JobContext, JobManager
from steamzero.jobs.models import Job


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[state.StateStore]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    fs.ensure_state_layout()
    s = state.open_state()
    yield s
    s.close()


def _noop(job: Job, ctx: JobContext) -> dict[str, bool]:
    return {"ok": True}


def test_remote_job_blocked_when_offline(store: state.StateStore) -> None:
    mgr = JobManager(store, network_available=lambda: False)
    mgr.register("sync", _noop)
    job = mgr.create("sync", constraints={"requiresNetwork": True})
    done = mgr.run(job.id)
    assert done.state == "blocked"
    assert done.error_code == "E-SUPPLY-OFFLINE"


def test_remote_job_runs_when_online(store: state.StateStore) -> None:
    online = {"net": False}
    mgr = JobManager(store, network_available=lambda: online["net"])
    mgr.register("sync", _noop)
    job = mgr.create("sync", constraints={"requiresNetwork": True})
    assert mgr.run(job.id).state == "blocked"  # offline: enfileirado
    online["net"] = True  # rede volta
    # o job bloqueado pode ser retomado quando a rede volta
    blocked = mgr.get(job.id)
    assert blocked is not None
    blocked.state = "queued"
    store.save_job(blocked.to_row())
    assert mgr.run(job.id).state == "completed"


def test_local_operations_work_offline(store: state.StateStore) -> None:
    # AC-OF-01: doctor e operações locais funcionam sem rede (não há I/O de rede no núcleo)
    _data, checks = run_doctor()
    assert {c["name"] for c in checks} >= {"runtime.python", "state.db.integrity"}
    # job puramente local roda offline
    mgr = JobManager(store, network_available=lambda: False)
    mgr.register("local", _noop)
    job = mgr.create("local")  # sem requiresNetwork
    assert mgr.run(job.id).state == "completed"
