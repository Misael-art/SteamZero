"""Auditoria de mídia respeita o sistema atualmente selecionado."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from steamzero.adapters.emulation import EmulationController
from steamzero.core.state import StateStore
from steamzero.domain.media_pipeline import AuditReport, MediaPipeline


def test_media_pipeline_audit_filters_managed_tree_and_registry(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    pipeline = MediaPipeline(media_root)
    source = tmp_path / "cover.png"
    source.write_bytes(b"cover")

    pipeline.collect(
        source,
        game_id="switch-1",
        title_id="0100ABCDEF123000",
        fingerprint="switch-fingerprint",
        canonical_name="Jogo Switch",
        platform_id="switch",
    )
    pipeline.collect(
        source,
        game_id="nes-1",
        title_id="nes-title",
        fingerprint="nes-fingerprint",
        canonical_name="Jogo NES",
        platform_id="nes",
    )
    switch_opt = media_root / "optimized" / "switch" / "grid" / "switch-1.png"
    nes_opt = media_root / "optimized" / "nes" / "grid" / "nes-1.png"
    switch_opt.parent.mkdir(parents=True)
    nes_opt.parent.mkdir(parents=True)
    switch_opt.write_bytes(b"switch-opt")
    nes_opt.write_bytes(b"nes-opt")
    views = media_root / "views"
    views.mkdir()
    (views / "switch.png").symlink_to(switch_opt)
    (views / "nes.png").symlink_to(nes_opt)

    scoped = pipeline.audit(platform_id="switch").to_dict()
    global_report = pipeline.audit().to_dict()

    assert scoped["stats"] == {
        "masterFiles": 1,
        "optimizedFiles": 1,
        "viewLinks": 1,
        "orphanMasters": 0,
        "registryEntries": 1,
    }
    assert all("nes-1" not in str(finding) for finding in scoped["findings"])
    assert global_report["stats"]["masterFiles"] == 2
    assert global_report["stats"]["optimizedFiles"] == 2
    assert global_report["stats"]["viewLinks"] == 2


def test_media_audit_job_persists_effective_platform_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    store_path = tmp_path / "state.db"
    controller = EmulationController(
        store_factory=lambda: StateStore(store_path),
        which=lambda _command: None,
        spawn=lambda _argv: None,
    )
    report = AuditReport()
    report.stats["registryEntries"] = 1
    calls: list[str | None] = []

    class FakeMediaManager:
        def audit(self, platform_id: str | None = None) -> AuditReport:
            calls.append(platform_id)
            return report

    monkeypatch.setattr(controller, "_media_manager", lambda _store: FakeMediaManager())
    job = SimpleNamespace(
        params={"mode": "audit", "platform_id": "switch"},
        id="job-media-audit",
        priority="maintenance",
    )
    progress: list[tuple[str, int, int, str]] = []
    ctx = SimpleNamespace(
        set_progress=lambda stage, **kwargs: progress.append(
            (stage, int(kwargs["current"]), int(kwargs["total"]), str(kwargs["unit"]))
        )
    )

    result = controller._media_global_job_handler(job, ctx)  # type: ignore[attr-defined]
    persisted = json.loads(controller._media_audit_path.read_text(encoding="utf-8"))  # type: ignore[attr-defined]

    assert calls == ["switch"]
    assert result["platformId"] == "switch"
    assert result["scope"] == {"platformId": "switch"}
    assert persisted["scope"] == {"platformId": "switch"}
    assert progress == [("done", 1, 1, "audit")]
