# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contratos do inventário read-only de armazenamento."""

from __future__ import annotations

import os
from pathlib import Path

from steamzero.adapters.storage_summary import collect_storage_summary


def _statvfs(_path: str | bytes | os.PathLike[str] | os.PathLike[bytes]) -> os.statvfs_result:
    return os.statvfs_result((1, 1, 100, 80, 80, 0, 0, 0, 0, 255))


def test_summary_reports_each_managed_category_and_volume(tmp_path: Path) -> None:
    roms = tmp_path / "roms"
    roms.mkdir()
    (roms / "game.nes").write_bytes(b"nes")
    saves = tmp_path / "saves"
    saves.mkdir()
    (saves / "save.dat").write_bytes(b"save-data")
    media = tmp_path / "media"
    media.mkdir()
    (media / "cover.png").write_bytes(b"cover")
    summary = collect_storage_summary(
        rom_roots=(roms,),
        emulator_roots=(tmp_path / "emulators",),
        saves_root=saves,
        media_root=media,
        cache_roots=(tmp_path / "cache",),
        volume_root=tmp_path,
        statvfs=_statvfs,
    )

    buckets = {bucket["id"]: bucket for bucket in summary["buckets"]}
    assert buckets["roms"]["files"] == 1
    assert buckets["roms"]["bytes"] == 3
    assert buckets["saves"]["bytes"] == 9
    assert buckets["media"]["bytes"] == 5
    assert buckets["emulators"]["state"] == "missing"
    assert summary["totals"] == {"files": 3, "bytes": 17}
    assert summary["volume"] == {
        "state": "ready",
        "capacityBytes": 100,
        "freeBytes": 80,
        "usedBytes": 20,
        "error": None,
    }


def test_summary_does_not_follow_symlinks(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.bin").write_bytes(b"secret")
    link = tmp_path / "roms-link"
    link.symlink_to(outside, target_is_directory=True)

    summary = collect_storage_summary(
        rom_roots=(link,),
        emulator_roots=(),
        saves_root=tmp_path / "saves",
        media_root=tmp_path / "media",
        cache_roots=(),
        volume_root=tmp_path,
        statvfs=_statvfs,
    )

    bucket = next(bucket for bucket in summary["buckets"] if bucket["id"] == "roms")
    assert bucket["state"] == "degraded"
    assert bucket["files"] == 0
    assert bucket["bytes"] == 0
    assert "simbólica" in bucket["error"]
