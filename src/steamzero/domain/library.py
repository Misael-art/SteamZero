# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Library: scan, organização transacional, import, dedupe e multidisco.

- Scan: leitura pura (hash blake2b + classificação); NUNCA escreve fora do state
  (AC-LB-01).
- Import: cópia com verificação de hash; a origem NUNCA é alterada (import é
  cópia — RT-07/AC-LB-02). Dedupe por hash. Archive passa por safezip; inseguro =>
  staging limpo + E-CONTENT-UNSAFE-ARCHIVE, origem intocada (AC-LB-03).
- Multidisco: agrupa "(Disc N)" no mesmo multi_disc_group.
- Organização: scan→plan→apply→verify→commit, com confirmação e rollback
  byte-idêntico pelo núcleo transacional (M7/G-FULL).

Conteúdo é sempre do usuário (CONTENT-POLICY): nada é obtido, sugerido ou baixado.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steamzero.core import fs, ids, paths, safezip, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore

_DISC_RE = re.compile(r"\s*\((?:disc|disk)\s*(\d+)\)", re.IGNORECASE)

_FORMAT_BY_EXT = {
    ".chd": "chd",
    ".rvz": "rvz",
    ".iso": "iso",
    ".cue": "cue",
    ".bin": "bin",
    ".m3u": "m3u",
    ".zip": "zip",
    ".7z": "7z",
    ".nes": "nes",
    ".sfc": "snes",
    ".smc": "snes",
    ".gba": "gba",
    ".nds": "nds",
}


def detect_format(name: str) -> str:
    return _FORMAT_BY_EXT.get(Path(name).suffix.lower(), "unknown")


_ARCHIVE_EXTS = frozenset({".zip", ".7z"})

_M3U_RE = re.compile(r"\.m3u$", re.IGNORECASE)


def build_ext_map(manifests: list[dict[str, Any]]) -> dict[str, list[str]]:
    ext_map: dict[str, list[str]] = {}
    for m in manifests:
        for ext in m.get("media", {}).get("extensions", []):
            ext_map.setdefault(f".{ext.lower()}", []).append(m["id"])
    return ext_map


#: Assinaturas de cabeçalho que desambiguam extensões disputadas (D1 passo 2b).
#: ``.iso`` é reivindicada por várias plataformas; só a assinatura decide. Cada
#: entrada é (offset, magic, plataforma) e o offset é lido sob demanda — nunca se
#: lê o arquivo inteiro (AC-LB-01).
_HEADER_MAGICS: tuple[tuple[int, bytes, str], ...] = (
    (0x18, b"\x5d\x1c\x9e\xa3", "nintendo-console"),  # disco Wii
    (0x1C, b"\xc2\x33\x9f\x3d", "nintendo-console"),  # disco GameCube
    (0x10000, b"MICROSOFT*XBOX*MEDIA", "xbox"),
)

#: Lê ``length`` bytes a partir de ``offset``; devolve menos que isso no EOF.
MagicReader = Callable[[int, int], bytes]


def platform_from_magic(read_at: MagicReader) -> str | None:
    """Identifica a plataforma pela assinatura do cabeçalho, ou ``None``.

    Recebe o leitor injetado em vez de um caminho: a função continua pura e os
    testes exercitam cada assinatura sem tocar em disco. Erro de leitura é
    tratado como "não identificado" — desambiguar é oportunista e nunca falha o
    scan (P9).
    """
    for offset, magic, platform_id in _HEADER_MAGICS:
        try:
            if read_at(offset, len(magic)) == magic:
                return platform_id
        except OSError:
            return None
    return None


def classify_rom(
    name: str,
    siblings: set[str],
    ext_map: dict[str, list[str]],
    *,
    root_platform: str | None = None,
    header_platform: str | None = None,
) -> tuple[str | None, str, str]:
    ext = Path(name).suffix.lower()

    if ext in _ARCHIVE_EXTS:
        return None, "unknown", "archived"

    stem = Path(name).stem.lower()
    has_bin = any(
        Path(s).stem.lower() == stem and Path(s).suffix.lower() == ".bin" for s in siblings
    )
    has_cue = any(
        Path(s).stem.lower() == stem and Path(s).suffix.lower() == ".cue" for s in siblings
    )

    if ext == ".cue":
        if has_bin:
            return "playstation", "base", "cue-pair"
        return None, "unknown", "cue-orphan"

    if ext == ".bin":
        if has_cue:
            return "playstation", "base", "cue-pair"
        if root_platform is not None:
            return root_platform, "base", "root-wins"
        return None, "unknown", "bin-orphan"

    platforms = ext_map.get(ext, [])
    if not platforms:
        return None, "unknown", "no-ext-match"

    if root_platform is not None:
        return root_platform, "base", "root-wins"

    if len(platforms) == 1:
        return platforms[0], "base", "exclusive-ext"

    # Extensão disputada: só a assinatura decide, e apenas entre as candidatas
    # daquela extensão — um header que aponta para plataforma que não reivindica
    # a extensão é ignorado em vez de sobrepor o mapa declarado.
    if header_platform is not None and header_platform in platforms:
        return header_platform, "base", "magic-header"

    return None, "unknown", "ambiguous-ext"


