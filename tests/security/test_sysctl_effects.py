# SPDX-License-Identifier: GPL-3.0-or-later
"""Provas transacionais do efetor sysctl antes de publicar transporte mutável."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.privileged.host_effects import transaction_lock
from steamzero.privileged.sysctl_effects import SysctlTransactionEngine


def _proc_sys(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "proc/sys"
    vm = root / "vm"
    vm.mkdir(parents=True)
    swappiness = vm / "swappiness"
    compaction = vm / "compaction_proactiveness"
    swappiness.write_text("60", encoding="utf-8")
    compaction.write_text("20", encoding="utf-8")
    return root, swappiness, compaction


def _write(path: Path, data: bytes) -> None:
    path.write_bytes(data)


@pytest.mark.security
def test_sysctl_apply_verify_and_rollback_are_journaled(tmp_path: Path) -> None:
    proc, swappiness, _compaction = _proc_sys(tmp_path)
    state = tmp_path / "state"
    engine = SysctlTransactionEngine(proc_sys_root=proc, state_root=state, writer=_write)

    applied = engine.apply("vm.swappiness", 10)
    assert applied["state"] == "applied"
    assert applied["key"] == "vm.swappiness"
    assert swappiness.read_text() == "10"
    journal_path = state / f"{applied['operationId']}.json"
    assert state.stat().st_mode & 0o777 == 0o700
    assert journal_path.stat().st_mode & 0o777 == 0o600
    assert json.loads(journal_path.read_text())["beforeValue"] == 60

    assert engine.rollback(applied["operationId"])["state"] == "rolled-back"
    assert swappiness.read_text() == "60"
    assert engine.rollback(applied["operationId"])["state"] == "noop"


@pytest.mark.security
@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("kernel.core_pattern", 1),
        ("vm.swappiness", 201),
        ("vm.compaction_proactiveness", -1),
    ],
)
def test_sysctl_rejects_non_allowlisted_or_out_of_range(
    tmp_path: Path, key: str, value: int
) -> None:
    proc, _swappiness, _compaction = _proc_sys(tmp_path)
    engine = SysctlTransactionEngine(proc_sys_root=proc, state_root=tmp_path / "state")
    with pytest.raises(SteamZeroError, match="E-PRIV-DENIED"):
        engine.apply(key, value)


@pytest.mark.security
def test_sysctl_verify_failure_restores_previous_value(tmp_path: Path) -> None:
    proc, swappiness, _compaction = _proc_sys(tmp_path)
    state = tmp_path / "state"

    def corrupt_desired(path: Path, data: bytes) -> None:
        path.write_bytes(b"11" if data == b"10" else data)

    engine = SysctlTransactionEngine(proc_sys_root=proc, state_root=state, writer=corrupt_desired)
    with pytest.raises(SteamZeroError, match="E-TX-VERIFY-FAILED"):
        engine.apply("vm.swappiness", 10)
    assert swappiness.read_text() == "60"
    assert json.loads(next(state.glob("*.json")).read_text())["state"] == "rolled-back"


@pytest.mark.security
def test_sysctl_recovery_repairs_interrupted_write(tmp_path: Path) -> None:
    proc, swappiness, _compaction = _proc_sys(tmp_path)
    state = tmp_path / "state"

    def killed(path: Path, data: bytes) -> None:
        path.write_bytes(data)
        raise SystemExit("FI-SIGKILL")

    interrupted = SysctlTransactionEngine(proc_sys_root=proc, state_root=state, writer=killed)
    with pytest.raises(SystemExit, match="FI-SIGKILL"):
        interrupted.apply("vm.swappiness", 10)
    assert swappiness.read_text() == "10"

    healthy = SysctlTransactionEngine(proc_sys_root=proc, state_root=state, writer=_write)
    with pytest.raises(SteamZeroError, match="E-TX-LOCKED"):
        healthy.apply("vm.compaction_proactiveness", 30)
    assert healthy.recover()["state"] == "recovered"
    assert swappiness.read_text() == "60"
    assert healthy.recover() == {"state": "noop", "operations": []}


@pytest.mark.security
def test_sysctl_failed_rollback_is_locked_until_recovery(tmp_path: Path) -> None:
    proc, _swappiness, _compaction = _proc_sys(tmp_path)
    state = tmp_path / "state"

    def fail(_path: Path, _data: bytes) -> None:
        raise OSError("FI-write")

    broken = SysctlTransactionEngine(proc_sys_root=proc, state_root=state, writer=fail)
    with pytest.raises(SteamZeroError, match="E-TX-ROLLBACK-FAILED"):
        broken.apply("vm.swappiness", 10)
    assert json.loads(next(state.glob("*.json")).read_text())["state"] == "rollback-failed"
    assert (
        SysctlTransactionEngine(proc_sys_root=proc, state_root=state, writer=_write).recover()[
            "state"
        ]
        == "recovered"
    )


@pytest.mark.security
def test_sysctl_rejects_invalid_journal_snapshot_and_interface(tmp_path: Path) -> None:
    proc, swappiness, _compaction = _proc_sys(tmp_path)
    state = tmp_path / "state"
    engine = SysctlTransactionEngine(proc_sys_root=proc, state_root=state, writer=_write)
    with pytest.raises(SteamZeroError, match="E-API-SCHEMA"):
        engine.rollback("invalid")
    with pytest.raises(SteamZeroError, match="E-STATE-INTEGRITY"):
        engine.rollback("01J000000000000000000000AZ")

    operation_id = "01J000000000000000000000AA"
    state.mkdir()
    (state / f"{operation_id}.json").write_text(
        json.dumps({"operationId": operation_id, "state": "pending", "key": "evil"}),
        encoding="utf-8",
    )
    with pytest.raises(SteamZeroError, match="E-STATE-INTEGRITY"):
        engine.rollback(operation_id)

    swappiness.unlink()
    with pytest.raises(SteamZeroError, match="E-PRIV-DENIED"):
        SysctlTransactionEngine(proc_sys_root=proc, state_root=tmp_path / "other").apply(
            "vm.swappiness", 10
        )


@pytest.mark.security
def test_transaction_lock_refuses_concurrency_and_symlink(tmp_path: Path) -> None:
    state = tmp_path / "state"
    with (
        transaction_lock(state),
        pytest.raises(SteamZeroError, match="E-TX-LOCKED"),
        transaction_lock(state),
    ):
        pytest.fail("lock concorrente não deveria ser adquirido")

    other = tmp_path / "unsafe"
    lock_path = tmp_path / ".unsafe.lock"
    lock_path.symlink_to(tmp_path / "target")
    with pytest.raises(SteamZeroError, match="E-TX-LOCKED"), transaction_lock(other):
        pytest.fail("lock symlink não deveria ser seguido")
