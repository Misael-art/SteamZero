# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Regressões do contrato do GAP-G22:

- benchmark de 10 mil fixtures permanece como teste funcional obrigatório;
- o teto absoluto de tempo de parede foi removido;
- as asserções funcionais essenciais permanecem;
- o CI produz JUnit XML por versão e publica como artifact.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_FILE = PROJECT_ROOT / "tests/integration/test_library_organize.py"
CI_FILE = PROJECT_ROOT / ".github/workflows/ci.yml"


def _get_benchmark_ast() -> ast.FunctionDef:
    source = BENCHMARK_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "test_10k_fixture_apply_and_rollback_benchmark"
        ):
            return node
    raise AssertionError("test_10k_fixture_apply_and_rollback_benchmark não encontrado no AST")


def test_10k_benchmark_collected_normally() -> None:
    """O teste de 10 mil fixtures permanece como teste coletado."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(BENCHMARK_FILE),
            "--collect-only",
            "-q",
        ],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, f"coleta falhou:\nstdout={result.stdout}\nstderr={result.stderr}"
    assert "test_10k_fixture_apply_and_rollback_benchmark" in result.stdout, (
        "benchmark não apareceu na coleta"
    )


def _assert_lines(func: ast.FunctionDef) -> set[str]:
    lines = BENCHMARK_FILE.read_text(encoding="utf-8").splitlines()
    target: set[int] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Assert):
            target.add(node.lineno)
    return {lines[lineno - 1].strip() for lineno in target}


def test_10k_functional_assertions_present() -> None:
    """Todas as asserções funcionais essenciais permanecem no AST."""
    func = _get_benchmark_ast()
    src_set = _assert_lines(func)

    expected = {
        'assert result.status == "ok"',
        'assert sum(1 for _ in fs.iter_files(root / "nes")) == 10_000',
        'assert not (root / "incoming" / "game-00000.nes").exists()',
        "assert len(plan.actions) == 10_000",
        'assert rollback.status == "rolled-back"',
        'assert sum(1 for _ in fs.iter_files(root / "incoming")) == 10_000',
        'assert not (root / "nes" / "game-00000.nes").exists()',
        "assert not paths.staging_for(result.operation_id).exists()",
    }
    missing = expected - src_set
    assert not missing, (
        f"asserções funcionais ausentes: {sorted(missing)}\npresentes: {sorted(src_set)}"
    )


def test_no_wall_clock_assertion() -> None:
    """Não existe comparação de wall-clock com teto absoluto no AST."""
    func = _get_benchmark_ast()
    for node in ast.walk(func):
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare):
            if isinstance(node.test.left, ast.Name) and node.test.left.id in (
                "elapsed",
                "started",
                "duration",
            ):
                raise AssertionError(
                    f"assert de tempo de parede encontrado na linha {node.lineno}: {ast.dump(node)}"
                )
            if isinstance(node.test.left, ast.Call):
                call = node.test.left
                if isinstance(call.func, ast.Attribute) and call.func.attr == "monotonic":
                    raise AssertionError(f"time.monotonic() encontrado na linha {node.lineno}")


def test_ci_has_durations_flag() -> None:
    """O workflow de CI contém ``--durations=20``."""
    text = CI_FILE.read_text(encoding="utf-8")
    assert "--durations=20" in text, "--durations=20 não encontrado no CI YAML"


def test_ci_has_junit_xml_per_version() -> None:
    """O workflow de CI produz JUnit XML por versão Python."""
    text = CI_FILE.read_text(encoding="utf-8")
    assert "--junitxml=build/test-results-${{ matrix.python-version }}.xml" in text, (
        "junitxml por versão não encontrado no CI YAML"
    )


def test_ci_publishes_junit_artifact() -> None:
    """O workflow publica o JUnit XML como artifact com ``if: always()``."""
    text = CI_FILE.read_text(encoding="utf-8")
    assert "Publicar resultados JUnit" in text
    assert "if: always()" in text
    assert "test-results-${{ matrix.python-version }}" in text
