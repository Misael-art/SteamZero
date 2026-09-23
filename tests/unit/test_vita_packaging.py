# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato do pacote Vita3K derivado."""

from __future__ import annotations

import struct
import time
import zipfile
from pathlib import Path

import pytest

from steamzero.adapters.discovery.vita_packaging import (
    canonical_vita_filename,
    package_vita_app,
    plan_from_app,
)
from steamzero.adapters.emulation import EmulationController
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore


def _sfo(*, title: str, title_id: str) -> bytes:
    keys = b"TITLE_ID\0TITLE\0"
    title_id_bytes = title_id.encode()
    title_bytes = title.encode()
    values = title_id_bytes + b"\0" + title_bytes + b"\0"
    key_offset = 20 + 16 * 2
    data_offset = key_offset + len(keys)
    entries = [
        (0, 0x0204, len(title_id_bytes) + 1, len(title_id_bytes) + 1, 0),
        (9, 0x0204, len(title_bytes) + 1, len(title_bytes) + 1, len(title_id_bytes) + 1),
    ]
    header = struct.pack("<4sIIII", b"\x00PSF", 0x101, key_offset, data_offset, 2)
    index = b"".join(struct.pack("<HHIII", *entry) for entry in entries)
    return header + index + keys + values


def _app(root: Path) -> Path:
    app = root / "PCSF00516"
    (app / "sce_sys").mkdir(parents=True)
    (app / "sce_sys" / "param.sfo").write_bytes(
        _sfo(
            title="LittleBigPlanet™ PlayStation®Vita Marvel Super Hero Edition",
            title_id="PCSF00516",
        )
    )
    (app / "eboot.bin").write_bytes(b"boot")
    (app / "data" / "game.bin").parent.mkdir()
    (app / "data" / "game.bin").write_bytes(b"data")
    return app


def test_vita_filename_keeps_title_id_and_normalizes_unsafe_chars() -> None:
    assert canonical_vita_filename("A/B: Vita", "pcsf00516") == "A-B- Vita [PCSF00516].zip"


def test_vita_app_is_packaged_at_archive_root_without_touching_source(tmp_path: Path) -> None:
    root = tmp_path / "roms"
    source = _app(root / "LittleBigPlanet")
    plan = plan_from_app(source, derived_root=root / ".steamzero" / "derived")

    result = package_vita_app(plan)

    assert result["status"] == "materialized"
    assert source.is_dir()
    assert (source / "sce_sys" / "param.sfo").is_file()
    with zipfile.ZipFile(plan.destination) as archive:
        assert "sce_sys/param.sfo" in archive.namelist()
        assert "eboot.bin" in archive.namelist()
    assert "data/game.bin" in archive.namelist()
    assert not any(name.startswith("app/") for name in archive.namelist())
    provenance = plan.destination.with_name(plan.destination.name + ".steamzero-derived.json")
    assert provenance.is_file()
    assert '"ownerPaths":["LittleBigPlanet/PCSF00516"]' in provenance.read_text(encoding="utf-8")


def test_vita_package_rejects_symlinked_content(tmp_path: Path) -> None:
    source = _app(tmp_path / "source")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    (source / "data" / "outside.bin").symlink_to(outside)

    try:
        plan_from_app(
            source,
            derived_root=tmp_path / ".steamzero" / "derived",
        )
    except SteamZeroError as exc:
        assert exc.code == "E-CONTENT-UNSAFE-PATH"
    else:
        raise AssertionError("symlink Vita3K deveria ser rejeitado")


def test_controller_exposes_governed_vita_package_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "roms"
    source = _app(root / "LittleBigPlanet")
    controller = EmulationController(store_factory=lambda: StateStore(tmp_path / "state.db"))
    monkeypatch.setattr(controller, "library_roots", lambda: [str(root)])

    plan = controller.plan_action(
        {
            "actionId": "library.vita.package",
            "libraryRoot": str(root),
            "sourcePath": str(source),
        }
    )
    assert plan["kind"] == "emulation.vita.package"
    assert "sem renomear, mover ou apagar a origem" in plan["preview"]

    applied = controller.apply_action(str(plan["planId"]), str(plan["confirmToken"]))
    job_id = str(applied["jobId"])
    status = None
    for _ in range(100):
        status = controller.get_job_status(job_id)
        if status is not None and status["rawState"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.02)

    assert status is not None
    assert status["rawState"] == "completed"
    destination = (
        root
        / ".steamzero"
        / "derived"
        / "playstation-vita"
        / "LittleBigPlanet PlayStation Vita Marvel Super Hero Edition [PCSF00516].zip"
    )
    assert destination.is_file()
    assert source.is_dir()
