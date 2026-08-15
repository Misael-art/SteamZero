# SPDX-License-Identifier: GPL-3.0-or-later
"""Jornada de credenciais pela UI real com bridge loopback controlada.

Não há mock dentro do QML: o caso sobe a mesma ``DesktopControlServer`` usada
pelo produto, publica o estado dos providers e só então o QuickTest digita,
salva, testa e revoga. Nenhuma credencial real existe: o payload é sintético
e o cofre é o dashboard em memória.
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

import pytest

from steamzero.adapters.desktop_contracts import handheld_ui_contracts
from steamzero.adapters.desktop_ui import DesktopControlServer
from steamzero.core.state import StateStore
from steamzero.domain.desktop import DesktopContext, DisplayState, ExperienceCoordinator

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests" / "qml" / "check_credential_journey_e2e.qml"
CONFIG = ROOT / "build" / "ui-credential-journey-e2e.json"


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


class _CredentialDashboard:
    """Cofre em memória; nenhuma credencial real, disco ou host é tocado."""

    def __init__(self) -> None:
        self.save_calls = 0
        self.test_calls = 0
        self.delete_calls = 0
        self.saved_values: list[tuple[str, dict[str, str]]] = []
        self.reject_tests = False
        self.configured = False
        self.credential_state = "notConfigured"
        self.started = {name: threading.Event() for name in ("save", "test", "delete")}
        self.release = {name: threading.Event() for name in ("save", "test", "delete")}

    def snapshot(self, _status: dict[str, object]) -> dict[str, object]:
        return {
            "uiContracts": handheld_ui_contracts(),
            "emulation": {"schemaVersion": 1, "emulators": [], "jobs": []},
        }

    def _provider(self, **overrides: object) -> dict[str, object]:
        provider: dict[str, object] = {
            "id": "steamgriddb",
            "name": "SteamGridDB",
            "description": "Arte remota",
            "enabled": True,
            "configured": self.configured,
            "credentialState": self.credential_state,
            "credentialTestSupported": True,
            "credentialRevokeSupported": True,
            "credentialFields": [
                {
                    "id": "api_key",
                    "label": "API key",
                    "placeholder": "Cole a chave",
                    "help": "Somente no cofre.",
                    "secret": True,
                    "required": True,
                }
            ],
            "links": {
                "createAccount": "https://www.steamgriddb.com/profile/preferences/api",
                "credentials": "https://www.steamgriddb.com/profile/preferences/api",
                "documentation": "https://www.steamgriddb.com/api/v2",
                "terms": "https://www.steamgriddb.com/terms",
            },
        }
        provider.update(overrides)
        return provider

    def credential_status(self) -> dict[str, object]:
        return {
            "providers": [
                self._provider(),
                self._provider(
                    id="provider-desabilitado",
                    name="Provedor desabilitado",
                    description="Não deve aparecer no diálogo.",
                    enabled=False,
                    configured=False,
                    credentialState="notConfigured",
                    credentialTestSupported=False,
                    credentialRevokeSupported=False,
                    credentialFields=[],
                    links={},
                ),
                self._provider(
                    id="steam-local",
                    name="Integração local com Steam",
                    description="Sem credenciais.",
                    enabled=False,
                    configured=True,
                    credentialState="local",
                    credentialTestSupported=False,
                    credentialRevokeSupported=False,
                    credentialFields=[],
                    links={},
                ),
                self._provider(
                    id="steam-web-api",
                    name="Steam Web API",
                    description="Opcional; não é necessária para atalhos nem artes locais.",
                    enabled=True,
                    configured=False,
                    credentialState="notConfigured",
                    credentialTestSupported=False,
                    credentialRevokeSupported=False,
                    credentialFields=[],
                    links={},
                ),
            ]
        }

    def save_credential(self, provider: str, values: dict[str, str]) -> dict[str, object]:
        assert provider == "steamgriddb"
        self.save_calls += 1
        self.saved_values.append((provider, dict(values)))
        self._await_release("save")
        self.configured = True
        self.credential_state = "stored"
        return {"providerStatus": {"configured": True, "credentialState": "stored"}}

    def test_credential(self, provider: str) -> dict[str, object]:
        assert provider == "steamgriddb"
        self.test_calls += 1
        self._await_release("test")
        if self.reject_tests:
            self.credential_state = "rejected"
            return {
                "valid": False,
                "state": "rejected",
                "error": "chave recusada pela API",
                "providerStatus": {"configured": True, "credentialState": "rejected"},
            }
        self.credential_state = "validated"
        return {
            "valid": True,
            "state": "validated",
            "providerStatus": {"configured": True, "credentialState": "validated"},
        }

    def delete_credential(self, provider: str) -> dict[str, object]:
        assert provider == "steamgriddb"
        self.delete_calls += 1
        self._await_release("delete")
        self.configured = False
        self.credential_state = "notConfigured"
        return {"providerStatus": {"configured": False, "credentialState": "notConfigured"}}

    def _await_release(self, name: str) -> None:
        self.started[name].set()
        assert self.release[name].wait(timeout=5), f"a barreira não liberou {name}"


class _SyncServer(ThreadingHTTPServer):
    dashboard: _CredentialDashboard

    def __init__(self, dashboard: _CredentialDashboard) -> None:
        self.dashboard = dashboard
        super().__init__(("127.0.0.1", 0), _SyncHandler)


class _SyncHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        server = self.server
        assert isinstance(server, _SyncServer)
        if self.path == "/credential/reject-tests":
            server.dashboard.reject_tests = True
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
def credential_bridge(tmp_path: Path) -> tuple[str, str, _CredentialDashboard, str]:
    ready: queue.Queue[DesktopControlServer] = queue.Queue()
    dashboard = _CredentialDashboard()
    sync_server = _SyncServer(dashboard)
    sync_thread = threading.Thread(target=sync_server.serve_forever, daemon=True)
    sync_thread.start()

    def run_server() -> None:
        store = StateStore(tmp_path / "credential.db")
        store.migrate()
        server = DesktopControlServer(
            ExperienceCoordinator(_Context(), (), store),
            "credential-token",
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
        "credential-token",
        dashboard,
        f"http://127.0.0.1:{sync_server.server_port}",
    )
    server.shutdown()
    thread.join(timeout=2)
    sync_server.shutdown()
    sync_server.server_close()
    sync_thread.join(timeout=2)


def test_credential_journey_uses_qml_and_the_real_bridge(
    credential_bridge: tuple[str, str, _CredentialDashboard, str],
) -> None:
    """Salvar/testar/revogar usam cliques Qt reais contra a bridge loopback."""
    assert RUNNER is not None, "qmltestrunner Qt 6 é obrigatório para esta prova"
    api_url, api_token, dashboard, sync_url = credential_bridge
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
            timeout=120,
            check=False,
        )
    finally:
        CONFIG.unlink(missing_ok=True)
    output = (completed.stdout or "") + (completed.stderr or "")
    assert completed.returncode == 0, (
        f"jornada de credenciais reprovou (save={dashboard.save_calls}, "
        f"test={dashboard.test_calls}, delete={dashboard.delete_calls}):\n{output[-4000:]}"
    )
    assert "FAIL" not in output, f"assertion QML reprovou:\n{output[-4000:]}"
    assert dashboard.save_calls == 1, "o clique repetido publicou mais de um salvamento"
    assert dashboard.test_calls == 2, "o CTA de teste não chegou à bridge nas duas rodadas"
    assert dashboard.delete_calls == 1, "o CTA de revogar não chegou à bridge"
    assert dashboard.reject_tests, "o modo de rejeição lógica não foi ativado"
    assert dashboard.saved_values == [("steamgriddb", {"api_key": "segredo-de-teste"})], (
        "o payload do cofre não contém somente o campo declarado"
    )
