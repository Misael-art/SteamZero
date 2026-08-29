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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from steamzero.core import fs, ids, paths
from steamzero.core.errors import SteamZeroError
from steamzero.core.lock import ResourceLock
from steamzero.ports import ConversionTimeout, ConverterPort

_SPACE_MARGIN = 16 * 1024 * 1024  # 16 MiB
_FORMAT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,15}$")
_PLATFORM_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_MEDIA_NATURES = frozenset({"cartridge", "optical", "floppy", "tape", "digital", "hdd"})


@dataclass(frozen=True)
class ConversionPolicy:
    """Contrato declarativo que autoriza uma conversão de mídia por plataforma."""

    platform_id: str
    nature: str
    formats: Mapping[str, Sequence[str]]
    conversion_targets: Sequence[str]
    preferred_format: str | None = None

    def __post_init__(self) -> None:
        platform_id = self.platform_id.strip().lower()
        nature = self.nature.strip().lower()
        if not _PLATFORM_RE.fullmatch(platform_id) or nature not in _MEDIA_NATURES:
            raise SteamZeroError(
                "E-API-SCHEMA", detail="contrato de conversão de plataforma inválido"
            )

        normalized_formats: dict[str, tuple[str, ...]] = {}
        for format_name, extensions in self.formats.items():
            normalized_name = str(format_name).strip().lower()
            if not _FORMAT_RE.fullmatch(normalized_name) or isinstance(extensions, str):
                raise SteamZeroError(
                    "E-API-SCHEMA", detail="formatos declarados para conversão são inválidos"
                )
            normalized_extensions = tuple(
                str(ext).strip().lower().lstrip(".") for ext in extensions
            )
            if not normalized_extensions or any(
                not re.fullmatch(r"[a-z0-9]{1,12}", ext) for ext in normalized_extensions
            ):
                raise SteamZeroError(
                    "E-API-SCHEMA", detail="extensões declaradas para conversão são inválidas"
                )
            normalized_formats[normalized_name] = normalized_extensions
        if not normalized_formats:
            raise SteamZeroError("E-API-SCHEMA", detail="plataforma sem formatos declarados")

        targets = tuple(str(target).strip().lower() for target in self.conversion_targets)
        if any(not _FORMAT_RE.fullmatch(target) for target in targets):
            raise SteamZeroError(
                "E-API-SCHEMA", detail="alvos declarados para conversão são inválidos"
            )
        preferred = self.preferred_format.strip().lower() if self.preferred_format else None
        if preferred is not None and preferred not in normalized_formats:
            raise SteamZeroError(
                "E-API-SCHEMA", detail="formato preferido não está declarado pela plataforma"
            )
        object.__setattr__(self, "platform_id", platform_id)
        object.__setattr__(self, "nature", nature)
        object.__setattr__(self, "formats", normalized_formats)
        object.__setattr__(self, "conversion_targets", targets)
        object.__setattr__(self, "preferred_format", preferred)

    def require_allowed(self, source: Path, target_format: str) -> None:
        source_extension = source.suffix.lower().lstrip(".")
        source_format = next(
            (
                format_name
                for format_name, extensions in self.formats.items()
                if source_extension in extensions
            ),
            None,
        )
        if source_format is None:
            raise SteamZeroError(
                "E-CONTENT-UNSUPPORTED",
                detail=(
                    f"{self.platform_id} ({self.nature}) não declara a extensão "
                    f".{source_extension or 'sem-extensão'} para conversão"
                ),
            )
        allowed_targets = set(self.conversion_targets)
        if self.preferred_format is not None:
            allowed_targets.add(self.preferred_format)
        if target_format not in self.formats or target_format not in allowed_targets:
            raise SteamZeroError(
                "E-CONTENT-UNSUPPORTED",
                detail=(
                    f"{self.platform_id} ({self.nature}) não declara conversão "
                    f"{source_format}->{target_format}"
                ),
            )


@dataclass(frozen=True)
class ConvertResult:
    dest: Path
    source_intact: bool


class ConversionManager:
    def __init__(self, converter: ConverterPort) -> None:
        self._converter = converter

    def convert(
        self,
        src: Path,
        target_format: str,
        *,
        policy: ConversionPolicy,
        dest_dir: Path | None = None,
    ) -> ConvertResult:
        dest_dir = dest_dir or (paths.roms_dir() / "converted")
        normalized_format = target_format.strip().lower()
        if not _FORMAT_RE.fullmatch(normalized_format):
            raise SteamZeroError("E-API-SCHEMA", detail="formato de conversão inválido")
        if src.is_symlink() or not src.is_file():
            raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="origem não é arquivo regular")

        source_path = src.resolve(strict=True)
        policy.require_allowed(source_path, normalized_format)
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
