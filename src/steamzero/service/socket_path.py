# SPDX-License-Identifier: GPL-3.0-or-later
"""Resolução compartilhada e fail-closed do socket AF_UNIX do core."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

from steamzero.core import fs, paths

# ``sockaddr_un.sun_path`` possui 108 bytes no Linux e caminhos de filesystem
# precisam reservar o byte NUL final.
_AF_UNIX_PATH_MAX = 107
_FALLBACK_ROOT = Path("/tmp")  # noqa: S108 - raiz curta Linux validada antes do uso
_SOCKET_NAME = "core.sock"


def safe_socket_path() -> Path:
    """Retorna o mesmo caminho bindável e seguro para cliente e servidor.

    O layout XDG normal permanece inalterado (inclusive para socket activation
    do systemd). Apenas candidatos que excedem ``sun_path`` — ou o default
    ausente de uma sessão sem ``XDG_RUNTIME_DIR`` — usam um diretório curto,
    determinístico e privado ao UID sob ``/tmp``.
    """
    runtime = paths.runtime_dir()
    socket_path = runtime / _SOCKET_NAME
    explicit_runtime = bool(os.environ.get("XDG_RUNTIME_DIR"))
    try:
        _validate_xdg_root(runtime.parent)
    except FileNotFoundError:
        if explicit_runtime:
            raise PermissionError(f"XDG runtime inexistente: {runtime.parent}") from None
        socket_path = _fallback_socket_path(socket_path)
    else:
        if len(os.fsencode(socket_path)) > _AF_UNIX_PATH_MAX:
            socket_path = _fallback_socket_path(socket_path)
        else:
            runtime = fs.ensure_private_child(runtime.parent, runtime.name)
            socket_path = runtime / _SOCKET_NAME
    _validate_existing_socket(socket_path)
    return socket_path


def _validate_xdg_root(root: Path) -> None:
    metadata = root.lstat()
    if (
        root.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise PermissionError(f"XDG runtime inseguro: {root}")


def _fallback_socket_path(original: Path) -> Path:
    _validate_fallback_root()
    uid = os.getuid()
    digest = hashlib.blake2b(
        os.fsencode(original), digest_size=12, person=b"steamzero-ipc"
    ).hexdigest()
    directory = fs.ensure_private_child(
        _FALLBACK_ROOT,
        f"steamzero-{uid}-{digest}",
        uid=uid,
        mode=0o700,
    )
    path = directory / _SOCKET_NAME
    if len(os.fsencode(path)) > _AF_UNIX_PATH_MAX:
        raise RuntimeError("fallback AF_UNIX excede sun_path")
    return path


def _validate_fallback_root() -> None:
    metadata = _FALLBACK_ROOT.lstat()
    allowed_owner = metadata.st_uid in {0, os.getuid()}
    if (
        _FALLBACK_ROOT.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or not allowed_owner
        or not metadata.st_mode & stat.S_ISVTX
    ):
        raise PermissionError(f"raiz de fallback insegura: {_FALLBACK_ROOT}")


def _validate_existing_socket(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if (
        path.is_symlink()
        or not stat.S_ISSOCK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise PermissionError(f"caminho do socket inseguro: {path}")
