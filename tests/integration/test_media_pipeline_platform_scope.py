"""Métricas do pipeline de mídia não devem atravessar plataformas."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.adapters.emulation import EmulationController
from steamzero.adapters.state_store_media import StateStoreGameMediaAdapter
from steamzero.core.state import StateStore
from steamzero.domain.switch_media import GameMediaState


def test_pipeline_cache_bytes_uses_only_context_media_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    switch_media = tmp_path / "switch-cover.png"
    other_media = tmp_path / "other-cover.png"
    switch_media.write_bytes(b"switch-cover")
    other_media.write_bytes(b"other-cover-is-not-switch")

    store_path = tmp_path / "state.db"
    with StateStore(store_path) as store:
        store.migrate()
        media = StateStoreGameMediaAdapter(store.adapter_connection())
        media.save(
            GameMediaState(
                game_id="switch-1",
                title_id="0100ABCDEF123000",
                title="Jogo Switch",
                media_source="scraper",
                media_path=str(switch_media),
            )
        )
        media.save(
            GameMediaState(
                game_id="other-1",
                title_id="other-title",
                title="Outro sistema",
                media_source="scraper",
                media_path=str(other_media),
            )
        )

    controller = EmulationController(
        store_factory=lambda: StateStore(store_path),
        which=lambda _command: None,
        spawn=lambda _argv: None,
    )
    pipeline = controller._media_pipeline_summary(  # type: ignore[attr-defined]
        [
            {
                "id": "switch-1",
                "mediaSource": "scraper",
                "mediaCandidateCount": 0,
                "mediaErrors": {},
            }
        ],
        platform_id="switch",
    )

    assert pipeline["cacheBytes"] == len(b"switch-cover")
    assert pipeline["scope"] == {"platformId": "switch", "games": 1, "mediaFiles": 1}
    assert other_media.read_bytes() == b"other-cover-is-not-switch"
