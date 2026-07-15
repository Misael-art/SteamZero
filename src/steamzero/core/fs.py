# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""``core.fs`` — a ÚNICA porta de escrita em disco (MODULE-BOUNDARIES).

Responsabilidades:
- Escrita atômica (tmp + fsync + rename no mesmo FS) — SR-05.
- Append durável (log/journal) via ``AppendWriter``.
- Containment / path-safety (realpath + prefixo por componentes) — SR-06, PATH-SAFETY.
- Staging, backup e quarentena (TRANSACTION-MODEL).
- Hash de conteúdo (blake2b — STATE-MODEL) e checagem de espaço.

Nenhum outro módulo pode chamar ``open(...,'w')``, ``os.rename/replace``,
``shutil`` mutável ou ``Path.write_*`` (verificado por tools/lint_boundaries.py).
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import secrets
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import TracebackType

from steamzero.core import paths
from steamzero.core.errors import SteamZeroError

_DIR_MODE = 0o700
_FILE_MODE = 0o600
_CHUNK = 1 << 20  # 1 MiB


# ===========================================================================
# Diretórios e permissões
# ===========================================================================
def ensure_dir(path: Path, *, mode: int = _DIR_MODE) -> Path:
    """Cria ``path`` (e pais) com permissão ``mode``; idempotente."""
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, mode)
    return path


def ensure_state_layout() -> None:
    """Cria a árvore de estado (state_home + subdiretórios) com 0700."""
    ensure_dir(paths.state_home())
    for factory in paths.STATE_SUBDIRS:
        ensure_dir(factory())


# ===========================================================================
# Escrita atômica
# ===========================================================================
def write_atomic(
    path: Path, data: bytes, *, mode: int = _FILE_MODE, fsync_dir: bool = True
) -> None:
    """Escreve ``data`` em ``path`` atomicamente (tmp+fsync+rename), 0600.

    Em crash no meio, ``path`` fica intacto (estado antigo ou ausente); o tmp
    órfão é removível por ``sweep_orphan_temps``. Base de AC-TX-02 / FI-10.
    """
    parent = path.parent
    ensure_dir(parent)
    tmp = parent / f".{path.name}.tmp.{os.getpid()}.{secrets.token_hex(6)}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        _write_all(fd, data)
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        _silent_unlink(tmp)
        raise
    else:
        os.close(fd)
    os.replace(tmp, path)
    if fsync_dir:
        _fsync_dir(parent)


def write_atomic_text(path: Path, text: str, *, mode: int = _FILE_MODE) -> None:
    write_atomic(path, text.encode("utf-8"), mode=mode)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def _fsync_dir(directory: Path) -> None:
    dfd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def _silent_unlink(path: Path) -> None:
    with contextlib.suppress(FileNotFoundError):
        os.unlink(path)


def sweep_orphan_temps(directory: Path) -> list[Path]:
    """Remove tmps órfãos (``.<nome>.tmp.*``) de ``directory``; retorna removidos.

    Usado no recovery pós-crash para garantir "zero temporários órfãos"
    (ROLLBACK-TESTS §6). Não recursivo por padrão.
    """
    removed: list[Path] = []
    if not directory.is_dir():
        return removed
    for entry in directory.iterdir():
        name = entry.name
        if name.startswith(".") and ".tmp." in name:
            _silent_unlink(entry)
            removed.append(entry)
    return removed


# ===========================================================================
# Append durável (log / journal)
# ===========================================================================
class AppendWriter:
    """Escritor append-only com fsync opcional. Base de core.log e core.journal."""

    def __init__(self, path: Path, *, mode: int = _FILE_MODE) -> None:
        ensure_dir(path.parent)
        self._path = path
        self._fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, mode)
        os.fchmod(self._fd, mode)

    @property
    def path(self) -> Path:
        return self._path

    def write_line(self, text: str, *, fsync: bool = False) -> None:
        _write_all(self._fd, (text + "\n").encode("utf-8"))
        if fsync:
            os.fsync(self._fd)

    def flush_fsync(self) -> None:
        os.fsync(self._fd)

    def close(self) -> None:
        os.close(self._fd)

    def __enter__(self) -> AppendWriter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


# ===========================================================================
# Containment / path-safety (SR-06, PATH-SAFETY)
# ===========================================================================
def is_within(root: Path, candidate: Path) -> bool:
    """True se ``candidate`` (após realpath) está dentro de ``root`` por componentes."""
    root_r = Path(os.path.realpath(root))
    cand_r = Path(os.path.realpath(candidate))
    return cand_r == root_r or root_r in cand_r.parents


def resolve_within(root: Path, candidate: Path) -> Path:
    """Resolve ``candidate`` e garante que está dentro de ``root``.

    Levanta ``E-CONTENT-UNSAFE-PATH`` em traversal, caminho absoluto que escapa
    ou symlink apontando para fora da raiz.
    """
    cand_r = Path(os.path.realpath(candidate))
    if not is_within(root, cand_r):
        raise SteamZeroError(
            "E-CONTENT-UNSAFE-PATH", detail=f"{candidate!s} escapa da raiz {root!s}"
        )
    return cand_r


