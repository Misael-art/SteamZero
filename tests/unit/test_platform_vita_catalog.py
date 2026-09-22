# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Cobertura declarativa do catálogo PlayStation Vita."""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path

from steamzero.adapters.discovery.vita_sfo import read_vita_metadata
from steamzero.adapters.scraping.screenscraper import _PLATFORMS_WITHOUT_SYSTEMEID
from steamzero.domain.library import PlatformDirectoryInventory, PlatformRomScanner
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
    assert manifest.media["directoryFormats"] == ["vita3k-app"]


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


def test_psvita_scanner_rejects_extracted_manual_and_module_files() -> None:
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

    for name in ("001.png", "eboot.bin"):
        platform, content_kind, evidence = scanner.classify(
            name,
            {name},
            root_platform="playstation-vita",
        )
        assert (platform, content_kind, evidence) == (
            None,
            "unknown",
            "unsupported-root-extension",
        )


def _sfo(*, title: str, title_id: str) -> bytes:
    keys = b"TITLE_ID\0TITLE\0"
    title_id_bytes = title_id.encode()
    title_bytes = title.encode()
    values = title_id_bytes + b"\0" + title_bytes + b"\0"
    key_offset = 20 + 16 * 2
    data_offset = key_offset + len(keys)
    entries = [
        (0, 0x0204, len(title_id_bytes) + 1, len(title_id_bytes) + 1, 0),
        (9, 0x0204, len(title_bytes) + 1, len(title_bytes) + 1, len(title_id_bytes) + 1),
    ]
    header = struct.pack("<4sIIII", b"\x00PSF", 0x101, key_offset, data_offset, 2)
    index = b"".join(struct.pack("<HHIII", *entry) for entry in entries)
    return header + index + keys + values


def test_vita_metadata_reads_title_id_from_zip_and_app_directory(tmp_path: Path) -> None:
    payload = _sfo(title="LittleBigPlanet™ PlayStation®Vita", title_id="PCSF00516")
    archive = tmp_path / "PCSF00516.zip"
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("sce_sys/param.sfo", payload)
    metadata = read_vita_metadata(archive)
    assert metadata.identity is not None
    assert metadata.identity.value == "PCSF00516"
    assert metadata.title == "LittleBigPlanet PlayStation Vita"

    app = tmp_path / "PCSF00516"
    (app / "sce_sys").mkdir(parents=True)
    (app / "sce_sys" / "param.sfo").write_bytes(payload)
    (app / "eboot.bin").write_bytes(b"boot")
    directory_metadata = read_vita_metadata(app)
    assert directory_metadata.identity is not None
    assert directory_metadata.title == "LittleBigPlanet PlayStation Vita"


def test_vita3k_app_directory_is_one_game_and_not_its_internal_assets(
    tmp_path: Path,
) -> None:
    app = tmp_path / "psvita" / "app" / "PCSF00516"
    (app / "sce_sys").mkdir(parents=True)
    (app / "sce_sys" / "param.sfo").write_bytes(
        _sfo(title="LittleBigPlanet™ PlayStation®Vita", title_id="PCSF00516")
    )
    (app / "eboot.bin").write_bytes(b"boot")
    manual = app / "sce_sys" / "manual"
    manual.mkdir()
    (manual / "001.png").write_bytes(b"manual")

    rows = PlatformDirectoryInventory.from_registry(PlatformRegistry.bundled()).inventory(tmp_path)

    assert len(rows) == 1
    assert rows[0].game_count == 1
    assert len(rows[0].selected_games) == 1
    assert rows[0].selected_games[0].format == "vita3k-app"
    assert rows[0].selected_games[0].path == app
    assert rows[0].selected_games[0].evidence == "directory-native"
    related = {item.path.relative_to(app).as_posix(): item for item in rows[0].related_content}
    assert "sce_sys/param.sfo" in related
    assert "sce_sys/manual/001.png" in related
    assert related["sce_sys/manual/001.png"].relation == "directory-member"
    assert related["sce_sys/manual/001.png"].owner_path == app
