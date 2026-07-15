# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes de core.lock — lease+dono, quebra de órfão (FI-15), sem deadlock."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from steamzero.core import fs, lock, paths
from steamzero.core.errors import SteamZeroError


@pytest.fixture
def state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    fs.ensure_state_layout()
    return paths.state_home()


def test_acquire_release_basic(state: Path) -> None:
    lk = lock.ResourceLock("component:duckstation", job_id="J1")
    lk.acquire()
    assert lk.broke_orphan is None
    lk.release()
    # após release, outro pode adquirir
    with lock.ResourceLock("component:duckstation"):
        pass


def test_second_acquire_live_owner_blocks(state: Path) -> None:
    with lock.ResourceLock("lib:psx", job_id="J1"):
        with pytest.raises(SteamZeroError) as ei:
            lock.ResourceLock("lib:psx", job_id="J2").acquire()
        assert ei.value.code == "E-TX-LOCKED"


def test_orphan_by_dead_owner_is_broken(state: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # dono "morto": força _pid_alive=False
    first = lock.ResourceLock("saves:game1", job_id="DEAD")
    first.acquire()
    monkeypatch.setattr(lock, "_pid_alive", lambda pid: False)
    second = lock.ResourceLock("saves:game1", job_id="NEW")
    second.acquire()
    assert second.broke_orphan is not None
    assert second.broke_orphan.job_id == "DEAD"
    second.release()


def test_orphan_by_expired_lease_is_broken(state: Path) -> None:
    resource = "bios:psx"
    stale = lock.LockInfo(
        resource=resource,
        pid=1,  # vivo, mas...
        job_id="OLD",
        acquired_at=time.time() - 10_000,
        lease_seconds=1.0,  # ...lease expirado
    )
    path = lock._lock_path(resource)
    fs.ensure_dir(path.parent)
    fs.write_atomic_text(path, stale.to_json())
    lk = lock.ResourceLock(resource, job_id="NEW")
    lk.acquire()
    assert lk.broke_orphan is not None
    assert lk.broke_orphan.job_id == "OLD"


def test_corrupt_lock_treated_as_orphan(state: Path) -> None:
    resource = "media:g"
    path = lock._lock_path(resource)
    fs.ensure_dir(path.parent)
    fs.write_atomic_text(path, "{lixo não-json")
    with lock.ResourceLock(resource):  # não deve deadlockar
        pass


def test_renew_updates_lease(state: Path) -> None:
    lk = lock.ResourceLock("component:x", lease_seconds=100)
    lk.acquire()
    info1 = lock.ResourceLock("component:x")._read()
    time.sleep(0.01)
    lk.renew()
    info2 = lock.ResourceLock("component:x")._read()
    assert info1 is not None and info2 is not None
    assert info2.acquired_at >= info1.acquired_at
    lk.release()


def test_lockinfo_is_orphan_logic() -> None:
    info = lock.LockInfo("r", pid=1, job_id=None, acquired_at=1000.0, lease_seconds=60.0)
    assert info.is_orphan(now=2000.0)  # expirado
    # não expirado + dono vivo (pid=1 existe) => não órfão
    assert not info.is_orphan(now=1030.0)
