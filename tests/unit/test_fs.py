# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes de core.fs: escrita atômica, containment/path-safety, hash, staging."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from steamzero.core import fs, paths
from steamzero.core.errors import SteamZeroError


@pytest.fixture
def state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    fs.ensure_state_layout()
    return paths.state_home()


# --- escrita atômica -------------------------------------------------------
def test_write_atomic_content_and_perms(tmp_path: Path) -> None:
    p = tmp_path / "sub" / "file.txt"
    fs.write_atomic_text(p, "olá")
    assert p.read_text(encoding="utf-8") == "olá"
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_write_atomic_no_leftover_temp(tmp_path: Path) -> None:
    p = tmp_path / "file.bin"
    fs.write_atomic(p, b"data")
    leftovers = [x for x in tmp_path.iterdir() if x.name.startswith(".") and ".tmp." in x.name]
    assert leftovers == []


def test_write_atomic_idempotent_and_overwrite(tmp_path: Path) -> None:
    p = tmp_path / "f"
    fs.write_atomic(p, b"v1")
    fs.write_atomic(p, b"v2")
    fs.write_atomic(p, b"v2")
    assert p.read_bytes() == b"v2"


def test_sweep_orphan_temps(tmp_path: Path) -> None:
    orphan = tmp_path / ".file.txt.tmp.123.abcdef"
    fs.write_atomic(orphan, b"junk")  # cria arquivo com nome de tmp órfão
    keep = tmp_path / "real.txt"
    fs.write_atomic(keep, b"keep")
    removed = fs.sweep_orphan_temps(tmp_path)
    assert orphan in removed
    assert not orphan.exists()
    assert keep.exists()


# --- append writer ---------------------------------------------------------
def test_append_writer(tmp_path: Path) -> None:
    p = tmp_path / "log.jsonl"
    with fs.AppendWriter(p) as w:
        w.write_line('{"a":1}')
        w.write_line('{"b":2}', fsync=True)
    with fs.AppendWriter(p) as w:
        w.write_line('{"c":3}')
    assert p.read_text().splitlines() == ['{"a":1}', '{"b":2}', '{"c":3}']
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


# --- containment -----------------------------------------------------------
def test_is_within_true(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / "a").mkdir(parents=True)
    assert fs.is_within(root, root / "a" / "b.txt")
    assert fs.is_within(root, root)


def test_resolve_within_rejects_traversal(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(SteamZeroError) as ei:
        fs.resolve_within(root, root / ".." / "escape")
    assert ei.value.code == "E-CONTENT-UNSAFE-PATH"


def test_resolve_within_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_text("x")
    root = tmp_path / "root"
    root.mkdir()
    (root / "link").symlink_to(outside)
    with pytest.raises(SteamZeroError) as ei:
        fs.resolve_within(root, root / "link" / "secret")
    assert ei.value.code == "E-CONTENT-UNSAFE-PATH"


@pytest.mark.parametrize(
    "bad",
    ["../../etc/passwd", "/etc/passwd", "a/../../b", "C:\\win", "C:/win", "a\\b", "x\x00y", "\t"],
)
def test_validate_relative_entry_rejects(bad: str) -> None:
    with pytest.raises(SteamZeroError) as ei:
        fs.validate_relative_entry(bad)
    assert ei.value.code == "E-CONTENT-UNSAFE-PATH"


@pytest.mark.parametrize("good", ["file.bin", "sub/dir/rom.chd", "psx/scph.bin", "a:b"])
def test_validate_relative_entry_accepts(good: str) -> None:
    rel = fs.validate_relative_entry(good)
    assert str(rel) == good


def test_validate_relative_entry_empty() -> None:
    with pytest.raises(SteamZeroError):
        fs.validate_relative_entry("")


# --- hash / espaço ---------------------------------------------------------
def test_hash_bytes_and_file_match(tmp_path: Path) -> None:
    data = b"conteudo sintetico"
    p = tmp_path / "f"
    fs.write_atomic(p, data)
    assert fs.hash_file(p) == fs.hash_bytes(data)


def test_free_space_positive(tmp_path: Path) -> None:
    assert fs.free_space(tmp_path / "nope" / "deeper") > 0


# --- staging / backup / quarentena ----------------------------------------
def test_stage_bytes(state: Path) -> None:
    dest = fs.stage_bytes("OP1", "sub/x.bin", b"stuff")
    assert dest.read_bytes() == b"stuff"
    assert fs.is_within(paths.staging_for("OP1"), dest)


def test_stage_bytes_rejects_traversal(state: Path) -> None:
    with pytest.raises(SteamZeroError):
        fs.stage_bytes("OP1", "../escape", b"x")


def test_backup_file_roundtrip(state: Path, tmp_path: Path) -> None:
    src = tmp_path / "orig.txt"
    fs.write_atomic_text(src, "dados do usuario")
    entry = fs.backup_file("OP1", src, "orig.txt")
    assert entry.hash == fs.hash_file(src)
    assert entry.size == src.stat().st_size
    backup_path = paths.backup_for("OP1") / "orig.txt"
    assert backup_path.read_text() == "dados do usuario"


def test_quarantine_moves_not_deletes(state: Path, tmp_path: Path) -> None:
    src = tmp_path / "suspeito.zip"
    fs.write_atomic(src, b"suspeito")
    dest = fs.quarantine_file("OP1", src, "suspeito.zip")
    assert dest.exists()
    assert not src.exists()  # movido, não copiado
    assert dest.read_bytes() == b"suspeito"


def test_ensure_state_layout_idempotent(state: Path) -> None:
    fs.ensure_state_layout()  # segunda vez não falha
    for factory in paths.STATE_SUBDIRS:
        d = factory()
        assert d.is_dir()
        assert stat.S_IMODE(d.stat().st_mode) == 0o700
