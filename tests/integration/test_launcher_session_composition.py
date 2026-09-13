# SPDX-License-Identifier: GPL-3.0-or-later
"""Prova de que o entry point real injeta o dono de sessão no overlay."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from steamzero.adapters.session_overlay import SessionOverlayAdapter
from steamzero.launcher.app import main


def test_launcher_entrypoint_composes_session_overlay_with_local_owner(
    tmp_path: Path, monkeypatch: Any
) -> None:
    library = tmp_path / "library.json"
    library.write_text(
        json.dumps(
            [
                {
                    "id": "game-1",
                    "name": "Game 1",
                    "platform": "nes",
                }
            ]
        ),
        encoding="utf-8",
    )
    captured: dict[str, Any] = {}

    def capture(bridge: Any) -> int:
        captured["bridge"] = bridge
        return 0

    monkeypatch.setattr("steamzero.adapters.launcher_ui.launch_launcher_ui", capture)
    monkeypatch.setattr("steamzero.launcher.app._host_accessibility", lambda: {})

    assert main(["--library", str(library)]) == 0
    bridge = captured["bridge"]
    assert isinstance(bridge._session_overlay, SessionOverlayAdapter)
    assert bridge._session_observer("game-1")["state"] == "unknown"
