# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Ciclo real de um core contido no arquivo Libretro pinado."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import py7zr
import pytest

from steamzero.adapters.libretro_cores import LibretroCoreExecutor
from steamzero.adapters.lifecycle import ComponentLifecycle
from steamzero.adapters.registry import AdapterRegistry, AdapterSource, load_manifest
from steamzero.core import fs, state
from steamzero.core.errors import SteamZeroError

_PREFIX = "RetroArch-Linux-x86_64/RetroArch-Linux-x86_64.AppImage.home/.config/retroarch/cores/"


class Artifacts:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def fetch(self, source: AdapterSource) -> bytes:
        return self.payload


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[state.StateStore]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    fs.ensure_state_layout()
    opened = state.open_state()
    yield opened
    opened.close()


def _archive(tmp_path: Path, core_id: str, payload: bytes) -> bytes:
    source = tmp_path / "input.so"
    fs.write_atomic(source, payload)
    archive_path = tmp_path / "cores.7z"
    with py7zr.SevenZipFile(archive_path, mode="w") as archive:
        archive.write(source, arcname=_PREFIX + f"{core_id}_libretro.so")
    return archive_path.read_bytes()


def _registry(archive: bytes, payload: bytes) -> AdapterRegistry:
    bundled = AdapterRegistry.bundled()
    retroarch = bundled.get("retroarch")
    raw = json.loads(json.dumps(bundled.get("libretro-mgba").raw))
    raw["sources"][0]["sha256"] = hashlib.sha256(archive).hexdigest()
    raw["core"]["sha256"] = hashlib.sha256(payload).hexdigest()
    return AdapterRegistry([retroarch, load_manifest(raw)])


def test_install_verify_rollback_and_refuse_unowned_overwrite(
    store: state.StateStore, tmp_path: Path
) -> None:
    payload = b"real-libretro-core"
    archive = _archive(tmp_path, "mgba", payload)
    root = tmp_path / "cores"
    executor = LibretroCoreExecutor(
        store, _registry(archive, payload), Artifacts(archive), core_root=root
    )

    prepared = executor.plan_install("libretro-mgba")
    assert executor.status("libretro-mgba")["state"] == "missing"
    applied = executor.apply(prepared, prepared.plan.confirm_token)
    assert executor.status("libretro-mgba")["state"] == "installed"
    assert (root / "mgba_libretro.so").read_bytes() == payload

    executor.rollback("libretro-mgba", applied.operation_id)
    assert executor.status("libretro-mgba")["state"] == "missing"

    fs.write_atomic(root / "mgba_libretro.so", b"other-owner")
    with pytest.raises(SteamZeroError, match="recusa sobrescrever"):
        executor.plan_install("libretro-mgba")


def test_refuses_archive_without_the_exact_declared_member(
    store: state.StateStore, tmp_path: Path
) -> None:
    archive = _archive(tmp_path, "other", b"not-mgba")
    executor = LibretroCoreExecutor(
        store,
        _registry(archive, b"not-mgba"),
        Artifacts(archive),
        core_root=tmp_path / "cores",
    )

    with pytest.raises(SteamZeroError, match="não contém exatamente o core declarado"):
        executor.plan_install("libretro-mgba")


def test_component_lifecycle_keeps_plan_apply_and_rollback_for_a_core(
    store: state.StateStore, tmp_path: Path
) -> None:
    payload = b"lifecycle-core"
    archive = _archive(tmp_path, "mgba", payload)
    lifecycle = ComponentLifecycle(
        store,
        _registry(archive, payload),
        artifacts=Artifacts(archive),
        libretro_core_root=tmp_path / "cores",
    )

    planned = lifecycle.plan("libretro-mgba")
    assert planned.executor == "libretro"
    applied = lifecycle.apply(planned.plan_id, planned.confirm_token)
    assert applied["executor"] == "libretro"
    assert lifecycle.verify("libretro-mgba")["verified"] is True
    rolled = lifecycle.rollback(str(applied["operationId"]))
    assert rolled["executor"] == "libretro"
    assert lifecycle.status("libretro-mgba")["state"] == "missing"
