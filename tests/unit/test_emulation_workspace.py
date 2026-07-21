# SPDX-License-Identifier: GPL-3.0-or-later

import json
from pathlib import Path

from steamzero.api import contracts
from steamzero.domain.emulation_workspace import build_switch_workspace
from steamzero.domain.keys_firmware import RequirementCheck


def test_switch_workspace_matches_versioned_contract() -> None:
    payload = build_switch_workspace(
        probe=lambda emulator_id: emulator_id == "eden",
        keys=RequirementCheck("ok", "keys", "rev17", "rev18", "Keys compatíveis."),
        firmware=RequirementCheck("ok", "firmware", "17.0.0", "18.0.1", "Firmware compatível."),
        games=[
            {
                "id": "game-demo",
                "titleId": "0100000000001000",
                "name": "Jogo de teste",
                "state": "ready",
                "statusLabel": "Compatível",
                "emulatorId": "eden",
                "requiresKeys": {"minimumRevision": 17},
                "requiresFirmware": {"minimumVersion": "17.0.0"},
            }
        ],
        emulator_capabilities={
            "eden": [
                {
                    "id": "configure",
                    "label": "Configuração por jogo",
                    "state": "ready",
                    "detail": "Perfis declarativos disponíveis.",
                }
            ]
        },
    )

    contracts.validate(payload, "emulation-workspace-v1.schema.json")
    assert payload["schemaVersion"] == 1
    assert payload["truthState"] == "ready"
    platform = payload["platforms"][0]
    assert platform["iconKey"] == "switch"
    assert [scope["id"] for scope in platform["scopes"]] == [
        "global",
        "emulator",
        "game",
        "handheld",
        "dock",
    ]
    assert set(platform["areaData"]) == {area["id"] for area in platform["areas"]}
    assert platform["emulators"][0]["name"] == "Eden"
    assert platform["emulators"][0]["state"] == "ready"


def test_versioned_golden_fixture_is_valid_and_complete() -> None:
    fixture = Path("tests/fixtures/switch/emulation-workspace-v1.json")
    payload = json.loads(fixture.read_text(encoding="utf-8"))

    contracts.validate(payload, "emulation-workspace-v1.schema.json")
    platform = payload["platforms"][0]
    assert set(platform["areaData"]) == {area["id"] for area in platform["areas"]}


def test_probe_failure_degrades_to_data_instead_of_crashing() -> None:
    def broken_probe(_emulator_id: str) -> bool:
        raise OSError("runtime indisponível")

    payload = build_switch_workspace(probe=broken_probe)

    assert payload["truthState"] == "unverified"
    assert all(row["state"] == "unverified" for row in payload["platforms"][0]["emulators"])
    assert payload["platforms"][0]["readiness"]["blockers"]


def test_invalid_selection_falls_back_to_safe_defaults() -> None:
    payload = build_switch_workspace(selected_scope="future", selected_area="future")

    platform = payload["platforms"][0]
    assert platform["selectedScope"] == "global"
    assert platform["selectedArea"] == "overview"


def test_requirement_kind_is_normalized_and_unwired_actions_are_disabled() -> None:
    payload = build_switch_workspace(
        keys={
            "kind": "firmware",
            "status": "ok",
            "required": "rev17",
            "installed": "rev18",
            "detail": "Compatível.",
            "blocksPlay": False,
        }
    )

    platform = payload["platforms"][0]
    assert platform["requirements"]["keys"]["kind"] == "keys"
    actions = [
        card["action"] for card in platform["areaData"]["keysFirmware"]["cards"] if "action" in card
    ]
    assert actions and all(not action["enabled"] and action["reason"] for action in actions)
