# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do Storage Monitor (F-SD-03): microSD por UUID, FM-06/AC-SD-02/FI-07."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from steamzero.core import state
from steamzero.core.errors import SteamZeroError
from steamzero.domain.storage import StorageMonitor, VolumeInfo


class FakeStoragePort:
    def __init__(self) -> None:
        self.volumes: list[VolumeInfo] = []

    def list_volumes(self) -> list[VolumeInfo]:
        return list(self.volumes)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[state.StateStore]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    s = state.open_state()
    yield s
    s.close()


def _sd(mount: str | None) -> VolumeInfo:
    return VolumeInfo(
        uuid="1234-ABCD", label="SDCARD", fstype="exfat", role="microsd", mountpoint=mount
    )


def test_scan_marks_mounted(store: state.StateStore, tmp_path: Path) -> None:
    mp = tmp_path / "run" / "media" / "sd"
    mp.mkdir(parents=True)
    port = FakeStoragePort()
    port.volumes = [_sd(str(mp))]
    StorageMonitor(port, store).scan()
    assert store.get_volume_by_uuid("1234-ABCD")["state"] == "mounted"


def test_removal_marks_missing_and_blocks_write(store: state.StateStore, tmp_path: Path) -> None:
    mp = tmp_path / "media" / "sd"
    mp.mkdir(parents=True)
    port = FakeStoragePort()
    port.volumes = [_sd(str(mp))]
    mon = StorageMonitor(port, store)
    mon.scan()
    # antes: escrita resolve normalmente
    dest = mon.resolve_write_path("1234-ABCD", "saves/game.sav")
    assert str(dest).startswith(str(mp))

    # remove o microSD (mountpoint fantasma continua existindo como dir vazio)
    port.volumes = []
    mon.scan()
    assert store.get_volume_by_uuid("1234-ABCD")["state"] == "missing"  # unavailable
    assert mp.exists()  # o dir de mountpoint pode continuar existindo
    with pytest.raises(SteamZeroError) as ei:
        mon.resolve_write_path("1234-ABCD", "saves/game.sav")  # zero escrita no fantasma
    assert ei.value.code == "E-STORAGE-MISSING"


def test_reinsert_restores_by_uuid(store: state.StateStore, tmp_path: Path) -> None:
    mp = tmp_path / "media" / "sd"
    mp.mkdir(parents=True)
    port = FakeStoragePort()
    mon = StorageMonitor(port, store)
    port.volumes = [_sd(str(mp))]
    mon.scan()
    port.volumes = []
    mon.scan()
    assert mon.volume_state("1234-ABCD") == "missing"
    # reinsere (mesmo UUID) -> restauração automática
    port.volumes = [_sd(str(mp))]
    mon.scan()
    assert mon.volume_state("1234-ABCD") == "mounted"
    assert mon.is_available("1234-ABCD") is True


def test_resolve_rejects_traversal(store: state.StateStore, tmp_path: Path) -> None:
    mp = tmp_path / "sd"
    mp.mkdir()
    port = FakeStoragePort()
    port.volumes = [_sd(str(mp))]
    mon = StorageMonitor(port, store)
    mon.scan()
    with pytest.raises(SteamZeroError) as ei:
        mon.resolve_write_path("1234-ABCD", "../../etc/passwd")
    assert ei.value.code == "E-CONTENT-UNSAFE-PATH"


def test_unknown_volume_state(store: state.StateStore) -> None:
    mon = StorageMonitor(FakeStoragePort(), store)
    assert mon.volume_state("nao-existe") == "unknown"
