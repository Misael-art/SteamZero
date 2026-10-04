# SPDX-License-Identifier: GPL-3.0-or-later
"""V2 — cenas ES-DE/RetroFE com imagens válidas, desenhadas pelo QML a partir da bridge real."""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
from pathlib import Path

import pytest
from tests.integration.test_desktop_ui_bridge import Context
from tests.integration.test_ui_shell_retrofe_import_late_response import RUNNER

from steamzero.adapters.desktop_dashboard import DesktopDashboard
from steamzero.adapters.desktop_ui import DesktopControlServer
from steamzero.core import paths
from steamzero.core.state import StateStore
from steamzero.domain import theme_assets
from steamzero.domain.desktop import ExperienceCoordinator

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "themes"
HARNESS = ROOT / "tests" / "qml" / "check_theme_scene_runtime_e2e.qml"
CONFIG = ROOT / "build" / "ui-theme-scene-runtime-e2e.json"
ESDE_ID = "org.steamzero.fixture.esde-mini"
RETROFE_ID = "org.example.retrofe-e2e"

pytestmark = pytest.mark.visual


def test_fixtures_sao_imagens_validas_e_licenciadas() -> None:
    from PIL import Image

    for path in (
        FIXTURES / "esde-mini" / "fundo.png",
        FIXTURES / "retrofe-mini" / "assets" / "logo.png",
    ):
        with Image.open(path) as image:
            image.verify()
        assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    for directory in ("esde-mini", "retrofe-mini"):
        assert "CC0-1.0" in (FIXTURES / directory / "LICENSE.txt").read_text()


def _install_esde() -> None:
    store = theme_assets.ThemeAssetStore(paths.theme_assets_dir())
    assets = {
        source.name: {"digest": store.put(source.name, source.read_bytes()).digest}
        for source in (FIXTURES / "esde-mini").iterdir()
        if source.suffix in {".png", ".xml"}
    }
    directory = paths.themes_dir() / ESDE_ID
    directory.mkdir(parents=True)
    (directory / "theme.json").write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "kind": "steamzero-theme-v1",
                "id": ESDE_ID,
                "name": "Fixture ES-DE mínimo",
                "version": "1",
                "license": "CC0-1.0",
                "assets": assets,
            }
        ),
        encoding="utf-8",
    )


def test_qml_desenha_pixels_das_cenas_esde_e_retrofe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert RUNNER is not None, "qmltestrunner Qt 6 é obrigatório para esta prova"
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
    _install_esde()
    source = tmp_path / "retrofe"
    shutil.copytree(FIXTURES / "retrofe-mini", source)
    dashboard = DesktopDashboard()
    dashboard.theme_import_retrofe_apply(
        str(source), "layout", RETROFE_ID, "RetroFE E2E", "Autor", "CC0-1.0"
    )
    ready: queue.Queue[DesktopControlServer] = queue.Queue()

    def run_server() -> None:
        store = StateStore(tmp_path / "state.db")
        store.migrate()
        server = DesktopControlServer(
            ExperienceCoordinator(Context(), (), store), "scene-token", dashboard
        )
        ready.put(server)
        server.serve_forever()
        server.server_close()
        store.close()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    server = ready.get(timeout=5)
    CONFIG.parent.mkdir(exist_ok=True)
    CONFIG.write_text(
        json.dumps(
            {
                "apiUrl": f"http://127.0.0.1:{server.server_port}",
                "apiToken": "scene-token",
                "esdeId": ESDE_ID,
                "retrofeId": RETROFE_ID,
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "QT_FORCE_STDERR_LOGGING": "1",
            "QT_LOGGING_RULES": "",
            "QML_XHR_ALLOW_FILE_READ": "1",
        }
    )
    try:
        completed = subprocess.run(
            [str(RUNNER), "-input", str(HARNESS)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    finally:
        CONFIG.unlink(missing_ok=True)
        server.shutdown()
        thread.join(timeout=3)
    output = (completed.stdout or "") + (completed.stderr or "")
    assert completed.returncode == 0, f"render de cena reprovou:\n{output[-5000:]}"
    assert "FAIL" not in output, output[-5000:]
