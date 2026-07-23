# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes de core.paths (layout XDG)."""

from __future__ import annotations

import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from steamzero.core import paths
from steamzero.service import core as service_core
from steamzero.service import socket_path


def test_state_home_respects_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "st"))
    assert paths.state_home() == tmp_path / "st" / "steamzero"


def test_state_home_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setattr(paths, "_home", lambda: tmp_path)
    assert paths.state_home() == tmp_path / ".local" / "state" / "steamzero"


def test_subpaths_under_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    root = paths.state_home()
    assert paths.journal_path("OP1") == root / "journal" / "OP1.jsonl"
    assert paths.staging_for("OP1") == root / "staging" / "OP1"
    assert paths.backup_for("OP1") == root / "backups" / "OP1"
    assert paths.quarantine_for("OP1") == root / "quarantine" / "OP1"
    assert paths.state_db() == root / "state.db"
    assert paths.core_log() == root / "logs" / "core.jsonl"


def test_runtime_dir_respects_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    assert paths.runtime_dir() == tmp_path / "run" / "steamzero"


def test_safe_socket_path_keeps_bindable_xdg_layout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_root = tmp_path / "run"
    runtime_root.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(socket_path, "_AF_UNIX_PATH_MAX", 4096)

    resolved = socket_path.safe_socket_path()

    assert resolved == runtime_root / "steamzero" / "core.sock"
    assert stat.S_IMODE(resolved.parent.stat().st_mode) == 0o700
    assert service_core._safe_socket_path() == resolved


def test_safe_socket_path_uses_deterministic_short_fallback_for_long_xdg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_root = tmp_path / ("runtime-" + "x" * 120)
    runtime_root.mkdir(mode=0o700)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_root))

    first = socket_path.safe_socket_path()
    second = socket_path.safe_socket_path()

    assert first == second
    assert first.parent.parent == Path("/tmp")  # noqa: S108 - valida o fallback Linux
    assert len(os.fsencode(first)) <= socket_path._AF_UNIX_PATH_MAX
    assert stat.S_IMODE(first.parent.stat().st_mode) == 0o700


def test_safe_socket_path_without_xdg_uses_fallback_when_default_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    missing = tmp_path / "missing" / "steamzero"
    fallback_root = tmp_path / "fallback"
    fallback_root.mkdir(mode=0o1777)
    fallback_root.chmod(0o1777)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(paths, "runtime_dir", lambda: missing)
    monkeypatch.setattr(socket_path, "_FALLBACK_ROOT", fallback_root)
    monkeypatch.setattr(socket_path, "_AF_UNIX_PATH_MAX", 4096)

    resolved = socket_path.safe_socket_path()

    assert resolved.parent.parent == fallback_root
    assert stat.S_IMODE(resolved.parent.stat().st_mode) == 0o700


@pytest.mark.parametrize("mode", [0o755, 0o770, 0o777])
def test_safe_socket_path_rejects_insecure_xdg_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mode: int
) -> None:
    runtime_root = tmp_path / f"run-{mode:o}"
    runtime_root.mkdir(mode=mode)
    runtime_root.chmod(mode)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_root))

    with pytest.raises(PermissionError, match="XDG runtime inseguro"):
        socket_path.safe_socket_path()


def test_safe_socket_path_rejects_symlinked_xdg_and_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(linked))
    with pytest.raises(PermissionError, match="XDG runtime inseguro"):
        socket_path.safe_socket_path()

    long_runtime = tmp_path / ("runtime-" + "y" * 120)
    long_runtime.mkdir(mode=0o700)
    fallback_link = tmp_path / "fallback-link"
    fallback_link.symlink_to(real, target_is_directory=True)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(long_runtime))
    monkeypatch.setattr(socket_path, "_FALLBACK_ROOT", fallback_link)
    with pytest.raises(PermissionError, match="fallback insegura"):
        socket_path.safe_socket_path()


def test_safe_socket_path_rejects_wrong_fallback_owner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    runtime_root = tmp_path / ("runtime-" + "z" * 120)
    runtime_root.mkdir(mode=0o700)
    fallback_root = tmp_path / "fallback"
    fallback_root.mkdir(mode=0o1777)
    fallback_root.chmod(0o1777)
    real_uid = os.getuid()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime_root))
    monkeypatch.setattr(socket_path, "_FALLBACK_ROOT", fallback_root)
    monkeypatch.setattr(socket_path, "_validate_xdg_root", lambda _root: None)
    monkeypatch.setattr(socket_path, "_validate_fallback_root", lambda: None)
    monkeypatch.setattr(socket_path.os, "getuid", lambda: real_uid + 1)

    with pytest.raises(PermissionError, match="subdiretório privado inseguro"):
        socket_path.safe_socket_path()


def test_safe_socket_fallbacks_are_concurrent_and_collision_resistant() -> None:
    originals = [Path(f"/very/long/runtime/{index}/steamzero/core.sock") for index in range(24)]

    with ThreadPoolExecutor(max_workers=8) as pool:
        resolved = list(pool.map(socket_path._fallback_socket_path, originals))

    assert len(set(resolved)) == len(originals)
    assert all(stat.S_IMODE(path.parent.stat().st_mode) == 0o700 for path in resolved)
