# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Regressoes do catalogo verificavel de estado do projeto."""

from __future__ import annotations

import project_status


def test_committed_catalog_and_generated_views_are_consistent() -> None:
    assert project_status.check_catalog() == []


def test_render_is_deterministic() -> None:
    catalog = project_status.load_catalog()
    assert project_status.render_catalog(catalog) == project_status.render_catalog(catalog)


def test_active_workstream_paths_cannot_overlap() -> None:
    assert project_status._paths_overlap("src/steamzero/ui", "src/steamzero/ui/qml")
    assert project_status._paths_overlap("tools/vm_harness", "tools/vm_harness")
    assert not project_status._paths_overlap("src/steamzero/ui", "tools/vm_harness")


def test_scope_digest_changes_when_a_claimed_file_changes(tmp_path) -> None:
    claimed = tmp_path / "claimed.txt"
    claimed.write_text("first\n", encoding="utf-8")
    first = project_status.scope_digest(tmp_path, ["claimed.txt"])
    claimed.write_text("second\n", encoding="utf-8")
    assert project_status.scope_digest(tmp_path, ["claimed.txt"]) != first


def test_scope_digest_ignores_worklog_bytes(tmp_path) -> None:
    worklog = tmp_path / "docs" / "WORKLOG.md"
    worklog.parent.mkdir(parents=True)
    worklog.write_text("sessao-1\n", encoding="utf-8")
    claimed = tmp_path / "claimed.txt"
    claimed.write_text("stable\n", encoding="utf-8")
    first = project_status.scope_digest(tmp_path, ["docs/WORKLOG.md", "claimed.txt"])
    worklog.write_text("sessao-1\nsessao-2\n", encoding="utf-8")
    assert project_status.scope_digest(tmp_path, ["docs/WORKLOG.md", "claimed.txt"]) == first


def test_worklog_append_only_accepts_suffix_and_rejects_rewrite(tmp_path) -> None:
    import subprocess

    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    docs = root / "docs"
    docs.mkdir()
    worklog = docs / "WORKLOG.md"
    worklog.write_text("## sessao A\n\n", encoding="utf-8")
    subprocess.run(["git", "add", "docs/WORKLOG.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "baseline worklog"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    assert project_status.check_worklog_append_only(root) == []
    worklog.write_text("## sessao A\n\n## sessao B\n\n", encoding="utf-8")
    assert project_status.check_worklog_append_only(root) == []
    worklog.write_text("## sessao reescrita\n\n", encoding="utf-8")
    errors = project_status.check_worklog_append_only(root)
    assert errors
    assert "reescrita" in errors[0]
