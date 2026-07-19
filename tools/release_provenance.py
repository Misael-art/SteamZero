#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verifica wheels SteamZero e emite proveniência local determinística."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from email.parser import Parser
from pathlib import Path
from typing import Any

_COMMIT_RE = re.compile(r"^[a-f0-9]{40}$")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _wheel_identity(path: Path) -> tuple[str, str]:
    with zipfile.ZipFile(path) as archive:
        metadata_files = [
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_files) != 1:
            raise ValueError("wheel deve conter exatamente um METADATA")
        metadata = Parser().parsestr(archive.read(metadata_files[0]).decode("utf-8"))
        names = set(archive.namelist())
    project = metadata.get("Name", "").strip().lower()
    version = metadata.get("Version", "").strip()
    if project != "steamzero" or not version:
        raise ValueError("METADATA não identifica um wheel SteamZero versionado")
    if "steamzero/ports.py" not in names:
        raise ValueError("wheel não contém a camada canônica steamzero.ports")
    return project, version


def _single_path(values: list[Path], label: str) -> Path:
    if len(values) != 1:
        raise ValueError(f"esperado exatamente um {label}")
    return values[0].resolve(strict=True)


def _verify_clean_source(expected_commit: str) -> None:
    if not _COMMIT_RE.fullmatch(expected_commit):
        raise ValueError("commit precisa ser um SHA-1 completo em minúsculas")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    ).stdout.strip()
    if head != expected_commit:
        raise ValueError(f"commit informado {expected_commit} diverge do HEAD {head}")
    for argv in (["git", "diff", "--quiet", "HEAD", "--"], ["git", "diff", "--cached", "--quiet"]):
        result = subprocess.run(argv, timeout=10, check=False)
        if result.returncode != 0:
            raise ValueError("árvore de origem possui alterações rastreadas")


def _create(args: argparse.Namespace) -> dict[str, Any]:
    wheel = _single_path(args.wheel, "wheel")
    sbom = args.sbom.resolve(strict=True)
    project, version = _wheel_identity(wheel)
    _verify_clean_source(args.commit)
    return {
        "schemaVersion": 1,
        "subject": {
            "name": wheel.name,
            "sha256": _sha256(wheel),
            "project": project,
            "version": version,
        },
        "source": {
            "commit": args.commit,
            "repository": args.repository,
            "ref": args.ref,
        },
        "build": {
            "builder": "github-actions",
            "runId": args.run_id,
            "sourceTreeState": "clean",
            "pythonRequires": ">=3.11",
        },
        "materials": {
            "sbom": {"name": sbom.name, "sha256": _sha256(sbom)},
            "runtimeLock": {
                "name": "requirements-runtime.lock",
                "sha256": _sha256(Path("requirements-runtime.lock")),
            },
            "pyproject": {"name": "pyproject.toml", "sha256": _sha256(Path("pyproject.toml"))},
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)
    verify = subparsers.add_parser("verify-wheel")
    verify.add_argument("--wheel", type=Path, action="append", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--wheel", type=Path, action="append", required=True)
    create.add_argument("--sbom", type=Path, required=True)
    create.add_argument("--commit", required=True)
    create.add_argument("--repository", required=True)
    create.add_argument("--ref", required=True)
    create.add_argument("--run-id", required=True)
    create.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.action == "verify-wheel":
            wheel = _single_path(args.wheel, "wheel")
            project, version = _wheel_identity(wheel)
            result: dict[str, Any] = {
                "project": project,
                "version": version,
                "sha256": _sha256(wheel),
            }
        else:
            result = _create(args)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
    except (OSError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
        print(f"erro de proveniência: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
