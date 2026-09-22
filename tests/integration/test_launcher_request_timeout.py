# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""A cena devolve controle quando a ponte loopback aceita e congela."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests" / "qml" / "launcher" / "check_launcher_request_timeout.qml"


def _runner() -> str | None:
    for candidate in (
        Path("/usr/lib/qt6/bin/qmltestrunner"),
        Path("/usr/lib64/qt6/bin/qmltestrunner"),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which("qmltestrunner6")


RUNNER = _runner()


def _require_runner() -> str:
    if RUNNER is None:
        pytest.fail("QML-VISUAL-ENVIRONMENT-001: qmltestrunner do Qt6 não está disponível")
    return RUNNER


class _HoldingHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.server.received.set()  # type: ignore[attr-defined]
        self.server.release.wait(timeout=15)  # type: ignore[attr-defined]

    def log_message(self, *_: object) -> None:
        pass


@pytest.mark.visual
def test_qml_watchdog_times_out_when_loopback_peer_is_suspended() -> None:
    runner = _require_runner()
    server = ThreadingHTTPServer(("127.0.0.1", 18169), _HoldingHandler)
    server.daemon_threads = True
    server.received = threading.Event()  # type: ignore[attr-defined]
    server.release = threading.Event()  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        environment = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
        completed = subprocess.run(
            [runner, "-input", str(HARNESS)],
            capture_output=True,
            text=True,
            timeout=20,
            cwd=ROOT,
            env=environment,
        )
        assert server.received.wait(timeout=5), (
            "o harness não alcançou o peer suspenso:\n" + completed.stdout + completed.stderr
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
    finally:
        server.release.set()  # type: ignore[attr-defined]
        server.shutdown()
        server.server_close()
