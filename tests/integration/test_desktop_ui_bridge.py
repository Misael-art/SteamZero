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

    def open_steam(self, target: str) -> dict[str, object]:
        self.calls.append(("steam", target))
        return {"status": "started", "target": target}

    def open_steam_input(self, game_id: str) -> dict[str, object]:
        self.calls.append(("steam-input", game_id))
        return {"status": "started", "gameId": game_id}

    def plan_steam_gameplay(
        self, payload: dict[str, object], _status: dict[str, object]
    ) -> dict[str, object]:
        self.calls.append(("gameplay-plan", str(payload["gameId"])))
        return {"planId": "gameplay-plan", "confirmToken": "gameplay-confirm"}

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
    request_json(base, token, "/steam/open", {"target": "library"})
    request_json(base, token, "/steam/input/open", {"gameId": "10"})
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
    assert dashboard.calls == [
        ("plan", "dolphin"),
        ("apply", "component-plan", "confirm"),
        ("launch", "dolphin"),
        ("steam", "library"),
        ("steam-input", "10"),
        ("gameplay-plan", "10"),
        ("gameplay-apply", "gameplay-plan", "gameplay-confirm"),
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
