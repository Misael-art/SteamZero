# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Cobertura declarativa do catálogo PlayStation 4."""

from __future__ import annotations

from steamzero.adapters.registry import AdapterRegistry
from steamzero.domain.input_profiles import InputProfileRegistry
from steamzero.domain.library import PlatformRomScanner
from steamzero.domain.platforms import PlatformRegistry


def test_ps4_manifest_declares_a_real_emulator_without_inventing_transport() -> None:
    """PS4 fecha GAP-PLATFORM-PS4-ABSENT com honestidade de transporte.

    O shadPS4 publica a release Linux como ZIP contendo um único membro
    (`Shadps4-sdl.AppImage`) — sem AppImage solto e sem Flathub, verificado
    em 2026-09-10 nas últimas 12 releases. O sha256 pinado é o do ZIP; o
    engine extrai o membro declarado via `payloadPath` e implanta o AppImage
    como payload. Este contrato prende o desenho: trocar a fonte por AppImage
    direto ou declarar instalação sem membro extraível são regressões.
    """
    manifest = PlatformRegistry.bundled().get("playstation-4")

    assert manifest.systems == ("ps4",)
    # O shadPS4 não consome firmware nem keys do usuário; exigir seria
    # inventar um requisito que o runtime não tem.
    assert manifest.requirements == ()
    assert [emulator["adapterId"] for emulator in manifest.emulators] == ["shadps4"]
    assert manifest.emulators[0]["role"] == "primary"
    assert manifest.emulators[0]["launch"]["gameArgs"] == ["{rom}"]

    adapter = AdapterRegistry.bundled().get("shadps4")
    assert adapter.platforms == ("playstation-4",)
    assert set(adapter.capabilities) == {
        "detect",
        "status",
        "install",
        "update",
        "uninstall",
        "configure",
        "verify",
        "repair",
        "backup",
        "restore",
    }
    source = adapter.sources[0]
    assert source.type == "native"
    assert source.sha256 is not None
    assert source.url.startswith("https://github.com/shadps4-emu/shadPS4/releases/")
    assert source.payload_path == "Shadps4-sdl.AppImage"


def test_ps4_media_declaration_is_explicit() -> None:
    manifest = PlatformRegistry.bundled().get("playstation-4")
    media = manifest.media

    assert media["nature"] == "optical"
    assert media["containerPolicy"] == "extract"
    assert media["auxiliaryContent"] == "both"
    # Conteúdo auxiliar de PS4 se vincula por Title ID (CUSA-xxxxx), não por
    # marcador no nome do arquivo.
    assert media["auxiliaryBinding"] == "titleid"
    assert "pkg" in media["extensions"]


def test_ps4_game_file_is_classified_by_the_manifest() -> None:
    manifest = PlatformRegistry.bundled().get("playstation-4")
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
    platform, content_kind, _evidence = scanner.classify(
        "demonstracao.pkg",
        {"demonstracao.pkg"},
        root_platform="ps4",
    )

    # O scanner rotula pelo sistema declarado (`ps4`); o vínculo com o
    # manifesto playstation-4 acontece pelo systems do catálogo.
    assert platform == "ps4"
    assert content_kind == "base"


def test_dualshock_4_profile_fits_the_platform() -> None:
    platform = PlatformRegistry.bundled().get("playstation-4")
    profiles = InputProfileRegistry.bundled()

    profile = profiles.get("dualshock-4")
    assert profile.platforms == ("playstation-4",)
    assert all(
        player_count <= int(platform.controls["maxPlayers"])
        for player_count in [profile.max_players]
    )
    assert "touchpad" in platform.controls["specialized"]
