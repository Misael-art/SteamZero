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
from typing import Any

from steamzero.core import fs, ids
from steamzero.core.state import StateStore
from steamzero.ports import DevicePort

# Marcadores DMI oficiais do Steam Deck (product_name).
_DECK_LCD = "jupiter"
_DECK_OLED = "galileo"


@dataclass(frozen=True)
class Device:
    id: str
    kind: str  # deck-lcd | deck-oled | desktop
    dmi_fingerprint: str
    quirks: dict[str, Any]


def classify(dmi: dict[str, str], signals: dict[str, str] | None = None) -> str:
    product = (dmi.get("product_name") or "").strip().lower()
    vendor = (dmi.get("sys_vendor") or "").strip().lower()
    board = (dmi.get("board_name") or "").strip().lower()
    observed = signals or {}
    panel = observed.get("internal_display_present") == "true"
    # O modelo continua derivado dos identificadores oficiais, mas um adapter
    # real precisa fornecer ao menos um segundo sinal (board ou painel). Portas
    # legadas sem sinais permanecem classificáveis para migração/testes.
    corroborated = not signals or board == product or panel
    if vendor == "valve" and product == _DECK_LCD and corroborated:
        return "deck-lcd"
    if vendor == "valve" and product == _DECK_OLED and corroborated:
        return "deck-oled"
    return "desktop"


class DeviceManager:
    def __init__(self, port: DevicePort, store: StateStore) -> None:
        self._port = port
        self._store = store

    def detect(self) -> Device:
        """Lê DMI, classifica e persiste a entidade device."""
        dmi = self._port.read_dmi()
        signal_reader = getattr(self._port, "read_platform_signals", None)
        signals = signal_reader() if callable(signal_reader) else {}
        kind = classify(dmi, signals)
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
        signal_reader = getattr(self._port, "read_platform_signals", None)
        signals = signal_reader() if callable(signal_reader) else {}
        return classify(self._port.read_dmi(), signals) in ("deck-lcd", "deck-oled")


def _quirks_for(kind: str) -> dict[str, Any]:
    # Faixas de TDP por modelo (usadas na validação do helper — PRIVILEGE-BOUNDARIES).
    if kind == "deck-lcd":
        return {"tdpRange": [3, 15], "hasOled": False}
    if kind == "deck-oled":
        return {"tdpRange": [3, 15], "hasOled": True}
    return {"tdpRange": [], "hasOled": False}
