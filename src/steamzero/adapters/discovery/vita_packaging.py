# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Empacotamento derivado e não destrutivo de instalações Vita3K."""

from __future__ import annotations

import os
import re
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path

from steamzero.adapters.discovery.vita_sfo import read_vita_metadata
from steamzero.core import fs
from steamzero.core.errors import SteamZeroError

_TITLE_ID_RE = re.compile(r"^[A-Z]{4}[0-9]{5}$")
_FORBIDDEN_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_PACKAGE_SPACE_MARGIN = 8 * 1024**2
_ZIP_MEMBER_OVERHEAD_ESTIMATE = 1024


@dataclass(frozen=True)
class VitaPackagePlan:
    source_app: Path
    destination: Path
    title: str
    title_id: str
    files: int
    source_bytes: int
    estimated_output_bytes: int
    required_space_bytes: int


def canonical_vita_filename(title: str, title_id: str) -> str:
    """Nome editorial estável, mantendo o Title ID como identidade técnica."""
    normalized_title = unicodedata.normalize("NFC", " ".join(title.split()))
    normalized_title = _FORBIDDEN_FILENAME_CHARS.sub("-", normalized_title)
    normalized_title = normalized_title.rstrip(" .") or "PlayStation Vita game"
    normalized_id = title_id.strip().upper()
    if _TITLE_ID_RE.fullmatch(normalized_id) is None:
        raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="Title ID Vita inválido")
    return f"{normalized_title} [{normalized_id}].zip"


def _validate_app(source_app: Path, title_id: str) -> tuple[str, tuple[Path, ...], int]:
    if source_app.is_symlink() or not source_app.is_dir():
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="app Vita3K inválido")
    if _TITLE_ID_RE.fullmatch(source_app.name) is None:
        raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="pasta Vita3K sem Title ID")
    normalized_id = title_id.strip().upper()
    if source_app.name != normalized_id:
        raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="pasta e Title ID divergem")
    required = (source_app / "sce_sys" / "param.sfo", source_app / "eboot.bin")
    if any(item.is_symlink() or not item.is_file() for item in required):
        raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="app Vita3K sem param.sfo/eboot.bin")
    files: list[Path] = []
    for path in sorted(source_app.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if path.is_symlink():
            raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail=f"symlink na app Vita3K: {path}")
        if path.is_file():
            files.append(path)
    source_bytes = sum(path.stat().st_size for path in files)
    return normalized_id, tuple(files), source_bytes


def plan_vita_package(
    source_app: Path, *, title: str, title_id: str, derived_root: Path
) -> VitaPackagePlan:
    """Valida uma app Vita3K e calcula seu destino gerenciado, sem escrever."""
    normalized_id, files, source_bytes = _validate_app(source_app, title_id)
    destination = derived_root / canonical_vita_filename(title, normalized_id)
    if destination.is_symlink() or (destination.exists() and not destination.is_file()):
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="destino Vita derivado inválido")
    if destination.is_file():
        raise SteamZeroError("E-TX-STALE-PLAN", detail="pacote Vita derivado já existe")
    estimated_output_bytes = source_bytes + len(files) * _ZIP_MEMBER_OVERHEAD_ESTIMATE
    required_space_bytes = estimated_output_bytes + _PACKAGE_SPACE_MARGIN
    return VitaPackagePlan(
        source_app,
        destination,
        title,
        normalized_id,
        len(files),
        source_bytes,
        estimated_output_bytes,
        required_space_bytes,
    )


def package_vita_app(plan: VitaPackagePlan) -> dict[str, object]:
    """Cria ZIP Vita3K em staging local e publica atomicamente o derivado.

    O ZIP contém o conteúdo da app na raiz (não ``app/<Title ID>/``), que é o
    mesmo contrato observado nos cinco archives Vita existentes. A origem só é
    lida e nunca é renomeada, apagada ou alterada.
    """
    normalized_id, files, source_bytes = _validate_app(plan.source_app, plan.title_id)
    if (
        normalized_id != plan.title_id
        or len(files) != plan.files
        or source_bytes != plan.source_bytes
    ):
        raise SteamZeroError("E-TX-STALE-PLAN", detail="app Vita3K mudou desde o plano")
    if fs.free_space(plan.destination.parent) < plan.required_space_bytes:
        raise SteamZeroError(
            "E-STORAGE-SPACE",
            detail=(
                f"necessários ~{plan.required_space_bytes} bytes livres em "
                f"{plan.destination.parent}"
            ),
        )
    fs.ensure_dir(plan.destination.parent)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{plan.destination.name}.", suffix=".tmp", dir=plan.destination.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive.write(path, path.relative_to(plan.source_app).as_posix())
        fs.move_file_noreplace(temporary, plan.destination)
    finally:
        fs.remove_file(temporary)
    with zipfile.ZipFile(plan.destination) as archive:
        names = set(archive.namelist())
        if "sce_sys/param.sfo" not in names or "eboot.bin" not in names:
            raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="ZIP Vita derivado incompleto")
    return {
        "status": "materialized",
        "destination": str(plan.destination),
        "title": plan.title,
        "titleId": plan.title_id,
        "files": plan.files,
    }


def plan_from_app(source_app: Path, *, derived_root: Path) -> VitaPackagePlan:
    """Deriva título e identidade do SFO antes de calcular o pacote."""
    metadata = read_vita_metadata(source_app)
    if metadata.identity is None or not metadata.title:
        raise SteamZeroError("E-CONTENT-INCOMPLETE", detail=metadata.diagnosis)
    return plan_vita_package(
        source_app,
        title=metadata.title,
        title_id=metadata.identity.value,
        derived_root=derived_root,
    )
