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
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
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
    runtime_captures = Path(os.environ.get("SZ_CAPTURE_DIR", str(tmp_path / "runtime-captures")))
    runtime_captures.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(
        json.dumps(
            {
                "apiUrl": f"http://127.0.0.1:{server.server_port}",
                "apiToken": "authoring-token",
                # Capturas só quando pedido (evidência visual); o teste normal não grava.
                "captureDir": os.environ.get("SZ_CAPTURE_DIR", ""),
                "runtimeCaptureDir": str(runtime_captures),
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
    assert completed.returncode == 0, (
        f"jornada de autoria reprovou:\n{output[:2500]}\n...\n{output[-1200:]}"
    )
    measurements = next(
        (
            line.split("TARGET_DIMENSIONS=", 1)[1].strip()
            for line in output.splitlines()
            if "TARGET_DIMENSIONS=" in line
        ),
        "",
    )
    assert measurements, "a jornada QML não registrou as dimensões efetivas dos alvos"
    measured_targets = json.loads(measurements)
    minimum_width = min(float(value["width"]) for value in measured_targets.values())
    minimum_height = min(float(value["height"]) for value in measured_targets.values())
    scales = sorted({float(value["visualScale"]) for value in measured_targets.values()})
    print(
        f"alvos de autoria medidos: {len(measured_targets)}; menor={minimum_width:.0f}x"
        f"{minimum_height:.0f} px; escalas={','.join(str(scale) for scale in scales)}"
    )
    assert "FAIL" not in output, output[-5000:]
    found = re.search(r"THEME_ID=(\S+)", output)
    assert found, f"o harness não publicou o id do tema:\n{output[-2000:]}"
    theme_id = found.group(1)
    assert f"THEME_RUNTIME_APPLIED={theme_id}" in output, output[-5000:]

    saved = json.loads((data / "steamzero" / "themes" / theme_id / "theme.json").read_text())
    assert saved["sceneMotion"]["states"]["loading"]["scale"] == 1.2
    assert saved["sceneMotion"]["timelines"]["entrada"]["kind"] == "sequence"
    assert saved["sceneMotion"]["timelines"]["entrada"]["repeat"] == 2
    assert [c["duration"] for c in saved["sceneMotion"]["timelines"]["entrada"]["clips"]] == [
        0,
        300,
    ]
    assert saved["sceneMotion"]["timelines"]["entrada"]["clips"][1]["state"] == "loading"
    stack = saved["effects"]["stacks"]["focusedCover"]
    assert any(item.get("radius") == 24 for item in stack)
    vignette = next(item for item in stack if item.get("type") == "vignette")
    assert vignette.get("strength") == 0.9 and vignette.get("fallback") == "minimal"
    assert not any(
        item.get("type") == "shadow" and item.get("color") == "#336699" for item in stack
    )
    preference = json.loads(
        (tmp_path / "config" / "steamzero" / "theme-preference-v1.json").read_text()
    )
    assert preference["themeId"] == theme_id

    resolved = ThemeResolver(_load_manifests_for_resolution()).resolve(theme_id)
    assert any(e.parameters.get("radius") == 24 for e in resolved.effects["focusedCover"])
    assert resolved.scene_motion is not None
    assert "entrada" in resolved.scene_motion.timelines

    from PIL import Image, ImageStat

    before_path = runtime_captures / "05-theme-runtime-baseline.png"
    after_path = runtime_captures / "06-theme-runtime-aplicado.png"
    assert (runtime_captures / "07-aura-library-theme-applied.png").is_file()
    with Image.open(before_path) as before_file, Image.open(after_path) as after_file:
        before = before_file.convert("RGB")
        after = after_file.convert("RGB")
        assert before.size == after.size and before.width > 20 and before.height > 20
        # Vinheta escurece a borda da capa. O pixel central é o controle para
        # descartar que a diferença venha de outro tema/tamanho/carregamento.
        border = (0, before.height // 3, before.width // 5, before.height * 2 // 3)
        center = (
            before.width * 2 // 5,
            before.height // 3,
            before.width * 3 // 5,
            before.height * 2 // 3,
        )
        before_border = ImageStat.Stat(before.crop(border)).mean
        after_border = ImageStat.Stat(after.crop(border)).mean
        before_center = ImageStat.Stat(before.crop(center)).mean
        after_center = ImageStat.Stat(after.crop(center)).mean
        assert sum(after_border) < sum(before_border) - 15, (
            f"a vinheta não alterou os pixels de borda: {before_border} -> {after_border}"
        )
        assert abs(sum(after_center) - sum(before_center)) < 12, (
            "a vinheta alterou inesperadamente o controle central: "
            f"{before_center} -> {after_center}"
        )
