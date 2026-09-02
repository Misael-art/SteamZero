# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Leitura segura do uso de armazenamento exposto pela central.

O inventário é deliberadamente limitado às raízes que o caller fornece. Ele
não segue symlinks, não varre a home inteira e não altera arquivos. Assim a UI
pode mostrar números reais sem transformar uma estatística em uma operação
destrutiva ou em uma sondagem arbitrária do host.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

StatVFS = Callable[[str | bytes | os.PathLike[str] | os.PathLike[bytes]], os.statvfs_result]


def _scan_root(root: Path) -> dict[str, Any]:
    absolute = root.absolute()
    if root.is_symlink() or any(parent.is_symlink() for parent in absolute.parents):
        return {
            "state": "blocked",
            "files": 0,
            "bytes": 0,
            "error": "a raiz ou um diretório pai simbólico não é contabilizado",
        }
    try:
        resolved = root.resolve(strict=True)
    except FileNotFoundError:
        return {"state": "missing", "files": 0, "bytes": 0, "error": "diretório ausente"}
    except OSError as exc:
        return {"state": "unreadable", "files": 0, "bytes": 0, "error": str(exc)}
    if not resolved.is_dir():
        return {
            "state": "invalid",
            "files": 0,
            "bytes": 0,
            "error": "o caminho não é um diretório",
        }

    files = 0
    total_bytes = 0
    errors = 0
    try:
        for candidate in resolved.rglob("*"):
            try:
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                files += 1
                total_bytes += candidate.stat().st_size
            except OSError:
                errors += 1
    except OSError as exc:
        return {
            "state": "unreadable",
            "files": files,
            "bytes": total_bytes,
            "error": str(exc),
        }
    return {
        "state": "degraded" if errors else "ready",
        "files": files,
        "bytes": total_bytes,
        "errors": errors,
        "error": "alguns arquivos não puderam ser lidos" if errors else None,
    }


def _aggregate_roots(roots: Iterable[Path]) -> dict[str, Any]:
    unique: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        try:
            identity = root.resolve(strict=False)
        except OSError:
            identity = root.absolute()
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(root)

    scans = [_scan_root(root) for root in unique]
    files = sum(int(scan["files"]) for scan in scans)
    total_bytes = sum(int(scan["bytes"]) for scan in scans)
    errors = sum(int(scan.get("errors", 0)) for scan in scans)
    if not scans:
        state = "empty"
        error = None
    elif any(scan["state"] in {"unreadable", "blocked", "invalid"} for scan in scans):
        state = "degraded"
        error = next(
            (str(scan["error"]) for scan in scans if scan.get("error")),
            "uma raiz não pôde ser lida",
        )
    elif all(scan["state"] == "missing" for scan in scans):
        state = "missing"
        error = "nenhum diretório foi encontrado"
    elif errors:
        state = "degraded"
        error = "alguns arquivos não puderam ser lidos"
    else:
        state = "ready" if files else "empty"
        error = None
    return {
        "state": state,
        "files": files,
        "bytes": total_bytes,
        "roots": len(unique),
        "error": error,
    }


def _aggregate_files(files: Iterable[Path]) -> dict[str, Any]:
    """Conta arquivos canônicos sem revarrer a raiz física inteira.

    Uma raiz de ROM pode conter mais de uma plataforma. Para uma superfície
    contextual, receber a lista de arquivos já classificados é a única forma
    de manter a métrica alinhada ao catálogo sem atribuir toda a raiz ao
    primeiro sistema encontrado.
    """
    unique: list[Path] = []
    seen: set[Path] = set()
    for file in files:
        absolute = file.absolute()
        if absolute not in seen:
            seen.add(absolute)
            unique.append(absolute)

    files_count = 0
    total_bytes = 0
    missing = 0
    errors = 0
    blocked = 0
    for file in unique:
        if file.is_symlink() or any(parent.is_symlink() for parent in file.parents):
            blocked += 1
            continue
        try:
            if not file.exists():
                missing += 1
                continue
            if not file.is_file():
                errors += 1
                continue
            files_count += 1
            total_bytes += file.stat().st_size
        except OSError:
            errors += 1

    if blocked or errors:
        state = "degraded"
        error = "alguns arquivos canônicos não puderam ser lidos"
    elif missing and files_count == 0:
        state = "missing"
        error = "nenhum arquivo canônico foi encontrado"
    elif missing:
        state = "degraded"
        error = f"{missing} arquivo(s) canônico(s) não encontrado(s)"
    else:
        state = "ready" if files_count else "empty"
        error = None
    return {
        "state": state,
        "files": files_count,
        "bytes": total_bytes,
        "roots": len({file.parent for file in unique}),
        "error": error,
    }


def _volume(root: Path, statvfs: StatVFS) -> dict[str, Any]:
    try:
        info = statvfs(str(root))
    except OSError as exc:
        return {
            "state": "unavailable",
            "capacityBytes": None,
            "freeBytes": None,
            "usedBytes": None,
            "error": str(exc),
        }
    capacity = int(info.f_blocks * info.f_frsize)
    free = int(info.f_bavail * info.f_frsize)
    return {
        "state": "ready",
        "capacityBytes": capacity,
        "freeBytes": free,
        "usedBytes": max(0, capacity - free),
        "error": None,
    }


def collect_storage_summary(
    *,
    rom_roots: Sequence[Path],
    emulator_roots: Sequence[Path],
    saves_root: Path,
    media_root: Path,
    cache_roots: Sequence[Path],
    volume_root: Path,
    rom_files: Sequence[Path] | None = None,
    platform_id: str | None = None,
    statvfs: StatVFS = os.statvfs,
) -> dict[str, Any]:
    """Retorna o uso observado das categorias gerenciadas pela emulação."""
    definitions = (
        ("roms", "ROMs", rom_roots),
        ("emulators", "Emuladores", emulator_roots),
        ("saves", "Saves", (saves_root,)),
        ("media", "Mídia", (media_root,)),
        ("cache", "Cache", cache_roots),
    )
    buckets: list[dict[str, Any]] = []
    for bucket_id, label, roots in definitions:
        values = (
            _aggregate_files(rom_files)
            if bucket_id == "roms" and rom_files is not None
            else _aggregate_roots(roots)
        )
        buckets.append({"id": bucket_id, "label": label, **values})
    total_files = sum(int(bucket["files"]) for bucket in buckets)
    total_bytes = sum(int(bucket["bytes"]) for bucket in buckets)
    return {
        "schemaVersion": 1,
        "buckets": buckets,
        "totals": {"files": total_files, "bytes": total_bytes},
        "volume": _volume(volume_root, statvfs),
        "scope": {
            "platformId": platform_id or "global",
            "romFiles": len(rom_files) if rom_files is not None else None,
        },
    }
