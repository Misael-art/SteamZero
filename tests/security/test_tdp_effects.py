# SPDX-License-Identifier: GPL-3.0-or-later
"""Provas G-STATE/FI do motor TDP antes de habilitar o transporte host."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.privileged.host_effects import TdpTransactionEngine


def _sysfs(tmp_path: Path) -> tuple[Path, Path]:
    sys_root = tmp_path / "sys"
    hwmon = sys_root / "class/hwmon/hwmon4"
    hwmon.mkdir(parents=True)
    values = {
        "name": "amdgpu",
        "power1_label": "slowPPT",
        "power2_label": "fastPPT",
        "power1_cap": "15000000",
        "power2_cap": "15000000",
        "power1_cap_max": "29000000",
        "power2_cap_max": "30000000",
    }
    for name, value in values.items():
        (hwmon / name).write_text(value, encoding="utf-8")
    return sys_root, hwmon


def _write(path: Path, data: bytes) -> None:
    path.write_bytes(data)


@pytest.mark.security
def test_tdp_apply_verify_and_rollback_are_journaled(tmp_path: Path) -> None:
    sys_root, hwmon = _sysfs(tmp_path)
    state_root = tmp_path / "state"
    # Exercita o writer real sobre arquivos descartáveis, nunca sobre /sys do host.
    engine = TdpTransactionEngine(sys_root=sys_root, state_root=state_root)

    applied = engine.apply(10)
    assert applied["state"] == "applied"
    assert (hwmon / "power1_cap").read_text() == "10000000"
    assert (hwmon / "power2_cap").read_text() == "10000000"
    journal_path = state_root / f"{applied['operationId']}.json"
    assert journal_path.stat().st_mode & 0o777 == 0o600
    journal = json.loads(journal_path.read_text())
    assert journal["beforeMicroWatts"] == [15_000_000, 15_000_000]

    rolled = engine.rollback(applied["operationId"])
    assert rolled["state"] == "rolled-back"
    assert (hwmon / "power1_cap").read_text() == "15000000"
    assert (hwmon / "power2_cap").read_text() == "15000000"
    assert engine.rollback(applied["operationId"])["state"] == "noop"


@pytest.mark.security
def test_tdp_rejects_value_above_observed_capability_without_journal(tmp_path: Path) -> None:
    sys_root, _hwmon = _sysfs(tmp_path)
    state_root = tmp_path / "state"
    engine = TdpTransactionEngine(sys_root=sys_root, state_root=state_root, writer=_write)
    with pytest.raises(SteamZeroError, match="E-PRIV-DENIED"):
        engine.apply(30)
    assert not state_root.exists()


@pytest.mark.security
def test_tdp_verify_failure_restores_previous_values(tmp_path: Path) -> None:
    sys_root, hwmon = _sysfs(tmp_path)

    def corrupt_desired(path: Path, data: bytes) -> None:
        path.write_bytes(b"9000000" if path.name == "power2_cap" and data == b"10000000" else data)

    engine = TdpTransactionEngine(
        sys_root=sys_root,
        state_root=tmp_path / "state",
        writer=corrupt_desired,
    )
    with pytest.raises(SteamZeroError, match="E-TX-VERIFY-FAILED"):
        engine.apply(10)
    assert (hwmon / "power1_cap").read_text() == "15000000"
    assert (hwmon / "power2_cap").read_text() == "15000000"
    journal = next((tmp_path / "state").glob("*.json"))
    assert json.loads(journal.read_text())["state"] == "rolled-back"


@pytest.mark.security
def test_tdp_recovery_repairs_kill_between_rails(tmp_path: Path) -> None:
    sys_root, hwmon = _sysfs(tmp_path)
    state_root = tmp_path / "state"
    writes = 0

    def killed_after_first(path: Path, data: bytes) -> None:
        nonlocal writes
        path.write_bytes(data)
        writes += 1
        if writes == 1:
            raise SystemExit("FI-SIGKILL")

    interrupted = TdpTransactionEngine(
        sys_root=sys_root,
        state_root=state_root,
        writer=killed_after_first,
    )
    with pytest.raises(SystemExit, match="FI-SIGKILL"):
        interrupted.apply(10)
    assert (hwmon / "power1_cap").read_text() == "10000000"
    assert (hwmon / "power2_cap").read_text() == "15000000"

    blocked = TdpTransactionEngine(sys_root=sys_root, state_root=state_root, writer=_write)
    with pytest.raises(SteamZeroError, match="E-TX-LOCKED"):
        blocked.apply(12)
    recovered = blocked.recover()
    assert recovered["state"] == "recovered"
    assert len(recovered["operations"]) == 1
    assert (hwmon / "power1_cap").read_text() == "15000000"
    assert (hwmon / "power2_cap").read_text() == "15000000"
    assert blocked.recover() == {"state": "noop", "operations": []}


@pytest.mark.security
def test_tdp_rejects_missing_interfaces_and_invalid_journals(tmp_path: Path) -> None:
    absent = TdpTransactionEngine(
        sys_root=tmp_path / "absent",
        state_root=tmp_path / "state-absent",
        writer=_write,
    )
    with pytest.raises(SteamZeroError, match="E-PRIV-DENIED"):
        absent.apply(10)
    with pytest.raises(SteamZeroError, match="E-API-SCHEMA"):
        absent.rollback("not-an-operation")
    with pytest.raises(SteamZeroError, match="E-STATE-INTEGRITY"):
        absent.rollback("01J000000000000000000000AZ")

    operation_id = "01J000000000000000000000AA"
    state_root = tmp_path / "state-invalid"
    state_root.mkdir()
    (state_root / f"{operation_id}.json").write_text(
        json.dumps({"operationId": "01J000000000000000000000AB", "state": "pending"}),
        encoding="utf-8",
    )
    invalid = TdpTransactionEngine(
        sys_root=tmp_path / "absent",
        state_root=state_root,
        writer=_write,
    )
    with pytest.raises(SteamZeroError, match="E-STATE-INTEGRITY"):
        invalid.rollback(operation_id)

    closed_id = "01J000000000000000000000AC"
    (state_root / f"{closed_id}.json").write_text(
        json.dumps({"operationId": closed_id, "state": "closed"}),
        encoding="utf-8",
    )
    with pytest.raises(SteamZeroError, match="E-STATE-INTEGRITY"):
        invalid.rollback(closed_id)


@pytest.mark.security
def test_tdp_rejects_unreadable_current_value(tmp_path: Path) -> None:
    sys_root, hwmon = _sysfs(tmp_path)
    (hwmon / "power1_cap").write_text("invalid", encoding="utf-8")
    engine = TdpTransactionEngine(
        sys_root=sys_root,
        state_root=tmp_path / "state",
        writer=_write,
    )
    with pytest.raises(SteamZeroError, match="E-PRIV-DENIED"):
        engine.apply(10)
