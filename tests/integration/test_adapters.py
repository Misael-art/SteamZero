# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""M10: registry e lifecycle transacional do engine de adapters."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

from steamzero.adapters import AdapterEngine, AdapterRegistry, AdapterSource
from steamzero.adapters.lockfile import (
    ComponentLock,
    LockedComponent,
    LockedSource,
    validate_registry_lock,
)
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


def portable_manifest(
    version: str,
    payload: bytes,
    *,
    checksum: str | None = None,
    capabilities: list[str] | None = None,
    end_of_life: bool = False,
) -> dict:
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
    if end_of_life:
        source["endOfLife"] = True
    return {
        "schemaVersion": 1,
        "id": "demo-emulator",
        "kind": "emulator",
        "platforms": ["demo"],
        "capabilities": capabilities or ["detect", "status", "install", "update", "verify"],
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


def test_bundled_registry_loads_verified_emulation_adapters() -> None:
    registry = AdapterRegistry.bundled()
    emulators = [m for m in registry.list() if m.kind == "emulator"]
    assert [manifest.id for manifest in emulators] == [
        "azahar",
        "cemu",
        "citron",
        "dolphin",
        "duckstation",
        "eden",
        "flycast",
        "melonds",
        "pcsx2",
        "ppsspp",
        "retroarch",
        "ryubing",
    ]
    assert all({"detect", "status", "install", "verify"} <= item.capabilities for item in emulators)
    assert registry.get("duckstation").sources[0].end_of_life is True


def test_bundled_registry_is_locked_without_manifest_drift() -> None:
    registry = AdapterRegistry.bundled()
    locked = validate_registry_lock(registry.list())
    assert [item.id for item in locked.components] == [
        "azahar",
        "cemu",
        "citron",
        "dolphin",
        "duckstation",
        "eden",
        "flycast",
        "melonds",
        "pcsx2",
        "ppsspp",
        "retroarch",
        "ryubing",
        "sunshine",
    ]


def test_lockfile_manifest_drift_is_rejected() -> None:
    manifest = load_manifest(portable_manifest("1.0.0", b"v1"))
    source = manifest.sources[0]
    locked_source = LockedSource(
        type=source.type,
        version=source.version,
        priority=source.priority,
        ref=source.ref,
        remote=source.remote,
        url=source.url,
        sha256=source.sha256,
        end_of_life=source.end_of_life,
    )
    valid = ComponentLock(1, (LockedComponent(manifest.id, manifest.manifest_hash, locked_source),))
    assert validate_registry_lock([manifest], valid) is valid

    locked = ComponentLock(
        1,
        (
            LockedComponent(
                manifest.id,
                "0" * 64,
                locked_source,
            ),
        ),
    )
    with pytest.raises(SteamZeroError) as error:
        validate_registry_lock([manifest], locked)
    assert error.value.code == "E-SUPPLY-CHECKSUM"


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


def test_manifest_rejects_ambiguous_source_priorities() -> None:
    data = portable_manifest("1.0.0", b"v1")
    second = dict(data["sources"][0])
    second["url"] = "https://fixtures.invalid/other.AppImage"
    data["sources"].append(second)

    with pytest.raises(SteamZeroError) as error:
        load_manifest(data)

    assert error.value.code == "E-API-SCHEMA"


def test_preferred_source_skips_eol_when_active_fallback_exists() -> None:
    data = portable_manifest("1.0.0", b"v1", end_of_life=True)
    active = dict(data["sources"][0])
    active.update(
        {
            "version": "2.0.0",
            "priority": 2,
            "url": "https://fixtures.invalid/demo-2.0.0.AppImage",
            "sha256": hashlib.sha256(b"v2").hexdigest(),
        }
    )
    active.pop("endOfLife")
    data["sources"].append(active)

    manifest = load_manifest(data)

    assert manifest.preferred_source(allow_eol=False).version == "2.0.0"
    assert manifest.preferred_source().version == "1.0.0"


def test_portable_engine_blocks_eol_source_before_fetch_or_write(
    store: state.StateStore, tmp_path: Path
) -> None:
    data = portable_manifest("1.0.0", b"v1", end_of_life=True)
    manifest = load_manifest(data)
    artifacts = FakeArtifacts({manifest.sources[0].url or "": b"v1"})
    root = tmp_path / "components"
    engine = AdapterEngine(store, AdapterRegistry([manifest]), artifacts, root=root)

    with pytest.raises(SteamZeroError) as error:
        engine.plan_install("demo-emulator")

    assert error.value.code == "E-SUPPLY-UPSTREAM-GONE"
    assert artifacts.requests == []
    assert not (root / "demo-emulator").exists()


def test_install_is_verified_persisted_and_idempotent(
    store: state.StateStore, tmp_path: Path
) -> None:
    root = tmp_path / "components"
    engine, artifacts = make_engine(store, root, "1.0.0", b"portable-v1")

    prepared = engine.plan_install("demo-emulator")
    payload_action = next(action for action in prepared.plan.actions if action.kind == "copy")
    assert payload_action.new_content_b64 == ""
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


def test_repair_fetches_again_and_uninstall_preserves_rollback(
    store: state.StateStore, tmp_path: Path
) -> None:
    root = tmp_path / "components"
    data = portable_manifest(
        "1.0.0",
        b"portable-v1",
        capabilities=[
            "detect",
            "status",
            "install",
            "update",
            "verify",
            "repair",
            "uninstall",
        ],
    )
    manifest = load_manifest(data)
    artifacts = FakeArtifacts({manifest.sources[0].url or "": b"portable-v1"})
    engine = AdapterEngine(store, AdapterRegistry([manifest]), artifacts, root=root)
    install = engine.plan_install("demo-emulator")
    engine.apply(install, install.plan.confirm_token)

    repair = engine.plan_install("demo-emulator", force=True)
    engine.apply(repair, repair.plan.confirm_token)
    assert len(artifacts.requests) == 2

    removal = engine.plan_uninstall("demo-emulator")
    removed = engine.apply(removal, removal.plan.confirm_token)
    assert engine.status("demo-emulator")["state"] == "missing"

    engine.rollback("demo-emulator", removed.operation_id)
    assert engine.status("demo-emulator")["state"] == "installed"
    assert engine.payload_path("demo-emulator").stat().st_mode & 0o111


def test_update_without_capability_is_blocked_before_fetch(
    store: state.StateStore, tmp_path: Path
) -> None:
    root = tmp_path / "components"
    first, _ = make_engine(store, root, "1.0.0", b"portable-v1")
    install = first.plan_install("demo-emulator")
    first.apply(install, install.plan.confirm_token)

    data = portable_manifest(
        "2.0.0",
        b"portable-v2",
        capabilities=["detect", "status", "install", "verify"],
    )
    manifest = load_manifest(data)
    artifacts = FakeArtifacts({manifest.sources[0].url or "": b"portable-v2"})
    engine = AdapterEngine(store, AdapterRegistry([manifest]), artifacts, root=root)

    with pytest.raises(SteamZeroError) as error:
        engine.plan_install("demo-emulator")

    assert error.value.code == "E-COMPONENT-DEGRADED"
    assert artifacts.requests == []
    assert first.status("demo-emulator")["version"] == "1.0.0"


def test_status_rejects_manifest_drift_and_parent_symlink_escape(
    store: state.StateStore, tmp_path: Path
) -> None:
    root = tmp_path / "components"
    engine, _ = make_engine(store, root, "1.0.0", b"portable-v1")
    prepared = engine.plan_install("demo-emulator")
    engine.apply(prepared, prepared.plan.confirm_token)
    current = root / "demo-emulator" / "current.json"
    metadata = current.read_text(encoding="utf-8").replace(
        prepared.manifest.manifest_hash, "0" * 64
    )
    fs.write_atomic_text(current, metadata)
    assert engine.status("demo-emulator")["state"] == "degraded"

    outside = tmp_path / "outside"
    fs.ensure_dir(outside / "1.0.0")
    fs.write_atomic(outside / "1.0.0" / "payload", b"portable-v1")
    releases = root / "demo-emulator" / "releases"
    fs.remove_tree(releases)
    fs.symlink_atomic(outside, releases)
    restored = metadata.replace("0" * 64, prepared.manifest.manifest_hash)
    fs.write_atomic_text(current, restored)
    status = engine.status("demo-emulator")
    assert status["state"] == "degraded"
    assert "escapa" in str(status["detail"])


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
