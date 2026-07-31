# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Executa pytest sem permitir que a suíte toque o estado XDG do operador.

O isolamento precisa existir antes de ``pytest`` importar plugins e módulos de
teste. Por isso este runner cria os cinco homes XDG e só então abre um novo
processo Python. Uma fotografia exata dos metadados do state home original
reprova o gate se qualquer entrada real for criada, removida ou modificada.
"""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

_XDG_LAYOUT = {
    "XDG_STATE_HOME": "state",
    "XDG_DATA_HOME": "data",
    "XDG_CONFIG_HOME": "config",
    "XDG_CACHE_HOME": "cache",
    "XDG_RUNTIME_DIR": "runtime",
}
_HOME_SUBDIR = "home"
_TEST_ROOT_ENV = "STEAMZERO_TEST_XDG_ROOT"
_STATE_CHANGE_EXIT = 86


@dataclass(frozen=True)
class StateEntry:
    """Metadados suficientes para detectar mutação sem ler conteúdo privado."""

    kind: str
    size: int
    mtime_ns: int
    ctime_ns: int
    link_target_hash: str = ""


@dataclass(frozen=True)
class StateSnapshot:
    root_exists: bool
    entries: tuple[tuple[str, StateEntry], ...]

    @property
    def file_count(self) -> int:
        return sum(entry.kind != "directory" for _, entry in self.entries)

    @property
    def directory_count(self) -> int:
        return sum(entry.kind == "directory" for _, entry in self.entries)

    @property
    def total_bytes(self) -> int:
        return sum(entry.size for _, entry in self.entries if entry.kind == "file")

    @property
    def max_mtime_ns(self) -> int:
        return max((entry.mtime_ns for _, entry in self.entries), default=0)

    def summary(self) -> str:
        return (
            f"exists={self.root_exists} files={self.file_count} "
            f"directories={self.directory_count} bytes={self.total_bytes} "
            f"max_mtime_ns={self.max_mtime_ns}"
        )


def resolve_real_state_home(environ: Mapping[str, str]) -> tuple[Path, str]:
    base_xdg = environ.get("XDG_STATE_HOME")
    if base_xdg is not None:
        return (Path(base_xdg) / "steamzero", "XDG_STATE_HOME")
    base_home = environ.get("HOME")
    if base_home is None:
        raise RuntimeError(
            "STEAMZERO: não é possível determinar o state home original — "
            "nem XDG_STATE_HOME nem HOME estão definidos no ambiente"
        )
    return (Path(base_home) / ".local" / "state" / "steamzero", "HOME-default")


def snapshot_state(root: Path) -> StateSnapshot:
    """Fotografa nomes e metadados, sem seguir links nem ler arquivos."""
    if not root.exists() and not root.is_symlink():
        return StateSnapshot(False, ())

    entries: list[tuple[str, StateEntry]] = []
    pending = [root]
    while pending:
        parent = pending.pop()
        try:
            children = sorted(parent.iterdir(), key=lambda item: item.name)
        except (FileNotFoundError, NotADirectoryError):
            continue
        for child in children:
            metadata = child.stat(follow_symlinks=False)
            mode = metadata.st_mode
            relative = child.relative_to(root).as_posix()
            if stat.S_ISDIR(mode):
                kind = "directory"
                pending.append(child)
            elif stat.S_ISREG(mode):
                kind = "file"
            elif stat.S_ISLNK(mode):
                kind = "symlink"
            else:
                kind = "other"
            target_hash = ""
            if kind == "symlink":
                target_hash = hashlib.sha256(os.readlink(child).encode("utf-8")).hexdigest()
            entries.append(
                (
                    relative,
                    StateEntry(
                        kind=kind,
                        size=metadata.st_size,
                        mtime_ns=metadata.st_mtime_ns,
                        ctime_ns=metadata.st_ctime_ns,
                        link_target_hash=target_hash,
                    ),
                )
            )
    return StateSnapshot(True, tuple(sorted(entries)))


def isolated_environment(root: Path, environ: Mapping[str, str]) -> dict[str, str]:
    child_env = dict(environ)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    home_dir = root / _HOME_SUBDIR
    home_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    home_dir.chmod(0o700)
    child_env["HOME"] = str(home_dir)
    for variable, directory in _XDG_LAYOUT.items():
        target = root / directory
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.chmod(0o700)
        child_env[variable] = str(target)
    child_env[_TEST_ROOT_ENV] = str(root)
    return child_env


def changed_entries(
    before: StateSnapshot, after: StateSnapshot
) -> tuple[list[str], list[str], list[str]]:
    before_entries = dict(before.entries)
    after_entries = dict(after.entries)
    created = sorted(after_entries.keys() - before_entries.keys())
    removed = sorted(before_entries.keys() - after_entries.keys())
    changed = sorted(
        name
        for name in before_entries.keys() & after_entries.keys()
        if before_entries[name] != after_entries[name]
    )
    return created, removed, changed


def _report_state_change(before: StateSnapshot, after: StateSnapshot) -> None:
    created, removed, changed = changed_entries(before, after)
    print(
        "E-TEST-REAL-STATE-MUTATED: pytest alterou o state home original",
        file=sys.stderr,
    )
    print(f"before: {before.summary()}", file=sys.stderr)
    print(f"after:  {after.summary()}", file=sys.stderr)
    for label, names in (("created", created), ("removed", removed), ("changed", changed)):
        if names:
            sample = ", ".join(names[:20])
            suffix = f" (+{len(names) - 20})" if len(names) > 20 else ""
            print(f"{label}: {sample}{suffix}", file=sys.stderr)


_INTERRUPT_EXIT = 130


def run_pytest(args: Sequence[str], *, environ: Mapping[str, str] | None = None) -> int:
    original_env = dict(os.environ if environ is None else environ)
    real_state_home, source = resolve_real_state_home(original_env)
    before = snapshot_state(real_state_home)
    print(f"real-state before: {before.summary()} source={source}")

    interrupted = False
    pytest_returncode = 0
    state_mutated = False
    with tempfile.TemporaryDirectory(prefix="steamzero-tests-") as temporary:
        isolated_root = Path(temporary)
        child_env = isolated_environment(isolated_root, original_env)
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "pytest", *args],
                env=child_env,
                check=False,
            )
            pytest_returncode = completed.returncode
        except KeyboardInterrupt:
            interrupted = True
        finally:
            after = snapshot_state(real_state_home)
            print(f"real-state after:  {after.summary()} source={source}")
            state_mutated = before != after
            if state_mutated:
                _report_state_change(before, after)

    if state_mutated:
        return _STATE_CHANGE_EXIT
    if interrupted:
        return _INTERRUPT_EXIT
    return pytest_returncode


def main(argv: Sequence[str] | None = None) -> int:
    return run_pytest(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    raise SystemExit(main())
