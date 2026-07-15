# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Device Manager (F-SD-02): detecção de dispositivo por DMI.

Classifica em deck-lcd (Valve "Jupiter"), deck-oled (Valve "Galileo") ou desktop.
A leitura de DMI é uma **porta** injetável (``DevicePort``) — o domínio não lê
sysfs diretamente (isso é um adapter). Persiste a entidade ``device`` no State Store.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from steamzero.core import fs, ids
from steamzero.core.state import StateStore

# Marcadores DMI oficiais do Steam Deck (product_name).
_DECK_LCD = "jupiter"
_DECK_OLED = "galileo"


class DevicePort(Protocol):
    """Capacidade de ler identificação de hardware (DMI/sysfs)."""

    def read_dmi(self) -> dict[str, str]:
        """Retorna campos DMI: product_name, sys_vendor, board_name (minúsculas)."""
        ...


@dataclass(frozen=True)
class Device:
    id: str
    kind: str  # deck-lcd | deck-oled | desktop
    dmi_fingerprint: str
    quirks: dict[str, Any]


def classify(dmi: dict[str, str]) -> str:
    product = (dmi.get("product_name") or "").strip().lower()
    vendor = (dmi.get("sys_vendor") or "").strip().lower()
    if vendor == "valve" and product == _DECK_LCD:
        return "deck-lcd"
    if vendor == "valve" and product == _DECK_OLED:
        return "deck-oled"
    return "desktop"


class DeviceManager:
    def __init__(self, port: DevicePort, store: StateStore) -> None:
        self._port = port
        self._store = store

    def detect(self) -> Device:
        """Lê DMI, classifica e persiste a entidade device."""
        dmi = self._port.read_dmi()
        kind = classify(dmi)
        fingerprint = fs.hash_bytes(
            json.dumps(dmi, sort_keys=True, ensure_ascii=False).encode("utf-8")
        )
        quirks = _quirks_for(kind)
        device = Device(id=ids.new_ulid(), kind=kind, dmi_fingerprint=fingerprint, quirks=quirks)
        self._store.save_device(
            {
                "id": device.id,
                "kind": device.kind,
                "dmi_fingerprint": device.dmi_fingerprint,
                "quirks_json": json.dumps(device.quirks, ensure_ascii=False),
            }
        )
        self._store.append_event(
            "entity.changed", entity=f"device:{device.id}", payload={"kind": kind}
        )
        return device

    def is_steam_deck(self) -> bool:
        return classify(self._port.read_dmi()) in ("deck-lcd", "deck-oled")


def _quirks_for(kind: str) -> dict[str, Any]:
    # Faixas de TDP por modelo (usadas na validação do helper — PRIVILEGE-BOUNDARIES).
    if kind == "deck-lcd":
        return {"tdpRange": [3, 15], "hasOled": False}
    if kind == "deck-oled":
        return {"tdpRange": [3, 15], "hasOled": True}
    return {"tdpRange": [], "hasOled": False}
