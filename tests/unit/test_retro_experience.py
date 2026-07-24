# SPDX-License-Identifier: GPL-3.0-or-later

from steamzero.api import contracts
from steamzero.domain.retro_experience import preset_catalog


def test_preset_catalog_is_versioned_and_names_are_canonical() -> None:
    catalog = preset_catalog()
    contracts.validate(catalog, "retro-experience-v1.schema.json")
    assert [preset["label"] for preset in catalog["presets"]] == [
        "Como era",
        "Equilibrado",
        "Melhorado",
    ]
    assert [preset["recommended"] for preset in catalog["presets"]] == [
        False,
        True,
        False,
    ]


def test_every_internal_setting_is_visible_in_expandable_differences() -> None:
    for preset in preset_catalog()["presets"]:
        assert set(preset["settings"]) == {
            difference["key"] for difference in preset["differences"]
        }
        assert len(preset["differences"]) == len(preset["settings"]) == 11


def test_readiness_does_not_claim_unimplemented_r2_or_r3_effects() -> None:
    preset = preset_catalog()["presets"][1]
    readiness = {difference["key"]: difference["readiness"] for difference in preset["differences"]}
    assert readiness["scalingMode"] == "ready"
    assert readiness["fallbackFilter"] == "ready"
    assert readiness["crop"] == "ready"
    assert readiness["stretch"] == "ready"
    assert readiness["pixelAspect"] == "planned"
    assert readiness["timingPolicy"] == "planned"
