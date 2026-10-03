# SPDX-License-Identifier: GPL-3.0-or-later

"""Component-level Qt interaction checks for the Journey panel.

The action callback deliberately denies bridge calls. This verifies the
visible, safe failure mode and layout; it does not claim production bridge or
runtime integration.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from tests.integration.test_ui_shell_retrofe_import_late_response import RUNNER

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests" / "qml" / "check_experience_journey.qml"

pytestmark = pytest.mark.visual


def test_journey_panel_compact_layout_and_safe_bridge_failure(tmp_path: Path) -> None:
    assert RUNNER is not None, "qmltestrunner Qt 6 é obrigatório para esta prova"
    env = os.environ.copy()
    env.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "QT_QUICK_BACKEND": "software",
            "QT_FORCE_STDERR_LOGGING": "1",
            "QT_LOGGING_RULES": "",
            "QML_XHR_ALLOW_FILE_READ": "1",
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "XDG_DATA_HOME": str(tmp_path / "data"),
        }
    )
    completed = subprocess.run(
        [str(RUNNER), "-input", str(HARNESS)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    assert completed.returncode == 0, f"painel de Jornada reprovou:\n{output[-6000:]}"
    assert "bridge indisponível" in output or "Totals:" in output
    assert "FAIL!" not in output
    assert "Unable to assign [undefined] to bool" not in output
