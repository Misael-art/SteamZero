# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Cobertura declarativa do catálogo PlayStation Vita."""

from __future__ import annotations

from pathlib import Path

from steamzero.adapters.scraping.screenscraper import _PLATFORMS_WITHOUT_SYSTEMEID
from steamzero.domain.library import PlatformRomScanner
from steamzero.domain.platforms import PlatformRegistry


def test_vita_manifest_declares_a_real_emulator() -> None:
    """Contrato alterado em 2026-09-02, por decisão explícita do operador.

    A versão anterior catalogava a Vita SEM emulador (`emulators == ()`), para
    classificar `roms/psvita` sem prometer lançamento. O desenho era
    defensável, mas colidia com o contrato mais antigo de
    `test_manifests_publish_all_capability_dimensions_and_safe_cloud_hosts`,
    que exige emulador declarado em toda plataforma `kind: emulated` — esse
    teste estava vermelho e ninguém viu, porque a suíte morria por disco cheio
    antes de chegar nele.

    Uma plataforma emulada visível e sem emulador é pior que a lacuna que
    substitui: os arquivos passam a pertencer a algo que não roda. Resolvido a
    favor do emulador real: `vita3k`, AppImage x86_64 fixado pelo SHA-256
    publicado na API do GitHub (o upstream não publica no Flathub).
    """
    manifest = PlatformRegistry.bundled().get("playstation-vita")

    assert manifest.systems == ("psvita", "playstation-vita", "vita")
    assert manifest.requirements == ("keys", "firmware")
    assert [emulator["adapterId"] for emulator in manifest.emulators] == ["vita3k"]
    assert manifest.emulators[0]["role"] == "primary"
    # Independente do emulador: o ScreenScraper não tem systemeID para a Vita,
    # então a busca de mídia não pode filtrar por plataforma nesta.
    assert "playstation-vita" in _PLATFORMS_WITHOUT_SYSTEMEID


def test_psvita_directory_is_classified_by_the_manifest() -> None:
    manifest = PlatformRegistry.bundled().get("playstation-vita")
    scanner = PlatformRomScanner.from_manifests(
        [
            {
                "id": manifest.id,
                "media": {
                    "extensions": list(manifest.media["extensions"]),
                    "formats": manifest.media.get("formats", {}),
                    "containerPolicy": manifest.media.get("containerPolicy"),
                },
            }
        ]
    )
    platform, content_kind, evidence = scanner.classify(
        "demo.vpk",
        {"demo.vpk"},
        root_platform="playstation-vita",
    )

    assert platform == "playstation-vita"
    assert content_kind == "base"
    assert evidence == "root-wins"


def test_psvita_root_name_resolves_to_the_canonical_platform() -> None:
    manifest = PlatformRegistry.bundled().get("playstation-vita")
    scanner = PlatformRomScanner.from_manifests(
        [
            {
                "id": manifest.id,
                "systems": list(manifest.systems),
                "media": {
                    "extensions": list(manifest.media["extensions"]),
                    "formats": manifest.media.get("formats", {}),
                },
            }
        ]
    )

    root = Path("/roms")
    platform, _kind, _evidence = scanner.classify(
        "demo.vpk",
        {"demo.vpk"},
        root_platform=None,
        path=root / "psvita" / "demo.vpk",
    )

    assert platform == "playstation-vita"
