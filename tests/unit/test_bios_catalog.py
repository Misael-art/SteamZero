# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Synthetic coverage for the universal BIOS scanner and CAS store."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.bios_catalog import BiosCatalog, BiosLibrary


def _catalog(payload: bytes) -> BiosCatalog:
    return BiosCatalog(
        {
            "schemaVersion": 2,
            "entries": [
                {
                    "id": "bios.synthetic.one",
                    "platformId": "synthetic",
                    "canonicalName": "canonical.bin",
                    "namingAuthority": "test",
                    "required": True,
                    "group": "allOf:synthetic.test",
                    "acceptedVariants": [
                        {"sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}
                    ],
                    "consumers": [
                        {
                            "adapterId": "test-adapter",
                            "relativePath": "required-name.bin",
                            "required": True,
                            "projectionModes": ["symlink"],
                        }
                    ],
                }
            ],
        }
    )


def test_wrong_name_is_recognized_and_stored_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = b"synthetic bios bytes"
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    source = tmp_path / "not-a-bios-no-extension"
    source.write_bytes(payload)
    library = BiosLibrary(_catalog(payload))
    scan = library.scan(source)
    assert scan["counts"] == {"new": 1}
    plan = library.import_plan(str(scan["scanId"]))
    result = library.import_apply(str(plan["planId"]), str(plan["confirmToken"]))
    assert result["imported"] == 1
    object_path = tmp_path / "data" / "steamzero" / "bios" / "objects" / "sha256"
    objects = list(object_path.rglob("*"))
    assert len([item for item in objects if item.is_file()]) == 1
    view = tmp_path / "data" / "steamzero" / "bios" / "platforms" / "synthetic" / "canonical.bin"
    assert view.is_symlink() and view.read_bytes() == payload
    second = library.scan(source)
    assert second["counts"] == {"already-present": 1}


def test_directory_and_zip_have_identical_recognition(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = b"synthetic bios bytes"
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    source_dir = tmp_path / "input"
    source_dir.mkdir()
    (source_dir / "wrong-name.bin").write_bytes(payload)
    (source_dir / "ignored.bin").write_bytes(b"not-known")
    source_zip = tmp_path / "input.zip"
    with zipfile.ZipFile(source_zip, "w") as archive:
        archive.writestr("nested/wrong-name.bin", payload)
        archive.writestr("nested/ignored.bin", b"not-known")
    library = BiosLibrary(_catalog(payload))
    directory = library.scan(source_dir)
    packed = library.scan(source_zip)
    assert directory["counts"] == packed["counts"] == {"new": 1, "unknown-ignored": 1}


def test_zip_slip_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    source = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("../escape.bin", b"not-content")
    with pytest.raises(SteamZeroError) as error:
        BiosLibrary(_catalog(b"synthetic bios bytes")).scan(source)
    assert error.value.code == "E-CONTENT-UNSAFE-ARCHIVE"


def test_changed_source_invalidates_plan(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    payload = b"synthetic bios bytes"
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    source = tmp_path / "input.bin"
    source.write_bytes(payload)
    library = BiosLibrary(_catalog(payload))
    scan = library.scan(source)
    plan = library.import_plan(str(scan["scanId"]))
    source.write_bytes(b"changed")
    with pytest.raises(SteamZeroError) as error:
        library.import_apply(str(plan["planId"]), str(plan["confirmToken"]))
    assert error.value.code == "E-TX-STALE-PLAN"