@dataclass(frozen=True)
class RomCandidate:
    path: Path
    format: str
    platform: str | None
    content_kind: str
    evidence: str


class PlatformRomScanner:
    def __init__(self, ext_map: dict[str, list[str]]) -> None:
        self._ext_map = ext_map

    @classmethod
    def from_manifests(cls, manifests: list[dict[str, Any]]) -> PlatformRomScanner:
        return cls(build_ext_map(manifests))

    def inventory(self, root: Path, *, root_platform: str | None = None) -> list[RomCandidate]:
        results: list[RomCandidate] = []
        for path in self._iter_files(root):
            siblings = self._siblings(root, path)
            plat, kind, ev = self.classify(
                path.name,
                siblings,
                root_platform=root_platform,
                path=path,
            )
            fmt = _FORMAT_BY_EXT.get(path.suffix.lower(), "unknown")
            results.append(
                RomCandidate(
                    path=path,
                    format=fmt,
                    platform=plat,
                    content_kind=kind,
                    evidence=ev,
                )
            )
        return results

    def classify(
        self,
        name: str,
        siblings: set[str],
        *,
        root_platform: str | None = None,
        path: Path | None = None,
    ) -> tuple[str | None, str, str]:
        """Classifica sem expor o mapa mutável de extensões do scanner."""
        return classify_rom(
            name,
            siblings,
            self._ext_map,
            root_platform=root_platform,
            header_platform=(
                self._header_platform(path, root_platform=root_platform)
                if path is not None
                else None
            ),
        )

    def _header_platform(self, path: Path, *, root_platform: str | None) -> str | None:
        """Lê a assinatura só quando ela pode mudar a decisão.

        Root explícito já resolve, e extensão com uma dona só não tem o que
        desambiguar: nos dois casos nenhum byte é lido. Symlink nunca é aberto
        (FM-13). Falha de I/O devolve ``None`` — o scan degrada para
        ``ambiguous-ext``, nunca levanta.
        """
        if root_platform is not None:
            return None
        if len(self._ext_map.get(path.suffix.lower(), [])) < 2:
            return None
        if path.is_symlink():
            return None
        try:
            with path.open("rb") as handle:

                def read_at(offset: int, length: int) -> bytes:
                    handle.seek(offset)
                    return handle.read(length)

                return platform_from_magic(read_at)
        except OSError:
            return None

    @staticmethod
    def _iter_files(root: Path) -> Iterator[Path]:
        if not root.is_dir():
            return
        for child in sorted(root.iterdir(), key=lambda p: p.name):
            if child.is_file():
                yield child

    @staticmethod
    def _siblings(root: Path, path: Path) -> set[str]:
        if not root.is_dir():
            return {path.name}
        return {p.name for p in root.iterdir() if p.is_file()}


# Diretórios auxiliares nunca são coleções de jogos. A lista é aplicada tanto
# na raiz informada quanto em seus descendentes: uma pasta ``updates`` dentro
# de uma plataforma não pode fazer um update aparecer como jogo base.
_NON_GAME_DIRECTORY_NAMES = frozenset(
    {
        ".directory",
        "_backup",
        "backup",
        "backups",
        "bios",
        "cache",
        "cheat",
        "cheats",
        "dlc",
        "dlcs",
        "emulators",
        "firmware",
        "generic-applications",
        "key",
        "keys",
        "kodi",
        "media",
        "medias",
        "mod",
        "mods",
        "nand",
        "patch",
        "patches",
        "save",
        "saves",
        "screenshot",
        "screenshots",
        "shader",
        "shaders",
        "system",
        "systeminfo",
        "update",
        "updates",
    }
)


