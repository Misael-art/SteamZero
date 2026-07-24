# SPDX-License-Identifier: GPL-3.0-or-later
"""Matriz verificável backend → tela → controle da central handheld."""

from __future__ import annotations

import re
from pathlib import Path

from steamzero.adapters.desktop_contracts import handheld_ui_contracts


def test_every_bridge_route_is_declared_by_backend_contract() -> None:
    source = Path("src/steamzero/adapters/desktop_ui.py").read_text(encoding="utf-8")
    exact = set(re.findall(r'path == "([^"]+)"', source))
    dynamic = set(re.findall(r'path\.startswith\("([^"]+)"\)', source))
    declared = {
        str(action["endpoint"])
        for action in handheld_ui_contracts()["actions"]
        if action["endpoint"] is not None
    }
    dynamic_contracts = {
        str(action["jobSemantics"]["pollEndpoint"])
        for action in handheld_ui_contracts()["actions"]
        if action["jobSemantics"]["pollEndpoint"] is not None
    }
    # /contracts publica o próprio catálogo; não é uma ação operacional.
    assert exact - {"/contracts"} <= declared
    assert all(
        any(endpoint.startswith(prefix) for endpoint in dynamic_contracts) for prefix in dynamic
    )


def test_contract_matrix_has_handheld_control_semantics() -> None:
    matrix = handheld_ui_contracts()
    required_states = {"ready", "empty", "degraded", "pending", "failed", "offline"}
    assert set(matrix["states"]) == required_states
    assert len(matrix["actions"]) == len(matrix["byId"])
    required_fields = {
        "id",
        "label",
        "enabled",
        "reason",
        "service",
        "endpoint",
        "method",
        "screen",
        "control",
        "states",
        "applicability",
        "confirmation",
        "inputSchema",
        "jobSemantics",
        "rollback",
    }
    for action in matrix["actions"]:
        assert set(action) == required_fields
        assert set(action["states"]) <= required_states
        assert action["label"]
        assert action["screen"]
        assert action["control"]
        if action["applicability"] == "not-applicable":
            assert action["enabled"] is False
            assert action["endpoint"] is None
            assert action["reason"]


def test_matrix_covers_required_services_and_explicit_non_applicable_items() -> None:
    matrix = handheld_ui_contracts()
    services = {str(action["service"]) for action in matrix["actions"]}
    assert {
        "bridge",
        "controller",
        "jobs",
        "components",
        "steam",
        "sync",
        "session",
        "maintenance",
        "media",
        "library",
        "emulation",
        "system",
    } <= services
    for action_id in (
        "component.rollback",
        "component.recover",
        "profiles.history",
        "session.recovery",
    ):
        action = matrix["byId"][action_id]
        assert action["applicability"] == "not-applicable"
        assert action["reason"]
    for action_id in (
        "operations.history",
        "state.export",
        "admin.health",
        "support.bundle",
    ):
        action = matrix["byId"][action_id]
        assert action["applicability"] == "applicable"
        assert action["enabled"] is True
        assert action["endpoint"]


def test_async_scan_contract_publishes_polling_and_terminal_states() -> None:
    scan = handheld_ui_contracts()["byId"]["library.scan"]
    assert scan["jobSemantics"] == {
        "kind": "asynchronous",
        "states": ["queued", "running", "succeeded", "failed", "cancelled"],
        "pollEndpoint": "/emulation/job/status/{jobId}",
    }


def test_cloud_launch_contract_is_closed_and_routes_to_allowlisted_bridge() -> None:
    action = handheld_ui_contracts()["byId"]["cloud.launch"]
    assert action["endpoint"] == "/cloud/launch"
    assert action["inputSchema"] == {
        "type": "object",
        "required": ["platformId"],
        "properties": {"platformId": {"type": "string"}},
        "additionalProperties": False,
    }
    assert action["rollback"]["supported"] is False


def test_qml_resolves_operational_routes_from_backend_catalog() -> None:
    qml = Path("src/steamzero/ui/qml/Main.qml").read_text(encoding="utf-8")
    direct_routes = re.findall(r'request\("(?:GET|POST)",\s*"([^"]+)"', qml)
    assert direct_routes == ["/status"]
    assert "o único bootstrap" in qml

    known = set(handheld_ui_contracts()["byId"])
    static_action_ids = set(re.findall(r'requestAction\("([^"]+)"', qml))
    assert static_action_ids <= known
    assert {
        "component.plan",
        "emulator.plan",
        "library.scan",
        "steam.gameplay.plan",
        "credential.save",
        "desktop.recover",
        "operations.detail",
        "operations.rollback.plan",
        "operations.rollback.apply",
        "collections.plan",
        "collections.apply",
        "library.health.plan",
        "library.health.apply",
    } <= static_action_ids


def test_qml_fallback_rows_do_not_publish_decorative_actions() -> None:
    qml = Path("src/steamzero/ui/qml/Main.qml").read_text(encoding="utf-8")
    fallback_region = qml[qml.index("property var fallbackComponents") :]
    fallback_region = fallback_region[: fallback_region.index("property var fallbackSteamGameplay")]
    assert '"label": "Ver detalhes", "enabled": true' not in fallback_region
    assert fallback_region.count('"enabled": false') >= 4
