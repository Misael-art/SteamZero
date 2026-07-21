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
import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from steamzero.api import contracts
from steamzero.core import fs, ids, paths, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.domain.convert import ConversionManager
from steamzero.ports import ConversionTimeout

Which = Callable[[str], str | None]
#: Executa argv com timeout; retorna returncode. Levanta ConversionTimeout no estouro.
CommandRunner = Callable[[Sequence[str], float], int]
ToolProbe = Callable[[Sequence[str], float], tuple[int, str]]

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


def default_tool_probe(argv: Sequence[str], timeout: float) -> tuple[int, str]:
    """Executa smoke test allowlisted e limita a saída usada na validação."""
    try:
        completed = subprocess.run(  # noqa: S603
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
            text=True,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)[:240]
    return completed.returncode, completed.stdout[:4096]


class ToolManifest:
    """Manifesto de ferramenta de conversão (tool-manifest-v1)."""

    def __init__(self, data: dict[str, Any]) -> None:
        contracts.validate(data, "tool-manifest-v1.schema.json")
        self.id: str = data["id"]
        self.conversions: frozenset[tuple[str, str]] = frozenset(
            (c["from"], c["to"]) for c in data["conversions"]
        )
        self.smoke_test: tuple[str, ...] = tuple(data.get("smokeTest", ()))
        sources = sorted(data["sources"], key=lambda item: int(item["priority"]))
        self.expected_version: str = str(sources[0]["version"])

    @classmethod
    def from_path(cls, path: Path) -> ToolManifest:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(data)

    def supports(self, from_fmt: str, to_fmt: str) -> bool:
        return (from_fmt, to_fmt) in self.conversions