def _directory_key(name: str) -> str:
    """Normaliza um nome de diretório sem transformar texto em código."""
    return re.sub(r"[^a-z0-9]+", "", name.casefold())


def _is_non_game_directory(name: str) -> bool:
    return name.casefold() in _NON_GAME_DIRECTORY_NAMES


# Os manifestos são a fonte de verdade. Estes aliases apenas acomodam grafias
# usuais em árvores locais; todos apontam a um ID canônico do próprio registry.
_DIRECTORY_PLATFORM_ALIASES = {
    "amiga600": "amiga",
    "amiga1200": "amiga",
    "amigacd32": "amiga",
    "atari800": "atari-classics",
    "atari800xl": "atari-classics",
    "cps1": "arcade",
    "cps2": "arcade",
    "cps3": "arcade",
    "famicom": "nes-famicom",
    "gameboy": "nintendo-handheld",
    "gameboyadvance": "nintendo-handheld",
    "gameboycolor": "nintendo-handheld",
    "gb": "nintendo-handheld",
    "gba": "nintendo-handheld",
    "gbc": "nintendo-handheld",
    "gc": "nintendo-console",
    "megadrive": "mega-drive",
    "megadrivejp": "mega-drive",
    "megacd": "sega-cd-32x",
    "megacdjp": "sega-cd-32x",
    "msx1": "msx",
    "n3ds": "nintendo-3ds",
    "n64": "nintendo-64",
    "nds": "nintendo-ds",
    "neogeo": "arcade",
    "pce": "pc-engine-turbografx",
    "ps1": "playstation",
    "ps2": "playstation-2",
    "ps3": "playstation-3",
    "psp": "playstation-portable",
    "psx": "playstation",
    "sega32x": "sega-cd-32x",
    "sega32xjp": "sega-cd-32x",
    "sega32xna": "sega-cd-32x",
    "segacd": "sega-cd-32x",
    "sfc": "snes",
    "sms": "master-system",
    "superfamicom": "snes",
    "tg16": "pc-engine-turbografx",
    "turbografx16": "pc-engine-turbografx",
    "wiiu": "wii-u",
    "xbox360": "xbox-360",
}


@dataclass(frozen=True)
class PlatformDirectory:
    """Resultado somente leitura de uma pasta irmã na coleção de ROMs."""

    path: Path
    disposition: str  # matched | excluded | unmatched
    platform_id: str | None
    game_count: int
    selected_games: tuple[RomCandidate, ...]
    skipped_symlinks: int


