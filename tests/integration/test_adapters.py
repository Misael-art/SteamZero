# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""M10: registry e lifecycle transacional do engine de adapters."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

from steamzero.adapters import AdapterEngine, AdapterRegistry, AdapterSource
from steamzero.adapters.registry import load_manifest
from steamzero.core import fs, state
from steamzero.core.errors import SteamZeroError


class FakeArtifacts:
    def __init__(self, artifacts: dict[str, bytes]) -> None:
        self.artifacts = artifacts
        self.requests: list[str] = []

    def fetch(self, source: AdapterSource) -> bytes:
        assert source.url is not None
        self.requests.append(source.url)
        return self.artifacts[source.url]


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[state.StateStore]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    fs.ensure_state_layout()
    opened = state.open_state()
    yield opened
    opened.close()


def portable_manifest(version: str, payload: bytes, *, checksum: str | None = None) -> dict:
    source: dict[str, object] = {
        "type": "appimage",
        "version": version,
        "priority": 1,
        "url": f"https://fixtures.invalid/demo-{version}.AppImage",
    }
    if checksum is not None:
        source["sha256"] = checksum
    else:
        source["sha256"] = hashlib.sha256(payload).hexdigest()
    return {
        "schemaVersion": 1,
        "id": "demo-emulator",
        "kind": "emulator",
        "platforms": ["demo"],
        "capabilities": ["detect", "status", "install", "update", "verify"],
        "sources": [source],
        "verify": {"smokeTest": ["--version"]},
        "license": "MIT",
        "upstream": "https://example.invalid/demo",
    }


def make_engine(
    store: state.StateStore, root: Path, version: str, payload: bytes
) -> tuple[AdapterEngine, FakeArtifacts]:
    manifest = load_manifest(portable_manifest(version, payload))
    artifacts = FakeArtifacts({manifest.sources[0].url or "": payload})
    return AdapterEngine(store, AdapterRegistry([manifest]), artifacts, root=root), artifacts


def test_bundled_registry_loads_three_core_adapters() -> None:
    registry = AdapterRegistry.bundled()
    assert [manifest.id for manifest in registry.list()] == [
        "dolphin",
        "duckstation",
        "retroarch",
    ]
    assert all(
        {"detect", "status", "install", "verify"} <= item.capabilities for item in registry.list()
    )
    assert registry.get("duckstation").sources[0].end_of_life is True


def test_manifest_rejects_portable_source_without_checksum() -> None:
    data = portable_manifest("1.0.0", b"v1")
    del data["sources"][0]["sha256"]
    with pytest.raises(SteamZeroError) as error:
        load_manifest(data)
    assert error.value.code == "E-SUPPLY-NO-CHECKSUM"


def test_manifest_requires_detect_and_status() -> None:
    data = portable_manifest("1.0.0", b"v1")
    data["capabilities"] = ["install", "verify"]
    with pytest.raises(SteamZeroError) as error:
        load_manifest(data)
    assert error.value.code == "E-API-SCHEMA"


def test_install_is_verified_persisted_and_idempotent(
    store: state.StateStore, tmp_path: Path
) -> None:
    root = tmp_path / "components"
    engine, artifacts = make_engine(store, root, "1.0.0", b"portable-v1")

    prepared = engine.plan_install("demo-emulator")
    result = engine.apply(prepared, prepared.plan.confirm_token)

    assert result.status == "ok"
    assert engine.detect("demo-emulator") is True
    assert engine.status("demo-emulator")["version"] == "1.0.0"
    assert store.get_component("demo-emulator")["state"] == "installed"  # type: ignore[index]
    assert len(artifacts.requests) == 1

    repeated = engine.plan_install("demo-emulator")
    assert repeated.plan.actions == []
    assert len(artifacts.requests) == 1
    engine.apply(repeated, repeated.plan.confirm_token)


@pytest.mark.rt
def test_rt02_update_and_manual_rollback_restore_previous_release(
    store: state.StateStore, tmp_path: Path
) -> None:
    root = tmp_path / "components"
    first, _ = make_engine(store, root, "1.0.0", b"portable-v1")
    install = first.plan_install("demo-emulator")
    first.apply(install, install.plan.confirm_token)
    current = root / "demo-emulator" / "current.json"
    before = current.read_bytes()

    second, _ = make_engine(store, root, "2.0.0", b"portable-v2")
    update = second.plan_install("demo-emulator")
    applied = second.apply(update, update.plan.confirm_token)
    assert second.status("demo-emulator")["version"] == "2.0.0"

    rolled_back = second.rollback("demo-emulator", applied.operation_id)
    assert rolled_back.status == "rolled-back"
    assert current.read_bytes() == before
    assert second.status("demo-emulator")["version"] == "1.0.0"
    assert store.get_component("demo-emulator")["version"] == "1.0.0"  # type: ignore[index]


def test_checksum_failure_happens_before_component_write(
    store: state.StateStore, tmp_path: Path
) -> None:
    root = tmp_path / "components"
    data = portable_manifest("1.0.0", b"expected", checksum="0" * 64)
    manifest = load_manifest(data)
    artifacts = FakeArtifacts({manifest.sources[0].url or "": b"tampered"})
    engine = AdapterEngine(store, AdapterRegistry([manifest]), artifacts, root=root)

    with pytest.raises(SteamZeroError) as error:
        engine.plan_install("demo-emulator")
    assert error.value.code == "E-SUPPLY-CHECKSUM"
    assert not (root / "demo-emulator").exists()


@pytest.mark.rt
def test_rt01_smoke_failure_rolls_back_install(store: state.StateStore, tmp_path: Path) -> None:
    root = tmp_path / "components"
    engine, _ = make_engine(store, root, "1.0.0", b"portable-v1")
    prepared = engine.plan_install("demo-emulator")

    def failed_smoke() -> None:
        raise RuntimeError("processo não iniciou")

    with pytest.raises(SteamZeroError) as error:
        engine.apply(prepared, prepared.plan.confirm_token, smoke=failed_smoke)
    assert error.value.code == "E-TX-VERIFY-FAILED"
    assert engine.status("demo-emulator")["state"] == "missing"
