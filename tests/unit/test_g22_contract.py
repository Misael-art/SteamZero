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


def _parse_step(
    yml_text: str, step_name: str
) -> tuple[dict[str, str], dict[str, str], list[str], tuple[str, ...], tuple[str, ...]]:
    """Parse a workflow step using indentation-aware state machine.

    Returns (direct, with_values, run_lines, duplicate_direct, duplicate_with).
    """
    lines = yml_text.splitlines()
    target = f"- name: {step_name}"
    step_start = next((i for i, line in enumerate(lines) if line.strip() == target), None)
    if step_start is None:
        raise AssertionError(f"step '{step_name}' não encontrado no YAML")
    dash_indent = len(lines[step_start]) - len(lines[step_start].lstrip())
    body_indent = dash_indent + 2
    direct: dict[str, str] = {}
    with_values: dict[str, str] = {}
    run_lines: list[str] = []
    seen_direct: dict[str, int] = {}
    seen_with: dict[str, int] = {}
    dup_direct: list[str] = []
    dup_with: list[str] = []
    mode: str = "direct"
    for line in lines[step_start + 1 :]:
        if not line.strip():
            continue
        stripped = line.strip()
        if not line[0].isspace() and ":" in line and not stripped.startswith("-"):
            break
        if stripped.startswith("- name:"):
            break
        if stripped.startswith("#"):
            continue
        line_indent = len(line) - len(line.lstrip())
        rel_indent = line_indent - body_indent
        if mode == "run_literal":
            if rel_indent > 0:
                run_lines.append(stripped)
                continue
            mode = "direct"
        if mode == "with":
            if rel_indent > 0:
                if ":" in stripped:
                    k, _, v = stripped.partition(":")
                    k = k.strip()
                    v = v.strip()
                    if " #" in v:
                        v = v.split(" #", 1)[0].strip()
                    seen_with[k] = seen_with.get(k, 0) + 1
                    if seen_with[k] > 1:
                        dup_with.append(k)
                    else:
                        with_values[k] = v
                continue
            mode = "direct"
        if mode == "direct":
            if stripped.startswith("run:"):
                if " |" in stripped:
                    mode = "run_literal"
                else:
                    val = stripped[len("run:") :].strip()
                    if val:
                        run_lines.append(val)
                continue
            if stripped == "with:":
                mode = "with"
                continue
            if ":" in stripped:
                k, _, v = stripped.partition(":")
                k = k.strip()
                v = v.strip()
                if " #" in v:
                    v = v.split(" #", 1)[0].strip()
                seen_direct[k] = seen_direct.get(k, 0) + 1
                if seen_direct[k] > 1:
                    dup_direct.append(k)
                else:
                    direct[k] = v
    return direct, with_values, run_lines, tuple(dup_direct), tuple(dup_with)


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
        _direct, _with_vals, run_lines, _dup_d, _dup_w = _parse_step(yml_text, "Testes e cobertura")
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
        direct, with_values, _run_lines, dup_direct, dup_with = _parse_step(
            yml_text, "Publicar resultados JUnit"
        )

        for k in dup_with:
            errors.append(f"chave duplicada em with no step Publicar resultados JUnit: {k}")
        for k in dup_direct:
            errors.append(f"chave direta duplicada no step Publicar resultados JUnit: {k}")

        if direct.get("if") != "always()":
            errors.append("if: always() ausente ou incorreto no step Publicar resultados JUnit")

        uses_val = direct.get("uses", "")
        if not uses_val.startswith("actions/upload-artifact@"):
            errors.append("actions/upload-artifact ausente no step Publicar resultados JUnit")
        else:
            sha = uses_val.split("@", 1)[1]
            if not (len(sha) == 40 and all(c in "0123456789abcdef" for c in sha)):
                msg = f"upload-artifact sem SHA hex de 40 caracteres: {sha!r}"
                errors.append(msg)

        expected_name = "test-results-${{ matrix.python-version }}"
        actual_name = with_values.get("name")
        if actual_name != expected_name:
            msg = f"name por versão incorreto no step Publicar resultados JUnit: {actual_name!r}"
            errors.append(msg)

        expected_path = "build/test-results-${{ matrix.python-version }}.xml"
        actual_path = with_values.get("path")
        if actual_path != expected_path:
            msg = f"path por versão incorreto no step Publicar resultados JUnit: {actual_path!r}"
            errors.append(msg)

        if with_values.get("if-no-files-found") != "error":
            errors.append("if-no-files-found: error ausente no step Publicar resultados JUnit")

        if with_values.get("retention-days") != "30":
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


