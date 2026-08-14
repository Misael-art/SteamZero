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
import errno
import os
import secrets
import shutil
import signal
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import TracebackType
from typing import IO

from steamzero.core import crypto, paths
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


def ensure_private_child(
    parent: Path,
    name: str,
    *,
    uid: int | None = None,
    mode: int = _DIR_MODE,
) -> Path:
    """Cria/valida um subdiretório privado sem seguir symlinks.

    A abertura relativa a ``parent`` com ``O_NOFOLLOW`` evita que um nome
    previsível em diretório compartilhado seja trocado por symlink entre a
    validação e o uso. Diretórios preexistentes nunca têm ownership ou modo
    "corrigidos" silenciosamente: estado inseguro falha fechado.
    """
    if not name or name in {".", ".."} or "/" in name or "\0" in name:
        raise ValueError("nome de subdiretório inválido")
    expected_uid = os.getuid() if uid is None else uid
    flags = os.O_RDONLY | os.O_DIRECTORY
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        parent_fd = os.open(parent, flags)
    except OSError as exc:
        raise PermissionError(f"diretório pai inseguro: {parent}") from exc
    created = False
    try:
        try:
            os.mkdir(name, mode, dir_fd=parent_fd)
            created = True
        except FileExistsError:
            pass
        if created:
            os.chmod(name, mode, dir_fd=parent_fd, follow_symlinks=False)
            os.fsync(parent_fd)
        try:
            child_fd = os.open(name, flags, dir_fd=parent_fd)
        except OSError as exc:
            raise PermissionError(f"subdiretório privado inseguro: {parent / name}") from exc
        try:
            metadata = os.fstat(child_fd)
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != expected_uid
                or stat.S_IMODE(metadata.st_mode) != mode
            ):
                raise PermissionError(f"subdiretório privado inseguro: {parent / name}")
        finally:
            os.close(child_fd)
    finally:
        os.close(parent_fd)
    return parent / name


def ensure_state_layout() -> None:
    """Cria a árvore de estado (state_home + subdiretórios) com 0700."""
    ensure_dir(paths.state_home())
    for factory in paths.STATE_SUBDIRS:
        ensure_dir(factory())


def set_mode(path: Path, mode: int) -> None:
    """Aplica permissões a um caminho pela porta central de escrita."""
    os.chmod(path, mode)


# ===========================================================================
# Escrita atômica
# ===========================================================================
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1 << 0
_RENAME_EXCHANGE = 1 << 1


def _renameat2(first: Path, second: Path, flags: int) -> bool:
    """``renameat2`` cru. ``False`` quando kernel/FS não suportam a flag."""
    import ctypes
    import ctypes.util

    libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)
    try:
        syscall = libc.renameat2
    except AttributeError:  # pragma: no cover - glibc antiga
        return False
    result = syscall(
        ctypes.c_int(_AT_FDCWD),
        ctypes.c_char_p(bytes(first)),
        ctypes.c_int(_AT_FDCWD),
        ctypes.c_char_p(bytes(second)),
        ctypes.c_uint(flags),
    )
    if result == 0:
        return True
    errno = ctypes.get_errno()
    if errno in {38, 22, 95}:  # ENOSYS, EINVAL, EOPNOTSUPP
        return False
    raise OSError(errno, os.strerror(errno), str(first))


def _rename_noreplace(src: Path, dst: Path) -> bool:
    """Move ``src`` para ``dst`` SEM substituir. ``False`` se não suportado.

    É a primitiva que sustenta a custódia: mover sem substituir é a única forma
    de *tomar* uma entrada do sistema de arquivos sem correr o risco de destruir
    o que estiver no destino.
    """
    if dst.exists() or dst.is_symlink():
        raise FileExistsError(f"destino já existe: {dst}")
    return _renameat2(src, dst, _RENAME_NOREPLACE)


def take_custody(path: Path, holding: Path) -> Path | None:
    """Retira ``path`` do lugar e o guarda, ATOMICAMENTE, sem substituir nada.

    Devolve o caminho sob custódia, ou ``None`` se ``path`` não existia.

    Existe porque conferir o alvo e só então destruí-lo nunca fecha a janela:
    entre a conferência e o syscall cabe uma troca. Tomando a entrada primeiro,
    tudo que vem depois — verificar, publicar, remover — acontece sobre algo que
    já está sob nosso controle, e o que for inesperado pode ser devolvido
    intacto.

    Falha FECHADA quando o sistema de arquivos não oferece a primitiva: sem ela
    não há como preservar o inesperado, e arriscar seria pior que recusar.
    """
    ensure_dir(holding)
    destino = holding / f"custody.{os.getpid()}.{secrets.token_hex(8)}"
    return take_custody_named(path, destino)


