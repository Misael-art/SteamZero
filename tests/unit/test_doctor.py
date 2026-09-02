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


def test_doctor_publishes_recovery_guidance_for_stale_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    from steamzero.core import fs as core_fs
    from steamzero.core import state as core_state
    from steamzero.jobs.manager import JobManager

    core_fs.ensure_state_layout()
    store = core_state.open_state()
    try:
        store.migrate()
        stale = JobManager(store).create("media.global")
        stale.state = "running"
        store.save_job(stale.to_row())
    finally:
        store.close()

    _data, checks = run_doctor()
    check = next(item for item in checks if item["name"] == "jobs.stale")
    assert check["status"] == "warn"
    assert check["severity"] == "warning"
    assert check["what"]
    assert check["impact"]
    assert "Tarefas" in check["manualAction"]
    assert check["action"] == {
        "kind": "navigate",
        "target": "system.operations",
        "label": "Abrir tarefas",
        "enabled": True,
        "requiresConfirmation": False,
    }


def test_doctor_marks_operator_only_recovery_without_fake_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    with patch("steamzero.diagnostics.doctor.boot_status") as mock:
        mock.return_value = {
            "state": "backoff",
            "configured": True,
            "permissionDenied": False,
            "reason": "falhas repetidas",
            "backoff": True,
        }
        _data, checks = run_doctor()

    check = next(item for item in checks if item["name"] == "boot.direct")
    assert check["status"] == "warn"
    assert check["action"] is None
    assert "operador" in check["manualAction"]


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


def test_doctor_reports_boot_direct_check(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # boot.direct existe no envelope e publica o estado lido de steam_boot.status.
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    with patch("steamzero.diagnostics.doctor.boot_status") as mock:
        mock.return_value = {
            "state": "ready",
            "configured": True,
            "permissionDenied": False,
            "reason": "Entrada SteamZero pronta; falha retorna ao greeter/Plasma.",
            "backoff": False,
        }
        data, checks = run_doctor()
    c = next(c for c in checks if c["name"] == "boot.direct")
    assert c["status"] == "pass"
    assert data["bootDirect"] == "ready"
    assert data["bootBackoff"] is False


@pytest.mark.parametrize(
    ("state", "backoff", "permission_denied", "expected"),
    [
        ("ready", False, False, "pass"),  # ativado e saudável
        ("available", False, False, "pass"),  # não ativado, estado legítimo
        ("backoff", True, False, "warn"),  # autologin suspenso após falhas
        ("degraded", False, False, "warn"),  # erro de health; causa visível
        ("unknown", False, True, "warn"),  # permissionDenied: nunca falso negativo
    ],
)
def test_doctor_boot_direct_status_mapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    backoff: bool,
    permission_denied: bool,
    expected: str,
) -> None:
    # boot.direct nunca dá falso verde (backoff/degraded warn) nem falso negativo
    # (permissionDenied vira warn explícito, não fail). ADR-0020 / AGENTS.md §8.
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    with patch("steamzero.diagnostics.doctor.boot_status") as mock:
        mock.return_value = {
            "state": state,
            "configured": state == "ready",
            "permissionDenied": permission_denied,
            "reason": "motivo de teste",
            "backoff": backoff,
        }
        _data, checks = run_doctor()
    c = next(c for c in checks if c["name"] == "boot.direct")
    assert c["status"] == expected


def test_doctor_boot_direct_never_crashes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # doctor nunca crashe: se steam_boot.status levantar, o check vira warn.
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    with patch("steamzero.diagnostics.doctor.boot_status") as mock:
        mock.side_effect = RuntimeError("boom")
        _data, checks = run_doctor()
    c = next(c for c in checks if c["name"] == "boot.direct")
    assert c["status"] == "warn"
    assert "boom" in c["message"]


def test_doctor_service_generation_fails_when_daemon_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G38: current=a44 e daemon=a42 não podem passar como generation=pass."""
    from steamzero.adapters.release_convergence import ConvergenceReport, ConvergenceState

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    report = ConvergenceReport(
        ConvergenceState.PENDING,
        (
            "current aponta para '0.1.0a44-07802589e985', "
            "mas o daemon responde por '0.1.0a42-39bd325cee60'"
        ),
        activated_release="0.1.0a44-07802589e985",
        daemon_release="0.1.0a42-39bd325cee60",
        code="E-HOST-DAEMON-PENDING",
    )
    with (
        patch("steamzero.diagnostics.doctor.read_quarantine", return_value=None),
        patch("steamzero.diagnostics.doctor.observe", return_value=report),
    ):
        _data, checks = run_doctor()
    c = next(c for c in checks if c["name"] == "service.generation")
    assert c["status"] == "fail"
    assert "0.1.0a44" in c["message"]
    assert "0.1.0a42" in c["message"]
    assert "E-HOST-DAEMON-PENDING" in c["message"]


def test_doctor_service_generation_passes_when_converged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from steamzero.adapters.release_convergence import ConvergenceReport, ConvergenceState

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    report = ConvergenceReport(
        ConvergenceState.CONVERGED,
        "o daemon responde na release ativada '0.1.0a44-07802589e985'",
        activated_release="0.1.0a44-07802589e985",
        daemon_release="0.1.0a44-07802589e985",
    )
    with (
        patch("steamzero.diagnostics.doctor.read_quarantine", return_value=None),
        patch("steamzero.diagnostics.doctor.observe", return_value=report),
    ):
        _data, checks = run_doctor()
    c = next(c for c in checks if c["name"] == "service.generation")
    assert c["status"] == "pass"
    assert "0.1.0a44" in c["message"]
