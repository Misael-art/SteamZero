# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from steamzero.core import transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain.cloud_platforms import CloudPlatformService


class FakeShortcuts:
    def __init__(self, published: set[str] | None = None) -> None:
        self.published = published or set()
        self.planned: list[dict[str, Any]] | None = None

    def managed_cloud_platform_ids(self) -> set[str]:
        return set(self.published)

    def plan_cloud(self, platforms: Sequence[Mapping[str, Any]]) -> transaction.Plan:
        self.planned = [dict(item) for item in platforms]
        return transaction.Plan(
            plan_id="01J000000000000000000000AA",
            kind="steam.cloud-shortcuts.sync",
            created_at="2026-07-23T00:00:00Z",
            expires_at="2026-07-23T01:00:00Z",
            confirm_token="token",
            root="/var/lib/steamzero-tests",
            status="pending",
            actions=[],
            preconditions=[],
            preview="test",
            requirements={},
            rollback_guarantee="test",
        )


def test_cloud_platforms_publish_truthful_operational_state() -> None:
    shortcuts = FakeShortcuts({"xbox-cloud-gaming"})
    service = CloudPlatformService(
        shortcuts,
        which=lambda command: "/usr/bin/xdg-open" if command == "xdg-open" else None,
        spawn=lambda _argv: None,
    )

    rows = service.platforms()
    assert [row["id"] for row in rows] == [
        "geforce-now",
        "xbox-cloud-gaming",
        "amazon-luna",
    ]
    xbox = rows[1]
    assert xbox["state"] == "attention"
    assert xbox["cloud"]["shortcutPublished"] is True
    assert xbox["cloud"]["serviceAvailability"] == "unverified"
    assert xbox["areaData"]["advanced"]["primaryAction"] == {
        "id": "cloud.launch:xbox-cloud-gaming",
        "label": "Abrir Xbox Cloud",
        "enabled": True,
        "reason": None,
        "requiresConfirmation": False,
    }
    detail = xbox["readiness"]["detail"].casefold()
    assert "não foram verificados" in detail
    assert "conta" in detail and "rede" in detail


def test_cloud_launch_uses_only_manifest_url_and_rejects_non_cloud() -> None:
    commands: list[tuple[str, ...]] = []
    service = CloudPlatformService(
        FakeShortcuts(),
        which=lambda _command: "/usr/bin/xdg-open",
        spawn=lambda argv: commands.append(tuple(argv)) or 321,
    )

    result = service.launch("geforce-now")
    assert commands == [("/usr/bin/xdg-open", "https://play.geforcenow.com/")]
    assert result == {
        "status": "started",
        "platformId": "geforce-now",
        "url": "https://play.geforcenow.com/",
        "pid": 321,
        "availability": "unverified",
    }
    with pytest.raises(SteamZeroError, match="não é uma plataforma cloud"):
        service.launch("switch")
    with pytest.raises(SteamZeroError, match="desconhecida"):
        service.launch("attacker.example")


def test_cloud_launch_degrades_without_opener_and_plan_contains_registry_only() -> None:
    shortcuts = FakeShortcuts()
    service = CloudPlatformService(
        shortcuts,
        which=lambda _command: None,
        spawn=lambda _argv: None,
    )

    assert all(row["state"] == "unavailable" for row in service.platforms())
    with pytest.raises(SteamZeroError, match="xdg-open"):
        service.launch("amazon-luna")
    plan = service.plan_shortcuts()
    assert plan.kind == "steam.cloud-shortcuts.sync"
    assert shortcuts.planned == [
        {"id": "geforce-now", "name": "NVIDIA GeForce NOW"},
        {"id": "xbox-cloud-gaming", "name": "Xbox Cloud Gaming"},
        {"id": "amazon-luna", "name": "Amazon Luna"},
    ]