class ToolRegistry:
    """Resolve disponibilidade de ferramentas sem inventar suporte."""

    def __init__(
        self,
        manifests: Sequence[ToolManifest],
        *,
        which: Which = shutil.which,
        probe: ToolProbe = default_tool_probe,
        probe_timeout: float = 5.0,
    ) -> None:
        self._manifests = tuple(manifests)
        self._which = which
        self._probe = probe
        self._probe_timeout = probe_timeout

    def available(self, tool_id: str) -> bool:
        return bool(self.status(tool_id)["available"])

    def status(self, tool_id: str) -> dict[str, Any]:
        manifest = next((item for item in self._manifests if item.id == tool_id), None)
        if manifest is None:
            return {"available": False, "state": "unverified", "reason": "manifesto ausente"}
        executable = self._which(tool_id)
        if executable is None:
            return {
                "available": False,
                "state": "missing",
                "reason": f"ferramenta {tool_id} não encontrada no host",
            }
        if not manifest.smoke_test:
            return {
                "available": False,
                "state": "unverified",
                "reason": f"ferramenta {tool_id} não declara smoke test",
            }
        try:
            returncode, output = self._probe(
                (executable, *manifest.smoke_test), self._probe_timeout
            )
        except Exception as exc:
            return {
                "available": False,
                "state": "unverified",
                "reason": f"probe de {tool_id} indisponível: {str(exc)[:160]}",
            }
        if returncode != 0:
            return {
                "available": False,
                "state": "degraded",
                "reason": f"smoke test de {tool_id} falhou (status {returncode})",
            }
        version_pattern = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(manifest.expected_version)}(?![A-Za-z0-9])"
        )
        if version_pattern.search(output) is None:
            return {
                "available": False,
                "state": "incompatible",
                "reason": (
                    f"versão de {tool_id} não corresponde ao manifesto "
                    f"({manifest.expected_version})"
                ),
            }
        return {
            "available": True,
            "state": "verified",
            "reason": None,
            "version": manifest.expected_version,
        }

    def converter_tool(self, from_fmt: str, to_fmt: str) -> ToolManifest | None:
        return next(
            (m for m in self._manifests if m.supports(from_fmt, to_fmt)),
            None,
        )

    def conversions(self) -> list[dict[str, Any]]:
        """Lista as conversões conhecidas com disponibilidade real (dados p/ UI)."""
        rows: list[dict[str, Any]] = []
        for manifest in self._manifests:
            status = self.status(manifest.id)
            for from_fmt, to_fmt in sorted(manifest.conversions):
                rows.append(
                    {
                        "tool": manifest.id,
                        "from": from_fmt,
                        "to": to_fmt,
                        "available": status["available"],
                        "state": status["state"],
                        "reason": status["reason"],
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

    def plan_convert(
        self,
        src: Path,
        target_format: str,
        *,
        dest_dir: Path | None = None,
        ttl_s: int = 3600,
    ) -> transaction.Plan:
        from_fmt = src.suffix.lstrip(".").lower()
        tool = self._registry.converter_tool(from_fmt, target_format)
        if tool is None:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=f"nenhuma ferramenta suporta {from_fmt}->{target_format}",
            )
        tool_status = self._registry.status(tool.id)
        if not tool_status["available"]:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=str(tool_status["reason"]),
            )
        if src.is_symlink() or not src.is_file():
            raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="origem não é arquivo regular")
        source = src.resolve(strict=True)
        source_hash = fs.hash_file(source)
        destination_root = (dest_dir or (paths.roms_dir() / "converted")).resolve(strict=False)
        destination = fs.resolve_within(
            destination_root, destination_root / f"{source.stem}.{target_format}"
        )
        preview_root = paths.staging_for(f"conversion-plan-{ids.new_ulid()}")
        try:
            converted = ConversionManager(self._converter).convert(
                source, target_format, dest_dir=preview_root
            )
            return transaction.plan_copy_files(
                {converted.dest: destination},
                root=destination_root,
                kind="library.convert",
                ttl_s=ttl_s,
                requirements_extra={
                    "inputPath": str(source),
                    "inputHash": source_hash,
                    "tool": tool.id,
                    "toolVersion": tool.expected_version,
                    "previewRoot": str(preview_root),
                },
            )
        except Exception:
            fs.remove_tree(preview_root)
            raise

    @staticmethod
    def apply(plan_id: str, confirm_token: str) -> transaction.ApplyResult:
        plan = transaction.load_plan(plan_id)
        if plan.kind != "library.convert":
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não é de conversão")
        if datetime.now(UTC) > datetime.fromisoformat(plan.expires_at):
            SwitchRomConversionService.cancel(plan_id, confirm_token)
            raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="confirmToken expirado")
        source = Path(str(plan.requirements.get("inputPath", "")))
        expected = str(plan.requirements.get("inputHash", ""))
        if source.is_symlink() or not source.is_file() or fs.hash_file(source) != expected:
            SwitchRomConversionService.cancel(plan_id, confirm_token)
            raise SteamZeroError("E-TX-STALE-PLAN", detail="origem mudou desde o preview")
        result = transaction.apply(plan_id, confirm_token)
        SwitchRomConversionService._cleanup_preview(plan)
        return result

    @staticmethod
    def cancel(plan_id: str, confirm_token: str) -> dict[str, str]:
        plan = transaction.load_plan(plan_id)
        if plan.kind != "library.convert":
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não é de conversão")
        transaction.abort(plan_id, confirm_token)
        SwitchRomConversionService._cleanup_preview(plan)
        return {"planId": plan_id, "status": "aborted"}

    @staticmethod
    def _cleanup_preview(plan: transaction.Plan) -> None:
        preview_root = Path(str(plan.requirements.get("previewRoot", "")))
        staging_root = paths.staging_dir().resolve(strict=False)
        if not preview_root.name.startswith("conversion-plan-"):
            raise SteamZeroError("E-TX-STALE-PLAN", detail="staging de conversão inválido")
        confined = fs.resolve_within(staging_root, preview_root)
        if confined.parent != staging_root:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="staging de conversão não é direto")
        fs.remove_tree(confined)

    @staticmethod
    def rollback(operation_id: str) -> transaction.RollbackResult:
        return transaction.rollback(operation_id, reason="library-convert")
