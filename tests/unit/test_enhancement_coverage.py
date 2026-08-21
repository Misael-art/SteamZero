# SPDX-License-Identifier: GPL-3.0-or-later
"""Onda 5 do SZ-EMULATION-ENHANCEMENTS: tabela de cobertura manifesto→
melhorias e spike do primeiro consumidor emulator-supplied (SUPER ZSNES,
perfil de launch sem escrita de arquivos).

O manifesto real do SUPER ZSNES fica pendente de asset verificável
(release com sha256 de zsnes.com / AppImage não-oficial); nada aqui
fabrica hash, URL ou argv que não existam."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.domain.game_enhancements import (
    EnhancementCoverage,
    EnhancementKind,
    ProviderRole,
    enhancement_coverage,
    resolve_provider_role,
)
from steamzero.domain.launch_profile import build_argv, parse_launch

_SUPERM_MANIFEST = {
    "schemaVersion": 1,
    "id": "superm",
    "kind": "emulator",
    "presentation": {"displayName": "SUPER ZSNES", "iconAsset": "../assets/superm.svg"},
    "platforms": ["snes"],
    "capabilities": ["detect", "status", "install", "configure"],
    "sources": [
        {
            "type": "appimage",
            "version": "0.100b",
            "priority": 1,
            "url": "https://example.invalid/superm/SuperZSNES-x86_64.AppImage",
            "sha256": "0" * 64,
        }
    ],
    "enhancements": {"supplied": ["cheat"], "formats": []},
    "configFormat": "none",
    "compat": ["linux"],
    "license": "proprietary",
    "upstream": "https://zsnes.com/",
}


def test_coverage_table_is_manifest_truth_never_inference() -> None:
    manifests = [
        {"id": "azahar", "platforms": ["switch"]},
        _SUPERM_MANIFEST,
        {
            "id": "duckstation",
            "platforms": ["psx"],
            "enhancements": {"supplied": [], "formats": ["pcsx2-pnach"]},
        },
    ]
    rows = enhancement_coverage(manifests)
    assert [row.emulator_id for row in rows] == ["azahar", "duckstation", "superm"]
    silent = rows[0]
    assert silent.supplied_kinds == frozenset()
    assert silent.formats == ()
    assert rows[2].supplied_kinds == frozenset({EnhancementKind.CHEAT})
    assert rows[2].formats == ()
    assert rows[1].formats == ("pcsx2-pnach",)


def test_coverage_ignores_non_dict_entries_and_unknown_kind_values() -> None:
    rows = enhancement_coverage(
        [
            None,
            {"id": "superm"},
            {
                "id": "fallback",
                "enhancements": {"supplied": ["cheat", "talkshow"], "formats": ["yaml"]},
            },
        ]
    )
    assert [row.emulator_id for row in rows] == ["fallback", "superm"]
    assert rows[1].supplied_kinds == frozenset()
    assert rows[0].formats == ("yaml",)


def _superzsnes_profile_manifest() -> dict[str, object]:
    return {
        "platformId": "snes",
        "adapterId": "superm",
        "gameArgs": ["--fullscreen", "{rom}"],
    }


def test_superzsnes_spike_profile_parses_and_builds_argv() -> None:
    """Spike de argv: o perfil do primeiro consumidor emulator-supplied cabe
    no frame de launch sem nenhuma escrita de arquivo de melhoria."""
    profile = parse_launch("snes", "superm", _superzsnes_profile_manifest())
    assert profile is not None
    assert profile.requires_core is False
    rom = Path("/roms/EarthBound.sfc")
    argv = build_argv(profile, "/opt/steamzero/superm/SUPER-ZSNES", rom=rom)
    assert argv == [
        "/opt/steamzero/superm/SUPER-ZSNES",
        "--fullscreen",
        "/roms/EarthBound.sfc",
    ]


def test_superzsnes_spike_role_is_emulator_supplied_when_declared() -> None:
    """Politica do papel: com o manifesto declarando 'cheat' em supplied, o
    SteamZero não escreve arquivo algum (alternância fica com o emulador)."""
    assert (
        resolve_provider_role(_SUPERM_MANIFEST, EnhancementKind.CHEAT)
        is ProviderRole.EMULATOR_SUPPLIED
    )
    assert (
        resolve_provider_role(_SUPERM_MANIFEST, EnhancementKind.MOD)
        is ProviderRole.STEAMZERO_SUPPLIED
    )


def test_superzsnes_spike_manifest_validates_form() -> None:
    """A forma do manifesto roda no mesmo contrato do schema adapter-v1."""
    import jsonschema

    from steamzero.api.contracts import validate

    validate(_SUPERM_MANIFEST, "adapter-v1.schema.json")
    invalid = dict(_SUPERM_MANIFEST, enhancements={"supplied": ["cheat", "talkshow"]})
    with pytest.raises(jsonschema.ValidationError):
        validate(invalid, "adapter-v1.schema.json")


def test_coverage_gap_table_shape() -> None:
    rows = enhancement_coverage([_SUPERM_MANIFEST, {"id": "azahar", "platforms": ["switch"]}])
    assert all(isinstance(row, EnhancementCoverage) for row in rows)
    assert rows[0].platforms == ("switch",)
    assert rows[1].platforms == ("snes",)
    assert rows[0].supplied_kinds == frozenset()
