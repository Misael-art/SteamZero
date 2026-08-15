# SPDX-License-Identifier: GPL-3.0-or-later

import json
from pathlib import Path

from steamzero.api import contracts
from steamzero.domain.emulation_workspace import build_global_management, build_switch_workspace
from steamzero.domain.keys_firmware import RequirementCheck
from steamzero.domain.platforms import PlatformRegistry


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
    # Sem facts de lifecycle nenhuma linha declara `installable`, então o card
    # não promete instalação que o backend recusaria: só abre a plataforma. O
    # alvo vai no próprio id para a ação ser despachável.
    assert global_management["platformCards"][0]["action"]["id"] == "platform.open:switch"
    assert global_management["platformCards"][0]["secondaryAction"] is None
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


def _card_for(emulator_rows: list[dict[str, object]]) -> dict[str, object]:
    """Monta um card de gestão geral para uma plataforma com as linhas dadas."""
    platform = {
        "id": "gamecube",
        "name": "Nintendo GameCube",
        "kind": "emulated",
        "state": "attention",
        "readiness": {"percent": 0, "blockers": ["o emulador desta plataforma não está instalado"]},
        "requirements": {},
        "emulators": emulator_rows,
    }
    management = build_global_management(
        platforms=[platform],
        editorial_platforms=[],
        canonical_experiences=[],
        truth_state="attention",
        emulators=[],
        directories=[],
        media_providers=[],
    )
    return management["platformCards"][0]


def test_platform_card_offers_installing_the_missing_emulator() -> None:
    """Abrir a plataforma não instala nada.

    A auditoria de 2026-08-11 (P0-5) mostrou o card anunciando "o emulador desta
    plataforma não está instalado" e oferecendo só "Abrir plataforma" — o único
    caminho de instalação ficava abaixo da dobra, em outro painel.
    """
    card = _card_for(
        [{"id": "dolphin", "name": "Dolphin", "installable": True, "installState": "not-installed"}]
    )

    assert card["action"]["id"] == "emulator.install:dolphin"
    assert card["action"]["label"] == "Instalar Dolphin"
    assert card["action"]["requiresConfirmation"] is True
    assert card["secondaryAction"]["id"] == "platform.open:gamecube"


def test_platform_card_does_not_offer_installing_what_is_already_installed() -> None:
    card = _card_for(
        [{"id": "dolphin", "name": "Dolphin", "installable": True, "installState": "installed"}]
    )

    assert card["action"]["id"] == "platform.open:gamecube"
    assert card["secondaryAction"] is None


def test_platform_card_does_not_promise_an_install_the_backend_refuses() -> None:
    """`installable=false` é resposta do lifecycle, não convite para inventar CTA."""
    card = _card_for(
        [
            {
                "id": "retroarch",
                "name": "RetroArch",
                "installable": False,
                "installState": "unverified",
                "reason": "componente sem executor declarado",
            }
        ]
    )

    assert card["action"]["id"] == "platform.open:gamecube"
    assert card["secondaryAction"] is None


def test_platform_card_repairs_a_degraded_emulator_instead_of_reinstalling() -> None:
    """Degradado não é ausente: reinstalar não corrige drift (G27).

    A gestão já anuncia "Reparar" para a linha degradada; o card da plataforma
    precisa do mesmo verbo, e não "Instalar" — arquivos existem e a causa do
    drift veio preservada.
    """
    card = _card_for(
        [{"id": "dolphin", "name": "Dolphin", "installable": True, "installState": "degraded"}]
    )

    assert card["action"]["id"] == "emulator.repair:dolphin"
    assert card["action"]["label"] == "Reparar Dolphin"
    assert card["action"]["requiresConfirmation"] is True
    assert card["secondaryAction"]["id"] == "platform.open:gamecube"


def test_cloud_platform_card_offers_only_open_and_never_an_install() -> None:
    """Plataforma de streaming não usa emulador local: nenhum CTA de instalação."""
    platform = {
        "id": "amazon-luna",
        "name": "Amazon Luna",
        "kind": "cloud",
        "state": "ready",
        "readiness": {"percent": 100, "blockers": []},
        "requirements": {},
        "emulators": [],
    }
    management = build_global_management(
        platforms=[platform],
        editorial_platforms=[],
        canonical_experiences=[],
        truth_state="ready",
        emulators=[],
        directories=[],
        media_providers=[],
    )
    card = management["platformCards"][0]

    assert card["identity"] == "cloud"
    assert card["action"]["id"] == "platform.open:amazon-luna"
    assert card["action"]["label"] == "Abrir plataforma"
    assert card["secondaryAction"] is None


def test_platform_card_actions_stay_within_the_platform_registry() -> None:
    """Compatibilidade emulador↔plataforma: o card só oferece o que a plataforma declara.

    A fonte das linhas é o registro de plataformas; um emulador de outra
    plataforma nunca pode virar CTA do card, e o alvo de abrir é sempre a
    própria plataforma do card.
    """
    registry = PlatformRegistry.bundled()
    platforms = []
    for manifest in list(registry.list())[:8]:
        platforms.append(
            {
                "id": manifest.id,
                "name": manifest.name,
                "kind": manifest.kind,
                "state": "attention",
                "readiness": {"percent": 0, "blockers": []},
                "requirements": {},
                "emulators": [
                    {
                        "id": emulator_id,
                        "name": emulator_id,
                        "installable": True,
                        "installState": "not-installed",
                    }
                    for emulator_id in registry.emulator_ids_for(manifest.id)
                ],
            }
        )
    management = build_global_management(
        platforms=platforms,
        editorial_platforms=[],
        canonical_experiences=[],
        truth_state="attention",
        emulators=[],
        directories=[],
        media_providers=[],
    )
    declared = {
        str(manifest.id): set(registry.emulator_ids_for(manifest.id))
        for manifest in registry.list()
    }

    for card in management["platformCards"]:
        action = card["action"]
        if action["id"].startswith(("emulator.install:", "emulator.repair:")):
            emulator_id = action["id"].split(":", 1)[1]
            assert emulator_id in declared[card["id"]], (
                f"card de {card['id']} oferece emulador fora do registro: {emulator_id}"
            )
        if card["secondaryAction"]:
            assert card["secondaryAction"]["id"] == f"platform.open:{card['id']}"
