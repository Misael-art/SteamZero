# SPDX-License-Identifier: GPL-3.0-or-later
"""V2/AC-134-11 — a prévia sintética não toca a biblioteca privada."""

from __future__ import annotations

from steamzero.adapters.desktop_dashboard import DesktopDashboard


def test_synthetic_model_ignores_private_snapshot_and_offers_no_play() -> None:
    dashboard = DesktopDashboard()
    dashboard._last_emulation = {
        "editorialPlatforms": [
            {"id": "ps2", "name": "PRIVADO", "games": [{"id": "x", "name": "Titulo Privado"}]}
        ]
    }
    real = dashboard._theme_runtime_model("ps2")
    fake = dashboard._theme_runtime_model("ps2", synthetic=True)
    assert real["items"][0]["name"] == "Titulo Privado"
    assert fake["isolated"] is True
    assert "Titulo Privado" not in str(fake) and "PRIVADO" not in str(fake)
    assert "Jogar" not in fake["actions"]
    assert all(g["coverUrl"].startswith("data:image/svg+xml") for g in fake["items"])
    assert fake == dashboard._theme_runtime_model("outro", synthetic=True)  # determinístico
