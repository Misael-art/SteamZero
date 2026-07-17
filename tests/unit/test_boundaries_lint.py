# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do lint de fronteiras (tools/lint_boundaries.py).

Prova dupla: (1) o código de produção passa limpo; (2) o linter realmente
detecta cada categoria de violação em snippets sintéticos.
"""

from __future__ import annotations

from pathlib import Path

import lint_boundaries

SRC = Path(__file__).parents[2] / "src"


def _codes(tmp_path: Path, rel: str, code: str) -> set[str]:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(code, encoding="utf-8")
    return {v.code for v in lint_boundaries.lint_file(p, tmp_path)}


def test_production_source_is_clean() -> None:
    violations = lint_boundaries.lint_tree(SRC)
    assert violations == [], "\n".join(str(v) for v in violations)


def test_detects_eval(tmp_path: Path) -> None:
    assert "BND-EVAL" in _codes(tmp_path, "steamzero/domain/x.py", "x = eval('1+1')\n")


def test_detects_exec(tmp_path: Path) -> None:
    assert "BND-EVAL" in _codes(tmp_path, "steamzero/domain/x.py", "exec('y=1')\n")


def test_detects_open_write_outside_fs(tmp_path: Path) -> None:
    code = "def f():\n    open('/tmp/x', 'w').write('a')\n"
    assert "BND-WRITE-PORT" in _codes(tmp_path, "steamzero/domain/x.py", code)


def test_allows_open_write_inside_fs(tmp_path: Path) -> None:
    code = "def f():\n    open('/tmp/x', 'w').write('a')\n"
    assert _codes(tmp_path, "steamzero/core/fs.py", code) == set()


def test_allows_read_open_everywhere(tmp_path: Path) -> None:
    code = "def f():\n    return open('/tmp/x').read() + open('/tmp/y', 'r').read()\n"
    assert "BND-WRITE-PORT" not in _codes(tmp_path, "steamzero/domain/x.py", code)


def test_detects_os_rename_outside_fs(tmp_path: Path) -> None:
    code = "import os\ndef f():\n    os.rename('a', 'b')\n"
    assert "BND-WRITE-PORT" in _codes(tmp_path, "steamzero/domain/x.py", code)


def test_detects_path_write_text(tmp_path: Path) -> None:
    code = "def f(p):\n    p.write_text('x')\n"
    assert "BND-WRITE-PORT" in _codes(tmp_path, "steamzero/domain/x.py", code)


def test_str_replace_is_not_a_false_positive(tmp_path: Path) -> None:
    code = "def f(s):\n    return s.replace('a', 'b')\n"
    assert "BND-WRITE-PORT" not in _codes(tmp_path, "steamzero/domain/x.py", code)


def test_detects_subprocess_outside_proc(tmp_path: Path) -> None:
    code = "import subprocess\ndef f():\n    subprocess.run(['ls'])\n"
    codes = _codes(tmp_path, "steamzero/domain/x.py", code)
    assert "BND-PROC" in codes


def test_allows_subprocess_in_proc_port(tmp_path: Path) -> None:
    code = "import subprocess\ndef f():\n    subprocess.run(['ls'])\n"
    assert "BND-PROC" not in _codes(tmp_path, "steamzero/core/proc.py", code)


def test_allows_subprocess_in_adapters(tmp_path: Path) -> None:
    code = "import subprocess\ndef f():\n    subprocess.run(['ls'])\n"
    assert "BND-PROC" not in _codes(tmp_path, "steamzero/adapters/emu/x.py", code)


def test_allows_subprocess_only_in_privileged_client(tmp_path: Path) -> None:
    code = "import subprocess\ndef f():\n    subprocess.run(['/usr/bin/pkexec'])\n"
    assert "BND-PROC" not in _codes(tmp_path, "steamzero/privileged/client.py", code)
    assert "BND-PROC" in _codes(tmp_path, "steamzero/privileged/other.py", code)


def test_detects_shell_true(tmp_path: Path) -> None:
    code = "import subprocess\ndef f():\n    subprocess.run('ls', shell=True)\n"
    assert "BND-SHELL" in _codes(tmp_path, "steamzero/adapters/x.py", code)


def test_detects_domain_importing_adapters(tmp_path: Path) -> None:
    code = "from steamzero.adapters import emu\n"
    assert "BND-DOMAIN-ADAPTER" in _codes(tmp_path, "steamzero/domain/x.py", code)


def test_domain_adapter_rule_scoped_to_domain(tmp_path: Path) -> None:
    code = "from steamzero.adapters import emu\n"
    # fora de domain, importar adapters é permitido (ex.: api monta o registry)
    assert "BND-DOMAIN-ADAPTER" not in _codes(tmp_path, "steamzero/api/x.py", code)
