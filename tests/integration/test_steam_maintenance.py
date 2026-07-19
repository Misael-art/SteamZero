# SPDX-License-Identifier: GPL-3.0-or-later
"""Manutenção Steam destrutiva, confinada e recuperável após crash."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.adapters.steam_maintenance import SteamMaintenance
from steamzero.core import fs
from steamzero.core.errors import SteamZeroError


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "Steam"
    (root / "steamapps" / "shadercache" / "10").mkdir(parents=True)
    fs.write_atomic(root / "steamapps" / "shadercache" / "10" / "cache.bin", b"cache")
    fs.write_atomic(root / "steamapps" / "compatdata" / "10" / "save.dat", b"save")
    fs.write_atomic(root / "dumps" / "crash.dmp", b"dump")
    return root


def test_cleanup_frees_only_allowlisted_cache_and_preserves_compatdata(tmp_path: Path) -> None:
    root = _root(tmp_path)
    maintenance = SteamMaintenance(roots=(root,), running_probe=lambda: False)
    snapshot = maintenance.snapshot()
    assert snapshot["totalBytes"] == 9
    assert "compatdata" in snapshot["excluded"]

    plan = maintenance.plan(("shader-cache", "crash-dumps"))
    assert plan["candidateCount"] == 2
    assert plan["confirmPhrase"] == "LIBERAR ESPACO"
    result = maintenance.apply(str(plan["planId"]), str(plan["confirmToken"]), "LIBERAR ESPACO")
    assert result["status"] == "completed"
    assert result["freedBytes"] == 9
    assert not (root / "steamapps" / "shadercache" / "10").exists()
    assert not (root / "dumps" / "crash.dmp").exists()
    assert (root / "steamapps" / "compatdata" / "10" / "save.dat").read_bytes() == b"save"


def test_cleanup_requires_closed_steam_and_typed_phrase(tmp_path: Path) -> None:
    root = _root(tmp_path)
    running = SteamMaintenance(roots=(root,), running_probe=lambda: True)
    with pytest.raises(SteamZeroError) as locked:
        running.plan(("shader-cache",), "10")
    assert locked.value.code == "E-TX-LOCKED"

    maintenance = SteamMaintenance(roots=(root,), running_probe=lambda: False)
    plan = maintenance.plan(("shader-cache",), "10")
    with pytest.raises(SteamZeroError) as confirmation:
        maintenance.apply(str(plan["planId"]), str(plan["confirmToken"]), "sim")
    assert confirmation.value.code == "E-TX-CONFIRM-REQUIRED"
    assert (root / "steamapps" / "shadercache" / "10").exists()


def test_cleanup_rejects_stale_or_symlinked_cache(tmp_path: Path) -> None:
    root = _root(tmp_path)
    maintenance = SteamMaintenance(roots=(root,), running_probe=lambda: False)
    plan = maintenance.plan(("shader-cache",), "10")
    fs.write_atomic(root / "steamapps" / "shadercache" / "10" / "new.bin", b"changed")
    with pytest.raises(SteamZeroError) as stale:
        maintenance.apply(str(plan["planId"]), str(plan["confirmToken"]), "LIBERAR ESPACO")
    assert stale.value.code == "E-TX-STALE-PLAN"

    external = tmp_path / "outside"
    fs.write_atomic(external, b"outside")
    (root / "steamapps" / "shadercache" / "10" / "escape").symlink_to(external)
    with pytest.raises(SteamZeroError) as unsafe:
        maintenance.plan(("shader-cache",), "10")
    assert unsafe.value.code == "E-CONTENT-UNSAFE-PATH"


def test_cleanup_recovers_after_detach_before_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    maintenance = SteamMaintenance(roots=(root,), running_probe=lambda: False)
    plan = maintenance.plan(("shader-cache",), "10")
    original_remove = fs.remove_path

    def crash_after_detach(_path: Path) -> None:
        raise RuntimeError("queda simulada")

    monkeypatch.setattr(fs, "remove_path", crash_after_detach)
    with pytest.raises(RuntimeError, match="queda simulada"):
        maintenance.apply(str(plan["planId"]), str(plan["confirmToken"]), "LIBERAR ESPACO")
    assert maintenance.snapshot("10")["recoveryRequired"] is True

    monkeypatch.setattr(fs, "remove_path", original_remove)
    recovered = maintenance.recover()
    assert recovered["status"] == "recovered"
    assert recovered["operations"][0]["status"] == "completed"
    assert not any((root / "steamapps" / "shadercache").glob(".*.steamzero-delete-*"))
