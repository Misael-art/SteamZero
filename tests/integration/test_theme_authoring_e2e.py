# SPDX-License-Identifier: GPL-3.0-or-later
"""V4 — autoria pela UI real contra a bridge real.

O QML (`check_theme_authoring_e2e.qml`) dispara cliques/teclas Qt sobre os
inspetores de efeitos e movimento; o servidor é o `DesktopControlServer` real com
dashboard real e dados em diretório temporário. Depois da corrida, o teste confere
no disco e no resolver de runtime que o tema salvo contém o que a UI editou.
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import threading
from pathlib import Path

import pytest
from tests.integration.test_desktop_ui_bridge import Context
from tests.integration.test_ui_shell_retrofe_import_late_response import RUNNER

from steamzero.adapters.desktop_dashboard import DesktopDashboard
from steamzero.adapters.desktop_ui import DesktopControlServer
from steamzero.core.state import StateStore
from steamzero.domain.desktop import ExperienceCoordinator
from steamzero.domain.theme_editor import _load_manifests_for_resolution
from steamzero.domain.themes import ThemeResolver

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests" / "qml" / "check_theme_authoring_e2e.qml"
CONFIG = ROOT / "build" / "ui-theme-authoring-e2e.json"

pytestmark = pytest.mark.visual


def test_autoria_pela_ui_real_persiste_e_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert RUNNER is not None, "qmltestrunner Qt 6 é obrigatório para esta prova"
    data = tmp_path / "data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
    ready: queue.Queue[DesktopControlServer] = queue.Queue()

    def run_server() -> None:
        store = StateStore(tmp_path / "state.db")
        store.migrate()
        server = DesktopControlServer(
            ExperienceCoordinator(Context(), (), store), "authoring-token", DesktopDashboard()
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
            {"apiUrl": f"http://127.0.0.1:{server.server_port}", "apiToken": "authoring-token"}
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
    assert completed.returncode == 0, f"jornada de autoria reprovou:\n{output[-5000:]}"
    assert "FAIL" not in output, output[-5000:]
    found = re.search(r"THEME_ID=(\S+)", output)
    assert found, f"o harness não publicou o id do tema:\n{output[-2000:]}"
    theme_id = found.group(1)

    saved = json.loads((data / "steamzero" / "themes" / theme_id / "theme.json").read_text())
    assert saved["sceneMotion"]["states"]["focused"]["scale"] == 1.2
    assert [c["duration"] for c in saved["sceneMotion"]["timelines"]["entrada"]["clips"]] == [
        0,
        300,
    ]
    stack = saved["effects"]["stacks"]["focusedCover"]
    assert any(item.get("radius") == 24 for item in stack)

    resolved = ThemeResolver(_load_manifests_for_resolution()).resolve(theme_id)
    assert any(e.parameters.get("radius") == 24 for e in resolved.effects["focusedCover"])
    assert resolved.scene_motion is not None
    assert "entrada" in resolved.scene_motion.timelines
