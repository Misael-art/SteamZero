# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from steamzero.api import contracts
from steamzero.domain.hud import MANGO_CONFIG, hud_catalog


def test_hud_catalog_proves_only_deterministic_1280x800_budget() -> None:
    catalog = hud_catalog(mangohud_available=True)

    contracts.validate(catalog, "gtool-hud-v1.schema.json")
    assert catalog["viewport"] == {"width": 1280, "height": 800}
    assert catalog["runtime"]["state"] == "ready"
    assert catalog["evidence"]["state"] == "verified-offscreen"
    assert catalog["evidence"]["humanReview"]["state"] == "PENDING-HUMAN"
    assert "Renderização real" in catalog["evidence"]["doesNotProve"][0]
    for preset in catalog["presets"]:
        layout = preset["layout"]
        assert layout["maxWidth"] + 2 * layout["margin"] <= 1280
        assert layout["maxHeight"] + 2 * layout["margin"] <= 800
        assert preset["config"] == MANGO_CONFIG[preset["mode"]]


def test_hud_runtime_truth_has_ready_unavailable_and_unverified_states() -> None:
    assert hud_catalog(mangohud_available=True)["runtime"]["state"] == "ready"
    assert hud_catalog(mangohud_available=False)["runtime"]["state"] == "unavailable"
    assert hud_catalog()["runtime"]["state"] == "unverified"
