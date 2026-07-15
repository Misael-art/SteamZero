# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Conversão de ROMs (F-LB-03, RT-06, FI-06/19, AC-LB-02).

Converte para staging via uma **porta** de ferramenta injetada (chdman/dolphin-tool
em produção; fake nas provas). Garantias:
- espaço checado com margem antes de iniciar (E-STORAGE-SPACE) — original intacto;
- o original NUNCA é tocado antes do commit (AC-LB-02): fica no lugar até a saída
  ser verificada e ativada;
- timeout da ferramenta => E-CONVERT-TIMEOUT; falha/saída vazia => E-CONVERT-FAILED;
  em ambos, staging é limpo e o original permanece byte-idêntico (RT-06).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from steamzero.core import fs, ids, paths
from steamzero.core.errors import SteamZeroError

_SPACE_MARGIN = 16 * 1024 * 1024  # 16 MiB


class ConversionTimeout(Exception):
    """A ferramenta de conversão excedeu o tempo limite."""


class ConverterPort(Protocol):
    """Ferramenta de conversão. Escreve ``dst``; True=ok. Pode levantar ConversionTimeout."""

    def convert(self, src: Path, dst: Path, target_format: str) -> bool: ...


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
        needed = src.stat().st_size + _SPACE_MARGIN
        if fs.free_space(dest_dir) < needed:  # preflight; original intacto
            raise SteamZeroError(
                "E-STORAGE-SPACE", detail=f"necessários ~{needed} bytes para converter"
            )
        op_id = ids.new_ulid()
        staging = paths.staging_for(op_id)
        staged = staging / f"{src.stem}.{target_format}"
        fs.ensure_dir(staging)
        try:
            ok = self._converter.convert(src, staged, target_format)
        except ConversionTimeout as exc:
            fs.remove_tree(staging)
            raise SteamZeroError("E-CONVERT-TIMEOUT", detail=str(exc)) from exc
        if not ok or not staged.exists() or staged.stat().st_size == 0:
            fs.remove_tree(staging)
            raise SteamZeroError("E-CONVERT-FAILED", detail=f"saída inválida para {src.name}")

        # commit: só agora a saída é ativada; o original nunca foi tocado (AC-LB-02)
        dest = fs.resolve_within(dest_dir, dest_dir / staged.name)
        fs.write_atomic(dest, staged.read_bytes())
        fs.remove_tree(staging)
        return ConvertResult(dest=dest, source_intact=src.exists())
