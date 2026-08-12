# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Regressoes do catalogo verificavel de estado do projeto."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

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


def test_unit_evidence_goes_stale_when_the_scope_changes(tmp_path: Path) -> None:
    """`verification: unit` envelhece como dev/vm/hw.

    Antes, `unit` era a verificacao mais comum do catalogo e a unica que nunca
    envelhecia: um item podia dizer "coberto por teste unitario" e seguir verde
    depois de o codigo do proprio escopo mudar. O teste mexe no ARQUIVO do
    escopo, nao no item, porque e essa a direcao do defeito — a alegacao fica
    parada enquanto o codigo anda.
    """
    root = tmp_path / "repo"
    scope = root / "src" / "steamzero"
    scope.mkdir(parents=True)
    (root / "docs" / "status" / "items").mkdir(parents=True)
    shutil.copy(
        project_status.ROOT / "docs" / "status" / "project-item-v1.schema.json",
        root / "docs" / "status" / "project-item-v1.schema.json",
    )
    covered = scope / "coberto.py"
    covered.write_text("VALOR = 1\n", encoding="utf-8")

    item = {
        "schemaVersion": 1,
        "kind": "project-item",
        "id": "SZ-EXEMPLO",
        "title": "Exemplo",
        "domain": "governance",
        "implementation": "complete",
        "integration": "integrated",
        "verification": "unit",
        "operation": "ready",
        "distribution": "not-packaged",
        "scopePaths": ["src/steamzero/coberto.py"],
        "dependsOn": [],
        "knownGaps": [],
        "acceptanceCriteria": ["Existe."],
        "evidence": [
            {
                "kind": "test",
                "reference": "src/steamzero/coberto.py",
                "command": "pytest",
                "result": "passed",
            }
        ],
        "nextAction": "Nada a fazer.",
        "activeWorkstreams": [],
        "updatedAt": "2026-08-11",
        "notes": "Item sintetico do teste.",
    }
    item_path = root / "docs" / "status" / "items" / "exemplo.json"

    def write(digest: str) -> None:
        item_path.write_text(json.dumps({**item, "scopeDigest": digest}), encoding="utf-8")

    write(project_status.scope_digest(root, item["scopePaths"]))
    assert project_status.check_catalog(root, check_generated=False) == [], (
        "selo em dia nao pode acusar nada"
    )

    covered.write_text("VALOR = 2\n", encoding="utf-8")
    errors = project_status.check_catalog(root, check_generated=False)
    assert any("SZ-EXEMPLO" in error and "obsoleta" in error for error in errors), (
        f"escopo mudou e a evidencia unitaria continuou valida: {errors}"
    )


def test_coverage_view_flags_a_claim_without_approved_evidence() -> None:
    """A visao de cobertura existe para acusar alegacao sem lastro.

    O STATUS diz o estagio; nao diz se ha evidencia aprovada por tras dele. Um
    item pode declarar `verification: unit` com a lista de evidencias vazia e a
    tabela do STATUS fica igual a de um item provado.
    """
    catalog = project_status.load_catalog()
    rendered = project_status.render_coverage(catalog)

    # Nenhum item do catalogo real pode estar nessa situacao.
    marked = [
        line
        for line in rendered.splitlines()
        if line.startswith("| SZ-") and "sem evidencia aprovada" in line
    ]
    assert marked == [], f"item alega verificacao sem evidencia aprovada: {marked}"

    # E a coluna precisa mesmo acusar quando o caso aparece.
    sample = next(item for item in catalog.items.values() if not item["id"].startswith("SZ-AGG-"))
    broken = dict(catalog.items)
    broken[sample["id"]] = {**sample, "verification": "unit", "evidence": []}
    flagged = project_status.render_coverage(
        project_status.Catalog(items=broken, workstreams=catalog.workstreams)
    )
    row = next(line for line in flagged.splitlines() if line.startswith(f"| {sample['id']} |"))
    assert "sem evidencia aprovada" in row


def test_every_source_file_has_a_custodian_item() -> None:
    """Nenhum arquivo de `src/` fica sem item responsavel.

    `check_catalog` so olha `HEAD^..HEAD` mais a arvore de trabalho: pega o
    arquivo no commit em que ele muda e nunca mais. Foi assim que 321 arquivos
    de `src/` chegaram a harmonizacao a45 sem dono — cada um passou verde no
    proprio commit e saiu do campo de visao no seguinte.

    Este teste varre a arvore inteira toda vez, que e a unica forma de a lacuna
    nao voltar por acumulo.
    """
    catalog = project_status.load_catalog()
    owners = [scope for item in catalog.items.values() for scope in item["scopePaths"]]
    orphans = sorted(
        str(path.relative_to(project_status.ROOT))
        for path in (project_status.ROOT / "src").rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and not any(
            project_status._paths_overlap(str(path.relative_to(project_status.ROOT)), scope)
            for scope in owners
        )
    )
    assert orphans == [], (
        f"{len(orphans)} arquivo(s) de src/ sem item de status responsavel: {orphans[:10]}"
    )


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
