# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes de core.paths (layout XDG)."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.core import paths


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