def validate_relative_entry(name: str) -> PurePosixPath:
    """Valida um nome de entrada relativo (archive/import) — PATH-SAFETY §3.

    Rejeita: vazio, absoluto, ``..``, NUL/controle, drive/backslash. Retorna o
    caminho relativo POSIX normalizado (sem resolver no FS).
    """
    if not name:
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="entrada vazia")
    if "\x00" in name or any(ord(ch) < 0x20 for ch in name):
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="caractere de controle/NUL")
    if name.startswith("/") or name.startswith("\\") or "\\" in name:
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail=f"absoluto/backslash: {name!r}")
    if (  # drive do Windows: C:, C:\ , C:/ (não confundir com ':' válido em POSIX)
        len(name) >= 2
        and name[0].isascii()
        and name[0].isalpha()
        and name[1] == ":"
        and (len(name) == 2 or name[2] in "/\\")
    ):
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail=f"drive absoluto: {name!r}")
    rel = PurePosixPath(name)
    if rel.is_absolute() or any(part == ".." for part in rel.parts):
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail=f"traversal: {name!r}")
    return rel


# ===========================================================================
# Hash e espaço
# ===========================================================================
def hash_bytes(data: bytes) -> str:
    """blake2b hex de ``data`` (STATE-MODEL: hash_blake2b)."""
    return hashlib.blake2b(data).hexdigest()


def hash_file(path: Path) -> str:
    """blake2b hex do conteúdo de ``path`` (streaming)."""
    h = hashlib.blake2b()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def free_space(path: Path) -> int:
    """Bytes livres no filesystem que contém ``path`` (ou o ancestral existente)."""
    probe = path
    while not probe.exists():
        probe = probe.parent
    return shutil.disk_usage(probe).free


def same_filesystem(a: Path, b: Path) -> bool:
    """True se ``a`` e ``b`` (ou ancestrais existentes) estão no mesmo FS (st_dev)."""
    return _dev_of(a) == _dev_of(b)


def _dev_of(path: Path) -> int:
    probe = path
    while not probe.exists():
        probe = probe.parent
    return os.stat(probe).st_dev


# ===========================================================================
# Staging / backup / quarentena
# ===========================================================================
@dataclass(frozen=True)
class BackupEntry:
    """Entrada do manifesto de backup (BACKUP-FORMAT): relpath, hash, tamanho."""

    relpath: str
    hash: str
    size: int


def stage_bytes(operation_id: str, relname: str, data: bytes) -> Path:
    """Materializa ``data`` em ``staging/<opId>/<relname>`` (validado) atômico."""
    rel = validate_relative_entry(relname)
    base = paths.staging_for(operation_id)
    dest = resolve_within_staging(base, base / rel)
    write_atomic(dest, data)
    return dest


def resolve_within_staging(base: Path, candidate: Path) -> Path:
    """Como resolve_within, mas cria ``base`` antes (staging sempre existe)."""
    ensure_dir(base)
    return resolve_within(base, candidate)


def backup_file(operation_id: str, src: Path, relpath: str) -> BackupEntry:
    """Copia ``src`` para ``backups/<opId>/<relpath>`` e retorna a entrada com hash.

    Backup verificado: o hash é do arquivo copiado (destino), garantindo cópia
    íntegra (supera o pz_rollback que copia sem verificar — TRANSACTION-MODEL §5).
    """
    rel = validate_relative_entry(relpath)
    base = paths.backup_for(operation_id)
    dest = resolve_within_staging(base, base / rel)
    _copy_atomic(src, dest)
    digest = hash_file(dest)
    src_digest = hash_file(src)
    if digest != src_digest:
        raise SteamZeroError("E-STORAGE-IO", detail="cópia de backup divergente do original")
    return BackupEntry(relpath=str(rel), hash=digest, size=dest.stat().st_size)


def quarantine_file(operation_id: str, src: Path, relpath: str) -> Path:
    """Move ``src`` para ``quarantine/<opId>/<relpath>`` (nunca deleta) — P1/§7."""
    rel = validate_relative_entry(relpath)
    base = paths.quarantine_for(operation_id)
    dest = resolve_within_staging(base, base / rel)
    ensure_dir(dest.parent)
    _move(src, dest)
    return dest


def _copy_atomic(src: Path, dest: Path) -> None:
    """Copia ``src`` para ``dest`` via write_atomic (streaming em memória por chunk)."""
    ensure_dir(dest.parent)
    with open(src, "rb") as f:
        data = f.read()
    write_atomic(dest, data)


def _move(src: Path, dest: Path) -> None:
    if same_filesystem(src, dest):
        os.replace(src, dest)
    else:
        _copy_atomic(src, dest)
        os.unlink(src)


def iter_files(root: Path) -> Iterator[Path]:
    """Itera arquivos regulares sob ``root`` (para snapshots/verificação)."""
    if not root.exists():
        return
    for entry in sorted(root.rglob("*")):
        if entry.is_file() and not entry.is_symlink():
            yield entry
