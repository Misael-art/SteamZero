# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Runtime-QML proof for the Launcher session-menu entry point."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests" / "qml" / "launcher" / "check_launcher_session_overlay_trigger.qml"


def _qt6_runner() -> str | None:
    for candidate in (
        Path("/usr/lib/qt6/bin/qmltestrunner"),
        Path("/usr/lib64/qt6/bin/qmltestrunner"),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which("qmltestrunner6")


RUNNER = _qt6_runner()


@pytest.mark.visual
@pytest.mark.skipif(RUNNER is None, reason="qmltestrunner do Qt6 não está disponível")
def test_menu_key_toggles_only_a_canonical_session_overlay() -> None:
    environment = dict(os.environ)
    environment["QT_QPA_PLATFORM"] = "offscreen"
    completed = subprocess.run(
        [str(RUNNER), "-input", str(HARNESS)],
        capture_output=True,
        text=True,
        timeout=180,
        env=environment,
        cwd=str(ROOT),
        check=False,
    )
    assert completed.returncode == 0, (
        f"o atalho do OSD não respeitou a sessão canônica:\n{completed.stdout}\n{completed.stderr}"
    )
