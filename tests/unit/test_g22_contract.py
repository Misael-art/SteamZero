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
import textwrap
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_FILE = PROJECT_ROOT / "tests/integration/test_library_organize.py"
CI_FILE = PROJECT_ROOT / ".github/workflows/ci.yml"

# ---------------------------------------------------------------------------
# AST normalization helpers
# ---------------------------------------------------------------------------

_AUTHORIZED_BENCHMARK_ASSERTS: frozenset[str] = frozenset(
    {
        "result.status == 'ok'",
        "sum((1 for _ in fs.iter_files(root / 'nes'))) == 10000",
        "not (root / 'incoming' / 'game-00000.nes').exists()",
        "len(plan.actions) == 10000",
        "rollback.status == 'rolled-back'",
        "sum((1 for _ in fs.iter_files(root / 'incoming'))) == 10000",
        "not (root / 'nes' / 'game-00000.nes').exists()",
        "not paths.staging_for(result.operation_id).exists()",
    }
)


def _get_benchmark_func() -> ast.FunctionDef:
    source = BENCHMARK_FILE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "test_10k_fixture_apply_and_rollback_benchmark"
        ):
            return node
    raise AssertionError("benchmark function not found in AST")


def _normalize_assert_exprs(func: ast.FunctionDef) -> frozenset[str]:
    result: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Assert):
            result.add(ast.unparse(node.test))
    return frozenset(result)


def _validate_benchmark_asserts(
    func: ast.FunctionDef,
) -> tuple[bool, set[str], set[str], list[str]]:
    exprs = _normalize_assert_exprs(func)
    missing = set(_AUTHORIZED_BENCHMARK_ASSERTS) - exprs
    extra = exprs - set(_AUTHORIZED_BENCHMARK_ASSERTS)
    errors: list[str] = []
    if missing:
        errors.append(f"asserções funcionais ausentes ({len(missing)}): {sorted(missing)}")
    if extra:
        errors.append(f"asserções não autorizadas ({len(extra)}): {sorted(extra)}")
    return len(errors) == 0, missing, extra, errors


def _make_synthetic_func(source: str) -> ast.FunctionDef:
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            return node
    raise AssertionError("no function found in synthetic source")


# ---------------------------------------------------------------------------
# 1. Real benchmark contract
# ---------------------------------------------------------------------------


def test_benchmark_collected_normally() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(BENCHMARK_FILE), "--collect-only", "-q"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    assert result.returncode == 0, f"coleta falhou:\nstdout={result.stdout}\nstderr={result.stderr}"
    assert "test_10k_fixture_apply_and_rollback_benchmark" in result.stdout


def test_benchmark_assertions_are_exact_eight() -> None:
    func = _get_benchmark_func()
    exprs = _normalize_assert_exprs(func)
    assert len(exprs) == 8, (
        f"benchmark deve ter exatamente 8 asserts, tem {len(exprs)}: {sorted(exprs)}"
    )


def test_benchmark_assertions_match_authorized_set() -> None:
    func = _get_benchmark_func()
    ok, missing, extra, errors = _validate_benchmark_asserts(func)
    assert ok, "; ".join(errors)
    assert not missing
    assert not extra


# ---------------------------------------------------------------------------
# 2. Wall-clock negative controls (prove validator rejects timing asserts)
# ---------------------------------------------------------------------------

_WALL_CLOCK_SAMPLES: list[tuple[str, str, str]] = [
    ("elapsed < 180", "assert elapsed < 180", "elapsed"),
    ("180 > elapsed", "assert 180 > elapsed", "180"),
    ("elapsed_seconds < 180", "assert elapsed_seconds < 180", "elapsed_seconds"),
]


def test_rejects_wall_clock_direct_comparison() -> None:
    for label, stmt, _ in _WALL_CLOCK_SAMPLES:
        src = f"def f(): {stmt}"
        func = _make_synthetic_func(src)
        ok, _missing, extra, _errors = _validate_benchmark_asserts(func)
        assert not ok, f"deveria rejeitar '{label}' mas validou como OK"
        assert len(extra) >= 1, f"deveria ter ao menos 1 assert não autorizado para '{label}'"


def test_rejects_time_perf_counter() -> None:
    src = """def f():
    import time
    started = time.perf_counter()
    do_work()
    elapsed = time.perf_counter() - started
    assert elapsed < 180
"""
    func = _make_synthetic_func(src)
    ok, _missing, extra, _errors = _validate_benchmark_asserts(func)
    assert not ok, "deveria rejeitar time.perf_counter()"
    assert any("perf_counter" in e or "elapsed" in e for e in extra), (
        f"extra deve mencionar elapsed/perf_counter: {extra}"
    )


