# SPDX-License-Identifier: GPL-3.0-or-later
"""Jornada QML + bridge real para confirmações, jobs e recovery.

Não há mock dentro do QML: o caso sobe a mesma ``DesktopControlServer`` usada
pelo produto, publica contratos e só então o QuickTest clica nos controles.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from steamzero.adapters.desktop_contracts import handheld_ui_contracts
from steamzero.adapters.desktop_ui import DesktopControlServer
from steamzero.core.state import StateStore
from steamzero.domain.desktop import DesktopContext, DisplayState, ExperienceCoordinator

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests" / "qml" / "check_confirm_job_recovery_e2e.qml"
CONFIG = ROOT / "build" / "ui-confirm-job-e2e.json"


def _qt6_runner() -> str | None:
    for candidate in (
        Path("/usr/lib/qt6/bin/qmltestrunner"),
        Path("/usr/lib64/qt6/bin/qmltestrunner"),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which("qmltestrunner6")


RUNNER = _qt6_runner()


class _Context:
    def snapshot(self) -> DesktopContext:
        return DesktopContext(
            "deck-lcd",
            "wayland",
            (DisplayState("eDP-1", True, True, 800, 1280, 60.0, 1.35),),
            False,
            False,
            False,
            frozenset(),
        )


class _JourneyDashboard:
    """Dados apenas em memória; nenhum componente, jogo ou raiz do host é aberto."""

    def __init__(self) -> None:
        self.apply_calls = 0
        self.cancel_calls = 0
        self.retry_calls = 0
        self.started = {name: threading.Event() for name in ("apply", "cancel", "retry", "list")}
        self.release = {name: threading.Event() for name in ("apply", "cancel", "retry", "list")}
        self.block_first_list = True
        self.jobs: list[dict[str, Any]] = [
            {
                "jobId": "running-job",
                "type": "library.scan",
                "state": "running",
                "progress": {"current": 1, "total": 2, "unit": "itens"},
                "canCancel": True,
                "canRetry": False,
                "result": {},
            },
            {
                "jobId": "failed-job",
                "type": "library.scan",
                "state": "failed",
                "progress": {},
                "canCancel": False,
                "canRetry": True,
                "result": {"message": "Falha simulada para jornada"},
            },
        ]

    def snapshot(self, _status: dict[str, object]) -> dict[str, object]:
        return {
            "uiContracts": handheld_ui_contracts(),
            "emulation": {"schemaVersion": 1, "emulators": [], "jobs": self.jobs},
        }

    def plan_component(self, component_id: str, action: str) -> dict[str, object]:
        assert (component_id, action) == ("dolphin", "install")
        return {
            "planId": "component-e2e-plan",
            "confirmToken": "component-e2e-token",
            "action": "install",
            "preview": "Instalação isolada de teste; nenhuma alteração no host.",
        }

    def apply_component(self, plan_id: str, confirm_token: str) -> dict[str, object]:
        assert (plan_id, confirm_token) == ("component-e2e-plan", "component-e2e-token")
        self.apply_calls += 1
        self._await_release("apply")
        return {"status": "ok", "verified": True}

    def list_emulation_jobs(self) -> list[dict[str, object]]:
        if self.block_first_list:
            self.block_first_list = False
            self._await_release("list")
        return self.jobs

    def cancel_emulation_job(self, job_id: str) -> dict[str, object]:
        assert job_id == "running-job"
        self.cancel_calls += 1
        self._await_release("cancel")
        self.jobs[0] = {**self.jobs[0], "state": "cancelled", "canCancel": False}
        return self.jobs[0]

    def retry_emulation_job(self, job_id: str) -> dict[str, object]:
        assert job_id == "failed-job"
        self.retry_calls += 1
        self._await_release("retry")
        self.jobs[1] = {**self.jobs[1], "state": "succeeded", "canRetry": False}
        return self.jobs[1]

    def _await_release(self, name: str) -> None:
        self.started[name].set()
        assert self.release[name].wait(timeout=5), f"a barreira não liberou {name}"


class _SyncServer(ThreadingHTTPServer):
    dashboard: _JourneyDashboard

    def __init__(self, dashboard: _JourneyDashboard) -> None:
        self.dashboard = dashboard
        super().__init__(("127.0.0.1", 0), _SyncHandler)


class _SyncHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        server = self.server
        assert isinstance(server, _SyncServer)
        if self.path == "/jobs/empty":
            server.dashboard.jobs = []
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        name = self.path.removeprefix("/release/")
        if name not in server.dashboard.started:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not server.dashboard.started[name].wait(timeout=3):
            self.send_error(HTTPStatus.CONFLICT, "mutação ainda não chegou à bridge")
            return
        server.dashboard.release[name].set()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, _format: str, *args: object) -> None:
        pass


@pytest.fixture
def journey_bridge(tmp_path: Path) -> tuple[str, str, _JourneyDashboard, str]:
    ready: queue.Queue[DesktopControlServer] = queue.Queue()
    dashboard = _JourneyDashboard()
    sync_server = _SyncServer(dashboard)
    sync_thread = threading.Thread(target=sync_server.serve_forever, daemon=True)
    sync_thread.start()

    def run_server() -> None:
        store = StateStore(tmp_path / "journey.db")
        store.migrate()
        server = DesktopControlServer(
            ExperienceCoordinator(_Context(), (), store),
            "journey-token",
            dashboard,  # type: ignore[arg-type]
        )
        ready.put(server)
        server.serve_forever()
        server.server_close()
        store.close()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    server = ready.get(timeout=3)
    yield (
        f"http://127.0.0.1:{server.server_port}",
        "journey-token",
        dashboard,
        f"http://127.0.0.1:{sync_server.server_port}",
    )
    server.shutdown()
    thread.join(timeout=2)
    sync_server.shutdown()
    sync_server.server_close()
    sync_thread.join(timeout=2)


def test_confirm_job_and_recovery_journeys_use_qml_and_the_real_bridge(
    journey_bridge: tuple[str, str, _JourneyDashboard, str],
) -> None:
    """Confirmação e jobs usam cliques Qt reais contra a bridge loopback."""
    assert RUNNER is not None, "qmltestrunner Qt 6 é obrigatório para esta prova"
    api_url, api_token, dashboard, sync_url = journey_bridge
    CONFIG.parent.mkdir(exist_ok=True)
    CONFIG.write_text(
        json.dumps({"apiUrl": api_url, "apiToken": api_token, "syncUrl": sync_url}),
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
            timeout=90,
            check=False,
        )
    finally:
        CONFIG.unlink(missing_ok=True)
    output = (completed.stdout or "") + (completed.stderr or "")
    assert completed.returncode == 0, (
        f"jornada QML reprovou (apply={dashboard.apply_calls}, "
        f"cancel={dashboard.cancel_calls}, retry={dashboard.retry_calls}):\n{output[-4000:]}"
    )
    assert "FAIL" not in output, f"assertion QML reprovou:\n{output[-4000:]}"
    assert dashboard.apply_calls == 1, "o clique repetido publicou mais de um apply"
    assert dashboard.cancel_calls == 1, "o CTA de cancelar não chegou à bridge"
    assert dashboard.retry_calls == 1, "o CTA de repetir não chegou à bridge"