class PlatformDirectoryInventory:
    """Indexa uma árvore de ROMs estruturada por diretórios de plataforma.

    A classe nunca escreve no conteúdo do usuário. Diretórios que não têm
    correspondência inequívoca permanecem ``unmatched`` para revisão humana;
    em especial, uma extensão não é usada para adivinhar a plataforma de uma
    pasta desconhecida.
    """

    def __init__(self, scanner: PlatformRomScanner, aliases: dict[str, str]) -> None:
        self._scanner = scanner
        self._aliases = dict(aliases)

    @classmethod
    def from_registry(cls, registry: Any) -> PlatformDirectoryInventory:
        manifests = list(registry.list())
        manifest_dicts = [{"id": m.id, "media": dict(m.media)} for m in manifests]
        known_ids = {manifest.id for manifest in manifests}
        aliases: dict[str, str] = {}
        for manifest in manifests:
            for name in (manifest.id, *manifest.systems):
                key = _directory_key(name)
                previous = aliases.get(key)
                if previous is None:
                    aliases[key] = manifest.id
                elif previous != manifest.id:
                    # Um alias ambíguo não é um vínculo seguro.
                    aliases.pop(key, None)
        for alias, platform_id in _DIRECTORY_PLATFORM_ALIASES.items():
            if platform_id in known_ids:
                aliases[_directory_key(alias)] = platform_id
        return cls(PlatformRomScanner.from_manifests(manifest_dicts), aliases)

    def inventory(self, root: Path) -> list[PlatformDirectory]:
        """Lista filhas de ``root`` em ordem estável, sem seguir symlinks.

        ``selected_games`` carrega TODOS os jogos únicos do diretório: a fonte
        canônica não amostra — uma biblioteca que publica 10 jogos de uma
        plataforma com 178 esconde 168 sem diagnóstico (AGENTS.md §8).
        """
        try:
            children = sorted(root.iterdir(), key=lambda item: item.name.casefold())
        except OSError:
            return []

        results: list[PlatformDirectory] = []
        for child in children:
            if child.is_symlink() or not child.is_dir():
                continue
            if _is_non_game_directory(child.name):
                results.append(PlatformDirectory(child, "excluded", None, 0, (), 0))
                continue
            platform_id = self._aliases.get(_directory_key(child.name))
            if platform_id is None:
                results.append(PlatformDirectory(child, "unmatched", None, 0, (), 0))
                continue
            candidates, skipped = self._inventory_tree(child, platform_id)
            selected = tuple(self._unique_games(candidates, child))
            results.append(
                PlatformDirectory(
                    child,
                    "matched",
                    platform_id,
                    self._unique_game_count(candidates, child),
                    selected,
                    skipped,
                )
            )
        return results

    def _inventory_tree(self, root: Path, platform_id: str) -> tuple[list[RomCandidate], int]:
        candidates: list[RomCandidate] = []
        skipped_symlinks = 0
        try:
            for directory, child_dirs, files in os.walk(root, followlinks=False):
                safe_dirs: list[str] = []
                for child_dir in child_dirs:
                    candidate = Path(directory) / child_dir
                    if candidate.is_symlink():
                        skipped_symlinks += 1
                    elif not _is_non_game_directory(child_dir):
                        safe_dirs.append(child_dir)
                child_dirs[:] = safe_dirs
                siblings = set(files)
                for filename in sorted(files, key=str.casefold):
                    path = Path(directory) / filename
                    if path.is_symlink():
                        skipped_symlinks += 1
                        continue
                    platform, kind, evidence = self._scanner.classify(
                        filename,
                        siblings,
                        root_platform=platform_id,
                    )
                    candidates.append(
                        RomCandidate(
                            path=path,
                            format=detect_format(filename),
                            platform=platform,
                            content_kind=kind,
                            evidence=evidence,
                        )
                    )
        except OSError:
            # Inventário é diagnóstico: uma pasta sem permissão não impede que
            # as demais sejam exibidas. O resultado parcial continua verdadeiro.
            pass
        return candidates, skipped_symlinks

    @staticmethod
    def _game_key(candidate: RomCandidate, root: Path) -> str:
        base_title, disc_number = disc_group(candidate.path.stem)
        if disc_number is not None:
            # Discos em subpastas diferentes ainda pertencem ao mesmo título.
            return f"disc:{base_title.casefold()}"
        parent = candidate.path.parent.relative_to(root).as_posix().casefold()
        return f"{parent}:{base_title.casefold()}"

    @classmethod
    def _unique_games(cls, candidates: list[RomCandidate], root: Path) -> list[RomCandidate]:
        chosen: dict[str, RomCandidate] = {}
        # CUE/M3U descrevem o conjunto; BIN é só um membro e nunca deve ocupar
        # uma posição extra no carrossel. A ordem posterior mantém o resultado
        # determinístico quando não há descritor preferido.
        priority = {"m3u": 0, "cue": 1, "chd": 2, "iso": 3, "bin": 9}
        for candidate in candidates:
            if candidate.content_kind != "base" or candidate.platform is None:
                continue
            key = cls._game_key(candidate, root)
            current = chosen.get(key)
            if current is None or (
                priority.get(candidate.format, 5),
                candidate.path.name.casefold(),
            ) < (priority.get(current.format, 5), current.path.name.casefold()):
                chosen[key] = candidate
        return [chosen[key] for key in sorted(chosen)]

    @classmethod
    def _unique_game_count(cls, candidates: list[RomCandidate], root: Path) -> int:
        return len(cls._unique_games(candidates, root))


def disc_group(title: str) -> tuple[str, int | None]:
    """Retorna (título-base, número do disco|None) para agrupamento multidisco."""
    match = _DISC_RE.search(title)
    if match is None:
        return title, None
    base = _DISC_RE.sub("", title).strip()
    return base, int(match.group(1))


@dataclass(frozen=True)
class ScannedRom:
    relpath: str
    size: int
    hash_blake2b: str
    format: str


@dataclass
class ImportResult:
    status: str  # imported | duplicate
    rom_id: str | None
    relpath: str | None
    hash_blake2b: str


