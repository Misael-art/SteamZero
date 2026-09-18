# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Defesas do payload tar.gz usado pelo SharpEmu."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from steamzero.adapters.engine import AdapterEngine
from steamzero.adapters.registry import AdapterSource
from steamzero.core.errors import SteamZeroError


def _tar(path: Path, members: list[tarfile.TarInfo], payloads: list[bytes]) -> None:
    with tarfile.open(path, mode="w:gz") as archive:
        for info, payload in zip(members, payloads, strict=True):
            archive.addfile(info, io.BytesIO(payload) if info.isfile() else None)


def _source() -> AdapterSource:
    return AdapterSource(
        type="native",
        version="0.0.3-release.4",
        priority=1,
        url="https://fixtures.invalid/sharpemu.tar.gz",
        sha256="a" * 64,
        payload_path="SharpEmu",
        archive_format="tar.gz",
    )


def test_extracts_only_the_declared_sharpemu_member(tmp_path: Path) -> None:
    archive = tmp_path / "sharpemu.tar.gz"
    payload = b"#!/bin/sh\necho SharpEmu\n"
    executable = tarfile.TarInfo("./SharpEmu")
    executable.size = len(payload)
    plugin = tarfile.TarInfo("./plugins/unused.so")
    plugin.size = 4
    _tar(archive, [plugin, executable], [b"plug", payload])

    assert AdapterEngine._extract_member("sharpemu", archive, _source()) == payload


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "device", "traversal"])
def test_rejects_unsafe_tar_members(tmp_path: Path, kind: str) -> None:
    archive = tmp_path / f"{kind}.tar.gz"
    info = tarfile.TarInfo("./SharpEmu")
    payload = b"safe"
    if kind == "symlink":
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/shadow"
    elif kind == "hardlink":
        info.type = tarfile.LNKTYPE
        info.linkname = "../escape"
    elif kind == "device":
        info.type = tarfile.CHRTYPE
        info.devmajor = 1
        info.devminor = 3
    else:
        info = tarfile.TarInfo("../SharpEmu")
        info.size = len(payload)
    _tar(archive, [info], [payload])

    with pytest.raises(SteamZeroError, match="E-CONTENT-UNSAFE"):
        AdapterEngine._extract_member("sharpemu", archive, _source())
