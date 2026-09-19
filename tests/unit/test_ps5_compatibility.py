# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato do snapshot público de compatibilidade SharpEmu/PS5."""

from steamzero.adapters.ps5_compatibility import (
    Ps5CompatibilityCatalog,
    Ps5CompatibilityRecord,
    bundled_ps5_compatibility,
    resolve_ps5_compatibility,
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