def take_custody_named(path: Path, custody: Path) -> Path | None:
    """Variante determinística de ``take_custody`` (nome de custódia explícito).

    O nome determinístico é o que torna a custódia RECUPERÁVEL: o journal grava
    a intenção com o caminho exato antes do rename, e um recovery posterior
    encontra a entrada pelo mesmo caminho. ``None`` se ``path`` não existia.
    """
    ensure_dir(custody.parent)
    try:
        if not _rename_noreplace(path, custody):
            raise SteamZeroError(
                "E-TX-STALE-PLAN",
                detail=(
                    "sistema de arquivos sem rename atômico sem substituição "
                    f"(renameat2/RENAME_NOREPLACE); recusando tocar {path}"
                ),
            )
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno == errno.EXDEV:
            raise SteamZeroError(
                "E-TX-CUSTODY-CROSS-FS",
                detail=(
                    f"alvo {path} está em outro filesystem que a área de custódia "
                    f"{custody.parent}; tomada atômica impossível"
                ),
            ) from exc
        raise
    _crash_apos_o_rename()
    return custody


def _crash_apos_o_rename() -> None:
    """Gate de crash DENTRO da janela rename→taken (somente teste).

    Dispara logo após o rename da custódia ter executado, antes de
    ``take_custody_named`` retornar ao chamador — o MESMO efeito de um SIGKILL
    entre o syscall e o registro do ``custody.taken`` no journal. Sem a
    variável de ambiente, não faz nada.
    """
    if os.environ.get("STEAMZERO_CRASH_AT") == "custody.after-rename":
        os.kill(os.getpid(), signal.SIGKILL)


def release_custody(custody: Path) -> None:
    """Remove uma entrada sob custódia (já verificada) e persiste o diretório."""
    _silent_unlink(custody)
    _fsync_dir(custody.parent)


def discard_tmp(tmp: Path) -> None:
    """Remove um temporário sem persistir (limpeza de falha)."""
    _silent_unlink(tmp)


def return_custody(custody: Path, path: Path) -> None:
    """Devolve ao lugar o que foi tomado, sem substituir o que apareceu.

    Se algo novo ocupou ``path`` nesse meio-tempo, a devolução falha e o
    conteúdo PERMANECE sob custódia — nada é destruído, e o erro nomeia os dois
    caminhos para que a recuperação seja possível.
    """
    try:
        if not _rename_noreplace(custody, path):
            raise SteamZeroError(
                "E-TX-ROLLBACK-FAILED",
                detail=f"não foi possível devolver {custody} para {path}",
            )
        _fsync_dir(path.parent)
    except FileExistsError as exc:
        raise SteamZeroError(
            "E-TX-ROLLBACK-FAILED",
            detail=(
                f"{path} foi ocupado durante a operação; o conteúdo anterior "
                f"permanece preservado em {custody}"
            ),
        ) from exc
    except OSError as exc:
        if exc.errno == errno.EXDEV:
            raise SteamZeroError(
                "E-TX-CUSTODY-CROSS-FS",
                detail=f"devolução da custódia {custody} cruzaria filesystems até {path}",
            ) from exc
        raise


def write_tmp(parent: Path, data: bytes, *, mode: int = _FILE_MODE) -> Path:
    """Cria um temporário no diretório do alvo com conteúdo e fsync.

    O temporário vive no diretório do alvo de propósito: publicá-lo depois por
    ``publish_link`` exige o mesmo filesystem, e qualquer fallback que cruze
    filesystems reintroduziria a janela que a custódia fecha.
    """
    ensure_dir(parent)
    tmp = parent / f".{secrets.token_hex(6)}.tmp.{os.getpid()}"
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
    return tmp


def publish_link(tmp: Path, path: Path) -> None:
    """Publica ``tmp`` em ``path`` por link exclusivo — nunca sobrescreve.

    ``os.link`` cria apenas se o destino não existir (pelo menos atomically
    quanto o `rename`), então não há janela entre conferir e publicar. O
    temporário é removido depois; o diretório é persistido.
    """
    os.link(tmp, path)
    _silent_unlink(tmp)
    _fsync_dir(path.parent)


