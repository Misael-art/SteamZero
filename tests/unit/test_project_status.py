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
