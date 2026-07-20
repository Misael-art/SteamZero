# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Conversão confinada de dumps locais (F-LB-03, RT-06, FI-06/19, AC-LB-02).

O conversor recebe uma cópia confinada, nunca o original. Entrada e saída são
verificadas por hash, a publicação final usa cópia atômica em streaming e qualquer
colisão ou mudança concorrente aborta antes de sobrescrever dados do usuário.
"""

from __future__ import annotations

import errno
import re
from dataclasses import dataclass
from pathlib import Path

from steamzero.core import fs, ids, paths
from steamzero.core.errors import SteamZeroError
from steamzero.core.lock import ResourceLock
from steamzero.ports import ConversionTimeout, ConverterPort

_SPACE_MARGIN = 16 * 1024 * 1024  # 16 MiB
_FORMAT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,15}$")


@dataclass(frozen=True)
class ConvertResult:
    dest: Path
    source_intact: bool


class ConversionManager:
    def __init__(self, converter: ConverterPort) -> None:
        self._converter = converter

    def convert(
        self, src: Path, target_format: str, *, dest_dir: Path | None = None
    ) -> ConvertResult:
        dest_dir = dest_dir or (paths.roms_dir() / "converted")
        normalized_format = target_format.strip().lower()
        if not _FORMAT_RE.fullmatch(normalized_format):
            raise SteamZeroError("E-API-SCHEMA", detail="formato de conversão inválido")
        if src.is_symlink() or not src.is_file():
            raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="origem não é arquivo regular")

        source_path = src.resolve(strict=True)
        destination_root = dest_dir.resolve(strict=False)
        destination = fs.resolve_within(
            destination_root, destination_root / f"{source_path.stem}.{normalized_format}"
        )
        resource_digest = fs.hash_bytes(str(source_path).encode(), algo="sha256")[:32]
        with ResourceLock(f"library:convert:{resource_digest}", job_id=ids.new_ulid()):
            return self._convert_locked(
                source_path, normalized_format, destination_root, destination
            )

    def _convert_locked(
        self,
        source: Path,
        target_format: str,
        destination_root: Path,
        destination: Path,
    ) -> ConvertResult:
        if destination == source or destination.exists() or destination.is_symlink():
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail=f"destino de conversão já existe: {destination.name}"
            )

        source_size = source.stat().st_size
        source_hash = fs.hash_file(source)
        # Pico conservador: cópia de entrada + saída potencialmente maior. O
        # destino também precisa comportar a publicação atômica em streaming.
        staging_needed = max(source_size * 2, 1) + _SPACE_MARGIN
        destination_needed = max(source_size * 2, 1) + _SPACE_MARGIN
        if (
            fs.free_space(paths.staging_dir()) < staging_needed
            or fs.free_space(destination_root) < destination_needed
        ):
            raise SteamZeroError(
                "E-STORAGE-SPACE",
                detail=(
                    "espaço insuficiente para staging e publicação da conversão "
                    f"(~{max(staging_needed, destination_needed)} bytes por volume)"
                ),
            )

        op_id = ids.new_ulid()
        staging = paths.staging_for(op_id)
        staged_source = staging / f"source{source.suffix.lower()}"
        staged_output = staging / f"output.{target_format}"
        fs.ensure_dir(staging)
        try:
            fs.copy_file_atomic(source, staged_source)
            if fs.hash_file(staged_source) != source_hash or fs.hash_file(source) != source_hash:
                raise SteamZeroError("E-TX-STALE-PLAN", detail="origem mudou durante a preparação")
            try:
                converted = self._converter.convert(staged_source, staged_output, target_format)
            except ConversionTimeout as exc:
                raise SteamZeroError("E-CONVERT-TIMEOUT", detail=str(exc)) from exc
            except OSError as exc:
                code = "E-STORAGE-SPACE" if exc.errno == errno.ENOSPC else "E-CONVERT-FAILED"
                raise SteamZeroError(code, detail=f"conversor falhou: {exc}") from exc
            except Exception as exc:
                raise SteamZeroError("E-CONVERT-FAILED", detail=f"conversor falhou: {exc}") from exc

            if (
                not converted
                or staged_output.is_symlink()
                or not staged_output.is_file()
                or staged_output.stat().st_size == 0
            ):
                raise SteamZeroError(
                    "E-CONVERT-FAILED", detail=f"saída inválida para {source.name}"
                )
            if fs.hash_file(staged_source) != source_hash or fs.hash_file(source) != source_hash:
                raise SteamZeroError("E-TX-STALE-PLAN", detail="entrada mudou durante a conversão")
            if destination.exists() or destination.is_symlink():
                raise SteamZeroError(
                    "E-TX-STALE-PLAN", detail="destino apareceu durante a conversão"
                )

            output_hash = fs.hash_file(staged_output)
            try:
                fs.copy_file_atomic(staged_output, destination)
            except OSError as exc:
                code = "E-STORAGE-SPACE" if exc.errno == errno.ENOSPC else "E-STORAGE-IO"
                raise SteamZeroError(code, detail=f"publicação da conversão falhou: {exc}") from exc
            if fs.hash_file(destination) != output_hash or fs.hash_file(source) != source_hash:
                fs.remove_file(destination)
                raise SteamZeroError(
                    "E-TX-VERIFY-FAILED",
                    detail="saída ou origem divergiu durante a publicação",
                )
            return ConvertResult(dest=destination, source_intact=True)
        finally:
            fs.remove_tree(staging)
