# SPDX-License-Identifier: GPL-3.0-or-later
"""Bridge QML: loopback, token, allowlist e confirmação do plano."""

from __future__ import annotations

import json
import queue
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, cast

import pytest

from steamzero.adapters import desktop_ui
from steamzero.adapters.desktop_dashboard import DesktopDashboard
from steamzero.adapters.desktop_ui import DesktopControlServer
from steamzero.adapters.emulation import EmulationController, SessionSecretStore
from steamzero.core.state import StateStore
from steamzero.domain.desktop import (
    DesktopConflictAction,
    DesktopContext,
    DisplayState,
    ExperienceCoordinator,
)


class Context:
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


class ConflictContext:
    def __init__(self) -> None:
        self.value = DesktopContext(
            "deck-lcd",
            "wayland",
            (DisplayState("eDP-1", True, True, 800, 1280, 60.0, 1.35),),
            False,
            False,
            False,
            frozenset(),
            ("controlador externo ativo: test-mode-watcher.service",),
        )

    def snapshot(self) -> DesktopContext:
        return self.value


class ConflictResolver:
    def __init__(self, context: ConflictContext) -> None:
        self.context = context
        self.calls = 0

    def actions(self, context: DesktopContext) -> tuple[DesktopConflictAction, ...]:
        if not context.conflicts:
            return ()
        return (
            DesktopConflictAction(
                "release-test-watcher",
                "test-mode-watcher.service",
                "user",
                "Desativar watcher de teste",
                False,
                (("systemctl", "--user", "stop", "test-mode-watcher.service"),),
            ),
        )

    def release(self, action: DesktopConflictAction) -> dict[str, object]:
        self.calls += 1
        self.context.value = DesktopContext(**{**self.context.value.__dict__, "conflicts": ()})
        return {"stopped": True, "disabled": True}


class BrokenContext:
    def snapshot(self) -> DesktopContext:
        raise RuntimeError("falha inesperada simulada")


class FakeSecretStore(SessionSecretStore):
    """Cofre estritamente em memória para atravessar a bridge sem credenciais reais."""


def test_ui_bootstrap_does_not_put_snapshot_in_process_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    argv: list[str] = []

    class Coordinator:
        def status(self) -> dict[str, object]:
            raise AssertionError("status deve ser obtido pela bridge após o QML iniciar")

    class Server:
        server_port = 43210
        timeout = 0.0

        def __init__(self, *_args: object) -> None:
            pass

        def handle_request(self) -> None:
            raise AssertionError("processo de teste já terminou")

        def server_close(self) -> None:
            pass

    class Process:
        returncode = 0

        def poll(self) -> int:
            return 0

    def popen(command: list[str], **_kwargs: object) -> Process:
        argv.extend(command)
        return Process()

    monkeypatch.setattr(desktop_ui.shutil, "which", lambda _name: "/usr/bin/qml6")
    monkeypatch.setattr(desktop_ui, "DesktopDashboard", lambda: object())
    monkeypatch.setattr(desktop_ui, "DesktopControlServer", Server)
    monkeypatch.setattr(desktop_ui.subprocess, "Popen", popen)

    assert desktop_ui.launch_desktop_ui(Coordinator()) == 0  # type: ignore[arg-type]
    assert "--steamzero-status" not in argv
    assert argv[0] == "/usr/bin/qml6"
    assert "--steamzero-api" in argv
    assert "--steamzero-token" in argv
    assert sum(len(value) for value in argv) < 4096


