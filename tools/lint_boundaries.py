#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Lint de fronteiras arquiteturais (MODULE-BOUNDARIES §Proibições verificáveis).

Análise estática por AST (stdlib pura, sem dependências). Detecta:

- BND-EVAL       : uso de ``eval``/``exec``/``compile`` (SR-02).
- BND-WRITE-PORT : escrita em disco fora de ``steamzero.core.fs`` — ``open`` em
                   modo de escrita, ``os.rename/replace/remove/...``, ``shutil``
                   mutável, métodos ``Path.write_*/rename/unlink/mkdir/...``.
- BND-PROC       : uso de ``subprocess`` fora de ``core.proc``/``adapters.*``.
- BND-NET        : cliente HTTP fora de ``core.net``.
- BND-SHELL      : ``shell=True`` (SR-03).
- BND-DOMAIN-ADAPTER : ``domain.*`` importando ``adapters.*``.

Uso: ``python tools/lint_boundaries.py [--root src]`` — sai 1 se houver violação.
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

PACKAGE = "steamzero"

# Única porta de escrita em disco.
WRITE_PORTS = frozenset({"steamzero.core.fs", "steamzero.privileged.host_effects"})
# Onde subprocess é permitido.
PROC_PORT_PREFIXES = (
    "steamzero.core.proc",
    "steamzero.adapters.",
    "steamzero.privileged.client",
)
NET_PORT = "steamzero.core.net"
# Adaptadores que falam HTTP LAN (descoberta mDNS / pareamento GFE) — protocolo
# exige HTTP puro; core.net exige HTTPS. A exceção é nominal por módulo porque
# o código LAN HTTP cruza a fronteira de segurança de forma controlada.
_NET_EXEMPT_MODULES = frozenset({"steamzero.adapters.game_stream"})
_HTTP_IMPORTS = frozenset({"urllib.request", "http.client", "requests", "httpx", "aiohttp"})

_OS_WRITE_FUNCS = frozenset(
    {"rename", "replace", "remove", "unlink", "mkdir", "makedirs", "rmdir", "symlink", "link"}
)
_SHUTIL_WRITE_FUNCS = frozenset({"move", "copy", "copy2", "copyfile", "copytree", "rmtree"})
# Métodos com nome específico de FS o suficiente para evitar falso-positivo
# (deliberadamente sem ``replace``/``remove`` — colidem com str/list).
_PATH_WRITE_METHODS = frozenset(
    {
        "write_text",
        "write_bytes",
        "rename",
        "unlink",
        "mkdir",
        "rmdir",
        "touch",
        "symlink_to",
        "hardlink_to",
        "chmod",
        "lchmod",
    }
)
_EVAL_NAMES = frozenset({"eval", "exec", "compile"})


@dataclass(frozen=True)
class Violation:
    code: str
    module: str
    file: str
    line: int
    message: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}: {self.code} [{self.module}] {self.message}"


def module_name_for(path: Path, root: Path) -> str:
    """Deriva o nome de módulo pontilhado (steamzero.core.fs) a partir do path."""
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _is_write_mode(mode: str) -> bool:
    return any(ch in mode for ch in ("w", "a", "x", "+"))


def _open_mode(call: ast.Call) -> str | None:
    """Retorna o modo textual de uma chamada open()/Path.open(), ou None."""
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
        val = call.args[1].value
        return val if isinstance(val, str) else None
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            val = kw.value.value
            return val if isinstance(val, str) else None
    return None


