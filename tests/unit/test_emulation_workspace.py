# SPDX-License-Identifier: GPL-3.0-or-later

import json
from pathlib import Path

from steamzero.api import contracts
from steamzero.domain.emulation_workspace import build_global_management, build_switch_workspace
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
    assert len(payload["canonicalExperiences"]) == 155
    assert (
        next(item for item in payload["canonicalExperiences"] if item["id"] == "game-boy-color")[
            "technicalPlatformId"
        ]
        == "nintendo-handheld"
    )
    assert len(payload["platforms"]) == 36
    assert payload["platforms"][1]["areas"][0]["id"] == "overview"
    cloud_platforms = [p for p in payload["platforms"] if p.get("cloud")]
    assert any(p["cloud"]["allowedHosts"] == ["luna.amazon.com"] for p in cloud_platforms)
    retroarch_artwork = [
        item
        for item in payload["platforms"]
        if item["fallbackArtworkAsset"].endswith("/retroarch.svg")
    ]
    assert len(retroarch_artwork) == 16
    assert len({item["fallbackArtworkAsset"] for item in payload["platforms"]}) == 21


def test_global_management_keeps_technical_and_editorial_counts_distinct() -> None:
    payload = build_switch_workspace()
    global_management = build_global_management(
        platforms=payload["platforms"],
        editorial_platforms=[
            {"id": "switch", "games": [{"id": "game-one"}]},
            {"id": "nintendo-handheld", "games": []},
        ],
        canonical_experiences=payload["canonicalExperiences"],
        truth_state=payload["truthState"],
        emulators=payload["platforms"][0]["emulators"],
        directories=[],
        media_providers=[],
    )

    assert global_management["technicalPlatformCount"] == 36
    assert global_management["editorialDestinationCount"] == 37
    assert global_management["editorialExperienceCount"] == 155
    assert global_management["editorialSource"]["id"] == "steam"
    assert global_management["platformCards"][0]["gameCount"] == 1
    assert global_management["platformCards"][0]["action"]["id"] == "platform.open"
    payload["globalManagement"] = global_management
    contracts.validate(payload, "emulation-workspace-v1.schema.json")


def test_workspace_accepts_visible_game_with_unverified_identity() -> None:
    payload = build_switch_workspace(
        games=[
            {
                "id": "hash-prefix",
                "titleId": None,
                "name": "Jogo sem Title ID no nome",
                "state": "unverified",
                "statusLabel": "NSP · Title ID não identificado",
                "emulatorId": None,
            }
        ]
    )

    contracts.validate(payload, "emulation-workspace-v1.schema.json")
    game = payload["platforms"][0]["games"][0]
    assert game["titleId"] is None
    assert game["state"] == "unverified"


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
