# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Conversores de ROM allowlisted, incluindo NSZ de Switch (WI-4, ADR-0021).

O ``ConversionManager`` do domínio já confina a conversão (staging, hash,
timeout/ENOSPC, original preservado). Aqui vivem apenas os adapters que falam com
a ferramenta externa via argv fixo (nunca shell) e o registro de ferramentas com
disponibilidade verificável: ferramenta ausente => capacidade degradada, nunca
crash. Nenhuma URL/hash/versão é inventada — as fontes vêm do tool-manifest-v1
validado; sem manifesto/binário, a conversão fica indisponível com motivo.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from steamzero.api import contracts
from steamzero.core import fs
from steamzero.core.errors import SteamZeroError
from steamzero.domain.convert import ConversionManager, ConvertResult
from steamzero.ports import ConversionTimeout

Which = Callable[[str], str | None]
#: Executa argv com timeout; retorna returncode. Levanta ConversionTimeout no estouro.
CommandRunner = Callable[[Sequence[str], float], int]

# Conversões allowlisted por ferramenta (nunca aceitar par arbitrário).
_NSZ_CONVERSIONS = frozenset({("nsp", "nsz"), ("nsz", "nsp")})


def default_runner(argv: Sequence[str], timeout: float) -> int:
    executable = shutil.which(argv[0])
    if executable is None:
        raise FileNotFoundError(argv[0])
    try:
        completed = subprocess.run(  # noqa: S603
            [executable, *argv[1:]],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConversionTimeout(f"{argv[0]} excedeu {timeout:g}s") from exc
    return completed.returncode


class ToolManifest:
    """Manifesto de ferramenta de conversão (tool-manifest-v1)."""

    def __init__(self, data: dict[str, Any]) -> None:
        contracts.validate(data, "tool-manifest-v1.schema.json")
        self.id: str = data["id"]
        self.conversions: frozenset[tuple[str, str]] = frozenset(
            (c["from"], c["to"]) for c in data["conversions"]
        )
        self.smoke_test: tuple[str, ...] = tuple(data.get("smokeTest", ()))

    @classmethod
    def from_path(cls, path: Path) -> ToolManifest:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(data)

    def supports(self, from_fmt: str, to_fmt: str) -> bool:
        return (from_fmt, to_fmt) in self.conversions


class ToolRegistry:
    """Resolve disponibilidade de ferramentas sem inventar suporte."""

    def __init__(self, manifests: Sequence[ToolManifest], *, which: Which = shutil.which) -> None:
        self._manifests = tuple(manifests)
        self._which = which

    def available(self, tool_id: str) -> bool:
        return self._which(tool_id) is not None

    def converter_tool(self, from_fmt: str, to_fmt: str) -> ToolManifest | None:
        return next(
            (m for m in self._manifests if m.supports(from_fmt, to_fmt)),
            None,
        )

    def conversions(self) -> list[dict[str, Any]]:
        """Lista as conversões conhecidas com disponibilidade real (dados p/ UI)."""
        rows: list[dict[str, Any]] = []
        for manifest in self._manifests:
            present = self.available(manifest.id)
            for from_fmt, to_fmt in sorted(manifest.conversions):
                rows.append(
                    {
                        "tool": manifest.id,
                        "from": from_fmt,
                        "to": to_fmt,
                        "available": present,
                        "reason": None
                        if present
                        else f"ferramenta {manifest.id} não encontrada no host",
                    }
                )
        return rows


class NszConverter:
    """ConverterPort para NSZ (nsp<->nsz) via argv fixo da ferramenta ``nsz``."""

    def __init__(
        self,
        *,
        runner: CommandRunner = default_runner,
        which: Which = shutil.which,
        timeout: float = 1800.0,
    ) -> None:
        self._runner = runner
        self._which = which
        self._timeout = timeout

    def convert(self, src: Path, dst: Path, target_format: str) -> bool:
        from_fmt = src.suffix.lstrip(".").lower()
        if (from_fmt, target_format) not in _NSZ_CONVERSIONS:
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail=f"conversão não suportada pelo nsz: {from_fmt}->{target_format}",
            )
        if self._which("nsz") is None:
            # Gating normalmente ocorre antes; se chegou aqui, degrada em falha limpa.
            return False
        argv = self._build_argv(src, dst, target_format)
        try:
            rc = self._runner(argv, self._timeout)
        except FileNotFoundError as exc:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=f"ferramenta {argv[0]} sumiu durante a execução: {exc}",
            ) from exc
        if rc != 0:
            return False
        return self._reconcile_output(src, dst, target_format)

    @staticmethod
    def _build_argv(src: Path, dst: Path, target_format: str) -> tuple[str, ...]:
        # nsz comprime (-C) para .nsz e descomprime (-D) para .nsp; direcionamos a
        # saída para o diretório do destino confinado. O nome real da saída segue o
        # stem do arquivo de entrada; reconcile_output move para ``dst``.
        mode = "-C" if target_format == "nsz" else "-D"
        return ("nsz", mode, "-o", str(dst.parent), str(src))

    @staticmethod
    def _reconcile_output(src: Path, dst: Path, target_format: str) -> bool:
        """Move a saída real do nsz (stem de src + target_format) para ``dst``."""
        if dst.is_symlink():
            return False
        if dst.is_file():
            return True
        produced = dst.parent / f"{src.stem}.{target_format}"
        if produced == dst:
            return produced.is_file() and not produced.is_symlink()
        if produced.is_file() and not produced.is_symlink():
            fs.move_file(produced, dst)
        return dst.is_file() and not dst.is_symlink()


class SwitchRomConversionService:
    """Gate de disponibilidade + conversão confinada (reusa o domínio)."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        converter: NszConverter | None = None,
    ) -> None:
        self._registry = registry
        self._converter = converter or NszConverter()

    def convert(
        self, src: Path, target_format: str, *, dest_dir: Path | None = None
    ) -> ConvertResult:
        from_fmt = src.suffix.lstrip(".").lower()
        tool = self._registry.converter_tool(from_fmt, target_format)
        if tool is None:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=f"nenhuma ferramenta suporta {from_fmt}->{target_format}",
            )
        if not self._registry.available(tool.id):
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=f"ferramenta {tool.id} não está instalada no host",
            )
        return ConversionManager(self._converter).convert(src, target_format, dest_dir=dest_dir)
