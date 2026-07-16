#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Gate: o pacote padrão não pode depender de runtime legado."""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

BANNED_MODULE_PREFIX = "phasezero"
BANNED_RUNTIME_LITERALS = (
    "/phasezero",
    "phasezero.service",
    "phasezero-admin",
    "phasezero-mode",
)


def check(root: Path) -> list[str]:
    violations: list[str] = []
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project.get("project", {}).get("dependencies", [])
    for dependency in dependencies:
        if BANNED_MODULE_PREFIX in str(dependency).lower():
            violations.append(f"dependência de runtime proibida: {dependency}")
    for entrypoint, target in project.get("project", {}).get("scripts", {}).items():
        if BANNED_MODULE_PREFIX in str(target).lower():
            violations.append(f"entrypoint padrão proibido: {entrypoint}={target}")
    wheel = (
        project.get("tool", {})
        .get("hatch", {})
        .get("build", {})
        .get("targets", {})
        .get("wheel", {})
    )
    if "src/steamzero/ports.py" in wheel.get("exclude", []):
        violations.append("wheel não pode excluir a camada neutra steamzero.ports")
    if not (root / "src" / "steamzero" / "ports.py").is_file():
        violations.append("camada neutra steamzero.ports ausente")

    source_root = root / "src" / "steamzero"
    for path in sorted(source_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                names = []
            for name in names:
                if name.lower().startswith(BANNED_MODULE_PREFIX):
                    violations.append(f"{path}: import proibido: {name}")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                lowered = node.value.lower()
                if any(literal in lowered for literal in BANNED_RUNTIME_LITERALS):
                    violations.append(f"{path}:{node.lineno}: literal de runtime legado proibido")
    return violations


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    violations = check(root)
    for violation in violations:
        print(violation)
    if violations:
        return 1
    print("independência de runtime: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