def test_ci_negative_echo_only_properties() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Testes e cobertura
        run: |
          pytest --durations=20 --junitxml=build/test-results-${{ matrix.python-version }}.xml
      - name: Publicar resultados JUnit
        run: |
          echo if: always()
          echo actions/upload-artifact@0123456789012345678901234567890123456789
          echo test-results-${{ matrix.python-version }}
          echo path: build/test-results-${{ matrix.python-version }}.xml
          echo if-no-files-found: error
          echo retention-days: 30
"""
    errors = _validate_ci_contract(yml)
    assert any("if: always()" in e for e in errors), f"erro 'if: always()' não encontrado: {errors}"
    assert any("upload-artifact" in e for e in errors), (
        f"erro 'upload-artifact' não encontrado: {errors}"
    )
    assert any("name por versão" in e for e in errors), (
        f"erro 'name por versão' não encontrado: {errors}"
    )
    assert any("path por versão" in e for e in errors), (
        f"erro 'path por versão' não encontrado: {errors}"
    )
    assert any("if-no-files-found" in e for e in errors), (
        f"erro 'if-no-files-found' não encontrado: {errors}"
    )
    assert any("retention-days" in e for e in errors), (
        f"erro 'retention-days' não encontrado: {errors}"
    )


def test_ci_negative_values_in_comments_junit() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Testes e cobertura
        run: |
          pytest --durations=20 --junitxml=build/test-results-${{ matrix.python-version }}.xml
      - name: Publicar resultados JUnit
        # if: always()
        # uses: actions/upload-artifact@0123456789012345678901234567890123456789
        # with:
        #   name: test-results-${{ matrix.python-version }}
        #   path: build/test-results-${{ matrix.python-version }}.xml
        #   if-no-files-found: error
        #   retention-days: 30
        run: echo nothing
"""
    errors = _validate_ci_contract(yml)
    assert any("if: always()" in e for e in errors), f"erro 'if: always()' não encontrado: {errors}"
    assert any("upload-artifact" in e for e in errors), (
        f"erro 'upload-artifact' não encontrado: {errors}"
    )
    assert any("name por versão" in e for e in errors), (
        f"erro 'name por versão' não encontrado: {errors}"
    )
    assert any("path por versão" in e for e in errors), (
        f"erro 'path por versão' não encontrado: {errors}"
    )


def test_ci_negative_if_inside_run() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Testes e cobertura
        run: |
          pytest --durations=20 --junitxml=build/test-results-${{ matrix.python-version }}.xml
      - name: Publicar resultados JUnit
        run: |
          echo if: always()
        uses: actions/upload-artifact@0123456789012345678901234567890123456789
        with:
          name: test-results-${{ matrix.python-version }}
          path: build/test-results-${{ matrix.python-version }}.xml
          if-no-files-found: error
          retention-days: 30
"""
    errors = _validate_ci_contract(yml)
    assert any("if: always()" in e for e in errors), f"erro 'if: always()' não encontrado: {errors}"
    assert not any("upload-artifact" in e for e in errors), f"erro de upload inesperado: {errors}"


def test_ci_negative_uses_inside_run() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Testes e cobertura
        run: |
          pytest --durations=20 --junitxml=build/test-results-${{ matrix.python-version }}.xml
      - name: Publicar resultados JUnit
        if: always()
        run: |
          echo actions/upload-artifact@0123456789012345678901234567890123456789
        with:
          name: test-results-${{ matrix.python-version }}
          path: build/test-results-${{ matrix.python-version }}.xml
          if-no-files-found: error
          retention-days: 30
"""
    errors = _validate_ci_contract(yml)
    assert any("upload-artifact" in e for e in errors), (
        f"erro 'upload-artifact' não encontrado: {errors}"
    )
    assert not any("if: always()" in e for e in errors), f"erro de if inesperado: {errors}"


def test_ci_negative_properties_outside_with() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Testes e cobertura
        run: |
          pytest --durations=20 --junitxml=build/test-results-${{ matrix.python-version }}.xml
      - name: Publicar resultados JUnit
        if: always()
        uses: actions/upload-artifact@0123456789012345678901234567890123456789
        name: test-results-${{ matrix.python-version }}
        path: build/test-results-${{ matrix.python-version }}.xml
        with:
          if-no-files-found: error
          retention-days: 30
