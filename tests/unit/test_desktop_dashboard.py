# SPDX-License-Identifier: GPL-3.0-or-later
"""Dashboard Desktop agrega providers opcionais sem esconder degradação."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from steamzero.adapters.desktop_dashboard import DesktopDashboard, SteamDesktopController
from steamzero.adapters.flatpak import FlatpakState
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore


class FakeFlatpak:
    def __init__(self, states: dict[str, FlatpakState] | None = None) -> None:
        self.states = states or {}

    def status(self, ref: str) -> FlatpakState:
        return self.states.get(ref, FlatpakState(False, ref))

    def resolve(self, remote: str, ref: str, commit: str) -> str:
        return commit

    def install(self, remote: str, ref: str) -> None:
        self.states[ref] = FlatpakState(True, ref, remote, "0" * 64)

    def deploy(self, ref: str, commit: str) -> None:
        origin = self.states.get(ref, FlatpakState(True, ref, "flathub")).origin or "flathub"
        self.states[ref] = FlatpakState(True, ref, origin, commit)

    def uninstall(self, ref: str) -> None:
        self.states[ref] = FlatpakState(False, ref)

    def smoke(self, ref: str, arguments: Sequence[str]) -> None:
        return


def _status(*, conflict: bool = False) -> dict[str, object]:
    return {
        "context": {
            "capabilities": ["steam-keyboard"],
            "conflicts": ["watcher.service"] if conflict else [],
        }
    }


def test_steam_rows_are_optional_and_conflict_aware() -> None:
    controller = SteamDesktopController(
        which=lambda command: "/usr/bin/steam" if command == "steam" else None,
        running_probe=lambda: False,
        spawn=lambda _argv: None,
    )

    rows = controller.rows(_status(conflict=True))

    assert rows[0]["statusLabel"] == "Instalado"
    assert rows[2]["state"] == "blocked"
    assert rows[3]["action"]["kind"] == "keyboard"


def test_steam_open_uses_only_allowlisted_uri() -> None:
    calls: list[tuple[str, ...]] = []
    controller = SteamDesktopController(
        which=lambda _command: "/usr/bin/steam",
        running_probe=lambda: False,
        spawn=lambda argv: calls.append(tuple(argv)),
    )

    assert controller.open("library")["uri"] == "steam://open/games"
    assert calls == [("/usr/bin/steam", "steam://open/games")]
    with pytest.raises(SteamZeroError, match="não permitido"):
        controller.open("arbitrary-uri")


def test_dashboard_snapshot_keeps_eol_component_honest(tmp_path: Path) -> None:
    flatpak = FakeFlatpak()
    steam = SteamDesktopController(
        which=lambda _command: None,
        running_probe=lambda: False,
        spawn=lambda _argv: None,
    )
    dashboard = DesktopDashboard(
        store_factory=lambda: StateStore(tmp_path / "state.db"),
        flatpak_factory=lambda: flatpak,  # type: ignore[arg-type]
        doctor_runner=lambda: ({"version": "test"}, []),
        steam=steam,
        which=lambda command: "/usr/bin/flatpak" if command == "flatpak" else None,
        spawn=lambda _argv: None,
    )

    snapshot = dashboard.snapshot(_status())

    components = snapshot["components"]
    assert isinstance(components, list)
    assert [row["id"] for row in components] == ["dolphin", "duckstation", "retroarch"]
    duckstation = components[1]
    assert duckstation["state"] == "unsupported"
    assert duckstation["action"]["enabled"] is False
    assert snapshot["doctor"]["state"] == "healthy"
