# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from steamzero.diagnostics.doctor import _pending_operations, run_doctor


def test_pending_operations_returns_zero_when_no_journal_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "nonexistent"))
    assert _pending_operations() == 0


def test_doctor_runs_and_returns_data_and_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    data, checks = run_doctor()
    assert "version" in data
    assert "stateHome" in data
    assert "schemaVersion" in data
    assert len(checks) >= 3
    assert any(c["name"] == "runtime.python" for c in checks)
    assert any(c["name"] == "state.layout" for c in checks)
    assert any(c["name"] == "recovery.pending" for c in checks)
    assert any(c["name"] == "state.db.integrity" for c in checks)


def test_doctor_handles_state_store_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    with patch("steamzero.diagnostics.doctor.StateStore") as mock_store:
        mock_store.side_effect = RuntimeError("db corrupt")
        data, checks = run_doctor()
    assert data["schemaVersion"] == -1
    fail_checks = [c for c in checks if c["name"] == "state.db.integrity"]
    assert any(c["status"] == "fail" for c in fail_checks)


def test_doctor_reports_g25_audit_checks_when_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # G25: estado limpo -> os 4 novos checks passam e os contadores vão a data.
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    data, checks = run_doctor()
    for name in ("jobs.stale", "staging.orphan", "backup.orphan", "journal.orphan"):
        c = next(c for c in checks if c["name"] == name)
        assert c["status"] == "pass", (name, c)
    assert data["staleJobs"] == 0
    assert data["orphanStaging"] == 0
    assert data["orphanBackups"] == 0
    assert data["orphanJournals"] == 0


def test_doctor_warns_on_stale_jobs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # G25: um job running (stalado) faz jobs.stale virar warn — elimina o falso
    # verde operacional que motivou o G25.
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    from steamzero.core import fs as core_fs
    from steamzero.core import state as core_state
    from steamzero.jobs.manager import JobManager

    core_fs.ensure_state_layout()
    store = core_state.open_state()
    try:
        store.migrate()
        mgr = JobManager(store)
        stale = mgr.create("media.global")
        stale.state = "running"
        store.save_job(stale.to_row())
    finally:
        store.close()

    data, checks = run_doctor()
    c = next(c for c in checks if c["name"] == "jobs.stale")
    assert c["status"] == "warn"
    assert data["staleJobs"] == 1


def test_doctor_warns_on_orphan_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # G25: staging sem operação no banco é órfão -> staging.orphan warn.
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    from steamzero.core import fs as core_fs
    from steamzero.core import paths as core_paths

    core_fs.ensure_state_layout()
    (core_paths.staging_dir() / "op-sem-banco").mkdir(parents=True, exist_ok=True)

    data, checks = run_doctor()
    c = next(c for c in checks if c["name"] == "staging.orphan")
    assert c["status"] == "warn"
    assert data["orphanStaging"] >= 1
