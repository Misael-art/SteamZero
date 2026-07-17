# SPDX-License-Identifier: GPL-3.0-or-later
"""Instalador LSFG: supply chain, confirmação, verify e rollback."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from steamzero.adapters import lsfg
from steamzero.core import transaction
from steamzero.core.errors import SteamZeroError


class FakeArtifacts:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls: list[tuple[str, int]] = []

    def fetch(self, url: str, *, max_bytes: int) -> bytes:
        self.calls.append((url, max_bytes))
        return self.payload


def _archive(library: bytes = b"official-library", *, extra: str | None = None) -> bytes:
    buffer = io.BytesIO()
    manifest = {
        "file_format_version": "1.0.0",
        "layer": {
            "name": "VK_LAYER_LS_frame_generation",
            "library_path": "liblsfg-vk.so",
        },
    }
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("lib/liblsfg-vk.so", library)
        bundle.writestr(
            "share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation.json",
            json.dumps(manifest),
        )
        if extra is not None:
            bundle.writestr(extra, b"unexpected")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))


def _installer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    payload: bytes | None = None,
    lossless: bool = True,
) -> tuple[lsfg.LsfgInstaller, FakeArtifacts]:
    archive = payload if payload is not None else _archive()
    monkeypatch.setattr(lsfg, "LSFG_ARCHIVE_SHA256", hashlib.sha256(archive).hexdigest())
    monkeypatch.setattr(
        lsfg, "LSFG_LIBRARY_SHA256", hashlib.sha256(b"official-library").hexdigest()
    )
    artifacts = FakeArtifacts(archive)
    installer = lsfg.LsfgInstaller(
        root=tmp_path / ".local",
        artifacts=artifacts,
        lossless_probe=lambda: lossless,
        machine=lambda: "x86_64",
    )
    return installer, artifacts


def test_install_is_confirmed_verified_and_reversible(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installer, artifacts = _installer(monkeypatch, tmp_path)
    plan = installer.plan_install()
    assert plan["version"] == "1.0.0"
    assert plan["rollbackGuarantee"] == "G-FULL"
    assert len(artifacts.calls) == 1
    with pytest.raises(SteamZeroError) as wrong:
        installer.apply(str(plan["planId"]), "wrong-token")
    assert wrong.value.code == "E-TX-CONFIRM-REQUIRED"

    applied = installer.apply(str(plan["planId"]), str(plan["confirmToken"]))
    assert applied["status"] == "installed"
    assert installer.status()["state"] == "ready"
    manifest = json.loads(installer.manifest_path.read_text(encoding="utf-8"))
    assert manifest["layer"]["library_path"] == str(installer.library_path)

    rolled_back = installer.rollback(str(applied["operationId"]))
    assert rolled_back["status"] == "rolled-back"
    assert installer.status()["state"] == "missing"


def test_install_refuses_missing_proprietary_dependency_without_fetch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installer, artifacts = _installer(monkeypatch, tmp_path, lossless=False)
    with pytest.raises(SteamZeroError) as error:
        installer.plan_install()
    assert error.value.code == "E-COMPONENT-DEGRADED"
    assert "993090" in str(error.value)
    assert artifacts.calls == []


def test_install_rejects_archive_checksum_before_writing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installer, _ = _installer(monkeypatch, tmp_path)
    monkeypatch.setattr(lsfg, "LSFG_ARCHIVE_SHA256", "0" * 64)
    with pytest.raises(SteamZeroError) as error:
        installer.plan_install()
    assert error.value.code == "E-SUPPLY-CHECKSUM"
    assert installer.status()["state"] == "missing"


def test_install_rejects_unexpected_archive_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = _archive(extra="../../escape")
    installer, _ = _installer(monkeypatch, tmp_path, payload=payload)
    with pytest.raises(SteamZeroError) as error:
        installer.plan_install()
    assert error.value.code == "E-CONTENT-UNSAFE-ARCHIVE"
    assert not (tmp_path / "escape").exists()


def test_install_endpoint_rejects_plan_from_another_subsystem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installer, _ = _installer(monkeypatch, tmp_path)
    unrelated = transaction.plan_write_files(
        {tmp_path / "other" / "file": b"x"},
        root=tmp_path / "other",
        kind="other.install",
    )
    with pytest.raises(SteamZeroError) as error:
        installer.apply(unrelated.plan_id, unrelated.confirm_token)
    assert error.value.code == "E-TX-STALE-PLAN"
    assert not (tmp_path / "other" / "file").exists()