"""
    errors = _validate_ci_contract(yml)
    assert any("name por versão" in e for e in errors), (
        f"erro 'name por versão' não encontrado: {errors}"
    )
    assert any("path por versão" in e for e in errors), (
        f"erro 'path por versão' não encontrado: {errors}"
    )
    assert not any("if-no-files-found" in e for e in errors), (
        f"erro de if-no-files-found inesperado: {errors}"
    )


def test_ci_negative_duplicate_path_in_with() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Testes e cobertura
        run: |
          pytest --durations=20 --junitxml=build/test-results-${{ matrix.python-version }}.xml
      - name: Publicar resultados JUnit
        if: always()
        uses: actions/upload-artifact@0123456789012345678901234567890123456789
        with:
          name: test-results-${{ matrix.python-version }}
          path: build/test-results-${{ matrix.python-version }}.xml
          path: build/other.xml
          if-no-files-found: error
          retention-days: 30
"""
    errors = _validate_ci_contract(yml)
    assert any("chave duplicada em with" in e for e in errors), (
        f"erro 'chave duplicada' não encontrado: {errors}"
    )


def test_ci_negative_run_literal_leak() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Testes e cobertura
        run: |
          pytest --durations=20 --junitxml=build/test-results-${{ matrix.python-version }}.xml
      - name: Publicar resultados JUnit
        run: |
          if: always()
          uses: actions/upload-artifact@0123456789012345678901234567890123456789
          with:
            name: test-results-${{ matrix.python-version }}
            path: build/test-results-${{ matrix.python-version }}.xml
            if-no-files-found: error
            retention-days: 30
"""
    errors = _validate_ci_contract(yml)
    assert any("if: always()" in e for e in errors), f"if não detectado: {errors}"
    assert any("upload-artifact" in e for e in errors), f"upload não detectado: {errors}"
    assert any("name por versão" in e for e in errors), f"name não detectado: {errors}"
    assert any("path por versão" in e for e in errors), f"path não detectado: {errors}"
    assert any("if-no-files-found" in e for e in errors), f"if-no-files não detectado: {errors}"
    assert any("retention-days" in e for e in errors), f"retention não detectado: {errors}"


def test_ci_negative_duplicate_direct_key() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Testes e cobertura
        run: |
          pytest --durations=20 --junitxml=build/test-results-${{ matrix.python-version }}.xml
      - name: Publicar resultados JUnit
        if: always()
        if: failure()
        uses: actions/upload-artifact@0123456789012345678901234567890123456789
        with:
          name: test-results-${{ matrix.python-version }}
          path: build/test-results-${{ matrix.python-version }}.xml
          if-no-files-found: error
          retention-days: 30
"""
    errors = _validate_ci_contract(yml)
    assert any("chave direta duplicada" in e for e in errors), (
        f"duplicata direta não detectada: {errors}"
    )


def test_ci_negative_duplicate_uses() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Testes e cobertura
        run: |
          pytest --durations=20 --junitxml=build/test-results-${{ matrix.python-version }}.xml
      - name: Publicar resultados JUnit
        if: always()
        uses: actions/upload-artifact@0123456789012345678901234567890123456789
        uses: actions/upload-artifact@abcdefabcdefabcdefabcdefabcdefabcdefabcd
        with:
          name: test-results-${{ matrix.python-version }}
          path: build/test-results-${{ matrix.python-version }}.xml
          if-no-files-found: error
          retention-days: 30
"""
    errors = _validate_ci_contract(yml)
    assert any("chave direta duplicada" in e for e in errors), (
        f"duplicata uses não detectada: {errors}"
    )


def test_ci_positive_comment_before_properties() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Testes e cobertura
        run: |
          pytest --durations=20 --junitxml=build/test-results-${{ matrix.python-version }}.xml
      - name: Publicar resultados JUnit
        # comentário imediatamente após name
        if: always()
        uses: actions/upload-artifact@0123456789012345678901234567890123456789
        with:
          name: test-results-${{ matrix.python-version }}
          path: build/test-results-${{ matrix.python-version }}.xml
          if-no-files-found: error
          retention-days: 30
"""
    errors = _validate_ci_contract(yml)
    assert not errors, f"comentário antes de props quebrou parser: {errors}"


def test_ci_positive_empty_line_before_properties() -> None:
    yml = """jobs:
  test:
    steps:
      - name: Testes e cobertura
        run: |
          pytest --durations=20 --junitxml=build/test-results-${{ matrix.python-version }}.xml
      - name: Publicar resultados JUnit

        if: always()
        uses: actions/upload-artifact@0123456789012345678901234567890123456789
        with:
          name: test-results-${{ matrix.python-version }}
          path: build/test-results-${{ matrix.python-version }}.xml
          if-no-files-found: error
          retention-days: 30
"""
    errors = _validate_ci_contract(yml)
    assert not errors, f"linha vazia antes de props quebrou parser: {errors}"
