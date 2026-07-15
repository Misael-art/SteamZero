# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do Device Manager (F-SD-02): classificação por DMI."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from steamzero.core import state
from steamzero.domain.device import DeviceManager, classify


class FakeDevicePort:
    def __init__(self, dmi: dict[str, str]) -> None:
        self._dmi = dmi

    def read_dmi(self) -> dict[str, str]:
        return self._dmi


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[state.StateStore]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    s = state.open_state()
    yield s
    s.close()


@pytest.mark.parametrize(
    ("dmi", "expected"),
    [
        ({"sys_vendor": "Valve", "product_name": "Jupiter"}, "deck-lcd"),
        ({"sys_vendor": "Valve", "product_name": "Galileo"}, "deck-oled"),
        ({"sys_vendor": "Dell", "product_name": "XPS"}, "desktop"),
        ({}, "desktop"),
        ({"sys_vendor": "valve", "product_name": "jupiter"}, "deck-lcd"),
    ],
)
def test_classify(dmi: dict[str, str], expected: str) -> None:
    assert classify(dmi) == expected


def test_detect_persists_device(store: state.StateStore) -> None:
    mgr = DeviceManager(FakeDevicePort({"sys_vendor": "Valve", "product_name": "Galileo"}), store)
    device = mgr.detect()
    assert device.kind == "deck-oled"
    assert device.quirks["hasOled"] is True
    persisted = store.get_device(device.id)
    assert persisted is not None
    assert persisted["kind"] == "deck-oled"


def test_is_steam_deck(store: state.StateStore) -> None:
    deck = DeviceManager(FakeDevicePort({"sys_vendor": "Valve", "product_name": "Jupiter"}), store)
    desktop = DeviceManager(FakeDevicePort({"sys_vendor": "Asus", "product_name": "PC"}), store)
    assert deck.is_steam_deck() is True
    assert desktop.is_steam_deck() is False