class FakeDashboard:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def snapshot(self, _status: dict[str, object]) -> dict[str, object]:
        return {
            "components": [{"id": "dolphin"}],
            "steam": [{"id": "steam-client"}],
            "steamGameplay": {"games": [{"id": "10"}]},
        }

    def plan_component(self, component_id: str) -> dict[str, object]:
        self.calls.append(("plan", component_id))
        return {"planId": "component-plan", "confirmToken": "confirm"}

    def apply_component(self, plan_id: str, confirm_token: str) -> dict[str, object]:
        self.calls.append(("apply", plan_id, confirm_token))
        return {"status": "ok"}

    def launch_component(self, component_id: str) -> dict[str, object]:
        self.calls.append(("launch", component_id))
        return {"status": "started"}

    def plan_emulation_emulator(self, emulator_id: str, action: str) -> dict[str, object]:
        self.calls.append(("emulation-emulator-plan", emulator_id, action))
        return {"planId": "emulator-plan", "confirmToken": "emulator-confirm"}

    def apply_emulation_emulator(self, plan_id: str, confirm_token: str) -> dict[str, object]:
        self.calls.append(("emulation-emulator-apply", plan_id, confirm_token))
        return {"status": "committed"}

    def launch_emulation_emulator(self, emulator_id: str) -> dict[str, object]:
        self.calls.append(("emulation-emulator-launch", emulator_id))
        return {"status": "started"}

    def stop_emulation_emulator(self, emulator_id: str) -> dict[str, object]:
        self.calls.append(("emulation-emulator-stop", emulator_id))
        return {"status": "stopping"}

    def launch_emulation_game(self, game_id: str) -> dict[str, object]:
        self.calls.append(("emulation-game-launch", game_id))
        return {"status": "started", "gameId": game_id}

    def launch_cloud_platform(self, platform_id: str) -> dict[str, object]:
        self.calls.append(("cloud-launch", platform_id))
        return {"status": "started", "platformId": platform_id}

    def plan_emulation_action(self, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("emulation-action-plan", str(payload["actionId"])))
        return {"planId": "emulation-plan", "confirmToken": "emulation-confirm"}

    def apply_emulation_action(self, plan_id: str, confirm_token: str) -> dict[str, object]:
        self.calls.append(("emulation-action-apply", plan_id, confirm_token))
        return {"status": "committed"}

    def rollback_emulation_action(self, operation_id: str) -> dict[str, object]:
        self.calls.append(("emulation-action-rollback", operation_id))
        return {"status": "rolled-back"}

    def scan_emulation_library(self) -> dict[str, object]:
        self.calls.append(("emulation-library-scan",))
        return {"status": "scanned", "games": 2}

    def list_emulation_jobs(self) -> list[dict[str, object]]:
        self.calls.append(("emulation-jobs-list",))
        return [{"jobId": "job-1", "state": "running"}]

    def cancel_emulation_job(self, job_id: str) -> dict[str, object]:
        self.calls.append(("emulation-job-cancel", job_id))
        return {"jobId": job_id, "state": "cancelled"}

    def retry_emulation_job(self, job_id: str) -> dict[str, object]:
        self.calls.append(("emulation-job-retry", job_id))
        return {"jobId": "job-2", "retryOf": job_id, "state": "succeeded"}

    def open_steam(self, target: str) -> dict[str, object]:
        self.calls.append(("steam", target))
        return {"status": "started", "target": target}

    def launch_steam_game(self, game_id: str) -> dict[str, object]:
        self.calls.append(("steam-game-launch", game_id))
        return {"status": "started", "gameId": game_id}

    def open_steam_input(self, game_id: str) -> dict[str, object]:
        self.calls.append(("steam-input", game_id))
        return {"status": "started", "gameId": game_id}

    def plan_steam_gameplay(
        self, payload: dict[str, object], _status: dict[str, object]
    ) -> dict[str, object]:
        self.calls.append(("gameplay-plan", str(payload["gameId"])))
        return {"planId": "gameplay-plan", "confirmToken": "gameplay-confirm"}

    def hud_presets(self) -> dict[str, object]:
        self.calls.append(("hud-presets",))
        return {"schemaVersion": 1, "presets": []}

    def apply_steam_gameplay(
        self,
        plan_id: str,
        confirm_token: str,
        _status: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append(("gameplay-apply", plan_id, confirm_token))
        return {"status": "saved"}

    def recover_steam_gameplay(self, game_id: str) -> dict[str, object]:
        self.calls.append(("gameplay-recover", game_id))
        return {"status": "recovered", "gameId": game_id}

    def rollback_steam_gameplay(self, operation_id: str) -> dict[str, object]:
        self.calls.append(("gameplay-rollback", operation_id))
        return {"status": "rolled-back", "operationId": operation_id}

    def plan_steam_launch_options(self, game_id: str) -> dict[str, object]:
        self.calls.append(("launch-options-plan", game_id))
        return {"planId": "launch-options-plan", "confirmToken": "launch-options-confirm"}

    def apply_steam_launch_options(
        self, plan_id: str, confirm_token: str, game_id: str
    ) -> dict[str, object]:
        self.calls.append(("launch-options-apply", plan_id, confirm_token, game_id))
        return {"status": "configured", "operationId": "launch-options-operation"}

    def rollback_steam_launch_options(self, operation_id: str) -> dict[str, object]:
        self.calls.append(("launch-options-rollback", operation_id))
        return {"status": "rolled-back"}

    def plan_lsfg_install(self) -> dict[str, object]:
        self.calls.append(("lsfg-plan",))
        return {"planId": "lsfg-plan", "confirmToken": "lsfg-confirm"}

    def apply_lsfg_install(self, plan_id: str, confirm_token: str) -> dict[str, object]:
        self.calls.append(("lsfg-apply", plan_id, confirm_token))
        return {"status": "installed", "operationId": "lsfg-operation"}

    def rollback_lsfg_install(self, operation_id: str) -> dict[str, object]:
        self.calls.append(("lsfg-rollback", operation_id))
        return {"status": "rolled-back"}

    def operations_history(self, page: int, page_size: int) -> dict[str, object]:
        self.calls.append(("operations-history", str(page), str(page_size)))
        return {"page": page, "pageSize": page_size, "total": 1, "items": []}

    def operation_detail(self, operation_id: str) -> dict[str, object]:
        self.calls.append(("operation-detail", operation_id))
        return {"operation": {"operationId": operation_id}}

    def plan_operation_rollback(self, operation_id: str) -> dict[str, object]:
        self.calls.append(("operation-rollback-plan", operation_id))
        return {"plan": {"planId": "rollback-plan", "confirmToken": "rollback-confirm"}}

    def apply_operation_rollback(self, plan_id: str, confirm_token: str) -> dict[str, object]:
        self.calls.append(("operation-rollback-apply", plan_id, confirm_token))
        return {"result": {"status": "rolled-back", "verified": True}}

    def collection_state(self) -> dict[str, object]:
        self.calls.append(("collections-list",))
        return {"schemaVersion": 1, "favorites": ["steam:10"]}

    def plan_collection_action(self, action: dict[str, object]) -> dict[str, object]:
        self.calls.append(("collections-plan", str(action["actionId"])))
        return {"planId": "collection-plan", "confirmToken": "collection-confirm"}

    def apply_collection_action(self, plan_id: str, confirm_token: str) -> dict[str, object]:
        self.calls.append(("collections-apply", plan_id, confirm_token))
        return {"status": "ok", "operationId": "collection-operation"}

    def library_health(self) -> dict[str, object]:
        self.calls.append(("library-health",))
        return {"schemaVersion": 1, "state": "healthy"}

    def plan_library_health(self) -> dict[str, object]:
        self.calls.append(("library-health-plan",))
        return {"planId": "health-plan", "confirmToken": "health-confirm"}

    def apply_library_health(self, plan_id: str, confirm_token: str) -> dict[str, object]:
        self.calls.append(("library-health-apply", plan_id, confirm_token))
        return {"status": "committed", "operationId": "health-operation"}

    def admin_health(self) -> dict[str, object]:
        self.calls.append(("admin-health",))
        return {"available": True, "state": "healthy"}


@pytest.fixture
def bridge(tmp_path: Path) -> tuple[str, str]:
    ready: queue.Queue[DesktopControlServer] = queue.Queue()

    def run_server() -> None:
        store = StateStore(tmp_path / "state.db")
        store.migrate()
        server = DesktopControlServer(ExperienceCoordinator(Context(), (), store), "secret-token")
        ready.put(server)
        server.serve_forever()
        server.server_close()
        store.close()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    server = ready.get(timeout=3)
    yield f"http://127.0.0.1:{server.server_port}", "secret-token"
    server.shutdown()
    thread.join(timeout=2)


@pytest.fixture
def conflict_bridge(tmp_path: Path) -> tuple[str, str, ConflictResolver]:
    ready: queue.Queue[DesktopControlServer] = queue.Queue()
    context = ConflictContext()
    resolver = ConflictResolver(context)

    def run_server() -> None:
        store = StateStore(tmp_path / "conflict-state.db")
        store.migrate()
        coordinator = ExperienceCoordinator(context, (), store, resolver)
        server = DesktopControlServer(coordinator, "secret-token")
        ready.put(server)
        server.serve_forever()
        server.server_close()
        store.close()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    server = ready.get(timeout=3)
    yield f"http://127.0.0.1:{server.server_port}", "secret-token", resolver
    server.shutdown()
    thread.join(timeout=2)


@pytest.fixture
def broken_bridge(tmp_path: Path) -> tuple[str, str]:
    ready: queue.Queue[DesktopControlServer] = queue.Queue()

    def run_server() -> None:
        store = StateStore(tmp_path / "broken-state.db")
        store.migrate()
        server = DesktopControlServer(
            ExperienceCoordinator(BrokenContext(), (), store), "secret-token"
        )
        ready.put(server)
        server.serve_forever()
        server.server_close()
        store.close()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    server = ready.get(timeout=3)
    yield f"http://127.0.0.1:{server.server_port}", "secret-token"
    server.shutdown()
    thread.join(timeout=2)


@pytest.fixture
def dashboard_bridge(tmp_path: Path) -> tuple[str, str, FakeDashboard]:
    ready: queue.Queue[DesktopControlServer] = queue.Queue()
    dashboard = FakeDashboard()

    def run_server() -> None:
        store = StateStore(tmp_path / "dashboard-state.db")
        store.migrate()
        server = DesktopControlServer(
            ExperienceCoordinator(Context(), (), store),
            "secret-token",
            dashboard,  # type: ignore[arg-type]
        )
        ready.put(server)
        server.serve_forever()
        server.server_close()
        store.close()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    server = ready.get(timeout=3)
    yield f"http://127.0.0.1:{server.server_port}", "secret-token", dashboard
    server.shutdown()
    thread.join(timeout=2)


@pytest.fixture
def conflicted_dashboard_bridge(tmp_path: Path) -> tuple[str, str, FakeDashboard]:
    ready: queue.Queue[DesktopControlServer] = queue.Queue()
    dashboard = FakeDashboard()

    def run_server() -> None:
        store = StateStore(tmp_path / "conflicted-dashboard-state.db")
        store.migrate()
        server = DesktopControlServer(
            ExperienceCoordinator(ConflictContext(), (), store),
            "secret-token",
            dashboard,  # type: ignore[arg-type]
        )
        ready.put(server)
        server.serve_forever()
        server.server_close()
        store.close()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    server = ready.get(timeout=3)
    yield f"http://127.0.0.1:{server.server_port}", "secret-token", dashboard
    server.shutdown()
    thread.join(timeout=2)


@pytest.fixture
def credential_bridge(tmp_path: Path) -> tuple[str, str, FakeSecretStore]:
    ready: queue.Queue[DesktopControlServer] = queue.Queue()
    secret_store = FakeSecretStore()
    store_factory = lambda: StateStore(tmp_path / "credential-state.db")  # noqa: E731
    emulation = EmulationController(
        store_factory=store_factory,
        which=lambda _command: None,
        spawn=lambda _argv: None,
        secret_store=secret_store,
    )
    dashboard = DesktopDashboard(
        store_factory=store_factory,
        emulation=emulation,
        which=lambda _command: None,
        spawn=lambda _argv: None,
    )

    def run_server() -> None:
        store = StateStore(tmp_path / "credential-coordinator.db")
        store.migrate()
        server = DesktopControlServer(
            ExperienceCoordinator(Context(), (), store),
            "secret-token",
            dashboard,
        )
        ready.put(server)
        server.serve_forever()
        server.server_close()
        store.close()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    server = ready.get(timeout=3)
    yield f"http://127.0.0.1:{server.server_port}", "secret-token", secret_store
    server.shutdown()
    thread.join(timeout=2)


def request_json(
    base: str, token: str, path: str, payload: dict[str, Any] | None = None
) -> dict[str, object]:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(  # noqa: S310 - URL loopback criada pela fixture
        base + path,
        data=data,
        method="GET" if payload is None else "POST",
        headers={"X-SteamZero-Token": token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=3) as response:  # noqa: S310 - loopback fixture
        loaded: dict[str, object] = json.loads(response.read())
        return loaded


def test_credential_bridge_complete_flow_uses_only_fake_secret_store(
    credential_bridge: tuple[str, str, FakeSecretStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from steamzero.adapters.scraping.steamgriddb import SteamGridDbAdapter

    base, token, secret_store = credential_bridge
    initial = request_json(base, token, "/scraping/credential/status", {})
    providers = cast(list[dict[str, object]], initial["providers"])
    initial_provider = next(item for item in providers if item["id"] == "steamgriddb")
    assert initial_provider["credentialState"] == "notConfigured"

    saved = request_json(
        base,
        token,
        "/scraping/credential/save",
        {
            "provider": "steamgriddb",
            "credentials": {"api_key": "bridge-only-secret"},
        },
    )
    assert saved["state"] == "stored"
    stored = secret_store.retrieve("steamgriddb", "api_key")
    assert stored is not None and stored.reveal() == "bridge-only-secret"
    assert "bridge-only-secret" not in json.dumps(saved, sort_keys=True)

    monkeypatch.setattr(SteamGridDbAdapter, "test_connection", lambda _self: True)
    tested = request_json(
        base,
        token,
        "/scraping/credential/test",
        {"provider": "steamgriddb"},
    )
    assert tested["valid"] is True
    assert tested["state"] == "validated"
    assert "bridge-only-secret" not in json.dumps(tested, sort_keys=True)

    deleted = request_json(
        base,
        token,
        "/scraping/credential/delete",
        {"provider": "steamgriddb"},
    )
    assert deleted["state"] == "notConfigured"
    assert secret_store.retrieve("steamgriddb", "api_key") is None


def test_bridge_rejects_missing_token(bridge: tuple[str, str]) -> None:
    base, _ = bridge
    with pytest.raises(urllib.error.HTTPError) as error:
        request_json(base, "wrong", "/status")
    assert error.value.code == 403
    error.value.close()


def test_bridge_plan_and_confirmed_safe_apply(bridge: tuple[str, str]) -> None:
    base, token = bridge
    status = request_json(base, token, "/status")
    assert status["independentRuntime"] is True
    planned = request_json(base, token, "/plan", {"profile": "safe"})
    plan = planned["plan"]
    assert isinstance(plan, dict)
    applied = request_json(
        base,
        token,
        "/reset",
        {"planId": str(plan["planId"]), "confirmToken": str(plan["confirmToken"])},
    )
    profile = applied["profile"]
    assert isinstance(profile, dict)
    assert profile["id"] == "safe"


def test_bridge_conflict_resolution_requires_confirmation_and_refreshes_status(
    conflict_bridge: tuple[str, str, ConflictResolver],
) -> None:
    base, token, resolver = conflict_bridge
    status = request_json(base, token, "/status")
    actions = status["conflictActions"]
    assert isinstance(actions, list) and len(actions) == 1
    action = actions[0]
    assert isinstance(action, dict)

    planned = request_json(base, token, "/conflict/plan", {"actionId": str(action["actionId"])})
    plan = planned["plan"]
    assert isinstance(plan, dict)
    with pytest.raises(urllib.error.HTTPError) as error:
        request_json(
            base,
            token,
            "/conflict/apply",
            {"planId": str(plan["planId"]), "confirmToken": "incorreto"},
        )
    assert error.value.code == 409
    error.value.close()
    assert resolver.calls == 0

    result = request_json(
        base,
        token,
        "/conflict/apply",
        {"planId": str(plan["planId"]), "confirmToken": str(plan["confirmToken"])},
    )
    assert result["status"] == "ok"
    assert resolver.calls == 1
    refreshed = request_json(base, token, "/status")
    assert refreshed["conflictActions"] == []


def test_bridge_returns_structured_error_instead_of_closing_connection(
    broken_bridge: tuple[str, str],
) -> None:
    base, token = broken_bridge
    with pytest.raises(urllib.error.HTTPError) as error:
        request_json(base, token, "/status")
    assert error.value.code == 500
    payload = json.loads(error.value.read())
    assert payload["error"]["code"] == "E-INTERNAL-UNEXPECTED"
    error.value.close()


def test_bridge_exposes_dashboard_component_and_steam_actions(
    dashboard_bridge: tuple[str, str, FakeDashboard],
) -> None:
    base, token, dashboard = dashboard_bridge
    status = request_json(base, token, "/status")
    assert status["dashboard"] == {
        "components": [{"id": "dolphin"}],
        "steam": [{"id": "steam-client"}],
        "steamGameplay": {"games": [{"id": "10"}]},
    }

    planned = request_json(base, token, "/component/plan", {"componentId": "dolphin"})
    assert planned["plan"] == {"planId": "component-plan", "confirmToken": "confirm"}
    request_json(
        base,
        token,
        "/component/apply",
        {"planId": "component-plan", "confirmToken": "confirm"},
    )
    request_json(base, token, "/component/launch", {"componentId": "dolphin"})
    emulator_plan = request_json(
        base,
        token,
        "/emulation/emulator/plan",
        {"emulatorId": "eden", "action": "install"},
    )
    assert emulator_plan["plan"] == {
        "planId": "emulator-plan",
        "confirmToken": "emulator-confirm",
    }
    request_json(
        base,
        token,
        "/emulation/emulator/apply",
        {"planId": "emulator-plan", "confirmToken": "emulator-confirm"},
    )
    request_json(base, token, "/emulation/emulator/launch", {"emulatorId": "eden"})
    request_json(base, token, "/emulation/emulator/stop", {"emulatorId": "eden"})
    request_json(base, token, "/emulation/game/launch", {"gameId": "game-1"})
    request_json(base, token, "/cloud/launch", {"platformId": "xbox-cloud-gaming"})
    emulation_plan = request_json(
        base,
        token,
        "/emulation/action/plan",
        {"actionId": "storage.recover"},
    )
    assert emulation_plan["plan"] == {
        "planId": "emulation-plan",
        "confirmToken": "emulation-confirm",
    }
    request_json(
        base,
        token,
        "/emulation/action/apply",
        {"planId": "emulation-plan", "confirmToken": "emulation-confirm"},
    )
    request_json(
        base,
        token,
        "/emulation/action/rollback",
        {"operationId": "emulation-operation"},
    )
    request_json(base, token, "/emulation/library/scan", {})
    jobs = request_json(base, token, "/emulation/jobs")
    assert jobs["jobs"] == [{"jobId": "job-1", "state": "running"}]
    request_json(base, token, "/emulation/job/cancel", {"jobId": "job-1"})
    request_json(base, token, "/emulation/job/retry", {"jobId": "job-1"})
    request_json(base, token, "/steam/open", {"target": "library"})
    request_json(base, token, "/steam/game/launch", {"gameId": "10"})
    request_json(base, token, "/steam/input/open", {"gameId": "10"})
    assert request_json(base, token, "/hud/presets")["schemaVersion"] == 1
    gameplay_plan = request_json(
        base,
        token,
        "/steam/gameplay/plan",
        {"gameId": "10"},
    )
    assert gameplay_plan["plan"] == {
        "planId": "gameplay-plan",
        "confirmToken": "gameplay-confirm",
    }
    request_json(
        base,
        token,
        "/steam/gameplay/apply",
        {"planId": "gameplay-plan", "confirmToken": "gameplay-confirm"},
    )
    request_json(
        base,
        token,
        "/steam/gameplay/rollback",
        {"operationId": "gameplay-operation"},
    )
    request_json(base, token, "/steam/gameplay/recover", {"gameId": "10"})
    launch_options_plan = request_json(
        base, token, "/steam/gameplay/launch-options/plan", {"gameId": "10"}
    )
    assert launch_options_plan["plan"] == {
        "planId": "launch-options-plan",
        "confirmToken": "launch-options-confirm",
    }
    request_json(
        base,
        token,
        "/steam/gameplay/launch-options/apply",
        {
            "planId": "launch-options-plan",
            "confirmToken": "launch-options-confirm",
            "gameId": "10",
        },
    )
    request_json(
        base,
        token,
        "/steam/gameplay/launch-options/rollback",
        {"operationId": "launch-options-operation"},
    )
    lsfg_plan = request_json(base, token, "/system/lsfg/plan", {})
    assert lsfg_plan["plan"] == {
        "planId": "lsfg-plan",
        "confirmToken": "lsfg-confirm",
    }
    request_json(
        base,
        token,
        "/system/lsfg/apply",
        {"planId": "lsfg-plan", "confirmToken": "lsfg-confirm"},
    )
    request_json(
        base,
        token,
        "/system/lsfg/rollback",
        {"operationId": "lsfg-operation"},
    )
    operations = request_json(base, token, "/system/operations?page=2&pageSize=5")
    assert operations == {"page": 2, "pageSize": 5, "total": 1, "items": []}
    assert request_json(
        base,
        token,
        "/system/operations/show",
        {"operationId": "operation-1"},
    ) == {"operation": {"operationId": "operation-1"}}
    rollback_plan = request_json(
        base,
        token,
        "/system/operations/rollback/plan",
        {"operationId": "operation-1"},
    )
    assert rollback_plan["plan"]["planId"] == "rollback-plan"
    rollback_result = request_json(
        base,
        token,
        "/system/operations/rollback/apply",
        {"planId": "rollback-plan", "confirmToken": "rollback-confirm"},
    )
    assert rollback_result["result"]["verified"] is True
    assert request_json(base, token, "/collections")["favorites"] == ["steam:10"]
    collection_plan = request_json(
        base,
        token,
        "/collections/plan",
        {"action": {"actionId": "favorite.set", "gameRef": "steam:10", "value": True}},
    )
    assert collection_plan["planId"] == "collection-plan"
    request_json(
        base,
        token,
        "/collections/apply",
        {"planId": "collection-plan", "confirmToken": "collection-confirm"},
    )
    assert request_json(base, token, "/library/health")["state"] == "healthy"
    health_plan = request_json(base, token, "/library/health/plan", {})
    assert health_plan["plan"]["planId"] == "health-plan"
    request_json(
        base,
        token,
        "/library/health/apply",
        {"planId": "health-plan", "confirmToken": "health-confirm"},
    )
    assert request_json(base, token, "/system/admin/health") == {
        "available": True,
        "state": "healthy",
    }
    assert dashboard.calls == [
        ("plan", "dolphin"),
        ("apply", "component-plan", "confirm"),
        ("launch", "dolphin"),
        ("emulation-emulator-plan", "eden", "install"),
        ("emulation-emulator-apply", "emulator-plan", "emulator-confirm"),
        ("emulation-emulator-launch", "eden"),
        ("emulation-emulator-stop", "eden"),
        ("emulation-game-launch", "game-1"),
        ("cloud-launch", "xbox-cloud-gaming"),
        ("emulation-action-plan", "storage.recover"),
        ("emulation-action-apply", "emulation-plan", "emulation-confirm"),
        ("emulation-action-rollback", "emulation-operation"),
        ("emulation-library-scan",),
        ("emulation-jobs-list",),
        ("emulation-job-cancel", "job-1"),
        ("emulation-job-retry", "job-1"),
        ("steam", "library"),
        ("steam-game-launch", "10"),
        ("steam-input", "10"),
        ("hud-presets",),
        ("gameplay-plan", "10"),
        ("gameplay-apply", "gameplay-plan", "gameplay-confirm"),
        ("gameplay-rollback", "gameplay-operation"),
        ("gameplay-recover", "10"),
        ("launch-options-plan", "10"),
        (
            "launch-options-apply",
            "launch-options-plan",
            "launch-options-confirm",
            "10",
        ),
        ("launch-options-rollback", "launch-options-operation"),
        ("lsfg-plan",),
        ("lsfg-apply", "lsfg-plan", "lsfg-confirm"),
        ("lsfg-rollback", "lsfg-operation"),
        ("operations-history", "2", "5"),
        ("operation-detail", "operation-1"),
        ("operation-rollback-plan", "operation-1"),
        ("operation-rollback-apply", "rollback-plan", "rollback-confirm"),
        ("collections-list",),
        ("collections-plan", "favorite.set"),
        ("collections-apply", "collection-plan", "collection-confirm"),
        ("library-health",),
        ("library-health-plan",),
        ("library-health-apply", "health-plan", "health-confirm"),
        ("admin-health",),
    ]


def test_bridge_rechecks_owner_conflict_before_dashboard_mutations(
    conflicted_dashboard_bridge: tuple[str, str, FakeDashboard],
) -> None:
    base, token, dashboard = conflicted_dashboard_bridge

    with pytest.raises(urllib.error.HTTPError) as error:
        request_json(
            base,
            token,
            "/component/apply",
            {"planId": "stale-plan", "confirmToken": "stale-confirmation"},
        )

    assert error.value.code == 409
    payload = json.loads(error.value.read())
    assert payload["error"]["code"] == "E-DESKTOP-OWNER-CONFLICT"
    error.value.close()

    with pytest.raises(urllib.error.HTTPError) as gameplay_error:
        request_json(
            base,
            token,
            "/steam/gameplay/apply",
            {"planId": "stale-plan", "confirmToken": "stale-confirmation"},
        )
    assert gameplay_error.value.code == 409
    gameplay_payload = json.loads(gameplay_error.value.read())
    assert gameplay_payload["error"]["code"] == "E-DESKTOP-OWNER-CONFLICT"
    gameplay_error.value.close()
    assert dashboard.calls == []


def test_bridge_keyboard_toggle_and_activate(
    bridge: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    base, token = bridge
    monkeypatch.setattr(
        "steamzero.adapters.desktop_ui.toggle_virtual_keyboard",
        lambda language=None: {"action": "show", "provider": "kwin-maliit", "language": language},
    )
    monkeypatch.setattr(
        "steamzero.adapters.desktop_ui.activate_virtual_keyboard",
        lambda language=None: "wvkbd",
    )
    toggled = request_json(base, token, "/keyboard", {"action": "toggle", "language": "br"})
    assert toggled["action"] == "show"
    assert toggled["language"] == "br"
    activated = request_json(base, token, "/keyboard", {})
    assert activated["provider"] == "wvkbd"


def test_bridge_launches_ashyterm(bridge: tuple[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    base, token = bridge
    monkeypatch.setattr(
        "steamzero.adapters.desktop_ui.launch_ashyterm",
        lambda: {"status": "started", "application": "ashyterm"},
    )
    result = request_json(base, token, "/ashyterm", {})
    assert result == {"status": "started", "application": "ashyterm"}


def test_bridge_panel_autohide_applies_profile_override(
    bridge: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    base, token = bridge
    applied: list[bool] = []

    class FakePanelEffect:
        def available(self, _context: object) -> bool:
            return True

        def apply(self, profile: object, _context: object) -> None:
            applied.append(bool(profile.panel_auto_hide))

    monkeypatch.setattr("steamzero.adapters.desktop_ui.KDEPanelEffect", FakePanelEffect)
    enabled = request_json(base, token, "/panel/autohide", {"enable": True})
    assert enabled == {"status": "ok", "autoHide": True}
    disabled = request_json(base, token, "/panel/autohide", {"enable": False})
    assert disabled == {"status": "ok", "autoHide": False}
    assert applied == [True, False]


def test_bridge_panel_autohide_conflicts_when_unavailable(
    bridge: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    base, token = bridge

    class UnavailablePanelEffect:
        def available(self, _context: object) -> bool:
            return False

    monkeypatch.setattr("steamzero.adapters.desktop_ui.KDEPanelEffect", UnavailablePanelEffect)
    with pytest.raises(urllib.error.HTTPError) as error:
        request_json(base, token, "/panel/autohide", {"enable": True})
    assert error.value.code == 409
    error.value.close()


def test_bridge_keyboard_settings_endpoint(
    bridge: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    base, token = bridge
    received: list[dict[str, object]] = []

    def fake_comfort(settings: dict[str, object]) -> dict[str, object]:
        received.append(settings)
        return {"applied": {"sound": "true"}, "previous": {"sound": "false"}}

    monkeypatch.setattr("steamzero.adapters.desktop_ui.apply_maliit_comfort", fake_comfort)
    result = request_json(
        base, token, "/keyboard/settings", {"sound": True, "ignored": "x", "theme": "SuruDark"}
    )
    assert result["applied"] == {"sound": "true"}
    assert received == [{"sound": True, "theme": "SuruDark"}]


def test_bridge_keyboard_settings_requires_known_keys(bridge: tuple[str, str]) -> None:
    base, token = bridge
    with pytest.raises(urllib.error.HTTPError) as error:
        request_json(base, token, "/keyboard/settings", {"ignored": "x"})
    assert error.value.code == 400
    error.value.close()


_READY_SESSION = {
    "state": "ready",
    "statusLabel": "Game Mode disponível",
    "steam": True,
    "gamescope": True,
    "gamescopeSession": True,
    "desktopFallback": True,
}


def test_bridge_session_select_requires_confirmation_then_switches(
    bridge: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    base, token = bridge
    requested: list[str] = []
    logouts: list[bool] = []

    monkeypatch.setattr(
        "steamzero.adapters.desktop_ui.session_readiness", lambda: dict(_READY_SESSION)
    )
    monkeypatch.setattr(
        "steamzero.adapters.desktop_ui.request_target",
        lambda target: (requested.append(target), {"status": "requested", "target": target})[1],
    )
    monkeypatch.setattr(
        "steamzero.adapters.desktop_ui.logout_desktop_session",
        lambda: (logouts.append(True), True)[1],
    )

    plan = request_json(base, token, "/session/select", {"target": "steam"})
    assert plan["target"] == "steam"
    assert plan["planId"] and plan["confirmToken"]
    assert requested == []  # nada muda sem confirmação

    result = request_json(
        base,
        token,
        "/session/select",
        {
            "target": "steam",
            "planId": str(plan["planId"]),
            "confirmToken": str(plan["confirmToken"]),
        },
    )
    assert result["status"] == "requested"
    assert result["logout"] is True
    assert requested == ["steam"]
    assert logouts == [True]


def test_bridge_session_select_degraded_readiness_conflicts(
    bridge: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    base, token = bridge
    monkeypatch.setattr(
        "steamzero.adapters.desktop_ui.session_readiness",
        lambda: {"state": "degraded", "statusLabel": "Dependências incompletas"},
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        request_json(base, token, "/session/select", {"target": "steam"})
    assert error.value.code == 409
    error.value.close()


def test_bridge_session_select_rejects_bad_target_and_token(
    bridge: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    base, token = bridge
    monkeypatch.setattr(
        "steamzero.adapters.desktop_ui.session_readiness", lambda: dict(_READY_SESSION)
    )
    with pytest.raises(urllib.error.HTTPError) as bad_target:
        request_json(base, token, "/session/select", {"target": "shutdown"})
    assert bad_target.value.code == 400
    bad_target.value.close()

    plan = request_json(base, token, "/session/select", {"target": "steam"})
    with pytest.raises(urllib.error.HTTPError) as bad_token:
        request_json(
            base,
            token,
            "/session/select",
            {"target": "steam", "planId": str(plan["planId"]), "confirmToken": "errado"},
        )
    assert bad_token.value.code == 400
    bad_token.value.close()
