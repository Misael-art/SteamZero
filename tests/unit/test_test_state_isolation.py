# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Regressões do isolamento XDG que fecha GAP-G26."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import run_tests_isolated
from run_tests_isolated import changed_entries, isolated_environment, snapshot_state

_XDG_LAYOUT = {
    "XDG_STATE_HOME": "state",
    "XDG_DATA_HOME": "data",
    "XDG_CONFIG_HOME": "config",
    "XDG_CACHE_HOME": "cache",
    "XDG_RUNTIME_DIR": "runtime",
}


def test_autouse_fixture_isolates_all_xdg_homes(isolated_xdg_root: Path) -> None:
    root = isolated_xdg_root.resolve(strict=True)
    for variable, directory in _XDG_LAYOUT.items():
        assert Path(os.environ[variable]).resolve(strict=True) == (root / directory).resolve(
            strict=True
        )


def test_isolated_environment_overrides_all_xdg_homes(tmp_path: Path) -> None:
    root = tmp_path / "isolated"
    original = {variable: f"/real/{directory}" for variable, directory in _XDG_LAYOUT.items()}

    result = isolated_environment(root, original)

    for variable, directory in _XDG_LAYOUT.items():
        assert result[variable] == str(root / directory)
    assert result["STEAMZERO_TEST_XDG_ROOT"] == str(root)
    assert all((root / directory).is_dir() for directory in _XDG_LAYOUT.values())


def test_snapshot_detects_create_change_and_remove(tmp_path: Path) -> None:
    root = tmp_path / "state" / "steamzero"
    root.mkdir(parents=True)
    kept = root / "kept.json"
    removed = root / "removed.json"
    kept.write_text("before", encoding="utf-8")
    removed.write_text("remove", encoding="utf-8")
    before = snapshot_state(root)

    kept.write_text("after-longer", encoding="utf-8")
    removed.unlink()
    (root / "created.json").write_text("new", encoding="utf-8")
    after = snapshot_state(root)

    created, deleted, changed = changed_entries(before, after)
    assert created == ["created.json"]
    assert deleted == ["removed.json"]
    assert changed == ["kept.json"]


def test_runner_rejects_any_change_to_original_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_base = tmp_path / "real-state"
    real_root = real_base / "steamzero"
    real_root.mkdir(parents=True)

    def mutate_real_state(argv, *, env, check):
        assert check is False
        assert argv[1:3] == ["-m", "pytest"]
        assert Path(env["XDG_STATE_HOME"]) != real_base
        journal = real_root / "journal"
        journal.mkdir()
        (journal / "unexpected.jsonl").write_text("mutation", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(run_tests_isolated.subprocess, "run", mutate_real_state)

    assert (
        run_tests_isolated.run_pytest([], environ={"XDG_STATE_HOME": str(real_base)})
        == run_tests_isolated._STATE_CHANGE_EXIT
    )


def test_runner_preserves_pytest_exit_when_original_state_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_base = tmp_path / "real-state"

    def finish_without_writes(argv, *, env, check):
        assert check is False
        assert Path(env["XDG_STATE_HOME"]) != real_base
        return subprocess.CompletedProcess(argv, 7)

    monkeypatch.setattr(run_tests_isolated.subprocess, "run", finish_without_writes)

    assert run_tests_isolated.run_pytest([], environ={"XDG_STATE_HOME": str(real_base)}) == 7


def test_canonical_entrypoints_use_isolated_runner() -> None:
    root = Path(__file__).resolve().parents[2]
    makefile = (root / "Makefile").read_text(encoding="utf-8")
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    governance = (root / "AGENTS.md").read_text(encoding="utf-8")

    assert "tools/run_tests_isolated.py" in makefile
    assert workflow.count("python tools/run_tests_isolated.py") == 2
    assert "tools/run_tests_isolated.py tests -q" in governance