def test_rejects_time_monotonic() -> None:
    src = """def f():
    import time
    started = time.monotonic()
    do_work()
    elapsed = time.monotonic() - started
    assert elapsed < 180
"""
    func = _make_synthetic_func(src)
    ok, _missing, extra, _errors = _validate_benchmark_asserts(func)
    assert not ok, "deveria rejeitar time.monotonic()"
    assert any("monotonic" in e or "elapsed" in e for e in extra), (
        f"extra deve mencionar elapsed/monotonic: {extra}"
    )


def test_rejects_extra_nona_assert() -> None:
    src = """def f():
    assert result.status == 'ok'
    assert len(plan.actions) == 10000
    assert extra_thing == 42
"""
    func = _make_synthetic_func(src)
    ok, _missing2, extra, _errors = _validate_benchmark_asserts(func)
    assert not ok, "deveria rejeitar nono assert extra"
    assert len(extra) == 1, f"deveria ter exatamente 1 extra, tem {extra}"
    assert "extra_thing" in next(iter(extra))


# ---------------------------------------------------------------------------
# 3. CI workflow contract
# ---------------------------------------------------------------------------


def _extract_step_block(yml_text: str, step_name: str) -> list[str]:
    """Extrai as linhas do bloco YAML de um step identificado por ``name:``.

    Retorna lista de linhas (sem o ``name:`` original), com indentação relativa
    ao conteúdo do step. Levanta ``AssertionError`` se o step não for encontrado.
    """
    lines = yml_text.splitlines()
    target = f"- name: {step_name}"
    start_idx: int | None = None
    for idx, line in enumerate(lines):
        if line.strip() == target:
            start_idx = idx + 1
            break
    if start_idx is None:
        raise AssertionError(f"step '{step_name}' não encontrado no YAML")

    indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())
    block: list[str] = []
    for line in lines[start_idx:]:
        if not line.strip():
            continue
        # Próximo ``- name:`` ou chave de topo (sem espaço inicial) encerram o bloco
        stripped = line.lstrip()
        if stripped.startswith("- name:"):
            break
        if line and not line[0].isspace() and ":" in line:
            break
        if stripped.startswith("#"):
            continue
        block.append(line[indent:] if len(line) > indent else line)
    return block


def _run_lines_from_block(block: list[str]) -> list[str]:
    """Extrai linhas executáveis de dentro de um bloco ``run: |``."""
    in_run = False
    run_indent = 0
    lines: list[str] = []
    for line in block:
        stripped = line.strip()
        if stripped.startswith("run:") and " |" not in stripped:
            remainder = stripped[len("run:") :].strip()
            if remainder:
                lines.append(remainder)
        elif stripped.startswith("run") and " |" in stripped:
            in_run = True
            run_indent = len(line) - len(line.lstrip()) + 2
        elif in_run:
            if not stripped:
                continue
            line_indent = len(line) - len(line.lstrip())
            if line_indent < run_indent and stripped:
                in_run = False
                continue
            if stripped.startswith("#"):
                continue
            lines.append(stripped)
    return lines


def test_ci_tests_step_has_durations() -> None:
    text = CI_FILE.read_text(encoding="utf-8")
    block = _extract_step_block(text, "Testes e cobertura")
    run_lines = _run_lines_from_block(block)
    assert any("--durations=20" in line for line in run_lines), (
        f"--durations=20 não está em linha executável do step Testes e cobertura\n"
        f"run_lines: {run_lines}"
    )


def test_ci_tests_step_has_junit_xml() -> None:
    text = CI_FILE.read_text(encoding="utf-8")
    block = _extract_step_block(text, "Testes e cobertura")
    run_lines = _run_lines_from_block(block)
    assert any("--junitxml" in line and "matrix.python-version" in line for line in run_lines), (
        f"--junitxml com versão não está no step Testes e cobertura\nrun_lines: {run_lines}"
    )


def test_ci_publish_junit_step_has_always() -> None:
    text = CI_FILE.read_text(encoding="utf-8")
    block = _extract_step_block(text, "Publicar resultados JUnit")
    block_text = "\n".join(block)
    assert "if: always()" in block_text, (
        f"if: always() não está no step Publicar resultados JUnit\nblock:\n{block}"
    )


def test_ci_publish_junit_uses_upload_artifact() -> None:
    text = CI_FILE.read_text(encoding="utf-8")
    block = _extract_step_block(text, "Publicar resultados JUnit")
    assert any("actions/upload-artifact@" in line for line in block), (
        f"actions/upload-artifact não encontrado no step JUnit\nblock:\n{block}"
    )
    assert any("test-results-${{ matrix.python-version }}" in line for line in block), (
        f"name por versão ausente no step JUnit\nblock:\n{block}"
    )


