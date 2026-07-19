# SPDX-License-Identifier: GPL-3.0-or-later
"""Pacotes de mídia Steam locais com substituição e rollback byte-idêntico."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.adapters.steam_media import SteamMediaManager
from steamzero.core import fs
from steamzero.core.errors import SteamZeroError

_PNG = b"\x89PNG\r\n\x1a\nnew-grid"
_JPG = b"\xff\xd8\xffold-grid"


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))


def _steam_root(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "Steam"
    grid = root / "userdata" / "123456" / "config" / "grid"
    grid.mkdir(parents=True)
    fs.write_atomic(grid / "10.jpg", _JPG)
    return root, grid


def test_media_package_replaces_extension_and_rolls_back(tmp_path: Path) -> None:
    root, grid = _steam_root(tmp_path)
    package = tmp_path / "package"
    fs.write_atomic(package / "grid.png", _PNG)
    manager = SteamMediaManager(roots=(root,), running_probe=lambda: False)

    snapshot = manager.snapshot("10")
    assert snapshot["accounts"][0]["id"] == "123456"
    assert snapshot["accounts"][0]["assets"][0] == {"kind": "grid", "configured": True}

    plan = manager.plan("10", "123456", package)
    assert plan["assets"] == ["grid"]
    assert plan["replacedVariants"] == 1
    applied = manager.apply(str(plan["planId"]), str(plan["confirmToken"]))
    assert (grid / "10.png").read_bytes() == _PNG
    assert not (grid / "10.jpg").exists()

    rolled_back = manager.rollback(str(applied["operationId"]))
    assert rolled_back["status"] == "rolled-back"
    assert (grid / "10.jpg").read_bytes() == _JPG
    assert not (grid / "10.png").exists()


def test_media_package_is_local_only_validated_and_requires_closed_steam(
    tmp_path: Path,
) -> None:
    root, _grid = _steam_root(tmp_path)
    package = tmp_path / "package"
    fs.write_atomic(package / "hero.png", b"not-png")
    manager = SteamMediaManager(roots=(root,), running_probe=lambda: False)
    with pytest.raises(SteamZeroError) as invalid:
        manager.plan("10", "123456", package)
    assert invalid.value.code == "E-CONTENT-POLICY"

    fs.write_atomic(package / "hero.png", _PNG)
    running = SteamMediaManager(roots=(root,), running_probe=lambda: True)
    with pytest.raises(SteamZeroError) as locked:
        running.plan("10", "123456", package)
    assert locked.value.code == "E-TX-LOCKED"


def test_media_package_rejects_symlinked_source(tmp_path: Path) -> None:
    root, _grid = _steam_root(tmp_path)
    package = tmp_path / "package"
    package.mkdir()
    outside = tmp_path / "outside.png"
    fs.write_atomic(outside, _PNG)
    (package / "grid.png").symlink_to(outside)
    manager = SteamMediaManager(roots=(root,), running_probe=lambda: False)
    with pytest.raises(SteamZeroError) as incomplete:
        manager.plan("10", "123456", package)
    assert incomplete.value.code == "E-CONTENT-INCOMPLETE"
