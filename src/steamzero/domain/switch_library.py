# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Biblioteca/mídia de Switch: scan, DAT local, matching e rename seguro (WI-5).

Apenas formatos allowlisted são considerados (``.nsp``, ``.nsz``, ``.xci``,
``.xcz``, ``.nro``). O DAT é importado localmente e validado contra o schema; nenhuma base
é redistribuída. O matching é por hash sha256; o preview de rename resolve
colisões sem escrever no disco.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import ValidationError

from steamzero.api import contracts
from steamzero.core import fs, transaction
from steamzero.core.errors import SteamZeroError

_TITLE_ID_RE = re.compile(r"^[0-9A-Fa-f]{16}$")
_TITLE_ID_IN_NAME_RE = re.compile(r"(?<![0-9A-Fa-f])([0-9A-Fa-f]{16})(?![0-9A-Fa-f])")
_AUXILIARY_CONTENT_IN_NAME_RE = re.compile(
    r"(?:^|[\s._\-\[\]()])(?:dlc|update|updates|patch|add[\s._-]?on)(?:$|[\s._\-\[\]()])",
    re.IGNORECASE,
)
_SWITCH_FORMATS = frozenset({"nsp", "nsz", "xci", "xcz", "nro"})
_BIDI_CONTROLS = frozenset({"LRE", "RLE", "LRO", "RLO", "PDF", "LRI", "RLI", "FSI", "PDI"})


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
        self._by_sha256: dict[str, dict[str, Any]] = {}
        for entry in self.entries:
            _validate_canonical_name(str(entry["name"]))
            previous = self._by_sha256.get(entry["sha256"])
            if previous is not None and previous != entry:
                raise SteamZeroError(
                    "E-API-SCHEMA",
                    detail=f"hash DAT duplicado com metadados divergentes: {entry['sha256'][:12]}…",
                )
            self._by_sha256[entry["sha256"]] = entry

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


@dataclass(frozen=True)
class SwitchRomCandidate:
    """Arquivo reconhecido por extensão, antes do hash integral opcional."""

    path: Path
    format: str
    title_id: str | None


