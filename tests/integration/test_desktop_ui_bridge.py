# SPDX-License-Identifier: GPL-3.0-or-later
"""Bridge QML: loopback, token, allowlist e confirmação do plano."""

from __future__ import annotations

import json
import queue
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from steamzero.adapters.desktop_ui import DesktopControlServer
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


class FakeDashboard:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def snapshot(self, _status: dict[str, object]) -> dict[str, object]:
        return {"components": [{"id": "dolphin"}], "steam": [{"id": "steam-client"}]}

    def plan_component(self, component_id: str) -> dict[str, object]:
        self.calls.append(("plan", component_id))
        return {"planId": "component-plan", "confirmToken": "confirm"}

    def apply_component(self, plan_id: str, confirm_token: str) -> dict[str, object]:
        self.calls.append(("apply", plan_id, confirm_token))
        return {"status": "ok"}

    def launch_component(self, component_id: str) -> dict[str, object]:
        self.calls.append(("launch", component_id))
        return {"status": "started"}

    def open_steam(self, target: str) -> dict[str, object]:
        self.calls.append(("steam", target))
        return {"status": "started", "target": target}


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


def request_json(
    base: str, token: str, path: str, payload: dict[str, str] | None = None
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
    request_json(base, token, "/steam/open", {"target": "library"})
    assert dashboard.calls == [
        ("plan", "dolphin"),
        ("apply", "component-plan", "confirm"),
        ("launch", "dolphin"),
        ("steam", "library"),
    ]


def test_bridge_rechecks_owner_conflict_before_component_apply(
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
    assert dashboard.calls == []
