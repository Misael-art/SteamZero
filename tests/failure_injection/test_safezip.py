# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""FI-16/17/18: safezip — zip bomb, traversal, symlink, limites (AC-LB-03, FM-14).

Fixtures 100% sintéticas (zeros/aleatório) — nenhum conteúdo protegido (CONTENT-POLICY).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from steamzero.core import fs, paths, safezip
from steamzero.core.errors import SteamZeroError


@pytest.fixture
def state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    fs.ensure_state_layout()
    return tmp_path


def _zip(path: Path, entries: list[tuple[str, bytes]], *, compress: bool = False) -> Path:
    ctype = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    with zipfile.ZipFile(path, "w", ctype) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return path


@pytest.mark.fi
def test_valid_zip_extracts_to_staging(state: Path) -> None:
    z = _zip(state / "ok.zip", [("a.bin", b"AAAA"), ("sub/b.bin", b"BBBB")])
    out = safezip.extract_safe(z, "OP1")
    assert len(out) == 2
    for p in out:
        assert fs.is_within(paths.staging_for("OP1"), p)
    assert (paths.staging_for("OP1") / "a.bin").read_bytes() == b"AAAA"


@pytest.mark.fi
def test_traversal_entry_rejected(state: Path) -> None:
    z = _zip(state / "trav.zip", [("../evil.txt", b"x")])
    with pytest.raises(SteamZeroError) as ei:
        safezip.extract_safe(z, "OP2")
    assert ei.value.code == "E-CONTENT-UNSAFE-PATH"
    # nada materializado fora do staging
    assert not (state / "evil.txt").exists()


@pytest.mark.fi
def test_absolute_entry_rejected(state: Path) -> None:
    z = _zip(state / "abs.zip", [("/etc/passwd", b"x")])
    with pytest.raises(SteamZeroError) as ei:
        safezip.extract_safe(z, "OP3")
    assert ei.value.code == "E-CONTENT-UNSAFE-PATH"


@pytest.mark.fi
def test_symlink_entry_rejected(state: Path) -> None:
    z = state / "link.zip"
    with zipfile.ZipFile(z, "w") as zf:
        info = zipfile.ZipInfo("evil-link")
        info.external_attr = (0o120777) << 16  # S_IFLNK
        zf.writestr(info, "/etc/passwd")
    with pytest.raises(SteamZeroError) as ei:
        safezip.extract_safe(z, "OP4")
    assert ei.value.code == "E-CONTENT-UNSAFE-PATH"


@pytest.mark.fi
def test_too_many_entries_rejected(state: Path) -> None:
    z = _zip(state / "many.zip", [(f"f{i}.bin", b"x") for i in range(20)])
    limits = safezip.SafeZipLimits(max_entries=10)
    with pytest.raises(SteamZeroError) as ei:
        safezip.extract_safe(z, "OP5", limits=limits)
    assert ei.value.code == "E-CONTENT-UNSAFE-ARCHIVE"


@pytest.mark.fi
def test_entry_too_large_bomb(state: Path) -> None:
    z = _zip(state / "bomb.zip", [("big.bin", b"Z" * 5000)])
    limits = safezip.SafeZipLimits(max_entry_bytes=100)
    with pytest.raises(SteamZeroError) as ei:
        safezip.extract_safe(z, "OP6", limits=limits)
    assert ei.value.code == "E-CONTENT-UNSAFE-ARCHIVE"


@pytest.mark.fi
def test_total_too_large(state: Path) -> None:
    z = _zip(state / "tot.zip", [(f"f{i}.bin", b"Z" * 400) for i in range(10)])
    limits = safezip.SafeZipLimits(max_total_bytes=1000, max_entry_bytes=10_000)
    with pytest.raises(SteamZeroError) as ei:
        safezip.extract_safe(z, "OP7", limits=limits)
    assert ei.value.code == "E-CONTENT-UNSAFE-ARCHIVE"


@pytest.mark.fi
def test_depth_too_deep(state: Path) -> None:
    deep = "/".join(f"d{i}" for i in range(20)) + "/f.bin"
    z = _zip(state / "deep.zip", [(deep, b"x")])
    limits = safezip.SafeZipLimits(max_depth=5)
    with pytest.raises(SteamZeroError) as ei:
        safezip.extract_safe(z, "OP8", limits=limits)
    assert ei.value.code == "E-CONTENT-UNSAFE-ARCHIVE"


@pytest.mark.fi
def test_ratio_bomb(state: Path) -> None:
    # 200k zeros comprime muito -> razão alta
    z = _zip(state / "ratio.zip", [("z.bin", b"\x00" * 200_000)], compress=True)
    limits = safezip.SafeZipLimits(max_ratio=5, max_entry_bytes=10**7, max_total_bytes=10**7)
    with pytest.raises(SteamZeroError) as ei:
        safezip.extract_safe(z, "OP9", limits=limits)
    assert ei.value.code == "E-CONTENT-UNSAFE-ARCHIVE"


@pytest.mark.fi
def test_not_a_zip(state: Path) -> None:
    bogus = state / "notazip.zip"
    fs.write_atomic(bogus, b"isto nao e um zip")
    with pytest.raises(SteamZeroError) as ei:
        safezip.extract_safe(bogus, "OP10")
    assert ei.value.code == "E-CONTENT-UNSAFE-ARCHIVE"