class SwitchLibraryScanner:
    """Scan read-only de dumps Switch (AC-LB-01)."""

    def __init__(self, *, formats: frozenset[str] = _SWITCH_FORMATS) -> None:
        self._formats = formats

    def discover(self, root: Path) -> list[SwitchRomCandidate]:
        """Descobre jogos por metadados baratos, sem ler dumps inteiros."""
        results: list[SwitchRomCandidate] = []
        for path in fs.iter_files(root):
            fmt = self._format_of(path.name)
            if fmt is None:
                continue
            title_id = self._title_id_from_path(path, root)
            if not self._is_base_game(path, root, fmt, title_id):
                continue
            results.append(
                SwitchRomCandidate(
                    path=path,
                    format=fmt,
                    title_id=title_id,
                )
            )
        return results

    def scan(self, root: Path) -> list[SwitchRomMatch]:
        """Lista arquivos Switch com hash sha256 integral (não escreve em disco)."""
        return [
            SwitchRomMatch(
                path=candidate.path,
                sha256=fs.hash_file(candidate.path, algo="sha256"),
                format=candidate.format,
                title_id=candidate.title_id,
                canonical_name=None,
                region=None,
            )
            for candidate in self.discover(root)
        ]

    def _format_of(self, name: str) -> str | None:
        ext = Path(name).suffix.lstrip(".").lower()
        return ext if ext in self._formats else None

    @classmethod
    def _is_base_game(
        cls,
        path: Path,
        root: Path,
        fmt: str,
        title_id: str | None,
    ) -> bool:
        """Recusa conteúdo auxiliar quando a evidência é inequívoca.

        Updates e DLCs distribuídos como NSP/NSZ compartilham a extensão dos
        jogos. Um Title ID de aplicação base termina em ``000``; updates usam
        ``800`` e conteúdo adicional usa outro sufixo. Sem Title ID, somente
        marcadores explícitos no nome/caminho relativo são usados para evitar
        esconder dumps legítimos por heurística ampla.
        """
        if fmt not in {"nsp", "nsz"}:
            return True
        if title_id is not None:
            return title_id.endswith("000")
        try:
            relative = path.relative_to(root)
        except ValueError:
            relative = Path(path.name)
        searchable = " ".join((*relative.parent.parts, path.stem))
        return _AUXILIARY_CONTENT_IN_NAME_RE.search(searchable) is None

    @staticmethod
    def _title_id_from_name(name: str) -> str | None:
        match = _TITLE_ID_IN_NAME_RE.search(name)
        return match.group(1).upper() if match is not None else None

    @classmethod
    def _title_id_from_path(cls, path: Path, root: Path) -> str | None:
        """Procura a identidade no arquivo e nas pastas dentro da raiz.

        Bibliotecas reais frequentemente usam ``<Title ID>/<nome>.nsp``. A
        busca nunca sobe acima da raiz selecionada e não interpreta conteúdo
        protegido quando a identidade não está disponível no nome.
        """
        from_name = cls._title_id_from_name(path.stem)
        if from_name is not None:
            return from_name
        try:
            relative_parent = path.relative_to(root).parent
        except ValueError:
            return None
        for part in reversed(relative_parent.parts):
            from_parent = cls._title_id_from_name(part)
            if from_parent is not None:
                return from_parent
        return None


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
    """Preview e rename transacional canônico, sem colisão."""

    def preview_rename(
        self,
        root: Path,
        matches: Sequence[SwitchRomMatch],
        *,
        collision_suffix: str = " ({n})",
    ) -> dict[Path, Path]:
        """Retorna mapeamento origem -> destino canônico, resolvendo colisões.

        Arquivos sem nome canônico (não constam no DAT) ficam de fora do plano.
        """
        _validate_collision_suffix(collision_suffix)
        root_resolved = root.resolve(strict=True)
        used_names = {entry.name.casefold() for entry in root_resolved.iterdir()}
        seen_sources: set[Path] = set()
        plan: dict[Path, Path] = {}
        for rom in matches:
            if rom.canonical_name is None:
                continue
            if rom.path.is_symlink() or not rom.path.is_file():
                raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="origem de rename inválida")
            source = fs.resolve_within(root_resolved, rom.path)
            if source in seen_sources:
                raise SteamZeroError("E-TX-STALE-PLAN", detail=f"origem duplicada: {source}")
            seen_sources.add(source)
            own_name = source.name.casefold()
            used_names.discard(own_name)
            target_name = self._unique_name(
                root, rom.canonical_name, rom.format, used_names, collision_suffix
            )
            target = fs.resolve_within(root_resolved, root_resolved / target_name)
            if target != source:
                plan[source] = target
            used_names.add(target.name.casefold())
        return plan

    def plan_rename(
        self,
        root: Path,
        matches: Sequence[SwitchRomMatch],
        *,
        collision_suffix: str = " ({n})",
    ) -> transaction.Plan:
        moves = self.preview_rename(root, matches, collision_suffix=collision_suffix)
        return transaction.plan_move_files(moves, root=root, kind="switch-library.rename")

    @staticmethod
    def apply(plan_id: str, confirm_token: str) -> transaction.ApplyResult:
        return transaction.apply(plan_id, confirm_token)

    @staticmethod
    def rollback(operation_id: str) -> transaction.RollbackResult:
        return transaction.rollback(operation_id, reason="switch-library-rename")

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
        if candidate.casefold() not in used_names:
            return candidate
        n = 2
        while n <= 10_000:
            candidate = f"{stem}{collision_suffix.format(n=n)}.{fmt}"
            if candidate.casefold() not in used_names:
                return candidate
            n += 1
        raise SteamZeroError("E-TX-STALE-PLAN", detail="limite de colisões de rename excedido")


def _validate_canonical_name(value: str) -> None:
    if any(
        unicodedata.category(char) == "Cc" or unicodedata.bidirectional(char) in _BIDI_CONTROLS
        for char in value
    ):
        raise SteamZeroError("E-API-SCHEMA", detail="nome canônico DAT contém controle invisível")
    # A entrada representa somente um nome, nunca um caminho.
    fs.validate_relative_entry(value)
    if len(Path(value).parts) != 1:
        raise SteamZeroError("E-API-SCHEMA", detail="nome canônico DAT não pode conter diretório")


def _validate_collision_suffix(value: str) -> None:
    if (
        value.count("{n}") != 1
        or len(value) > 64
        or any(ord(char) < 0x20 for char in value)
        or "/" in value
        or "\\" in value
        or value.replace("{n}", "").find("{") >= 0
        or value.replace("{n}", "").find("}") >= 0
    ):
        raise SteamZeroError("E-API-SCHEMA", detail="collision_suffix precisa conter {n}")
