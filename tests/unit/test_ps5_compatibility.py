# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato do snapshot público de compatibilidade SharpEmu/PS5."""

from pathlib import Path

from steamzero.adapters.ps5_compatibility import (
    Ps5CompatibilityCatalog,
    Ps5CompatibilityRecord,
    _ps5_source_kind,
    _ps5_source_namespace,
    build_ps5_source_identity,
    bundled_ps5_compatibility,
    resolve_ps5_compatibility,
    resolve_ps5_content_status,
)


def test_bundled_snapshot_is_pinned_and_complete() -> None:
    catalog = bundled_ps5_compatibility()

    assert catalog.source_url == "https://sharpemu.app/compatibility/"
    assert catalog.source_commit == "5a6f37843b8d3eab8cd6dde95d147e9b3f6d529a"
    assert len(catalog.records) == 46
    assert catalog.lookup("ppsa02929").state == "playable"


def test_resolution_requires_exact_build_and_operating_system() -> None:
    catalog = Ps5CompatibilityCatalog(
        source_url="https://sharpemu.app/compatibility/",
        source_repository="https://github.com/sharpemu/sharpemu-site",
        source_path="src/content/compat",
        source_commit="0" * 40,
        snapshot_date="2026-09-19",
        records=(
            Ps5CompatibilityRecord(
                title_id="PPSA02929",
                state="playable",
                tested_build="linux-build",
                tested_date="2026-09-19",
                tested_os="linux",
                game_version="1.000",
            ),
        ),
    )

    exact = resolve_ps5_compatibility(
        "PPSA02929", "linux-build", runtime_os="linux", catalog=catalog
    )
    assert exact["state"] == "playable"
    assert exact["testedBuild"] == "linux-build"

    wrong_build = resolve_ps5_compatibility(
        "PPSA02929", "other-build", runtime_os="linux", catalog=catalog
    )
    assert wrong_build["state"] == "unknown"
    assert wrong_build["testedBuild"] == "linux-build"
    assert "não foi testada" in wrong_build["reason"]

    wrong_os = resolve_ps5_compatibility(
        "PPSA02929", "linux-build", runtime_os="windows", catalog=catalog
    )
    assert wrong_os["state"] == "unknown"
    assert "host windows" in wrong_os["reason"]


def test_resolution_explains_missing_title_id() -> None:
    result = resolve_ps5_compatibility(None, "0.0.3-release.4", runtime_os="linux")

    assert result["state"] == "unknown"
    assert result["build"] == "0.0.3-release.4"
    assert "Title ID PS5 ausente" in result["reason"]


def test_content_status_distinguishes_missing_source_and_incomplete_dump(tmp_path) -> None:  # type: ignore[no-untyped-def]
    eboot = tmp_path / "eboot.bin"
    eboot.write_bytes(b"ELF")

    complete = resolve_ps5_content_status(
        str(eboot), identity_verified=True, identity_diagnosis="ps5-param-sfo"
    )
    assert complete["contentState"] == "complete"

    incomplete = resolve_ps5_content_status(
        str(eboot), identity_verified=False, identity_diagnosis="ps5-param-sfo-missing"
    )
    assert incomplete["contentState"] == "content-incomplete"
    assert "param-sfo-missing" in incomplete["contentReason"]

    missing = resolve_ps5_content_status(
        str(tmp_path / "gone"), identity_verified=False, identity_diagnosis=None
    )
    assert missing["contentState"] == "source-missing"
    assert missing["contentAvailability"] == "missing"

    json_identity = resolve_ps5_content_status(
        str(eboot), identity_verified=True, identity_diagnosis="ps5-param-json"
    )
    assert json_identity["contentState"] == "complete"
    assert "param.json" in json_identity["contentReason"]


def test_source_identity_uses_relative_path_and_entrypoint_hash_not_absolute_path(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "roms" / "ps5"
    eboot = root / "Demo" / "eboot.bin"
    eboot.parent.mkdir(parents=True)
    eboot.write_bytes(b"ELF-v1")

    first = build_ps5_source_identity(eboot, root, title_id="PPSA12345_00")
    assert first["sourceKind"] == "local"
    assert first["volumeId"] is not None
    assert first["shareId"] is None
    assert first["relativePath"] == "Demo/eboot.bin"
    assert first["sizeBytes"] == 6
    assert first["identityState"] == "verified"
    assert first["entrypointSha256"]
    assert str(root) not in first["relativePath"]

    # A timestamp-only change must not create a new game identity.
    eboot.touch()
    second = build_ps5_source_identity(eboot, root, title_id="PPSA12345_00")
    assert second["stableId"] == first["stableId"]
    enriched = build_ps5_source_identity(eboot, root, title_id="PPSA54321_00")
    assert enriched["stableId"] == first["stableId"]
    assert enriched["titleId"] == "PPSA54321_00"

    eboot.write_bytes(b"ELF-v2")
    changed = build_ps5_source_identity(eboot, root, title_id="PPSA12345_00")
    assert changed["stableId"] != first["stableId"]
    assert changed["entrypointSha256"] != first["entrypointSha256"]


def test_unobserved_source_namespace_never_uses_absolute_path(tmp_path) -> None:  # type: ignore[no-untyped-def]
    first = _ps5_source_namespace(tmp_path / "missing-a", "removable")
    second = _ps5_source_namespace(tmp_path / "missing-b", "removable")

    assert first == second
    assert str(tmp_path) not in first


def test_source_kind_recognizes_removable_network_and_local_roots() -> None:
    assert _ps5_source_kind(Path("/run/media/misael/deck/roms")) == "removable"
    assert _ps5_source_kind(Path("/mnt/ps5-dump/roms")) == "removable"
    assert _ps5_source_kind(Path("//nas.example/roms")) == "network"
    assert _ps5_source_kind(Path("/net/nas/roms")) == "network"
    assert _ps5_source_kind(Path("/opt/roms")) == "local"


def test_source_identity_separates_removable_volume_and_network_share(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "roms" / "ps5"
    eboot = root / "Demo" / "eboot.bin"
    eboot.parent.mkdir(parents=True)
    eboot.write_bytes(b"ELF-v1")

    monkeypatch.setattr(
        "steamzero.adapters.ps5_compatibility._ps5_source_kind",
        lambda _root: "removable",
    )
    removable = build_ps5_source_identity(eboot, root, title_id="PPSA12345_00")
    assert removable["sourceKind"] == "removable"
    assert removable["volumeId"]
    assert removable["shareId"] is None

    monkeypatch.setattr(
        "steamzero.adapters.ps5_compatibility._ps5_source_kind",
        lambda _root: "network",
    )
    network = build_ps5_source_identity(eboot, root, title_id="PPSA12345_00")
    assert network["sourceKind"] == "network"
    assert network["volumeId"] is None
    assert network["shareId"]
    assert network["stableId"] != removable["stableId"]
