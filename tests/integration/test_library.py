# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes da Library (F-LB-01/02/04/06): scan, import, dedupe, multidisco, quarentena.

Fixtures sintéticas (CONTENT-POLICY): dumps falsos, nenhum conteúdo protegido.
"""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from steamzero.core import fs, paths, state
from steamzero.core.errors import SteamZeroError
from steamzero.domain.library import (
    LibraryImporter,
    LibraryScanner,
    detect_format,
    disc_group,
)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[tuple[state.StateStore, Path]]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    fs.ensure_state_layout()
    src = tmp_path / "src"
    src.mkdir()
    store = state.open_state()
    yield store, src
    store.close()


def test_detect_format() -> None:
    assert detect_format("game.chd") == "chd"
    assert detect_format("game.SFC") == "snes"
    assert detect_format("x.qqq") == "unknown"


@pytest.mark.parametrize(
    ("title", "base", "disc"),
    [
        ("Final Quest (Disc 1)", "Final Quest", 1),
        ("Final Quest (Disc 2)", "Final Quest", 2),
        ("Solo Game", "Solo Game", None),
        ("Epic (Disk 3)", "Epic", 3),
    ],
)
def test_disc_group(title: str, base: str, disc: int | None) -> None:
    assert disc_group(title) == (base, disc)


def test_scan_is_read_only(env: tuple[state.StateStore, Path]) -> None:
    store, src = env
    fs.write_atomic(src / "a.nes", b"NEScontent")
    fs.write_atomic(src / "sub" / "b.sfc", b"SNEScontent")
    before = {p: fs.hash_file(p) for p in fs.iter_files(src)}
    scanned = LibraryScanner(store).scan(src)
    assert {s.relpath for s in scanned} == {"a.nes", "sub/b.sfc"}
    assert {s.format for s in scanned} == {"nes", "snes"}
    # AC-LB-01: scan não escreve nada (nem roms, nem altera a origem)
    assert not paths.roms_dir().exists()
    assert {p: fs.hash_file(p) for p in fs.iter_files(src)} == before


def test_import_copies_and_source_untouched(env: tuple[state.StateStore, Path]) -> None:
    store, src = env
    rom = src / "Game.chd"
    fs.write_atomic(rom, b"synthetic-dump")
    src_hash = fs.hash_file(rom)

    result = LibraryImporter(store).import_file(rom, "psx")
    assert result.status == "imported"
    # RT-07: origem intocada byte a byte
    assert rom.exists()
    assert fs.hash_file(rom) == src_hash
    # cópia registrada e verificável
    assert store.find_rom_by_hash(src_hash) is not None
    copied = paths.roms_dir() / "psx" / "Game.chd"
    assert copied.read_bytes() == b"synthetic-dump"


def test_import_dedupe(env: tuple[state.StateStore, Path]) -> None:
    store, src = env
    a = src / "A.chd"
    b = src / "B.chd"
    fs.write_atomic(a, b"same-content")
    fs.write_atomic(b, b"same-content")
    imp = LibraryImporter(store)
    first = imp.import_file(a, "psx")
    second = imp.import_file(b, "psx")
    assert first.status == "imported"
    assert second.status == "duplicate"
    assert len(store.list_roms()) == 1


def test_import_multidisc_grouping(env: tuple[state.StateStore, Path]) -> None:
    store, src = env
    d1 = src / "Saga (Disc 1).chd"
    d2 = src / "Saga (Disc 2).chd"
    fs.write_atomic(d1, b"disc1")
    fs.write_atomic(d2, b"disc2")
    imp = LibraryImporter(store)
    imp.import_file(d1, "psx")
    imp.import_file(d2, "psx")
    games = store.export_json()["tables"]["game"]
    groups = {g["multi_disc_group"] for g in games}
    assert groups == {"Saga"}


def test_import_archive_valid(env: tuple[state.StateStore, Path]) -> None:
    store, src = env
    archive = src / "pack.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("rom1.nes", b"one")
        zf.writestr("rom2.sfc", b"two")
    results = LibraryImporter(store).import_archive(archive, "multi")
    assert {r.status for r in results} == {"imported"}
    assert len(store.list_roms()) == 2
    # staging limpo após import
    assert not any(paths.staging_dir().iterdir())


def test_import_archive_traversal_quarantined(env: tuple[state.StateStore, Path]) -> None:
    store, src = env
    archive = src / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../escape.txt", b"x")
    src_hash = fs.hash_file(archive)
    with pytest.raises(SteamZeroError) as ei:
        LibraryImporter(store).import_archive(archive, "psx")
    assert ei.value.code == "E-CONTENT-UNSAFE-PATH"
    # AC-LB-03: origem intocada, nada em roms, staging limpo
    assert fs.hash_file(archive) == src_hash
    assert not paths.roms_dir().exists()
    assert not any(paths.staging_dir().iterdir())