class _Visitor(ast.NodeVisitor):
    def __init__(self, module: str, file: str) -> None:
        self.module = module
        self.file = file
        self.violations: list[Violation] = []
        self._is_write_port = module in WRITE_PORTS
        self._is_proc_port = any(module == p or module.startswith(p) for p in PROC_PORT_PREFIXES)
        self._is_net_port = module == NET_PORT
        self._is_domain = module.startswith("steamzero.domain")

    def _add(self, code: str, node: ast.AST, message: str) -> None:
        self.violations.append(
            Violation(code, self.module, self.file, getattr(node, "lineno", 0), message)
        )

    # -- imports -----------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_import(node, alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self._check_import(node, node.module)
        self.generic_visit(node)

    def _check_import(self, node: ast.AST, name: str) -> None:
        if name == "subprocess" and not self._is_proc_port:
            self._add("BND-PROC", node, "importa subprocess fora de core.proc/adapters")
        if self._is_domain and (
            name.startswith("steamzero.adapters") or name == "steamzero.adapters"
        ):
            self._add("BND-DOMAIN-ADAPTER", node, "domain importa adapters (proibido)")
        if (
            not self._is_net_port
            and self.module not in _NET_EXEMPT_MODULES
            and (
                name in _HTTP_IMPORTS
                or any(name.startswith(f"{prefix}.") for prefix in {"requests", "httpx", "aiohttp"})
            )
        ):
            self._add("BND-NET", node, "cliente HTTP fora de core.net")

    # -- calls -------------------------------------------------------------
    def visit_Call(self, node: ast.Call) -> None:
        self._check_eval(node)
        self._check_subprocess(node)
        self._check_shell_true(node)
        if not self._is_write_port:
            self._check_write(node)
        self.generic_visit(node)

    def _check_eval(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name) and func.id in _EVAL_NAMES:
            self._add("BND-EVAL", node, f"chamada a {func.id}() proibida")

    def _check_subprocess(self, node: ast.Call) -> None:
        if self._is_proc_port:
            return
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "subprocess"
        ):
            self._add("BND-PROC", node, "uso de subprocess fora de core.proc/adapters")
        if isinstance(func, ast.Name) and func.id in {"system", "popen"}:
            self._add("BND-PROC", node, f"uso de os.{func.id} proibido")

    def _check_shell_true(self, node: ast.Call) -> None:
        for kw in node.keywords:
            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                self._add("BND-SHELL", node, "shell=True proibido (SR-03)")

    def _check_write(self, node: ast.Call) -> None:
        func = node.func
        # builtin open(...) em modo de escrita
        if isinstance(func, ast.Name) and func.id == "open":
            # sem 2º arg = 'r' (leitura) -> ok; só flag modo de escrita.
            mode = _open_mode(node)
            if mode is not None and _is_write_mode(mode):
                self._add("BND-WRITE-PORT", node, f"open(mode={mode!r}) fora de core.fs")
            return
        if isinstance(func, ast.Attribute):
            attr = func.attr
            base = func.value
            if isinstance(base, ast.Name) and base.id == "os" and attr in _OS_WRITE_FUNCS:
                self._add("BND-WRITE-PORT", node, f"os.{attr}() fora de core.fs")
            elif (
                isinstance(base, ast.Attribute)
                and base.attr == "path"
                and isinstance(base.value, ast.Name)
                and base.value.id == "os"
            ):
                pass  # os.path.* é leitura
            elif isinstance(base, ast.Name) and base.id == "shutil" and attr in _SHUTIL_WRITE_FUNCS:
                self._add("BND-WRITE-PORT", node, f"shutil.{attr}() fora de core.fs")
            elif attr in _PATH_WRITE_METHODS:
                self._add("BND-WRITE-PORT", node, f".{attr}() (escrita FS) fora de core.fs")
            elif attr == "open":
                mode = _open_mode(node)
                if mode is not None and _is_write_mode(mode):
                    self._add("BND-WRITE-PORT", node, f".open(mode={mode!r}) fora de core.fs")


def lint_file(path: Path, root: Path) -> list[Violation]:
    module = module_name_for(path, root)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    visitor = _Visitor(module, str(path))
    visitor.visit(tree)
    return visitor.violations


def iter_py_files(root: Path) -> Iterator[Path]:
    yield from sorted(root.rglob("*.py"))


def lint_tree(root: Path) -> list[Violation]:
    violations: list[Violation] = []
    for path in iter_py_files(root):
        violations.extend(lint_file(path, root))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint de fronteiras arquiteturais")
    parser.add_argument("--root", default="src", help="raiz do pacote (default: src)")
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.exists():
        print(f"raiz inexistente: {root}", file=sys.stderr)
        return 2
    violations = lint_tree(root)
    for v in violations:
        print(str(v))
    if violations:
        print(f"\n{len(violations)} violação(ões) de fronteira.", file=sys.stderr)
        return 1
    print("lint de fronteiras: OK (0 violações)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
