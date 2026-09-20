# SPDX-License-Identifier: GPL-3.0-or-later
"""Transactional archive-to-M3U projection tests."""

from __future__ import annotations

import time
import zipfile
from pathlib import Path

import pytest

from steamzero.adapters.emulation import EmulationController
from steamzero.adapters.multidisc_materializer import (
    MaterializationRequest,
    MultiDiscMaterializer,
)
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain.multidisc_artifacts import OWNERSHIP_MARKER


def _manifest(*, support: str = "unproven", container: str = "extract") -> dict[str, object]:
    return {
        "media": {
            "containerPolicy": container,
            "multiDisc": {
                "enabled": True,
                "descriptor": "m3u",
                "media": ["adf"],
                "filenamePatterns": ["disc", "disk"],
                "requiresContinuousSequence": True,
                "adapterPlaylistSupport": support,
                "archiveMemberPolicy": {"allowedFormats": ["adf"]},
            },
        }
    }


def _zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)


def _request(
    root: Path, sources: list[Path], title: str = "Street Fighter"
) -> MaterializationRequest:
    return MaterializationRequest(
        platform_id="amiga",
        system_id="amiga1200",
        title=title,
        source_paths=tuple(sources),
        library_root=root,
        manifest=_manifest(),
    )


def test_zip_archive_is_extracted_and_m3u_is_published_atomically(tmp_path: Path) -> None:
    archives: list[Path] = []
    for number in range(1, 3):
        archive = tmp_path / f"Street Fighter (Disk {number} of 2).zip"
        _zip(archive, {f"Street Fighter (Disk {number} of 2).adf": bytes([number])})
        archives.append(archive)

    materializer = MultiDiscMaterializer()
    inspection = materializer.inspect(_request(tmp_path, archives))
    assert inspection.state == "needs-extraction"
    result = materializer.run(_request(tmp_path, archives))

    destination = tmp_path / ".steamzero" / "derived" / "amiga" / "street-fighter"
    descriptor = destination / "street-fighter.m3u"
    assert result["status"] == "materialized"
    assert descriptor.read_text(encoding="utf-8") == (
        f"{OWNERSHIP_MARKER}\n"
        "# SteamZero-MultiDisc-Set: amiga:amiga1200:street fighter\n"
        "disk-01.adf\n"
        "disk-02.adf\n"
    )
    assert (destination / "disk-01.adf").read_bytes() == b"\x01"
    assert (destination / "disk-02.adf").read_bytes() == b"\x02"
    assert all(path.read_bytes() for path in archives)


def test_user_owned_playlist_is_a_conflict(tmp_path: Path) -> None:
    first = tmp_path / "Game (Disk 1 of 2).adf"
    second = tmp_path / "Game (Disk 2 of 2).adf"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    destination = tmp_path / ".steamzero" / "derived" / "amiga" / "game"
    destination.mkdir(parents=True)
    (destination / "game.m3u").write_text("Game (Disk 1 of 2).adf\n", encoding="utf-8")

    inspection = MultiDiscMaterializer().inspect(_request(tmp_path, [first, second], "Game"))
    assert inspection.state == "conflict"
    with pytest.raises(SteamZeroError, match="ownership"):
        MultiDiscMaterializer().run(_request(tmp_path, [first, second], "Game"))
    assert (destination / "game.m3u").read_text(encoding="utf-8").startswith("Game")


def test_unsafe_zip_never_creates_projection(tmp_path: Path) -> None:
    archive = tmp_path / "Game (Disk 1 of 2).zip"
    _zip(archive, {"../escape.adf": b"bad"})
    second = tmp_path / "Game (Disk 2 of 2).zip"
    _zip(second, {"Game (Disk 2 of 2).adf": b"two"})

    inspection = MultiDiscMaterializer().inspect(_request(tmp_path, [archive, second], "Game"))
    assert inspection.state == "unsafe"
    assert not (tmp_path / ".steamzero").exists()


def test_cancelled_materialization_cleans_staging_and_leaves_destination(tmp_path: Path) -> None:
    archives: list[Path] = []
    for number in range(1, 3):
        archive = tmp_path / f"Game (Disk {number} of 2).zip"
        _zip(archive, {f"Game (Disk {number} of 2).adf": bytes([number])})
        archives.append(archive)
    calls = 0

    def cancel_after_first() -> None:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise RuntimeError("cancelled")

    with pytest.raises(RuntimeError, match="cancelled"):
        MultiDiscMaterializer().run(
            _request(tmp_path, archives, "Game"), safepoint=cancel_after_first
        )
    assert not (tmp_path / ".steamzero").exists()


def test_unsupported_platform_contract_does_not_publish_x68000_m3u(tmp_path: Path) -> None:
    first = tmp_path / "Game (Disk 1 of 2).dim"
    second = tmp_path / "Game (Disk 2 of 2).dim"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    request = MaterializationRequest(
        platform_id="x68000",
        system_id="x68000",
        title="Game",
        source_paths=(first, second),
        library_root=tmp_path,
        manifest={
            "media": {
                "containerPolicy": "native",
                "multiDisc": {
                    "enabled": True,
                    "descriptor": "m3u",
                    "media": ["dim"],
                    "filenamePatterns": ["disc", "disk"],
                    "adapterPlaylistSupport": "unsupported",
                },
            }
        },
    )
    inspection = MultiDiscMaterializer().inspect(request)
    assert inspection.state == "needs-platform-contract"
    assert not (tmp_path / ".steamzero").exists()


def test_controller_action_starts_async_materialization_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "roms"
    root.mkdir()
    first = root / "Game (Disk 1 of 2).adf"
    second = root / "Game (Disk 2 of 2).adf"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    controller = EmulationController(store_factory=lambda: StateStore(tmp_path / "state.db"))
    monkeypatch.setattr(controller, "library_roots", lambda: [str(root)])

    plan = controller.plan_action(
        {
            "actionId": "multidisc.materialize",
            "platformId": "amiga",
            "systemId": "amiga1200",
            "title": "Game",
            "libraryRoot": str(root),
            "sourcePaths": [str(first), str(second)],
        }
    )
    applied = controller.apply_action(str(plan["planId"]), str(plan["confirmToken"]))
    job_id = str(applied["jobId"])
    for _ in range(100):
        status = controller.get_job_status(job_id)
        if status is not None and status["rawState"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(0.02)
    assert status is not None
    assert status["rawState"] == "completed"
    assert (root / ".steamzero" / "derived" / "amiga" / "game" / "game.m3u").is_file()