def publish_symlink(tmp: Path, path: Path) -> None:
    """Publica um symlink por link exclusivo do próprio symlink.

    O temporário é um symlink e o hard link preserva a entrada sem seguir o
    alvo (``follow_symlinks=False``): o destino só é criado se estiver vazio.
    """
    os.link(tmp, path, follow_symlinks=False)
    _silent_unlink(tmp)
    _fsync_dir(path.parent)


def make_symlink_tmp(parent: Path, name: str, source: Path) -> Path:
    """Cria um symlink temporário no diretório do destino (absolute realpath).

    Devolve o caminho do temporário; ``publish_symlink`` o publica e o remove.
    """
    ensure_dir(parent)
    tmp = parent / f".{name}.tmp.{os.getpid()}.{secrets.token_hex(6)}"
    os.symlink(str(Path(os.path.realpath(source))), tmp)
    return tmp


def copy_exclusive(src: Path, dest: Path, *, mode: int = _FILE_MODE) -> None:
    """Copia ``src`` para ``dest`` publicando por link exclusivo (sem janela).

    Usada quando o destino precisa ser criado SEM substituir o que aparecer:
    o temporário vive no diretório do destino e a publicação é ``publish_link``.
    """
    tmp = write_tmp(dest.parent, b"", mode=mode)
    try:
        src_fd = os.open(src, os.O_RDONLY)
        try:
            dst_fd = os.open(tmp, os.O_WRONLY | os.O_APPEND)
            try:
                while chunk := os.read(src_fd, _CHUNK):
                    _write_all(dst_fd, chunk)
                os.fsync(dst_fd)
            finally:
                os.close(dst_fd)
        finally:
            os.close(src_fd)
    except BaseException:
        _silent_unlink(tmp)
        raise
    publish_link(tmp, dest)


def move_file_noreplace(src: Path, dest: Path) -> None:
    """Move ``src`` para ``dest`` SEM substituir o que estiver no destino.

    No mesmo filesystem usa ``renameat2(RENAME_NOREPLACE)``. Entre filesystems
    (ou em FS sem a flag) faz cópia verificada por link exclusivo antes de
    remover a origem — a remoção da origem só acontece depois que o destino já
    é uma cópia íntegra e publicada.
    """
    ensure_dir(dest.parent)
    if dest.exists() or dest.is_symlink():
        raise FileExistsError(f"destino já existe: {dest}")
    try:
        if _rename_noreplace(src, dest):
            _fsync_dir(dest.parent)
            if src.parent != dest.parent:
                _fsync_dir(src.parent)
            return
        raise SteamZeroError(
            "E-TX-STALE-PLAN",
            detail=f"filesystem sem rename sem substituição para mover {src}",
        )
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
    copy_exclusive(src, dest)
    _silent_unlink(src)
    _fsync_dir(src.parent)


def _rename_exchange(first: Path, second: Path) -> bool:
    """Troca dois caminhos ATOMICAMENTE (``renameat2`` + ``RENAME_EXCHANGE``).

    Devolve ``False`` quando o kernel ou o filesystem não suportam. É o único
    jeito de publicar sobre um arquivo existente sem janela: verificar antes do
    ``rename`` sempre deixa um intervalo em que o alvo pode ser trocado, e é
    dentro dele que um arquivo alheio seria destruído.
    """
    import ctypes
    import ctypes.util

    return _renameat2(first, second, _RENAME_EXCHANGE)


