#!/usr/bin/env python3
"""Valida e renderiza o estado atual do projeto SteamZero.

Os arquivos em ``docs/status/items`` sao a fonte de verdade para estagio de
capacidade. Os documentos Markdown gerados sao visoes; WORKLOG e diagnosticos
permanecem evidencias historicas, nunca um painel de estado concorrente.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
STATUS_ROOT = ROOT / "docs" / "status"
ITEMS_DIR = STATUS_ROOT / "items"
WORKSTREAMS_DIR = STATUS_ROOT / "workstreams"
SCHEMA_PATH = STATUS_ROOT / "project-item-v1.schema.json"
GENERATED_STATUS = ROOT / "docs" / "STATUS.md"
GENERATED_ACTIVE = ROOT / "docs" / "ACTIVE-WORK.md"


@dataclass(frozen=True)
class Catalog:
    items: dict[str, dict[str, Any]]
    workstreams: dict[str, dict[str, Any]]


def _read_json(path: Path, *, root: Path = ROOT) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path.relative_to(root)}: JSON invalido: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"{path.relative_to(root)}: raiz precisa ser objeto JSON")
    return loaded


def _validator(root: Path) -> Draft202012Validator:
    schema_path = root / "docs" / "status" / "project-item-v1.schema.json"
    return Draft202012Validator(_read_json(schema_path, root=root), format_checker=FormatChecker())


def _json_paths(directory: Path) -> list[Path]:
    return sorted(path for path in directory.glob("*.json") if path.is_file())


def load_catalog(root: Path = ROOT) -> Catalog:
    items_dir = root / "docs" / "status" / "items"
    workstreams_dir = root / "docs" / "status" / "workstreams"
    validator = _validator(root)
    items: dict[str, dict[str, Any]] = {}
    workstreams: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for path in [*_json_paths(items_dir), *_json_paths(workstreams_dir)]:
        try:
            entry = _read_json(path, root=root)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        for error in sorted(validator.iter_errors(entry), key=str):
            pointer = "/".join(str(part) for part in error.path) or "<raiz>"
            errors.append(f"{path.relative_to(root)}:{pointer}: {error.message}")
        identifier = entry.get("id")
        if not isinstance(identifier, str):
            continue
        target = items if entry.get("kind") == "project-item" else workstreams
        if identifier in target:
            errors.append(f"{path.relative_to(root)}: id duplicado {identifier}")
        target[identifier] = entry
    if errors:
        raise ValueError("\n".join(errors))
    return Catalog(items=items, workstreams=workstreams)


def _iter_scope_files(root: Path, scope_paths: Iterable[str]) -> Iterable[Path]:
    files: set[Path] = set()
    for raw_path in scope_paths:
        candidate = (root / raw_path).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"scope fora do repositorio: {raw_path}") from exc
        if not candidate.exists():
            raise ValueError(f"scope inexistente: {raw_path}")
        if candidate.is_file():
            files.add(candidate)
            continue
        for child in candidate.rglob("*"):
            if child.is_file() and "__pycache__" not in child.parts and child.suffix != ".pyc":
                files.add(child)
    return sorted(files)


def scope_digest(root: Path, scope_paths: Iterable[str]) -> str:
    """Digest funcional do escopo.

    ``docs/WORKLOG.md`` é append-only histórico e **não** entra no digest: um
    fechamento de sessão legítimo não pode invalidar evidência de governança.
    O gate :func:`check_worklog_append_only` protege o conteúdo anterior.
    """
    digest = hashlib.sha256()
    for path in _iter_scope_files(root, scope_paths):
        relative = path.relative_to(root).as_posix()
        if relative == "docs/WORKLOG.md":
            continue
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def check_worklog_append_only(root: Path = ROOT) -> list[str]:
    """Reprova reescrita/remoção de conteúdo já commitado em ``docs/WORKLOG.md``.

    Só o acréscimo no final é permitido. Compara o blob em ``HEAD`` com o
    conteúdo atual (working tree se sujo; caso contrário o próprio HEAD).
    """
    worklog = root / "docs" / "WORKLOG.md"
    if not worklog.is_file():
        return []
    result = subprocess.run(
        ["git", "show", "HEAD:docs/WORKLOG.md"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        # Arquivo ainda não versionado: qualquer conteúdo inicial é válido.
        return []
    committed = result.stdout
    try:
        current = worklog.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"docs/WORKLOG.md: ilegível: {exc}"]
    if current == committed:
        return []
    if current.startswith(committed):
        return []
    return [
        "docs/WORKLOG.md: reescrita ou remoção de conteúdo histórico reprovada; "
        "somente acréscimo no final é permitido (AGENTS.md §2)"
    ]


def _derived_stage(item: dict[str, Any]) -> str:
    if item["operation"] == "blocked":
        return "blocked"
    verification = item["verification"]
    if verification == "hw":
        return "verified-hw"
    if verification == "vm":
        return "verified-vm"
    if verification == "dev":
        return "verified-dev"
    if item["implementation"] == "complete":
        return "implemented"
    if item["implementation"] == "partial":
        return "partial"
    return "planned"


def _paths_overlap(first: str, second: str) -> bool:
    left = first.rstrip("/")
    right = second.rstrip("/")
    return left == right or left.startswith(f"{right}/") or right.startswith(f"{left}/")


def _changed_paths(root: Path) -> set[str]:
    commands = [
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "diff", "--name-only", "HEAD^", "HEAD"],
    ]
    changed: set[str] = set()
    for command in commands:
        result = subprocess.run(command, cwd=root, text=True, capture_output=True, check=False)
        if result.returncode == 0:
            changed.update(line for line in result.stdout.splitlines() if line)
    return changed


def _is_generated_or_status(path: str) -> bool:
    return path in {"docs/STATUS.md", "docs/ACTIVE-WORK.md", "docs/WORKLOG.md"} or path.startswith(
        "docs/status/"
    )


def check_catalog(root: Path = ROOT, *, check_generated: bool = True) -> list[str]:
    try:
        catalog = load_catalog(root)
    except ValueError as exc:
        return str(exc).splitlines()
    errors: list[str] = []
    errors.extend(check_worklog_append_only(root))
    for identifier, item in catalog.items.items():
        for dependency in item["dependsOn"]:
            if dependency not in catalog.items:
                errors.append(f"{identifier}: dependencia inexistente {dependency}")
        for workstream_id in item["activeWorkstreams"]:
            workstream = catalog.workstreams.get(workstream_id)
            if workstream is None:
                errors.append(f"{identifier}: workstream inexistente {workstream_id}")
            elif workstream["item"] != identifier:
                errors.append(
                    f"{identifier}: workstream {workstream_id} pertence a {workstream['item']}"
                )
        # `unit` entra junto de dev/vm/hw. Sem isto, a verificacao mais COMUM do
        # catalogo era tambem a unica que nao envelhecia: um item podia declarar
        # "coberto por teste unitario" e continuar verde depois de o proprio
        # codigo do escopo mudar, porque nada amarrava a alegacao ao conteudo.
        if item["verification"] in {"unit", "dev", "vm", "hw"}:
            if not any(entry["result"] == "passed" for entry in item["evidence"]):
                errors.append(
                    f"{identifier}: verificacao {item['verification']} exige evidencia aprovada"
                )
            expected = item.get("scopeDigest")
            if not expected:
                errors.append(f"{identifier}: verificacao exige scopeDigest")
            else:
                try:
                    actual = scope_digest(root, item["scopePaths"])
                except ValueError as exc:
                    errors.append(f"{identifier}: {exc}")
                else:
                    if actual != expected:
                        errors.append(
                            f"{identifier}: evidencia obsoleta; scopeDigest esperado "
                            f"{expected}, atual {actual}"
                        )
        if item["implementation"] == "complete" and item["verification"] == "none":
            errors.append(f"{identifier}: implementacao completa sem verificacao")
        if item["integration"] == "released" and item["distribution"] == "not-packaged":
            errors.append(f"{identifier}: item released sem distribuicao")
        for entry in item["evidence"]:
            if not (root / entry["reference"]).exists():
                errors.append(f"{identifier}: evidencia ausente {entry['reference']}")
    active = [entry for entry in catalog.workstreams.values() if entry["state"] == "active"]
    for index, first in enumerate(active):
        if first["item"] not in catalog.items:
            errors.append(f"{first['id']}: item inexistente {first['item']}")
        for second in active[index + 1 :]:
            for left in first["exclusivePaths"]:
                for right in second["exclusivePaths"]:
                    if _paths_overlap(left, right):
                        errors.append(
                            f"workstreams {first['id']} e {second['id']} disputam {left} / {right}"
                        )
    scope_owners = [
        (identifier, scope)
        for identifier, item in catalog.items.items()
        for scope in item["scopePaths"]
    ]
    for changed in _changed_paths(root):
        if _is_generated_or_status(changed):
            continue
        if not any(_paths_overlap(changed, scope) for _identifier, scope in scope_owners):
            errors.append(f"arquivo alterado sem item de status responsavel: {changed}")
    if check_generated:
        expected_status, expected_active = render_catalog(catalog)
        actual_status = (
            (root / "docs" / "STATUS.md").read_text(encoding="utf-8")
            if (root / "docs" / "STATUS.md").exists()
            else ""
        )
        actual_active = (
            (root / "docs" / "ACTIVE-WORK.md").read_text(encoding="utf-8")
            if (root / "docs" / "ACTIVE-WORK.md").exists()
            else ""
        )
        if actual_status != expected_status:
            errors.append(
                "docs/STATUS.md esta desatualizado; execute tools/project_status.py render --write"
            )
        if actual_active != expected_active:
            errors.append(
                "docs/ACTIVE-WORK.md esta desatualizado; execute "
                "tools/project_status.py render --write"
            )
    return errors


def render_catalog(catalog: Catalog) -> tuple[str, str]:
    # `operation` e `distribution` sao colunas, nao rodape: sem elas a tabela
    # deixava um item aparecer como pronto por implementacao e verificacao sem
    # dizer se ele opera no host ou se sequer chegou a ser empacotado — que e
    # justamente a diferenca entre codigo escrito e capacidade entregue.
    item_rows = [
        "| ID | Capacidade | Estagio | Implementacao | Integracao | Verificacao | "
        "Operacao | Distribuicao | Proxima acao |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for identifier, item in sorted(catalog.items.items()):
        item_rows.append(
            "| {id} | {title} | {stage} | {implementation} | {integration} | "
            "{verification} | {operation} | {distribution} | {next_action} |".format(
                id=identifier,
                title=item["title"],
                stage=_derived_stage(item),
                implementation=item["implementation"],
                integration=item["integration"],
                verification=item["verification"],
                operation=item["operation"],
                distribution=item["distribution"],
                next_action=item["nextAction"],
            )
        )
    status = "\n".join(
        [
            "# STATUS — SteamZero",
            "",
            "<!-- Gerado por tools/project_status.py; nao editar manualmente. -->",
            "",
            "Esta e a visao atual do projeto. A fonte de verdade sao os arquivos em "
            "`docs/status/items/`; WORKLOG, diagnosticos e relatorios sao evidencias "
            "historicas.",
            "",
            *item_rows,
            "",
            "Consulte `docs/ACTIVE-WORK.md` antes de criar uma branch ou editar arquivos "
            "compartilhados.",
            "",
        ]
    )
    active_rows = [
        "| Workstream | Item | Branch | Base | Owner | Escopo exclusivo | Proxima acao |",
        "|---|---|---|---|---|---|---|",
    ]
    for identifier, workstream in sorted(catalog.workstreams.items()):
        if workstream["state"] != "active":
            continue
        active_rows.append(
            "| {id} | {item} | `{branch}` | `{base}` | {owner} | {scope} | {next_action} |".format(
                id=identifier,
                item=workstream["item"],
                branch=workstream["branch"],
                base=workstream["baseRef"],
                owner=workstream["owner"],
                scope="<br>".join(workstream["exclusivePaths"]) or "—",
                next_action=workstream["nextAction"],
            )
        )
    active = "\n".join(
        [
            "# ACTIVE-WORK — SteamZero",
            "",
            "<!-- Gerado por tools/project_status.py; nao editar manualmente. -->",
            "",
            "Somente workstreams `active` aparecem aqui. O coordenador deve criar ou "
            "atualizar o registro antes de delegar trabalho.",
            "",
            *active_rows,
            "",
        ]
    )
    return status, active


def _item_by_id(catalog: Catalog, identifier: str) -> dict[str, Any]:
    try:
        return catalog.items[identifier]
    except KeyError as exc:
        raise ValueError(f"item desconhecido: {identifier}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "render", "digest"))
    parser.add_argument("--write", action="store_true", help="grava as visoes Markdown geradas")
    parser.add_argument("--item", help="id do item para o comando digest")
    args = parser.parse_args(argv)
    if args.command == "check":
        errors = check_catalog()
        if errors:
            print("STATUS-CHECK: FALHOU", file=sys.stderr)
            print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
            return 1
        print("STATUS-CHECK: OK")
        return 0
    catalog = load_catalog()
    if args.command == "digest":
        if not args.item:
            parser.error("digest exige --item SZ-...")
        print(scope_digest(ROOT, _item_by_id(catalog, args.item)["scopePaths"]))
        return 0
    status, active = render_catalog(catalog)
    if args.write:
        GENERATED_STATUS.write_text(status, encoding="utf-8")
        GENERATED_ACTIVE.write_text(active, encoding="utf-8")
    else:
        print(status, end="")
        print(active, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
