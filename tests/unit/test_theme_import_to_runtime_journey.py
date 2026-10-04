# SPDX-License-Identifier: GPL-3.0-or-later
"""V2 — tema ES-DE importado até a cena com dados sintéticos isolados."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from steamzero.adapters.desktop_dashboard import DesktopDashboard
from steamzero.core import paths
from steamzero.domain import theme_assets

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "themes" / "esde-mini"
THEME_ID = "org.steamzero.fixture.esde-mini"


@pytest.fixture
def installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
    store = theme_assets.ThemeAssetStore(paths.theme_assets_dir())
    assets = {}
    for source in (p for p in FIXTURE.iterdir() if p.suffix in {".png", ".xml"}):
        assets[source.name] = {"digest": store.put(source.name, source.read_bytes()).digest}
    directory = paths.themes_dir() / THEME_ID
    directory.mkdir(parents=True)
    (directory / "theme.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "kind": "steamzero-theme-v1",
                "id": THEME_ID,
                "name": "Fixture ES-DE mínimo",
                "version": "1",
                "license": "CC0-1.0",
                "assets": assets,
            }
        ),
        encoding="utf-8",
    )


def test_esde_fixture_renders_with_synthetic_data_and_reports_loss(installed: None) -> None:
    dashboard = DesktopDashboard()
    dashboard._last_emulation = {
        "editorialPlatforms": [{"id": "x", "games": [{"id": "p", "name": "Titulo Privado"}]}]
    }
    rendered = dashboard.theme_scene_render(THEME_ID, aspect_ratio="16:10", synthetic=True)

    elements = {e["name"]: e for e in rendered["scene"]["views"][0]["elements"]}
    assert elements["fundo"]["source"].startswith("file://")
    assert elements["titulo"]["layout"]["x"] == pytest.approx(0.4)
    # Binding de metadado é declarado e resolvido contra o modelo sintético.
    assert rendered["synthetic"] is True
    model = rendered["runtimeModel"]
    assert model["isolated"] is True
    assert model["selected"]["name"] and "Privado" not in json.dumps(rendered)
    assert "Jogar" not in model["actions"]
    # Asset ausente: diagnóstico acionável, sem abortar nem trocar por demo.
    report = json.dumps(rendered["assets"]) + json.dumps(rendered["fidelity"])
    assert "nao-existe.png" in report
    assert rendered["themeId"] == THEME_ID


def test_retrofe_import_is_rendered_by_the_same_resolver_and_not_activated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
    source = tmp_path / "retrofe"
    shutil.copytree(FIXTURE.parent / "retrofe-mini", source)  # PNG válido, CC0
    dashboard = DesktopDashboard()
    dashboard._last_emulation = {
        "editorialPlatforms": [{"id": "x", "games": [{"name": "Privado"}]}]
    }
    dashboard.theme_import_retrofe_apply(
        str(source), "layout", "org.example.retrofe-run", "RetroFE", "Autor", "CC0-1.0"
    )

    rendered = dashboard.theme_imported_scene_render("org.example.retrofe-run")

    assert rendered["origin"] == "retrofe" and rendered["synthetic"] is True
    sources = [
        e.get("source")
        for v in rendered["scene"]["views"]
        for e in v["elements"]
        if e.get("source")
    ]
    assert sources and sources[0].startswith("file://")
    assert rendered["assets"]["resolved"] == 1 and rendered["assets"]["missing"] == []
    # O renderizador de cena lê frações da tela: pixels do layout 1920x1080 viram frações.
    layout = rendered["scene"]["views"][0]["elements"][0]["layout"]
    assert layout["x"] == pytest.approx(10 / 1920) and layout["width"] == pytest.approx(200 / 1920)
    assert layout["height"] == pytest.approx(100 / 1080)
    assert rendered["fidelity"] and "Privado" not in json.dumps(rendered)
    from steamzero.core.errors import SteamZeroError

    with pytest.raises(SteamZeroError):
        dashboard.theme_imported_scene_render("nao-importada")


def test_retrofe_percent_and_default_canvas_are_normalized_without_touching_the_stored_scene() -> (
    None
):
    from steamzero.domain.theme_scene import _normalize_retrofe_scene

    scene = {
        "views": [
            {
                "id": "v",
                "elements": [{"layout": {"x": "50%", "width": 960, "y": 540, "height": "10%"}}],
            }
        ]
    }
    out = _normalize_retrofe_scene(scene)
    layout = out["views"][0]["elements"][0]["layout"]
    assert layout == {"x": 0.5, "width": 0.5, "y": 0.5, "height": 0.1}
    assert scene["views"][0]["elements"][0]["layout"]["x"] == "50%"  # origem intacta
    canvas = {
        "views": [
            {"canvas": {"width": 800.0, "height": 400.0}, "elements": [{"layout": {"x": 400}}]}
        ]
    }
    assert _normalize_retrofe_scene(canvas)["views"][0]["elements"][0]["layout"]["x"] == 0.5