def write_atomic(
    path: Path,
    data: bytes,
    *,
    mode: int = _FILE_MODE,
    fsync_dir: bool = True,
    must_not_exist: bool = False,
    expect_hash: str | None = None,
    holding: Path | None = None,
) -> None:
    """Escreve ``data`` em ``path`` atomicamente (tmp+fsync+rename), 0600.

    Em crash no meio, ``path`` fica intacto (estado antigo ou ausente); o tmp
    órfão é removível por ``sweep_orphan_temps``. Base de AC-TX-02 / FI-10.

    Com ``must_not_exist``, a publicação usa ``os.link`` e falha com
    ``FileExistsError`` se o destino existir. É a única forma ATÔMICA de dizer
    "crie, mas não sobrescreva": qualquer verificação anterior ao ``rename``
    deixa uma janela, e é dentro dela que um arquivo alheio seria destruído.

    Com ``expect_hash``, a publicação sobre um arquivo EXISTENTE é condicionada
    à identidade dele: a troca é atômica (``RENAME_EXCHANGE``) e o conteúdo que
    saiu é conferido depois. Se não for o esperado, a troca é DESFEITA e a
    operação falha — o arquivo alheio volta ao lugar intacto.
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
    try:
        if must_not_exist:
            os.link(tmp, path)
            _silent_unlink(tmp)
        elif expect_hash is not None:
            if holding is None:
                raise SteamZeroError(
                    "E-TX-STALE-PLAN", detail="publicação verificada exige área de custódia"
                )
            _publish_verified(tmp, path, expect_hash, holding)
        else:
            os.replace(tmp, path)
    except BaseException:
        _silent_unlink(tmp)
        raise
    if fsync_dir:
        _fsync_dir(parent)


def _publish_verified(tmp: Path, path: Path, expect_hash: str, holding: Path) -> None:
    """Publica sobre um alvo existente tomando-o em custódia primeiro.

    A ordem importa e é o ponto inteiro: primeiro TIRA o alvo do lugar (sem
    substituir nada), depois confere o que tirou, e só então publica no lugar
    agora vazio. Nada destrutivo acontece sobre uma entrada que ainda não
    inspecionamos, então não existe janela entre conferir e destruir — que era o
    defeito que três correções seguidas não fecharam.
    """
    custody = take_custody(path, holding)
    if custody is None:
        # Sumiu entre a decisão e a publicação: criar é seguro, e se algo
        # aparecer no caminho a criação exclusiva recusa.
        os.link(tmp, path)
        _silent_unlink(tmp)
        return
    if hash_file(custody) != expect_hash:
        return_custody(custody, path)
        raise SteamZeroError("E-TX-STALE-PLAN", detail=f"alvo mudou antes de publicar: {path}")
    try:
        os.link(tmp, path)
    except OSError:
        return_custody(custody, path)
        raise
    _silent_unlink(tmp)
    _silent_unlink(custody)


def delete_verified(path: Path, expect_hash: str | None, holding: Path) -> None:
    """Remove ``path`` só se ele ainda for o que esperávamos — sem janela.

    Toma a entrada em custódia antes de qualquer conferência. O que não for
    reconhecido volta para o lugar intacto em vez de ser removido.
    """
    custody = take_custody(path, holding)
    if custody is None:
        return
    if expect_hash is not None and hash_file(custody) != expect_hash:
        return_custody(custody, path)
        raise SteamZeroError(
            "E-TX-ROLLBACK-FAILED", detail=f"rollback recusou remover arquivo alterado: {path}"
        )
    _silent_unlink(custody)


def restore_verified(
    backup: Path, path: Path, accepted: set[str], holding: Path, *, mode: int = _FILE_MODE
) -> None:
    """Restaura ``backup`` sobre ``path`` sem sobrescrever o inesperado."""
    custody = take_custody(path, holding)
    if custody is not None and hash_file(custody) not in accepted:
        return_custody(custody, path)
        raise SteamZeroError(
            "E-TX-ROLLBACK-FAILED",
            detail=f"rollback recusou sobrescrever arquivo alterado: {path}",
        )
    tmp = path.parent / f".{path.name}.tmp.{os.getpid()}.{secrets.token_hex(6)}"
    try:
        copy_file_atomic(backup, tmp, mode=mode)
        os.link(tmp, path)
    except BaseException:
        _silent_unlink(tmp)
        if custody is not None:
            return_custody(custody, path)
        raise
    _silent_unlink(tmp)
    if custody is not None:
        _silent_unlink(custody)


def write_atomic_text(path: Path, text: str, *, mode: int = _FILE_MODE) -> None:
    write_atomic(path, text.encode("utf-8"), mode=mode)


def write_stream_atomic(
    path: Path,
    source: IO[bytes],
    *,
    max_bytes: int,
    mode: int = _FILE_MODE,
) -> int:
    """Publica um stream com limite estrito sem materializá-lo em memória."""
    parent = ensure_dir(path.parent)
    tmp = parent / f".{path.name}.tmp.{os.getpid()}.{secrets.token_hex(6)}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    written = 0
    try:
        while chunk := source.read(_CHUNK):
            written += len(chunk)
            if written > max_bytes:
                raise SteamZeroError("E-CONTENT-LIMIT", detail="stream excede limite seguro")
            _write_all(fd, chunk)
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        _silent_unlink(tmp)
        raise
    else:
        os.close(fd)
    os.replace(tmp, path)
    _fsync_dir(parent)
    return written


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


def remove_file(path: Path) -> None:
    """Remove um arquivo (idempotente). Deleção também passa pela porta core.fs."""
    _silent_unlink(path)


def remove_tree(path: Path) -> None:
    """Remove uma árvore de diretório (idempotente). Usado no GC de staging."""
    if path.exists():
        shutil.rmtree(path)


def move_tree(src: Path, dest: Path) -> None:
    """Move uma árvore para outro local, suportando cross-filesystem.

    Tenta rename atômico primeiro; se cruzar filesystems, faz cópia+remoção.
    """
    if not src.exists():
        raise SteamZeroError("E-TX-STALE-PLAN", detail=f"origem inválida: {src}")
    if dest.exists() or dest.is_symlink():
        raise SteamZeroError("E-TX-STALE-PLAN", detail=f"destino já existe: {dest}")
    ensure_dir(dest.parent)
    try:
        src.rename(dest)
    except OSError:
        shutil.copytree(src, dest, symlinks=False, dirs_exist_ok=False)
        remove_tree(src)


def copy_file_atomic(src: Path, dest: Path, *, mode: int = _FILE_MODE) -> None:
    """Copia um arquivo em streaming e publica ``dest`` atomicamente.

    O temporário vive no diretório de destino, portanto o ``replace`` final é
    atômico. A função não carrega ROMs/imagens grandes inteiras na memória.

    """
    parent = ensure_dir(dest.parent)
    tmp = parent / f".{dest.name}.tmp.{os.getpid()}.{secrets.token_hex(6)}"
    dst_fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        src_fd = os.open(src, os.O_RDONLY)
        try:
            while chunk := os.read(src_fd, _CHUNK):
                _write_all(dst_fd, chunk)
        finally:
            os.close(src_fd)
        os.fsync(dst_fd)
    except BaseException:
        _silent_unlink(tmp)
        raise
    finally:
        os.close(dst_fd)
    os.replace(tmp, dest)
    _fsync_dir(parent)


def copy_file_range_atomic(
    src: Path,
    dest: Path,
    *,
    offset: int,
    length: int,
    mode: int = _FILE_MODE,
) -> None:
    """Copia um intervalo regular sem carregar containers grandes na memória."""
    if offset < 0 or length < 0 or src.is_symlink() or not src.is_file():
        raise SteamZeroError("E-STORAGE-IO", detail="intervalo de cópia inválido")
    if offset + length > src.stat().st_size:
        raise SteamZeroError("E-STORAGE-IO", detail="intervalo excede o arquivo de origem")
    parent = ensure_dir(dest.parent)
    tmp = parent / f".{dest.name}.tmp.{os.getpid()}.{secrets.token_hex(6)}"
    dst_fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        src_fd = os.open(src, os.O_RDONLY)
        try:
            os.lseek(src_fd, offset, os.SEEK_SET)
            remaining = length
            while remaining:
                chunk = os.read(src_fd, min(_CHUNK, remaining))
                if not chunk:
                    raise SteamZeroError(
                        "E-STORAGE-IO", detail="origem terminou antes do intervalo"
                    )
                _write_all(dst_fd, chunk)
                remaining -= len(chunk)
        finally:
            os.close(src_fd)
        os.fsync(dst_fd)
    except BaseException:
        _silent_unlink(tmp)
        raise
    finally:
        os.close(dst_fd)
    os.replace(tmp, dest)
    _fsync_dir(parent)


def move_file(src: Path, dest: Path) -> None:
    """Move ``src`` para ``dest`` pela porta central de escrita.

    No mesmo filesystem usa rename atômico; entre filesystems faz
    copy+fsync+replace antes de remover a origem. O chamador é responsável por
    congelar/revalidar a precondição do destino antes da chamada.
    """
    ensure_dir(dest.parent)
    _move(src, dest)


def move_path_atomic(src: Path, dest: Path) -> None:
    """Move arquivo ou diretório no mesmo filesystem por rename atômico.

    Usado por operações destrutivas que primeiro retiram um cache do namespace
    ativo e só depois o removem. Nunca faz cópia implícita de uma árvore.
    """
    if src.is_symlink() or not src.exists():
        raise SteamZeroError("E-TX-STALE-PLAN", detail=f"origem inválida: {src}")
    if dest.exists() or dest.is_symlink():
        raise SteamZeroError("E-TX-STALE-PLAN", detail=f"destino já existe: {dest}")
    ensure_dir(dest.parent)
    if not same_filesystem(src, dest.parent):
        raise SteamZeroError("E-STORAGE-IO", detail="rename destrutivo cruza filesystems")
    os.replace(src, dest)
    _fsync_dir(dest.parent)
    if src.parent != dest.parent:
        _fsync_dir(src.parent)


def remove_path(path: Path) -> None:
    """Remove arquivo ou árvore sem seguir symlink."""
    if path.is_symlink():
        _silent_unlink(path)
    elif path.is_dir():
        shutil.rmtree(path)
    else:
        _silent_unlink(path)


def symlink_atomic(source: Path, target: Path) -> None:
    """Publica um symlink por troca atômica e persiste o diretório.

    ``source`` é gravado como caminho absoluto para que o consumidor não dependa
    do diretório corrente. O temporário é removido se a criação falhar.
    """
    parent = ensure_dir(target.parent)
    tmp = parent / f".{target.name}.tmp.{os.getpid()}.{secrets.token_hex(6)}"
    try:
        os.symlink(str(Path(os.path.realpath(source))), tmp)
        os.replace(tmp, target)
        _fsync_dir(parent)
    except BaseException:
        _silent_unlink(tmp)
        raise


def rotate_log(path: Path, *, keep: int = 3) -> None:
    """Rotaciona ``path`` -> ``path.1`` -> ... -> ``path.<keep>`` (o mais antigo cai).

    No-op se ``path`` não existe. Escrita centralizada aqui (core.fs é a porta).
    """
    if not path.exists():
        return
    oldest = path.with_name(f"{path.name}.{keep}")
    _silent_unlink(oldest)
    for i in range(keep - 1, 0, -1):
        src = path.with_name(f"{path.name}.{i}")
        if src.exists():
            os.replace(src, path.with_name(f"{path.name}.{i + 1}"))
    os.replace(path, path.with_name(f"{path.name}.1"))


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
        self._closed = False

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
        if not self._closed:
            os.close(self._fd)
            self._closed = True

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
def hash_bytes(data: bytes, *, algo: str = "blake2b") -> str:
    """Hash hex de ``data`` (default blake2b — STATE-MODEL; ``sha256`` p/ bios-db)."""
    return crypto.digest_bytes(data, algorithm=algo).hexdigest


def hash_file(path: Path, *, algo: str = "blake2b") -> str:
    """Hash hex do conteúdo de ``path`` (streaming). ``algo`` = blake2b | sha256."""
    return crypto.digest_file(path, algorithm=algo).hexdigest


def read_at(path: Path, offset: int, length: int) -> bytes:
    """Lê ``length`` bytes a partir de ``offset`` (leitura defensiva de header).

    Devolve menos bytes no EOF; ``OSError`` (permissão, symlink, arquivo
    somem) propaga para o chamador tratar como diagnóstico. Não abre symlink
    (FM-13): um symlink é recusado antes da leitura.
    """
    if offset < 0 or length < 0:
        raise ValueError("offset e length precisam ser não negativos")
    if path.is_symlink():
        raise OSError(f"leitura recusada: {path} é symlink")
    with path.open("rb") as handle:
        if offset:
            handle.seek(offset)
        return handle.read(length)


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
    """Compatibilidade interna para cópia atômica em streaming."""
    copy_file_atomic(src, dest)


def _move(src: Path, dest: Path) -> None:
    if same_filesystem(src, dest):
        os.replace(src, dest)
        _fsync_dir(dest.parent)
        if src.parent != dest.parent:
            _fsync_dir(src.parent)
    else:
        _copy_atomic(src, dest)
        os.unlink(src)
        _fsync_dir(src.parent)


def iter_files(root: Path) -> Iterator[Path]:
    """Itera arquivos regulares sob ``root`` (para snapshots/verificação)."""
    if not root.exists():
        return
    for entry in sorted(root.rglob("*")):
        if entry.is_file() and not entry.is_symlink():
            yield entry
