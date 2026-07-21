# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Biblioteca/mídia de Switch: scan, DAT local, matching e rename seguro (WI-5).

Apenas formatos allowlisted são considerados (``.nsp``, ``.nsz``, ``.xci``,
``.nro``). O DAT é importado localmente e validado contra o schema; nenhuma base
é redistribuída. O matching é por hash sha256; o preview de rename resolve
colisões sem escrever no disco.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import ValidationError

from steamzero.api import contracts
from steamzero.core import fs
from steamzero.core.errors import SteamZeroError

_TITLE_ID_RE = re.compile(r"^[0-9A-Fa-f]{16}$")
_SWITCH_FORMATS = frozenset({"nsp", "nsz", "xci", "nro"})


def _validate_title_id(value: str) -> str:
    """Normaliza e valida Title ID de 16 hex digits."""
    normalized = value.upper()
    if not _TITLE_ID_RE.fullmatch(normalized):
        raise SteamZeroError("E-API-SCHEMA", detail=f"titleId inválido: {value!r}")
    return normalized


class DatIndex:
    """Índice DAT local validado (hash sha256 -> metadados)."""

    def __init__(self, data: dict[str, Any]) -> None:
        try:
            contracts.validate(data, "dat-index-v1.schema.json")
        except ValidationError as exc:
            raise SteamZeroError("E-API-SCHEMA", detail=f"DAT inválido: {exc}") from exc
        self.platform: str = data["platform"]
        self.entries: tuple[dict[str, Any], ...] = tuple(data["entries"])
        self._by_sha256: dict[str, dict[str, Any]] = {
            entry["sha256"]: entry for entry in self.entries
        }

    @classmethod
    def from_path(cls, path: Path) -> DatIndex:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(data)

    def lookup(self, sha256: str) -> dict[str, Any] | None:
        return self._by_sha256.get(sha256)

    def match(self, sha256: str) -> DatMatch | None:
        entry = self.lookup(sha256)
        if entry is None:
            return None
        title_id = entry.get("titleId")
        return DatMatch(
            sha256=sha256,
            canonical_name=entry["name"],
            title_id=_validate_title_id(title_id) if title_id else None,
            region=entry.get("region"),
        )


@dataclass(frozen=True)
class DatMatch:
    sha256: str
    canonical_name: str
    title_id: str | None
    region: str | None


@dataclass(frozen=True)
class SwitchRomMatch:
    path: Path
    sha256: str
    format: str
    title_id: str | None
    canonical_name: str | None
    region: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "format": self.format,
            "titleId": self.title_id,
            "canonicalName": self.canonical_name,
            "region": self.region,
        }


class SwitchLibraryScanner:
    """Scan read-only de dumps Switch (AC-LB-01)."""

    def __init__(self, *, formats: frozenset[str] = _SWITCH_FORMATS) -> None:
        self._formats = formats

    def scan(self, root: Path) -> list[SwitchRomMatch]:
        """Lista arquivos Switch com hash sha256 (não escreve em disco)."""
        results: list[SwitchRomMatch] = []
        for path in fs.iter_files(root):
            fmt = self._format_of(path.name)
            if fmt is None:
                continue
            sha = fs.hash_file(path, algo="sha256")
            results.append(
                SwitchRomMatch(
                    path=path,
                    sha256=sha,
                    format=fmt,
                    title_id=None,
                    canonical_name=None,
                    region=None,
                )
            )
        return results

    def _format_of(self, name: str) -> str | None:
        ext = Path(name).suffix.lstrip(".").lower()
        return ext if ext in self._formats else None


class SwitchMediaMatcher:
    """Cruza scans locais com um DAT importado pelo usuário."""

    def __init__(self, dat_index: DatIndex | None = None) -> None:
        self._dat = dat_index

    def match(self, roms: Sequence[SwitchRomMatch]) -> list[SwitchRomMatch]:
        """Enriquece cada ROM com título/Title ID/region quando conhecido."""
        if self._dat is None:
            return list(roms)
        result: list[SwitchRomMatch] = []
        for rom in roms:
            dat_match = self._dat.match(rom.sha256)
            if dat_match is not None:
                result.append(
                    SwitchRomMatch(
                        path=rom.path,
                        sha256=rom.sha256,
                        format=rom.format,
                        title_id=dat_match.title_id,
                        canonical_name=dat_match.canonical_name,
                        region=dat_match.region,
                    )
                )
            else:
                result.append(rom)
        return result


class SwitchLibraryOrganizer:
    """Preview de renomeio canônico sem colisão (não muta disco)."""

    def plan_rename(
        self,
        root: Path,
        matches: Sequence[SwitchRomMatch],
        *,
        collision_suffix: str = " ({n})",
    ) -> dict[Path, Path]:
        """Retorna mapeamento origem -> destino canônico, resolvendo colisões.

        Arquivos sem nome canônico (não constam no DAT) ficam de fora do plano.
        """
        used_names: set[str] = set()
        plan: dict[Path, Path] = {}
        for rom in matches:
            if rom.canonical_name is None:
                continue
            target_name = self._unique_name(
                root, rom.canonical_name, rom.format, used_names, collision_suffix
            )
            target = fs.resolve_within(root, root / target_name)
            if target.resolve() != rom.path.resolve():
                plan[rom.path] = target
            used_names.add(target.name)
        return plan

    @staticmethod
    def _unique_name(
        root: Path,
        canonical_name: str,
        fmt: str,
        used_names: set[str],
        collision_suffix: str,
    ) -> str:
        base = fs.validate_relative_entry(canonical_name).name
        if not base:
            base = "unknown"
        # Remove extensão eventualmente presente no nome canônico para aplicar fmt.
        stem = Path(base).stem
        candidate = f"{stem}.{fmt}"
        if candidate not in used_names:
            return candidate
        n = 2
        while True:
            candidate = f"{stem}{collision_suffix.format(n=n)}.{fmt}"
            if candidate not in used_names:
                return candidate
            n += 1