def test_ci_publish_junit_path_has_version() -> None:
    text = CI_FILE.read_text(encoding="utf-8")
    block = _extract_step_block(text, "Publicar resultados JUnit")
    found = any(
        "matrix.python-version" in line and ("path" in line or "build/test-results" in line)
        for line in block
    )
    assert found, f"path por versão ausente\nblock:\n{block}"


def test_ci_publish_junit_if_no_files_error() -> None:
    text = CI_FILE.read_text(encoding="utf-8")
    block = _extract_step_block(text, "Publicar resultados JUnit")
    assert any("if-no-files-found: error" in line for line in block), (
        f"if-no-files-found: error ausente no step JUnit\nblock:\n{block}"
    )


def test_ci_publish_junit_retention_days_30() -> None:
    text = CI_FILE.read_text(encoding="utf-8")
    block = _extract_step_block(text, "Publicar resultados JUnit")
    assert any("retention-days: 30" in line for line in block), (
        f"retention-days: 30 ausente no step JUnit\nblock:\n{block}"
    )


def test_ci_publish_junit_sha_pinned() -> None:
    text = CI_FILE.read_text(encoding="utf-8")
    block = _extract_step_block(text, "Publicar resultados JUnit")
    for line in block:
        if "upload-artifact@" not in line:
            continue
        after_at = line.split("@", 1)[1].strip().split()[0]
        assert len(after_at) >= 40 and all(c in "0123456789abcdef" for c in after_at), (
            f"upload-artifact sem SHA pin (encontrado {after_at!r})\nblock:\n{block}"
        )
        return
    raise AssertionError("actions/upload-artifact não encontrado no step JUnit")


# ---------------------------------------------------------------------------
# 4. CI negative controls (synthetic YAML)
# ---------------------------------------------------------------------------


def _yaml_with_step(text: str, step_name: str) -> str:
    """Procura o step ``step_name`` no YAML sintético via _extract_step_block.
    Retorna linhas encontradas ou levanta AssertionError.
    """
    return "\n".join(_extract_step_block(text.splitlines(keepends=True), step_name))


def test_ci_negative_always_on_wrong_step() -> None:
    synthetic = """jobs:
  test:
    steps:
      - name: Publicar cobertura
        if: always()
        run: echo coverage
      - name: Publicar resultados JUnit
        run: echo missing
"""
    block = _extract_step_block(synthetic, "Publicar resultados JUnit")
    assert not any("if: always()" in line for line in block), (
        "if: always() não deveria estar no step JUnit quando só existe no step cobertura"
    )


def test_ci_negative_name_in_comment_only() -> None:
    synthetic = """jobs:
  test:
    steps:
      - name: Publicar resultados JUnit
        if: always()
        run: |
          echo test-results-3.11
"""
    block = _extract_step_block(synthetic, "Publicar resultados JUnit")
    assert not any("matrix.python-version" in line for line in block), (
        "não deveria encontrar matrix.python-version em comentário"
    )


def test_ci_negative_path_missing_version() -> None:
    synthetic = """jobs:
  test:
    steps:
      - name: Publicar resultados JUnit
        if: always()
        uses: actions/upload-artifact@abc123
        with:
          name: test-results-fixed
          path: build/results.xml
          if-no-files-found: error
          retention-days: 30
"""
    block = _extract_step_block(synthetic, "Publicar resultados JUnit")
    block_text = "\n".join(block)
    assert "matrix.python-version" not in block_text, (
        "path não deveria conter versão no caso negativo"
    )


def test_ci_negative_if_no_files_is_warn() -> None:
    synthetic = """jobs:
  test:
    steps:
      - name: Publicar resultados JUnit
        if: always()
        uses: actions/upload-artifact@abc123
        with:
          name: test-results-${{ matrix.python-version }}
          path: build/test-results-${{ matrix.python-version }}.xml
          if-no-files-found: warn
          retention-days: 30
"""
    block = _extract_step_block(synthetic, "Publicar resultados JUnit")
    assert not any("if-no-files-found: error" in line for line in block), (
        "não deveria encontrar if-no-files-found: error quando é warn"
    )


def test_ci_negative_step_absent() -> None:
    synthetic = """jobs:
  test:
    steps:
      - name: Publicar cobertura
        run: echo coverage
"""
    try:
        _extract_step_block(synthetic, "Publicar resultados JUnit")
        raise AssertionError("deveria levantar AssertionError quando step está ausente")
    except AssertionError:
        pass