class LibraryScanner:
    """Scan read-only de uma árvore de ROMs (AC-LB-01)."""

    def __init__(self, store: StateStore) -> None:
        self._store = store

    def scan(self, root: Path) -> list[ScannedRom]:
        results: list[ScannedRom] = []
        for path in fs.iter_files(root):
            rel = path.relative_to(root)
            results.append(
                ScannedRom(
                    relpath=str(rel),
                    size=path.stat().st_size,
                    hash_blake2b=fs.hash_file(path),
                    format=detect_format(path.name),
                )
            )
        return results


class LibraryOrganizer:
    """Planeja e executa movimentos/renomes explícitos dentro da biblioteca.

    ``moves`` usa caminhos relativos ``origem -> destino``. A árvore inteira é
    escaneada antes do plano, mas nenhum arquivo é alterado até ``apply`` com o
    confirmToken correspondente.
    """

    def __init__(self, store: StateStore) -> None:
        self._scanner = LibraryScanner(store)

    def plan(self, root: Path, moves: dict[str, str]) -> transaction.Plan:
        scanned = {item.relpath: item for item in self._scanner.scan(root)}
        planned: dict[Path, Path] = {}
        for source_name, target_name in moves.items():
            source_rel = fs.validate_relative_entry(source_name)
            target_rel = fs.validate_relative_entry(target_name)
            normalized_source = str(source_rel)
            if normalized_source not in scanned:
                raise SteamZeroError(
                    "E-TX-STALE-PLAN", detail=f"origem não encontrada: {normalized_source}"
                )
            planned[root / source_rel] = root / target_rel
        return transaction.plan_move_files(planned, root=root, kind="library.organize")

    @staticmethod
    def apply(
        plan_id: str, confirm_token: str, *, dry_run: bool = False
    ) -> transaction.ApplyResult:
        return transaction.apply(plan_id, confirm_token, dry_run=dry_run)

    @staticmethod
    def rollback(operation_id: str) -> transaction.RollbackResult:
        return transaction.rollback(operation_id, reason="library-organize")


class LibraryImporter:
    """Import de dumps do usuário (cópia verificada; origem intocada)."""

    def __init__(self, store: StateStore) -> None:
        self._store = store

    def import_file(
        self, src: Path, platform_slug: str, *, title: str | None = None
    ) -> ImportResult:
        slug = ids.require_slug(platform_slug)
        src_hash = fs.hash_file(src)  # origem só é LIDA
        dup = self._store.find_rom_by_hash(src_hash)
        if dup is not None:
            return ImportResult("duplicate", dup["id"], dup["relpath"], src_hash)

        roms = paths.roms_dir()
        dest = fs.resolve_within(roms, roms / slug / src.name)
        data = src.read_bytes()
        fs.write_atomic(dest, data)
        if fs.hash_file(dest) != src_hash:  # cópia corrompida
            fs.remove_file(dest)
            raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="cópia divergente da origem")

        rom_id = self._register(dest, slug, src_hash, title or src.stem)
        return ImportResult("imported", rom_id, str(dest.relative_to(roms)), src_hash)

    def import_archive(self, src: Path, platform_slug: str) -> list[ImportResult]:
        op_id = ids.new_ulid()
        try:
            extracted = safezip.extract_safe(src, op_id)
        except SteamZeroError as exc:
            fs.remove_tree(paths.staging_for(op_id))  # nunca deixa parcial fora
            self._store.append_event(
                "alert", entity=f"import:{src.name}", payload={"code": exc.code}
            )
            raise
        try:
            return [self.import_file(p, platform_slug) for p in extracted]
        finally:
            fs.remove_tree(paths.staging_for(op_id))  # limpa staging após import

    def _register(self, dest: Path, slug: str, rom_hash: str, title: str) -> str:
        self._store.save_platform({"id": slug, "name": slug.upper()})
        base_title, disc = disc_group(title)
        group = base_title if disc is not None else None
        game_id = ids.new_ulid()
        self._store.save_game(
            {
                "id": game_id,
                "platform_id": slug,
                "title": base_title,
                "multi_disc_group": group,
                "state": "ready",
            }
        )
        rom_id = ids.new_ulid()
        self._store.save_rom(
            {
                "id": rom_id,
                "game_id": game_id,
                "volume_id": None,
                "relpath": str(dest.relative_to(paths.roms_dir())),
                "size": dest.stat().st_size,
                "hash_blake2b": rom_hash,
                "format": detect_format(dest.name),
                "verified_at": _now_iso(),
            }
        )
        self._store.append_event(
            "entity.changed", entity=f"rom:{rom_id}", payload={"title": base_title}
        )
        return rom_id


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
