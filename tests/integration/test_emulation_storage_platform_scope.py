"""Integração das métricas físicas com o escopo canônico da plataforma."""

from __future__ import annotations

from pathlib import Path

from steamzero.adapters.storage_summary import collect_storage_summary


def test_mixed_root_counts_only_canonical_files_in_platform_scope(tmp_path: Path) -> None:
    root = tmp_path / "roms"
    root.mkdir()
    switch_rom = root / "switch.nsp"
    other_rom = root / "other.nes"
    switch_rom.write_bytes(b"switch-data")
    other_rom.write_bytes(b"foreign-data")

    summary = collect_storage_summary(
        rom_roots=(root,),
        emulator_roots=(),
        saves_root=tmp_path / "saves",
        media_root=tmp_path / "media",
        cache_roots=(),
        volume_root=tmp_path,
        rom_files=(switch_rom,),
        platform_id="switch",
    )

    roms = next(bucket for bucket in summary["buckets"] if bucket["id"] == "roms")
    assert roms["files"] == 1
    assert roms["bytes"] == len(b"switch-data")
    assert summary["scope"] == {"platformId": "switch", "romFiles": 1}
    assert other_rom.read_bytes() == b"foreign-data"
