# SPDX-License-Identifier: GPL-3.0-or-later
"""Provas G-STATE/FI do motor de clock GPU antes de habilitar o transporte host."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.privileged.gpu_effects import GpuClockTransactionEngine


class FakeGpuSysfs:
    """Interpreta os comandos sysfs AMDGPU sobre arquivos descartáveis."""

    def __init__(self, root: Path, *, minimum: int = 200, maximum: int = 1600) -> None:
        self.sys_root = root / "sys"
        self.device = self.sys_root / "class/drm/card1/device"
        self.device.mkdir(parents=True)
        self.clock = self.device / "pp_od_clk_voltage"
        self.level = self.device / "power_dpm_force_performance_level"
        self.lower = 200
        self.upper = 1600
        self.minimum = minimum
        self.maximum = maximum
        self.staged_min = minimum
        self.staged_max = maximum
        self.commits = 0
        self._render()
        self.level.write_text("auto", encoding="utf-8")

    def _render(self) -> None:
        self.clock.write_text(
            "OD_SCLK:\n"
            f"0: {self.minimum}Mhz\n"
            f"1: {self.maximum}Mhz\n"
            "OD_RANGE:\n"
            f"SCLK: {self.lower}Mhz {self.upper}Mhz\n",
            encoding="utf-8",
        )

    @staticmethod
    def write_value(path: Path, data: bytes) -> None:
        path.write_bytes(data)

    def write_command(self, path: Path, data: bytes) -> None:
        assert path == self.clock
        command = data.decode("ascii")
        match = re.fullmatch(r"s ([01]) (\d+)", command)
        if match:
            if match.group(1) == "0":
                self.staged_min = int(match.group(2))
            else:
                self.staged_max = int(match.group(2))
            return
        if command != "c":
            raise OSError("comando inesperado")
        self.minimum, self.maximum = self.staged_min, self.staged_max
        self.commits += 1
        self._render()


def _engine(fake: FakeGpuSysfs, state: Path) -> GpuClockTransactionEngine:
    return GpuClockTransactionEngine(
        sys_root=fake.sys_root,
        state_root=state,
        value_writer=fake.write_value,
        command_writer=fake.write_command,
    )


@pytest.mark.security
def test_gpu_clock_apply_verify_and_rollback_are_journaled(tmp_path: Path) -> None:
    fake = FakeGpuSysfs(tmp_path)
    state = tmp_path / "state"
    engine = _engine(fake, state)

    applied = engine.apply(800)
    assert applied == {
        "operationId": applied["operationId"],
        "state": "applied",
        "mhz": 800,
        "rollbackAvailable": True,
    }
    assert (fake.minimum, fake.maximum) == (800, 800)
    assert fake.level.read_text() == "manual"
    journal_path = state / f"{applied['operationId']}.json"
    assert state.stat().st_mode & 0o777 == 0o700
    assert journal_path.stat().st_mode & 0o777 == 0o600
    journal = json.loads(journal_path.read_text())
    assert journal["beforeMhz"] == [200, 1600]
    assert journal["beforePerformanceLevel"] == "auto"

    assert engine.rollback(applied["operationId"])["state"] == "rolled-back"
    assert (fake.minimum, fake.maximum) == (200, 1600)
    assert fake.level.read_text() == "auto"
    assert engine.rollback(applied["operationId"])["state"] == "noop"


@pytest.mark.security
def test_gpu_clock_rejects_outside_observed_range_without_journal(tmp_path: Path) -> None:
    fake = FakeGpuSysfs(tmp_path)
    state = tmp_path / "state"
    with pytest.raises(SteamZeroError, match="E-PRIV-DENIED"):
        _engine(fake, state).apply(1800)
    assert not state.exists()


@pytest.mark.security
def test_gpu_clock_verify_failure_restores_snapshot(tmp_path: Path) -> None:
    fake = FakeGpuSysfs(tmp_path)
    state = tmp_path / "state"

    def corrupt_first_commit(path: Path, data: bytes) -> None:
        if data == b"c" and fake.commits == 0:
            fake.commits += 1
            return
        fake.write_command(path, data)

    engine = GpuClockTransactionEngine(
        sys_root=fake.sys_root,
        state_root=state,
        value_writer=fake.write_value,
        command_writer=corrupt_first_commit,
    )
    with pytest.raises(SteamZeroError, match="E-TX-VERIFY-FAILED"):
        engine.apply(800)
    assert (fake.minimum, fake.maximum) == (200, 1600)
    assert fake.level.read_text() == "auto"
    assert json.loads(next(state.glob("*.json")).read_text())["state"] == "rolled-back"


@pytest.mark.security
def test_gpu_clock_recovery_repairs_kill_after_manual_mode(tmp_path: Path) -> None:
    fake = FakeGpuSysfs(tmp_path)
    state = tmp_path / "state"
    writes = 0

    def killed_value_write(path: Path, data: bytes) -> None:
        nonlocal writes
        fake.write_value(path, data)
        writes += 1
        if writes == 1:
            raise SystemExit("FI-SIGKILL")

    interrupted = GpuClockTransactionEngine(
        sys_root=fake.sys_root,
        state_root=state,
        value_writer=killed_value_write,
        command_writer=fake.write_command,
    )
    with pytest.raises(SystemExit, match="FI-SIGKILL"):
        interrupted.apply(800)
    assert fake.level.read_text() == "manual"

    blocked = _engine(fake, state)
    with pytest.raises(SteamZeroError, match="E-TX-LOCKED"):
        blocked.apply(1000)
    recovered = blocked.recover()
    assert recovered["state"] == "recovered"
    assert len(recovered["operations"]) == 1
    assert (fake.minimum, fake.maximum) == (200, 1600)
    assert fake.level.read_text() == "auto"
    assert blocked.recover() == {"state": "noop", "operations": []}


@pytest.mark.security
def test_gpu_clock_marks_failed_rollback_and_later_recovers(tmp_path: Path) -> None:
    fake = FakeGpuSysfs(tmp_path)
    state = tmp_path / "state"

    def reject_commit(_path: Path, data: bytes) -> None:
        if data == b"c":
            raise OSError("FI-commit")

    broken = GpuClockTransactionEngine(
        sys_root=fake.sys_root,
        state_root=state,
        value_writer=fake.write_value,
        command_writer=reject_commit,
    )
    with pytest.raises(SteamZeroError, match="E-TX-ROLLBACK-FAILED"):
        broken.apply(800)
    assert json.loads(next(state.glob("*.json")).read_text())["state"] == "rollback-failed"
    assert _engine(fake, state).recover()["state"] == "recovered"


@pytest.mark.security
def test_gpu_clock_rejects_missing_interface_and_invalid_journals(tmp_path: Path) -> None:
    absent = GpuClockTransactionEngine(
        sys_root=tmp_path / "absent",
        state_root=tmp_path / "state",
    )
    with pytest.raises(SteamZeroError, match="E-PRIV-DENIED"):
        absent.apply(800)
    with pytest.raises(SteamZeroError, match="E-API-SCHEMA"):
        absent.rollback("invalid")
    with pytest.raises(SteamZeroError, match="E-STATE-INTEGRITY"):
        absent.rollback("01J000000000000000000000AZ")

    fake = FakeGpuSysfs(tmp_path / "valid")
    state = tmp_path / "bad-state"
    state.mkdir()
    operation_id = "01J000000000000000000000AA"
    (state / f"{operation_id}.json").write_text(
        json.dumps({"operationId": operation_id, "state": "closed"}), encoding="utf-8"
    )
    engine = _engine(fake, state)
    with pytest.raises(SteamZeroError, match="E-STATE-INTEGRITY"):
        engine.rollback(operation_id)

    snapshot_id = "01J000000000000000000000AB"
    (state / f"{snapshot_id}.json").write_text(
        json.dumps({"operationId": snapshot_id, "state": "pending", "beforeMhz": []}),
        encoding="utf-8",
    )
    with pytest.raises(SteamZeroError, match="E-STATE-INTEGRITY"):
        engine.rollback(snapshot_id)


@pytest.mark.security
@pytest.mark.parametrize(
    "clock,level",
    [
        ("invalid", "auto"),
        ("OD_SCLK:\n0: 50Mhz\n1: 6000Mhz\nOD_RANGE:\nSCLK: 50Mhz 6000Mhz", "auto"),
        ("OD_SCLK:\n0: 200Mhz\n1: 1600Mhz\nOD_RANGE:\nSCLK: 200Mhz 1600Mhz", "evil"),
    ],
)
def test_gpu_clock_rejects_malformed_capability(tmp_path: Path, clock: str, level: str) -> None:
    fake = FakeGpuSysfs(tmp_path)
    fake.clock.write_text(clock, encoding="utf-8")
    fake.level.write_text(level, encoding="utf-8")
    with pytest.raises(SteamZeroError, match="E-PRIV-DENIED"):
        _engine(fake, tmp_path / "state").apply(800)
