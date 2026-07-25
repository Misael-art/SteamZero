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


def test_doctor_runs_and_returns_data_and_checks(tmp_path: Path) -> None:
    import os

    os.environ["XDG_STATE_HOME"] = str(tmp_path / "state")
    data, checks = run_doctor()
    assert "version" in data
    assert "stateHome" in data
    assert "schemaVersion" in data
    assert len(checks) >= 3
    assert any(c["name"] == "runtime.python" for c in checks)
    assert any(c["name"] == "state.layout" for c in checks)
    assert any(c["name"] == "recovery.pending" for c in checks)
    assert any(c["name"] == "state.db.integrity" for c in checks)


def test_doctor_handles_state_store_failure(tmp_path: Path) -> None:
    import os

    os.environ["XDG_STATE_HOME"] = str(tmp_path / "state")
    with patch("steamzero.diagnostics.doctor.StateStore") as mock_store:
        mock_store.side_effect = RuntimeError("db corrupt")
        data, checks = run_doctor()
    assert data["schemaVersion"] == -1
    fail_checks = [c for c in checks if c["name"] == "state.db.integrity"]
    assert any(c["status"] == "fail" for c in fail_checks)
