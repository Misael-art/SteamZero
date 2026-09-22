# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from steamzero.adapters import emulation
from steamzero.adapters.emulation import EmulationController
from steamzero.core.state import StateStore


def _controller(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> EmulationController:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return EmulationController(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        which=lambda _command: None,
        spawn=lambda _argv: None,
        secret_store=emulation.SessionSecretStore(),
    )


@pytest.mark.parametrize(
    ("cached_title_id", "expected_count"),
    [("PCSF00516", 1), ("PCSA00017", 0)],
)
def test_directory_native_vita_game_survives_cache_only_with_matching_sfo(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cached_title_id: str,
    expected_count: int,
) -> None:
    controller = _controller(monkeypatch, tmp_path)
    source = tmp_path / "home" / "emulation" / "roms" / "psvita" / "app" / "PCSF00516"
    (source / "sce_sys").mkdir(parents=True)
    (source / "sce_sys" / "param.sfo").write_bytes(b"SFO")
    (source / "eboot.bin").write_bytes(b"EBOOT")
    metadata = SimpleNamespace(identity=SimpleNamespace(value="PCSF00516"))
    monkeypatch.setattr(emulation, "read_vita_metadata", lambda _path: metadata)
    cache = controller._library_cache_path  # type: ignore[attr-defined]
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "unidentified": 0,
                "games": [
                    {
                        "id": "vita-directory-game",
                        "name": "LittleBigPlanet PlayStation Vita",
                        "state": "ready",
                        "path": str(source),
                        "size": 10,
                        "format": "vita3k-app",
                        "contentKind": "base",
                        "platform": "playstation-vita",
                        "titleId": cached_title_id,
                        "identityScheme": "vita-title-id",
                        "evidence": "directory-native",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    games, _ = controller._load_library_cache()  # type: ignore[attr-defined]

    assert len(games) == expected_count
    if expected_count:
        assert games[0]["platformId"] == "playstation-vita"
        assert games[0]["format"] == "vita3k-app"
