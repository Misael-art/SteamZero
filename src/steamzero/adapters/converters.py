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
import os
import re
import shutil
import subprocess
import sys
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
_NSZ_VERSION = "4.6.1"
_NSZ_REQUIREMENTS = (
    "\n".join(
        (
            "nsz==4.6.1 --hash=sha256:"
            "3b65c3ccc5620d713b7d862191f2f657f1b019ec6173e95ddf274c4e196a714d",
            "enlighten==1.14.1 --hash=sha256:"
            "5fbd0c959ca1644034c41bb0ace5db19c9852cf9d721b6103f5f130663c57be8",
            "blessed==1.47.0 --hash=sha256:"
            "f4df54a32289b6a3eaca49387b4f6823ba7e04ddb5ffa18f5e1fde44e8b79681",
            "jinxed==2.1.0 --hash=sha256:"
            "43b802d18b70e405d410fb66eb2837d1101e7e5ea922e666507bb43f34d11d09",
            "prefixed==0.9.0 --hash=sha256:"
            "3cdb74bfc4cf0aba28f3574662b13afdcac27c463dcbef320fe5d03f4c5fbca8",
            "wcwidth==0.8.2 --hash=sha256:"
            "d63947694a0539a1d51e01eda7caf800c291020e6cdd7e28ad7b14dd33ad4f85",
            "pycryptodome==3.23.0 --hash=sha256:"
            "c8987bd3307a39bc03df5c8e0e3d8be0c4c3518b7f044b0f4c15d1aa78f52575",
            "zstandard==0.25.0 --hash=sha256:"
            "e09bb6252b6476d8d56100e8147b803befa9a12cea144bbe629dd508800d1ad0",
        )
    )
    + "\n"
)


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


class NszToolManager:
    """Instala NSZ em venv privado, com dependências e hashes fechados.

    Nada é instalado globalmente. O diretório final só é preservado após
    `pip check`; falhas removem o staging parcial e a UI permanece degradada.
    """

    def __init__(self, *, runner: Callable[[Sequence[str]], None] | None = None) -> None:
        self._runner = runner or self._run

    @property
    def root(self) -> Path:
        return paths.data_home() / "tools" / "nsz" / _NSZ_VERSION

    @property
    def executable(self) -> Path:
        return self.root / "venv" / "bin" / "nsz"

    def status(self) -> dict[str, Any]:
        executable = self.executable
        if executable.is_file() and not executable.is_symlink() and os.access(executable, os.X_OK):
            return {"state": "installed", "available": True, "path": str(executable)}
        return {
            "state": "missing",
            "available": False,
            "reason": "NSZ ainda não foi instalado para este usuário.",
        }

    def install(self) -> dict[str, Any]:
        if self.status()["available"]:
            return {"status": "already-installed", "path": str(self.executable)}
        root = self.root
        if root.exists() or root.is_symlink():
            fs.remove_tree(root)
        fs.ensure_dir(root)
        wheelhouse = root / "wheelhouse"
        requirements = root / "requirements.lock"
        fs.write_atomic_text(requirements, _NSZ_REQUIREMENTS)
        try:
            fs.ensure_dir(wheelhouse)
            self._runner(
                (
                    sys.executable,
                    "-m",
                    "pip",
                    "download",
                    "--disable-pip-version-check",
                    "--only-binary=:all:",
                    "--require-hashes",
                    "-r",
                    str(requirements),
                    "-d",
                    str(wheelhouse),
                )
            )
            self._runner((sys.executable, "-m", "venv", str(root / "venv")))
            pip = root / "venv" / "bin" / "pip"
            self._runner(
                (
                    str(pip),
                    "install",
                    "--disable-pip-version-check",
                    "--no-index",
                    "--only-binary=:all:",
                    "--require-hashes",
                    f"--find-links={wheelhouse}",
                    "-r",
                    str(requirements),
                )
            )
            self._runner((str(pip), "check"))
        except Exception as exc:
            fs.remove_tree(root)
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail=f"instalação NSZ falhou: {exc}"
            ) from exc
        if not self.status()["available"]:
            fs.remove_tree(root)
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail="instalação NSZ não publicou binário"
            )
        return {"status": "installed", "path": str(self.executable)}

    @staticmethod
    def _run(argv: Sequence[str]) -> None:
        try:
            result = subprocess.run(  # noqa: S603
                list(argv),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=300,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(str(exc)) from exc
        if result.returncode != 0:
            raise RuntimeError(result.stdout[-1000:])


def nsz_tool_manifest() -> ToolManifest:
    """Retorna o manifesto do NSZ instalado pelo gerenciador privado."""
    return ToolManifest(
        {
            "schemaVersion": 1,
            "id": "nsz",
            "kind": "converter",
            "conversions": [
                {"from": "nsp", "to": "nsz"},
                {"from": "nsz", "to": "nsp"},
            ],
            "smokeTest": ["--version"],
            "sources": [
                {
                    "type": "pip",
                    "version": _NSZ_VERSION,
                    "priority": 1,
                    "url": "https://pypi.org/project/nsz/",
                    "sha256": "3b65c3ccc5620d713b7d862191f2f657f1b019ec6173e95ddf274c4e196a714d",
                }
            ],
            "license": "MIT",
            "upstream": "https://github.com/nicoboss/nsz",
        }
    )


class NszConverter:
    """ConverterPort para NSZ (nsp<->nsz) via argv fixo da ferramenta ``nsz``."""

    def __init__(
        self,
        *,
        runner: CommandRunner = default_runner,
        which: Which = shutil.which,
        executable: str = "nsz",
        timeout: float = 1800.0,
    ) -> None:
        self._runner = runner
        self._which = which
        self._executable = executable
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
        argv = self._build_argv(src, dst, target_format, executable=self._executable)
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
    def _build_argv(
        src: Path, dst: Path, target_format: str, *, executable: str = "nsz"
    ) -> tuple[str, ...]:
        # nsz comprime (-C) para .nsz e descomprime (-D) para .nsp; direcionamos a
        # saída para o diretório do destino confinado. O nome real da saída segue o
        # stem do arquivo de entrada; reconcile_output move para ``dst``.
        mode = "-C" if target_format == "nsz" else "-D"
        return (executable, mode, "-o", str(dst.parent), str(src))

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
