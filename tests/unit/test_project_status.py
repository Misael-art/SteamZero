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


def _table_rows(status: str) -> dict[str, list[str]]:
    """Linhas da tabela de itens, indexadas por ID e ja divididas em colunas.

    Parsear a tabela em vez de procurar substring importa: `grep` por
    "degraded" passaria se a palavra aparecesse na proxima acao de qualquer
    item, e continuaria passando com a coluna ausente.
    """
    rows: dict[str, list[str]] = {}
    for line in status.splitlines():
        if not line.startswith("| SZ-"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        rows[cells[0]] = cells
    return rows


def test_status_table_publishes_operation_and_distribution_per_item() -> None:
    """Estado operacional e de distribuicao sao colunas, item a item.

    Sem elas a tabela deixava um item parecer entregue por implementacao e
    verificacao sem dizer se ele opera no host ou se chegou a ser empacotado.
    """
    catalog = project_status.load_catalog()
    status, _ = project_status.render_catalog(catalog)

    header = next(line for line in status.splitlines() if line.startswith("| ID |"))
    columns = [cell.strip() for cell in header.strip("|").split("|")]
    assert columns.index("Operacao") == 6
    assert columns.index("Distribuicao") == 7

    rows = _table_rows(status)
    assert set(rows) == set(catalog.items), "toda capacidade precisa de uma linha"
    for identifier, item in catalog.items.items():
        cells = rows[identifier]
        assert len(cells) == len(columns), f"{identifier}: numero de colunas divergente"
        assert cells[6] == item["operation"], f"{identifier}: coluna de operacao divergente"
        assert cells[7] == item["distribution"], f"{identifier}: coluna de distribuicao divergente"


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
