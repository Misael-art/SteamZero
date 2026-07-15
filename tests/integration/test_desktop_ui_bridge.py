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
from steamzero.domain.desktop import DesktopContext, DisplayState, ExperienceCoordinator


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
