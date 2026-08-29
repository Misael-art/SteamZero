# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Declaração de mídia por plataforma (lote declarativo de SZ-LIBRARY-CANONICAL).

A particularidade da plataforma (natureza da mídia, formatos, conversão,
contêiner, conteúdo auxiliar) pertence ao manifesto — não a `if` no domínio.
Estes testes garantem que a declaração existe, é coerente e é exposta pelo
registry; o domínio que consome é a etapa seguinte.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.platforms import PlatformRegistry, load_platform_manifest

MANIFESTS = Path("src/steamzero/platform_manifests")

NATURES = {"cartridge", "optical", "floppy", "tape", "digital", "hdd"}
AUXILIARY = {"none", "update", "dlc", "both"}

#: Manifestos que ESTA frente não pode migrar: 15-atari-classics tem
#: modificação não commitada de WS-2026-08-EMULATION-LONG-OPERATIONS e os 25
#: do lote de plataformas nasceram nessa mesma frente sem o bloco. A migração
#: deles é compromisso da frente que os commitar — retirar o nome desta
#: lista ao migrar. Tolerância nomeada e gateada, não omissão.
PENDENTES_DE_MIGRACAO = frozenset(
    {
        "atari-classics",
        "sega-saturn",
        "sg-1000",
        "neo-geo-cd",
        "vectrex",
        "odyssey2",
        "channelf",
        "pc-engine-supergrafx",
        "atari-st",
        "apple2",
        "bbc-micro",
        "coco",
        "ti99",
        "zx81",
        "thomson",
        "x68000",
        "pc88",
        "pc98",
        "gameandwatch",
        "supervision",
        "megaduck",
        "doom",
        "quake",
        "pico8",
        "tic80",
        "wasm4",
    }
)


def _raw_manifests() -> dict[str, dict]:
    result = {}
    for path in sorted(MANIFESTS.glob("*.platform.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        result[data["id"]] = data
    return result


def test_every_manifest_declares_media_nature_and_auxiliary_model() -> None:
    """Migração completa dos manifestos commitados: natureza e modelo de
    conteúdo auxiliar são declaração explícita — 'none' declarado é
    informação, ausência é omissão."""
    missing = [
        platform_id
        for platform_id, data in _raw_manifests().items()
        if "nature" not in data["media"] or "auxiliaryContent" not in data["media"]
    ]
    fora_da_tolerancia = set(missing) - PENDENTES_DE_MIGRACAO
    assert not fora_da_tolerancia, (
        f"manifestos sem declaração de mídia: {sorted(fora_da_tolerancia)}"
    )
    sumiram = PENDENTES_DE_MIGRACAO - set(missing)
    assert not sumiram, f"migrar da lista de pendentes (a declaração já existe): {sorted(sumiram)}"


def test_declared_formats_reference_declared_extensions() -> None:
    for platform_id, data in _raw_manifests().items():
        media = data["media"]
        formats = media.get("formats")
        if formats is None:
            continue
        declared = set(media["extensions"])
        for fmt, exts in formats.items():
            unknown = set(exts) - declared
            assert not unknown, f"{platform_id}: formato {fmt} usa ext não declarada {unknown}"


def test_preferred_format_is_a_declared_format() -> None:
    for platform_id, data in _raw_manifests().items():
        media = data["media"]
        preferred = media.get("preferredFormat")
        if preferred is None:
            continue
        assert preferred in media.get("formats", {}), (
            f"{platform_id}: preferredFormat {preferred} fora de formats"
        )


def test_auxiliary_content_beyond_none_declares_binding() -> None:
    for platform_id, data in _raw_manifests().items():
        aux = data["media"].get("auxiliaryContent")
        if aux is not None and aux != "none":
            assert data["media"].get("auxiliaryBinding") in {"titleid", "filename", "directory"}, (
                f"{platform_id}: auxiliar {aux} sem vinculação declarada"
            )


def test_registry_exposes_media_declaration() -> None:
    registry = PlatformRegistry.bundled()
    switch = registry.get("switch").media
    assert switch["nature"] == "digital"
    assert switch["auxiliaryContent"] == "both"
    assert switch["auxiliaryBinding"] == "titleid"
    assert "chd" in registry.get("playstation").media["conversionTargets"]
    assert registry.get("nes-famicom").media["containerPolicy"] == "native"


def test_invalid_nature_is_rejected_by_schema() -> None:
    data = json.loads((MANIFESTS / "12-master-system.platform.json").read_text(encoding="utf-8"))
    data["media"]["nature"] = "vhs"
    with pytest.raises(SteamZeroError, match="inválido"):
        load_platform_manifest(data)


def test_unknown_media_property_is_rejected_by_schema() -> None:
    data = json.loads((MANIFESTS / "12-master-system.platform.json").read_text(encoding="utf-8"))
    data["media"]["regionFree"] = True
    with pytest.raises(SteamZeroError, match="inválido"):
        load_platform_manifest(data)
