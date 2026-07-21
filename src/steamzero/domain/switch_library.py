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
_UPDATE_CONTENT_IN_NAME_RE = re.compile(
    r"(?:^|[\s._\-\[\]()])(?:upd|update|updates|patch)(?:$|[\s._\-\[\]()])",
    re.IGNORECASE,
)
_DLC_CONTENT_IN_NAME_RE = re.compile(
    r"(?:^|[\s._\-\[\]()])(?:dlc|add[\s._-]?on)(?:$|[\s._\-\[\]()])",
    re.IGNORECASE,
)
_SCENE_VERSION_RE = re.compile(r"(?<![A-Za-z0-9])v([0-9]+)(?![A-Za-z0-9])", re.IGNORECASE)
_TRAILING_METADATA_RE = re.compile(
    r"(?:\s*\[(?:[0-9A-Fa-f]{16}|v[0-9]+)\]\s*)+$",
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
    content_kind: str = "base"
    parent_title_id: str | None = None
    version: int | None = None
    metadata_source: str = "fallback"


class SwitchLibraryScanner:
    """Scan read-only de dumps Switch (AC-LB-01)."""

    def __init__(self, *, formats: frozenset[str] = _SWITCH_FORMATS) -> None:
        self._formats = formats

    def discover(self, root: Path) -> list[SwitchRomCandidate]:
        """Descobre jogos por metadados baratos, sem ler dumps inteiros."""
        return [candidate for candidate in self.inventory(root) if candidate.content_kind == "base"]

    def inventory(self, root: Path) -> list[SwitchRomCandidate]:
        """Classifica jogos e complementos sem transformar auxiliares em jogos.

        O Title ID é a evidência estrutural primária. Quando ele não está
        disponível (por exemplo, antes da importação das keys), diretório, nome
        e versão de cena fornecem um fallback conservador. Conteúdo auxiliar
        permanece no inventário para associação ao jogo base, mas nunca é
        retornado por :meth:`discover`.
        """
        results: list[SwitchRomCandidate] = []
        for path in fs.iter_files(root):
            fmt = self._format_of(path.name)
            if fmt is None:
                continue
            title_id = self._title_id_from_path(path, root)
            kind, parent_title_id, version, source = self.classify(
                path, root=root, fmt=fmt, title_id=title_id
            )
            results.append(
                SwitchRomCandidate(
                    path=path,
                    format=fmt,
                    title_id=title_id,
                    content_kind=kind,
                    parent_title_id=parent_title_id,
                    version=version,
                    metadata_source=source,
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
        kind, _parent, _version, _source = cls.classify(
            path, root=root, fmt=fmt, title_id=title_id
        )
        return kind == "base"

    @classmethod
    def classify(
        cls,
        path: Path,
        *,
        root: Path,
        fmt: str,
        title_id: str | None,
    ) -> tuple[str, str | None, int | None, str]:
        """Retorna ``kind``, parent, versão e fonte da decisão.

        Updates oficiais usam o Title ID da aplicação base acrescido de
        ``0x800``. DLCs ocupam a faixa seguinte de ``0x1000``. A matemática só
        é aplicada a NSP/NSZ, formatos que podem carregar conteúdo instalável.
        """
        try:
            relative = path.relative_to(root)
        except ValueError:
            relative = Path(path.name)
        searchable = " ".join((*relative.parent.parts, path.stem))
        parent_markers = " ".join(relative.parent.parts)
        version_match = _SCENE_VERSION_RE.search(searchable)
        version = int(version_match.group(1)) if version_match is not None else None

        if fmt not in {"nsp", "nsz"}:
            return "base", None, version, "format"
        if title_id is not None:
            numeric = int(title_id, 16)
            suffix = numeric & 0xFFF
            if suffix == 0:
                # Coleções reais costumam separar complementos em diretórios
                # ``DLC``/``Updates``. Alguns pacotes auxiliares autônomos usam
                # um application Title ID terminado em 000 e, sem esta
                # evidência de diretório, poluiriam a biblioteca jogável.
                if _DLC_CONTENT_IN_NAME_RE.search(parent_markers) is not None:
                    return "dlc", None, version, "directory"
                if _UPDATE_CONTENT_IN_NAME_RE.search(parent_markers) is not None:
                    return "update", None, version, "directory"
                return "base", None, version, "title-id"
            if suffix == 0x800:
                return "update", f"{numeric - 0x800:016X}", version, "title-id"
            parent = (numeric & ~0xFFF) - 0x1000
            if parent >= 0:
                return "dlc", f"{parent:016X}", version, "title-id"

        if _DLC_CONTENT_IN_NAME_RE.search(searchable) is not None:
            return "dlc", None, version, "name"
        if _UPDATE_CONTENT_IN_NAME_RE.search(searchable) is not None or (
            version is not None and version > 0
        ):
            return "update", None, version, "name"
        return "base", None, version, "fallback"

    @staticmethod
    def clean_display_name(path: Path) -> str:
        """Remove somente metadados de cena terminais, preservando o título."""
        cleaned = _TRAILING_METADATA_RE.sub("", path.stem).strip(" ._-[]()")
        return cleaned or path.stem

    @staticmethod
    def association_key(path: Path) -> str:
        """Chave nominal conservadora para complemento sem parent ID resolvível."""
        title = path.stem.split("[", 1)[0]
        title = _AUXILIARY_CONTENT_IN_NAME_RE.sub(" ", title)
        return "".join(character for character in title.casefold() if character.isalnum())

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
