# SPDX-License-Identifier: GPL-3.0-or-later
"""Reconciliador persiste somente mudanças materiais do ambiente."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from steamzero.core.state import StateStore
from steamzero.service.reconciler import SessionEnvironmentReconciler


def _snapshot() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "observedAt": "2026-07-17T00:00:00+00:00",
        "readOnly": True,
        "device": {"kind": "deck-lcd", "signals": {"internal_display_present": "true"}},
        "session": {"id": "2", "type": "wayland"},
        "power": {"onAC": False, "batteries": [{"capacityPercent": 80}]},
        "network": {"online": True},
        "displays": [
            {
                "name": "eDP-1",
                "connected": True,
                "enabled": "enabled",
                "preferredMode": "800x1280",
                "edidSha256": "a" * 64,
            }
        ],
        "volumes": [
            {
                "uuid": "CARD",
                "role": "microsd",
                "mountpoint": "/mnt/sdcard",
                "fstype": "ext4",
                "free": 10,
            }
        ],
    }


def test_reconciler_ignores_volatile_values_and_emits_topology_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    current = _snapshot()
    reconciler = SessionEnvironmentReconciler(probe=lambda: deepcopy(current), interval=0)

    first = reconciler.sample()
    assert first["status"] == "changed"
    assert first["changes"] == ["initial"]

    current["observedAt"] = "2026-07-17T00:01:00+00:00"
    current["power"]["batteries"][0]["capacityPercent"] = 79  # type: ignore[index]
    current["volumes"][0]["free"] = 9  # type: ignore[index]
    assert reconciler.sample()["status"] == "noop"

    current["power"]["onAC"] = True  # type: ignore[index]
    changed = reconciler.sample()
    assert changed["status"] == "changed"
    assert changed["changes"] == ["power"]

    with StateStore() as store:
        store.migrate()
        events = [row for row in store.events_since(0) if row["kind"] == "session.environment"]
        assert len(events) == 2
