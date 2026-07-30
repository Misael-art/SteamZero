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
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_FILE = PROJECT_ROOT / "tests/integration/test_library_organize.py"
CI_FILE = PROJECT_ROOT / ".github/workflows/ci.yml"

# ---------------------------------------------------------------------------
# AST normalization helpers
# ---------------------------------------------------------------------------

_AUTHORIZED_BENCHMARK_ASSERTS: Counter[str] = Counter(
    {
        "result.status == 'ok'": 1,
        "sum((1 for _ in fs.iter_files(root / 'nes'))) == 10000": 1,
        "not (root / 'incoming' / 'game-00000.nes').exists()": 1,
        "len(plan.actions) == 10000": 1,
        "rollback.status == 'rolled-back'": 1,
        "sum((1 for _ in fs.iter_files(root / 'incoming'))) == 10000": 1,
        "not (root / 'nes' / 'game-00000.nes').exists()": 1,
        "not paths.staging_for(result.operation_id).exists()": 1,
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


def _normalize_assert_exprs(func: ast.FunctionDef) -> Counter[str]:
    result: list[str] = []
    for node in ast.walk(func):
        if isinstance(node, ast.Assert):
            result.append(ast.unparse(node.test))
    return Counter(result)


def _validate_benchmark_asserts(
    func: ast.FunctionDef,
) -> tuple[bool, set[str], set[str], list[str]]:
    exprs = _normalize_assert_exprs(func)
    missing: set[str] = set()
    extra: set[str] = set()
    errors: list[str] = []
    total = sum(exprs.values())
    if total != 8:
        errors.append(f"total de asserts é {total}, esperado 8")
    for expr, count in _AUTHORIZED_BENCHMARK_ASSERTS.items():
        if exprs.get(expr, 0) < count:
            missing.add(expr)
    for expr, count in exprs.items():
        auth_count = _AUTHORIZED_BENCHMARK_ASSERTS.get(expr, 0)
        if count > auth_count:
            if auth_count == 0:
                extra.add(expr)
            else:
                errors.append(f"assert duplicado: {expr} (count={count})")
    if missing:
        errors.append(f"asserções ausentes ({len(missing)}): {sorted(missing)}")
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
    assert sum(exprs.values()) == 8, (
        f"benchmark deve ter exatamente 8 asserts, tem {sum(exprs.values())}: {dict(exprs)}"
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


def test_rejects_duplicate_assert() -> None:
    src = """def f():
    assert result.status == 'ok'
    assert sum((1 for _ in fs.iter_files(root / 'nes'))) == 10000
    assert not (root / 'incoming' / 'game-00000.nes').exists()
    assert len(plan.actions) == 10000
    assert rollback.status == 'rolled-back'
    assert sum((1 for _ in fs.iter_files(root / 'incoming'))) == 10000
    assert not (root / 'nes' / 'game-00000.nes').exists()
    assert not paths.staging_for(result.operation_id).exists()
    assert rollback.status == 'rolled-back'
"""
    func = _make_synthetic_func(src)
    ok, _missing, _extra, errors = _validate_benchmark_asserts(func)
    assert not ok, "deveria rejeitar assert duplicado"
    assert any("duplicado" in e for e in errors), f"erro 'duplicado' não encontrado: {errors}"


# ---------------------------------------------------------------------------
# 3. CI workflow helpers
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


def _validate_ci_contract(yml_text: str) -> list[str]:
    """Valida contrato do workflow CI.

    Retorna lista de erros (vazia se tudo ok).
    """
    errors: list[str] = []

    lines = yml_text.splitlines()
    step_names: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- name:"):
            step_names.append(stripped[len("- name:") :].strip())

    for required in ["Testes e cobertura", "Publicar resultados JUnit"]:
        count = step_names.count(required)
        if count == 0:
            errors.append(f"step obrigatório ausente: {required}")
        elif count > 1:
            errors.append(f"step duplicado: {required}")

    try:
        coverage_block = _extract_step_block(yml_text, "Testes e cobertura")
        run_lines = _run_lines_from_block(coverage_block)
        non_echo_lines = [line for line in run_lines if not line.strip().startswith("echo")]
        if not any("--durations=20" in line for line in non_echo_lines):
            errors.append("--durations=20 ausente no step Testes e cobertura")
        if not any(
            "--junitxml" in line and "matrix.python-version" in line for line in non_echo_lines
        ):
            errors.append("--junitxml por versão ausente no step Testes e cobertura")
    except AssertionError as e:
        errors.append(str(e))

    try:
        junit_block = _extract_step_block(yml_text, "Publicar resultados JUnit")
        block_text = "\n".join(junit_block)
        if "if: always()" not in block_text:
            errors.append("if: always() ausente no step Publicar resultados JUnit")
        found_upload = False
        for line in junit_block:
            if "actions/upload-artifact@" not in line:
                continue
            found_upload = True
            after_at = line.split("@", 1)[1].strip().split()[0]
            if not (len(after_at) == 40 and all(c in "0123456789abcdef" for c in after_at)):
                errors.append(
                    f"upload-artifact sem SHA hex de 40 caracteres no step "
                    f"Publicar resultados JUnit: {after_at!r}"
                )
        if not found_upload:
            errors.append("actions/upload-artifact ausente no step Publicar resultados JUnit")
        if not any("test-results-${{ matrix.python-version }}" in line for line in junit_block):
            errors.append("name por versão ausente no step Publicar resultados JUnit")
        if not any(
            "matrix.python-version" in line and ("path" in line or "build/test-results" in line)
            for line in junit_block
        ):
            errors.append("path por versão ausente no step Publicar resultados JUnit")
        if not any("if-no-files-found: error" in line for line in junit_block):
            errors.append("if-no-files-found: error ausente no step Publicar resultados JUnit")
        if not any("retention-days: 30" in line for line in junit_block):
            errors.append("retention-days: 30 ausente no step Publicar resultados JUnit")
    except AssertionError as e:
        errors.append(str(e))

    return errors


# ---------------------------------------------------------------------------
# 4. CI workflow contract (positive)
# ---------------------------------------------------------------------------


def test_ci_contract_validates_real_file() -> None:
    text = CI_FILE.read_text(encoding="utf-8")
    errors = _validate_ci_contract(text)
    assert not errors, f"erros no CI real: {errors}"


# ---------------------------------------------------------------------------
# 5. CI negative controls (synthetic YAML)
# ---------------------------------------------------------------------------


def test_ci_negative_always_on_wrong_step() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Publicar cobertura
        if: always()
        run: echo coverage
      - name: Publicar resultados JUnit
        run: echo missing
"""
    errors = _validate_ci_contract(yml)
    assert any("if: always() ausente" in e for e in errors), (
        f"erro 'if: always() ausente' não encontrado: {errors}"
    )


def test_ci_negative_value_in_comment_only() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Testes e cobertura
        run: |
          echo some test
          # --junitxml=build/test-results-${{ matrix.python-version }}.xml
      - name: Publicar resultados JUnit
        if: always()
        uses: actions/upload-artifact@abc123
        with:
          name: test-results-fixed
          path: build/results.xml
          if-no-files-found: error
          retention-days: 30
"""
    errors = _validate_ci_contract(yml)
    assert any("--junitxml por versão" in e for e in errors), (
        f"erro '--junitxml' não encontrado: {errors}"
    )


def test_ci_negative_value_in_echo_only() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Testes e cobertura
        run: |
          echo --junitxml=build/test-results-${{ matrix.python-version }}.xml
      - name: Publicar resultados JUnit
        if: always()
        uses: actions/upload-artifact@abc123
        with:
          name: test-results-fixed
          path: build/results.xml
          if-no-files-found: error
          retention-days: 30
"""
    errors = _validate_ci_contract(yml)
    assert any("--junitxml por versão" in e for e in errors), (
        f"erro '--junitxml' não encontrado: {errors}"
    )


def test_ci_negative_path_missing_version() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Testes e cobertura
        run: |
          pytest --durations=20 --junitxml=build/test-results-${{ matrix.python-version }}.xml
      - name: Publicar resultados JUnit
        if: always()
        uses: actions/upload-artifact@abc123
        with:
          name: test-results-fixed
          path: build/results.xml
          if-no-files-found: error
          retention-days: 30
"""
    errors = _validate_ci_contract(yml)
    assert any("path por versão" in e for e in errors), (
        f"erro 'path por versão' não encontrado: {errors}"
    )


def test_ci_negative_if_no_files_is_warn() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Testes e cobertura
        run: |
          pytest --durations=20 --junitxml=build/test-results-${{ matrix.python-version }}.xml
      - name: Publicar resultados JUnit
        if: always()
        uses: actions/upload-artifact@abc123
        with:
          name: test-results-${{ matrix.python-version }}
          path: build/test-results-${{ matrix.python-version }}.xml
          if-no-files-found: warn
          retention-days: 30
"""
    errors = _validate_ci_contract(yml)
    assert any("if-no-files-found: error" in e for e in errors), (
        f"erro 'if-no-files-found' não encontrado: {errors}"
    )


def test_ci_negative_missing_property() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Testes e cobertura
        run: |
          pytest --durations=20 --junitxml=build/test-results-${{ matrix.python-version }}.xml
      - name: Publicar resultados JUnit
        if: always()
        uses: actions/upload-artifact@abc123
        with:
          name: test-results-${{ matrix.python-version }}
          path: build/test-results-${{ matrix.python-version }}.xml
          if-no-files-found: error
"""
    errors = _validate_ci_contract(yml)
    assert any("retention-days: 30" in e for e in errors), (
        f"erro 'retention-days' não encontrado: {errors}"
    )


def test_ci_negative_step_absent() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Publicar cobertura
        run: echo coverage
"""
    errors = _validate_ci_contract(yml)
    assert any("step obrigatório ausente: Publicar resultados JUnit" in e for e in errors), (
        f"erro 'step obrigatório ausente' não encontrado: {errors}"
    )
    assert any("step obrigatório ausente: Testes e cobertura" in e for e in errors), (
        f"erro 'step obrigatório ausente' não encontrado: {errors}"
    )


def test_ci_negative_step_duplicated() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Testes e cobertura
        run: |
          pytest --durations=20 --junitxml=build/test-results-${{ matrix.python-version }}.xml
      - name: Publicar resultados JUnit
        if: always()
        uses: actions/upload-artifact@abc123
        with:
          name: test-results-${{ matrix.python-version }}
          path: build/test-results-${{ matrix.python-version }}.xml
          if-no-files-found: error
          retention-days: 30
      - name: Publicar resultados JUnit
        if: always()
        uses: actions/upload-artifact@abc1234567890123456789012345678901234567890
        with:
          name: test-results-${{ matrix.python-version }}
          path: build/test-results-${{ matrix.python-version }}.xml
          if-no-files-found: error
          retention-days: 30
"""
    errors = _validate_ci_contract(yml)
    assert any("step duplicado: Publicar resultados JUnit" in e for e in errors), (
        f"erro 'step duplicado' não encontrado: {errors}"
    )


def test_ci_negative_action_without_sha() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Testes e cobertura
        run: |
          pytest --durations=20 --junitxml=build/test-results-${{ matrix.python-version }}.xml
      - name: Publicar resultados JUnit
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-results-${{ matrix.python-version }}
          path: build/test-results-${{ matrix.python-version }}.xml
          if-no-files-found: error
          retention-days: 30
"""
    errors = _validate_ci_contract(yml)
    assert any("SHA hex" in e for e in errors), f"erro 'SHA hex' não encontrado: {errors}"


def test_ci_negative_short_sha() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Testes e cobertura
        run: |
          pytest --durations=20 --junitxml=build/test-results-${{ matrix.python-version }}.xml
      - name: Publicar resultados JUnit
        if: always()
        uses: actions/upload-artifact@abc123def
        with:
          name: test-results-${{ matrix.python-version }}
          path: build/test-results-${{ matrix.python-version }}.xml
          if-no-files-found: error
          retention-days: 30
"""
    errors = _validate_ci_contract(yml)
    assert any("SHA hex" in e for e in errors), f"erro 'SHA hex' não encontrado: {errors}"


def test_ci_negative_empty_yaml() -> None:
    errors = _validate_ci_contract("")
    assert any("step obrigatório ausente" in e for e in errors), (
        f"erro 'step obrigatório ausente' não encontrado em YAML vazio: {errors}"
    )


def test_ci_negative_incorrect_retention() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Testes e cobertura
        run: |
          pytest --durations=20 --junitxml=build/test-results-${{ matrix.python-version }}.xml
      - name: Publicar resultados JUnit
        if: always()
        uses: actions/upload-artifact@abc1234567890123456789012345678901234567890
        with:
          name: test-results-${{ matrix.python-version }}
          path: build/test-results-${{ matrix.python-version }}.xml
          if-no-files-found: error
          retention-days: 7
"""
    errors = _validate_ci_contract(yml)
    assert any("retention-days: 30" in e for e in errors), (
        f"erro 'retention-days' não encontrado: {errors}"
    )
