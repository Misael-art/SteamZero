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
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steamzero.core import fs, ids, paths, safezip, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain.multidisc import (
    ArchiveAwareMultiDiscResolver,
    MultiDiscResolution,
    resolve_multidisc,
)

_DISC_RE = re.compile(r"\s*\((?:disc|disk)\s*(\d+)\)", re.IGNORECASE)


def detect_format(name: str, formats: Mapping[str, Sequence[str]] | None = None) -> str:
    """Formato lógico do arquivo a partir da DECLARAÇÃO da plataforma.

    Sem `formats` declarado o formato é honestamente ``unknown`` — nunca mais
    um mapa hardcoded de 14 extensões aplicando hipótese de mídia óptica a
    cartucho, fita e disco igualmente.
    """
    ext = Path(name).suffix.lower().lstrip(".")
    if formats:
        for fmt, exts in formats.items():
            if ext in exts:
                return fmt
    return "unknown"


_ARCHIVE_SUFFIXES = frozenset({".zip", ".7z", ".rar", ".tar.gz", ".tar.bz2", ".tar.xz"})


def _archive_suffix(name: str) -> str | None:
    lowered = name.casefold()
    for suffix in sorted(_ARCHIVE_SUFFIXES, key=len, reverse=True):
        if lowered.endswith(suffix):
            return suffix
    return None


# `containerPolicy` do manifesto: `native` = o container roda direto no
# emulador; `extract` = o conteúdo precisa ser extraído antes do lançamento.
# A ausência não é um terceiro valor com semântica: é falta de declaração, e
# nesse caso o arquivo fica fora do catálogo em vez de virar um palpite.
_CONTAINER_NATIVE = "native"
_CONTAINER_EXTRACT = "extract"

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


def _declares_format(
    platform_formats: Mapping[str, Any] | None, platform_id: str, ext: str
) -> bool:
    """True se a plataforma DECLARA um formato realizado por `ext` (sem ponto).

    Declarar a extensão não basta: o formato precisa existir no mapa
    `media.formats` do manifesto — é ele que nomeia o conteúdo.
    """
    formats = (platform_formats or {}).get(platform_id) or {}
    return any(ext in exts for exts in formats.values())


def _declares_extension(
    platform_extensions: Mapping[str, Sequence[str]] | None,
    platform_id: str,
    ext: str,
) -> bool:
    """Return whether a matched platform declares the file extension."""
    if platform_extensions is None:
        # Direct callers of the pure classifier historically supplied only the
        # global extension map. Keep that API meaningful; manifest-backed
        # scanners always provide the per-platform declaration.
        return True
    declared = platform_extensions.get(platform_id, ())
    if platform_id not in platform_extensions:
        # ``root_platform`` may be a system alias (for example ``ps4``) while
        # the manifest is keyed by its editorial platform id. Keep aliases
        # compatible when the caller did not provide an explicit alias map;
        # canonical manifest ids still receive the strict extension gate.
        return True
    normalized = ext.lstrip(".").casefold()
    return normalized in {str(item).lstrip(".").casefold() for item in declared}


def classify_rom(
    name: str,
    siblings: set[str],
    ext_map: dict[str, list[str]],
    *,
    root_platform: str | None = None,
    header_platform: str | None = None,
    platform_formats: Mapping[str, Any] | None = None,
    platform_extensions: Mapping[str, Sequence[str]] | None = None,
    container_policies: Mapping[str, str] | None = None,
) -> tuple[str | None, str, str]:
    ext = Path(name).suffix.lower()
    archive_suffix = _archive_suffix(name)

    if root_platform in {"playstation-5", "ps5"}:
        lowered = Path(name).name.casefold()
        if ext == ".pkg":
            return None, "unknown", "ps5-pkg-unresolved"
        if ext == ".bin" and lowered != "eboot.bin":
            return None, "unknown", "ps5-auxiliary-bin"
        if ext == ".elf":
            # Um ELF genérico não prova que é um executável PS5. O formato
            # alternativo só pode entrar no catálogo depois de uma identidade
            # PS5 observável; promover por extensão fabricaria jogos a partir
            # de ferramentas, módulos ou dumps de outra plataforma.
            return None, "unknown", "ps5-elf-unresolved"
        if ext != ".bin" and archive_suffix is None:
            return None, "unknown", "ps5-unsupported-entry"

    if archive_suffix is not None:
        # A lista de extensões comprimidas era um veto fixo: qualquer .zip/.7z
        # saía do catálogo antes de qualquer pergunta. Mas 45 dos 63 manifestos
        # declaram `zip` entre as extensões da plataforma, e 22 declaram
        # `containerPolicy: native` — ou seja, o domínio já dizia que aquele
        # container roda direto. O veto fixo vencia a declaração, e ~1000
        # arquivos do acervo real ficavam invisíveis no Launcher.
        #
        # Quem decide agora é a plataforma. Sem plataforma resolvida não há
        # política a consultar, e adivinhar aqui repetiria o erro que custou o
        # ciclo dos defaults de Switch.
        platform = root_platform
        if platform is None:
            candidates = ext_map.get(ext, [])
            if len(candidates) != 1:
                return None, "unknown", "archive-platform-unknown"
            platform = candidates[0]
        policy = (container_policies or {}).get(platform)
        if policy == _CONTAINER_NATIVE:
            return platform, "base", "archive-native"
        if policy == _CONTAINER_EXTRACT:
            # Fica fora do catálogo, mas com o motivo exato: é extraível, não
            # incompatível. O genérico "archived" impedia distinguir o que
            # precisa de trabalho do que precisa de declaração.
            return None, "unknown", "archive-needs-extraction"
        return None, "unknown", "archive-policy-undeclared"

    if root_platform is not None and not _declares_extension(
        platform_extensions, root_platform, ext
    ):
        # A matched platform directory supplies context, not a wildcard. The
        # old root-wins rule promoted manual PNGs and internal BIN modules
        # from an extracted Vita3K installation to games because those
        # extensions existed somewhere else in the global registry.
        return None, "unknown", "unsupported-root-extension"

    stem = Path(name).stem.lower()
    has_bin = any(
        Path(s).stem.lower() == stem and Path(s).suffix.lower() == ".bin" for s in siblings
    )
    has_cue = any(
        Path(s).stem.lower() == stem and Path(s).suffix.lower() == ".cue" for s in siblings
    )

    if ext == ".cue":
        if not has_bin:
            return None, "unknown", "cue-orphan"
        candidates = ext_map.get(".cue", [])
        if root_platform is not None and root_platform in candidates:
            return root_platform, "base", "cue-pair"
        declaring = [p for p in candidates if _declares_format(platform_formats, p, "cue")]
        if len(declaring) == 1:
            return declaring[0], "base", "cue-pair"
        # Vários declaram (ou nenhum): chute seria mentir a plataforma.
        return None, "unknown", "ambiguous-cue"

    if ext == ".bin":
        if has_cue:
            candidates = ext_map.get(".bin", [])
            if root_platform is not None and root_platform in candidates:
                return root_platform, "base", "cue-pair"
            declaring = [p for p in candidates if _declares_format(platform_formats, p, "bin")]
            if len(declaring) == 1:
                return declaring[0], "base", "cue-pair"
            return None, "unknown", "ambiguous-cue-bin"
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
    member_path: str | None = None
    multi_disc_set_id: str | None = None
    multi_disc_state: str | None = None


@dataclass(frozen=True)
class RelatedContent:
    """Arquivo/diretório pertencente a um jogo ou grupo de conteúdo.

    Conteúdo relacionado nunca vira jogo por acidente. Ele permanece visível
    para a Gestão de arquivos, que pode montar uma operação explícita de
    limpeza/organização com preview, confirmação e rollback.
    """

    path: Path
    relation: str  # directory-member | auxiliary-content
    content_kind: str  # internal | update | dlc | unknown
    owner_path: Path | None = None


@dataclass(frozen=True)
class AuxiliaryContent:
    """Update/DLC pronto para associação, seja qual for a plataforma.

    Os dois produtores de auxiliar — o passe do Switch e o inventário canônico
    de diretórios — convergem para esta forma. ``title_id`` e ``version`` são o
    que o Switch consegue extrair do nome e o que as demais plataformas não
    declaram; explícitos como ``None``, eles deixam de ser um atributo que o
    consumidor precisa adivinhar com ``getattr``.
    """

    path: Path
    content_kind: str
    parent_title_id: str | None = None
    title_id: str | None = None
    version: int | None = None

    @classmethod
    def from_candidate(cls, candidate: Any) -> AuxiliaryContent:
        return cls(
            path=candidate.path,
            content_kind=candidate.content_kind,
            parent_title_id=getattr(candidate, "parent_title_id", None),
            title_id=getattr(candidate, "title_id", None),
            version=getattr(candidate, "version", None),
        )


class PlatformRomScanner:
    def __init__(
        self,
        ext_map: dict[str, list[str]],
        platform_formats: dict[str, dict[str, list[str]]] | None = None,
        container_policies: dict[str, str] | None = None,
        manifests: dict[str, dict[str, Any]] | None = None,
        platform_extensions: dict[str, list[str]] | None = None,
        directory_formats: dict[str, list[str]] | None = None,
    ) -> None:
        self._ext_map = ext_map
        self._platform_formats = platform_formats or {}
        self._platform_extensions = platform_extensions
        self._container_policies = container_policies or {}
        self._manifests = manifests or {}
        self._directory_formats = directory_formats or {}

    @classmethod
    def from_manifests(cls, manifests: list[dict[str, Any]]) -> PlatformRomScanner:
        formats_by_platform = {
            str(m["id"]): dict(m.get("media", {}).get("formats") or {}) for m in manifests
        }
        extensions_by_platform = {
            str(m["id"]): [str(ext) for ext in m.get("media", {}).get("extensions", ())]
            for m in manifests
        }
        directory_formats_by_platform = {
            str(m["id"]): [
                str(value) for value in (m.get("media", {}).get("directoryFormats") or [])
            ]
            for m in manifests
        }
        policies = {
            str(m["id"]): str((m.get("media", {}) or {}).get("containerPolicy") or "")
            for m in manifests
            if (m.get("media", {}) or {}).get("containerPolicy")
        }
        return cls(
            build_ext_map(manifests),
            formats_by_platform,
            policies,
            {str(manifest["id"]): manifest for manifest in manifests},
            extensions_by_platform,
            directory_formats_by_platform,
        )

    def container_policy_for(self, platform_id: str | None) -> str:
        """Política de container declarada (vazio quando não declarada)."""
        if platform_id is None:
            return ""
        return self._container_policies.get(platform_id, "")

    def formats_for(self, platform_id: str | None) -> dict[str, list[str]]:
        """Mapa formato->extensões declarado pela plataforma (vazio se não declarado)."""
        if platform_id is None:
            return {}
        return self._platform_formats.get(platform_id, {})

    def multi_disc_manifest_for(self, platform_id: str | None) -> dict[str, Any]:
        """Return the immutable manifest projection used by the set resolver."""

        if platform_id is None:
            return {}
        return self._manifests.get(platform_id, {})

    def directory_formats_for(self, platform_id: str | None) -> tuple[str, ...]:
        if platform_id is None:
            return ()
        return tuple(self._directory_formats.get(platform_id, ()))

    def system_for(self, platform_id: str) -> str:
        systems = self._manifests.get(platform_id, {}).get("systems")
        if isinstance(systems, list) and systems and isinstance(systems[0], str):
            return systems[0]
        return platform_id

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
            # O formato vem da DECLARAÇÃO da plataforma classificada (ou da
            # raiz, enquanto não classificado) — não de um mapa hardcoded.
            fmt = detect_format(path.name, self.formats_for(plat or root_platform) or None)
            if fmt == "unknown" and ev == "archive-native":
                # Um container nativo É o formato entregue ao emulador. Só um
                # manifesto (arcade) lista `zip` em `media.formats`, então o
                # mapa declarado devolveria "unknown" para os demais e o jogo
                # entraria no catálogo sem formato nenhum.
                fmt = path.suffix.lower().lstrip(".")
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
            # `platform_formats` existia no scanner e nunca era repassado, então
            # `_declares_format` respondia falso sempre e a desambiguação por
            # formato declarado era código morto: todo .cue/.bin disputado caía
            # em `ambiguous-*` sem consultar quem declarava o formato.
            platform_formats=self._platform_formats,
            platform_extensions=self._platform_extensions,
            container_policies=self._container_policies,
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
        ".steamzero",
        ".steamzero-quarantine",
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


def system_for_path(path: Path, root: Path, systems: Sequence[str]) -> str | None:
    """Qual SISTEMA da plataforma o caminho declara, ou ``None``.

    O manifesto agrupa sistemas que compartilham runtime: `nintendo-handheld`
    cobre gb, gbc e gba; `nes-famicom` cobre nes e famicom. O agrupamento existe
    porque o emulador é o mesmo, e vazou para a experiência — 296 jogos viram
    "nintendo-handheld" na tela.

    A informação para desfazer isso já está no disco: o acervo real tem
    diretórios separados para gb, gbc, gba, nes, famicom, snes, sfc. Esta função
    lê o que o usuário já organizou; ela não deduz por extensão, porque 43 das
    213 extensões declaradas pertencem a mais de uma plataforma.

    Os 101 nomes de sistema declarados são únicos entre todas as plataformas,
    então um diretório que casa com um deles não é ambíguo. Sem casamento
    devolve ``None``: o jogo fica no grupo e a UI diz o grupo, em vez de a
    varredura inventar um sistema.
    """
    declared = {_directory_key(name): name for name in systems}
    if not declared:
        return None
    try:
        parts = path.relative_to(root).parts[:-1]
    except ValueError:
        parts = path.parts[:-1]
    # O diretório mais específico vence: `roms/nintendo/gbc/jogo.gbc` deve
    # resolver gbc, não o ancestral.
    for part in reversed(parts):
        match = declared.get(_directory_key(part))
        if match is not None:
            return match
    return None


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
    auxiliary_content: tuple[RomCandidate, ...]
    skipped_symlinks: int
    multi_disc_sets: tuple[MultiDiscResolution, ...] = ()
    related_content: tuple[RelatedContent, ...] = ()
    unclaimed_content: tuple[Path, ...] = ()


class PlatformDirectoryInventory:
    """Indexa uma árvore de ROMs estruturada por diretórios de plataforma.

    A classe nunca escreve no conteúdo do usuário. Diretórios que não têm
    correspondência inequívoca permanecem ``unmatched`` para revisão humana;
    em especial, uma extensão não é usada para adivinhar a plataforma de uma
    pasta desconhecida.
    """

    def __init__(
        self, scanner: PlatformRomScanner, aliases: dict[str, str], auxiliary: dict[str, str]
    ) -> None:
        self._scanner = scanner
        self._aliases = dict(aliases)
        self._auxiliary = dict(auxiliary)

    @classmethod
    def from_registry(cls, registry: Any) -> PlatformDirectoryInventory:
        manifests = list(registry.list())
        manifest_dicts = [
            {"id": m.id, "systems": list(m.systems), "media": dict(m.media)} for m in manifests
        ]
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
        auxiliary = {m.id: str(m.media.get("auxiliaryContent") or "none") for m in manifests}
        return cls(PlatformRomScanner.from_manifests(manifest_dicts), aliases, auxiliary)

    def inventory(
        self,
        root: Path,
        *,
        include_unclaimed: bool = False,
        safepoint: Callable[[], None] | None = None,
        progress: Callable[[int, int, str], None] | None = None,
    ) -> list[PlatformDirectory]:
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
        total = len(children)
        for index, child in enumerate(children, start=1):
            if safepoint is not None:
                safepoint()
            if progress is not None:
                progress(index, total, child.name)
            if child.is_symlink() or not child.is_dir():
                continue
            if _is_non_game_directory(child.name):
                unclaimed = (
                    self._unclaimed_files(child, safepoint=safepoint)
                    if include_unclaimed
                    and child.name not in {".steamzero", ".steamzero-quarantine"}
                    else ()
                )
                results.append(
                    PlatformDirectory(child, "excluded", None, 0, (), (), 0, (), (), unclaimed)
                )
                continue
            platform_id = self._aliases.get(_directory_key(child.name))
            if platform_id is None:
                unclaimed = (
                    self._unclaimed_files(child, safepoint=safepoint)
                    if include_unclaimed
                    else ()
                )
                results.append(
                    PlatformDirectory(child, "unmatched", None, 0, (), (), 0, (), (), unclaimed)
                )
                continue
            candidates, skipped, visited = self._inventory_tree(
                child,
                platform_id,
                include_unclaimed=include_unclaimed,
                safepoint=safepoint,
            )
            multi_disc_sets = self._resolve_multidisc(candidates, platform_id)
            selected = tuple(self._unique_games(candidates, child, multi_disc_sets))
            related_content = self._related_content(
                child, candidates, selected, multi_disc_sets, visited=visited
            )
            claimed = {candidate.path for candidate in selected}
            claimed.update(item.path for item in related_content)
            unclaimed = tuple(
                path
                for path in visited
                if path.is_file()
                and path not in claimed
                and not self._managed_path(path, child)
            )
            results.append(
                PlatformDirectory(
                    child,
                    "matched",
                    platform_id,
                    self._unique_game_count(candidates, child, multi_disc_sets),
                    selected,
                    tuple(
                        candidate for candidate in candidates if candidate.content_kind != "base"
                    ),
                    skipped,
                    tuple(multi_disc_sets),
                    related_content,
                    unclaimed,
                )
            )
        return results

    def _inventory_tree(
        self,
        root: Path,
        platform_id: str,
        *,
        include_unclaimed: bool = False,
        safepoint: Callable[[], None] | None = None,
    ) -> tuple[list[RomCandidate], int, tuple[Path, ...]]:
        candidates: list[RomCandidate] = []
        skipped_symlinks = 0
        visited: set[Path] = set()
        try:
            for game_directory in self._directory_game_candidates(root, platform_id):
                candidates.append(
                    RomCandidate(
                        path=game_directory,
                        format="vita3k-app",
                        platform=platform_id,
                        content_kind="base",
                        evidence="directory-native",
                    )
                )
            for directory, child_dirs, files in os.walk(root, followlinks=False):
                if safepoint is not None:
                    safepoint()
                current = Path(directory)
                if include_unclaimed:
                    visited.add(current)
                    for filename in files:
                        path = current / filename
                        if not path.is_symlink():
                            visited.add(path)
                safe_dirs: list[str] = []
                for child_dir in child_dirs:
                    candidate = Path(directory) / child_dir
                    if candidate.is_symlink():
                        skipped_symlinks += 1
                    elif (include_unclaimed and child_dir not in {
                        ".steamzero",
                        ".steamzero-quarantine",
                    }) or self._auxiliary_kind(
                        platform_id, child_dir
                    ) is not None or not _is_non_game_directory(child_dir):
                        safe_dirs.append(child_dir)
                        if include_unclaimed:
                            visited.add(candidate)
                child_dirs[:] = safe_dirs
                blocked = include_unclaimed and any(
                    _is_non_game_directory(part)
                    and self._auxiliary_kind(platform_id, part) is None
                    for part in current.relative_to(root).parts
                )
                if blocked:
                    continue
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
                    multi_disc_manifest = self._scanner.multi_disc_manifest_for(platform_id)
                    multi_disc_policy = multi_disc_manifest.get("media")
                    multi_disc_config = (
                        multi_disc_policy.get("multiDisc")
                        if isinstance(multi_disc_policy, Mapping)
                        else None
                    )
                    archive_name = path.name.casefold()
                    archive_candidate = any(
                        archive_name.endswith(suffix) for suffix in _ARCHIVE_SUFFIXES
                    )
                    if (
                        archive_candidate
                        and isinstance(multi_disc_config, Mapping)
                        and multi_disc_config.get("enabled") is True
                    ):
                        platform, kind, evidence = (
                            platform_id,
                            "base",
                            "archive-indexed",
                        )
                    elif (
                        archive_candidate
                        and self._scanner.container_policy_for(platform_id) == _CONTAINER_EXTRACT
                    ):
                        # Containers extract-only permanecem visíveis como
                        # conteúdo recuperável. Antes eles eram descartados
                        # pelo scanner e o usuário não tinha título, motivo ou
                        # caminho para iniciar a preparação — especialmente
                        # RAR de PS4/PS5. O preflight continua recusando spawn
                        # até a materialização validada.
                        platform, kind, evidence = (
                            platform_id,
                            "base",
                            "archive-needs-extraction",
                        )
                    relative_parts = path.relative_to(root).parts[:-1]
                    auxiliary_kind = next(
                        filter(
                            None,
                            (self._auxiliary_kind(platform_id, part) for part in relative_parts),
                        ),
                        None,
                    )
                    # `detect_format` sem o mapa declarado sempre devolvia
                    # "unknown": 216 dos 231 jogos do acervo real entravam no
                    # catálogo sem formato. O mapa da plataforma é exatamente o
                    # que nomeia o conteúdo, e o scanner já o carrega.
                    fmt = detect_format(
                        filename, self._scanner.formats_for(platform or platform_id) or None
                    )
                    if fmt == "unknown" and evidence.startswith("archive-"):
                        fmt = path.suffix.lower().lstrip(".")
                    candidates.append(
                        RomCandidate(
                            path=path,
                            format=fmt,
                            platform=platform,
                            content_kind=auxiliary_kind or kind,
                            evidence="manifest-auxiliary-directory" if auxiliary_kind else evidence,
                        )
                    )
        except OSError:
            # Inventário é diagnóstico: uma pasta sem permissão não impede que
            # as demais sejam exibidas. O resultado parcial continua verdadeiro.
            pass
        return candidates, skipped_symlinks, tuple(
            sorted(visited, key=lambda item: item.as_posix().casefold())
        )

    @staticmethod
    def _managed_path(path: Path, root: Path) -> bool:
        try:
            parts = path.relative_to(root).parts
        except ValueError:
            parts = path.parts
        return any(part in {".steamzero", ".steamzero-quarantine"} for part in parts)

    @classmethod
    def _unclaimed_files(
        cls,
        root: Path,
        *,
        safepoint: Callable[[], None] | None = None,
    ) -> tuple[Path, ...]:
        files: list[Path] = []
        try:
            for directory, child_dirs, names in os.walk(root, followlinks=False):
                if safepoint is not None:
                    safepoint()
                current = Path(directory)
                child_dirs[:] = [
                    name
                    for name in child_dirs
                    if name not in {".steamzero", ".steamzero-quarantine"}
                    and not (current / name).is_symlink()
                ]
                files.extend(
                    current / name
                    for name in names
                    if not (current / name).is_symlink()
                )
        except OSError:
            pass
        return tuple(sorted(files, key=lambda item: item.as_posix().casefold()))

    @staticmethod
    def _related_content(
        root: Path,
        candidates: Sequence[RomCandidate],
        selected: Sequence[RomCandidate] = (),
        multi_disc_sets: Sequence[MultiDiscResolution] = (),
        *,
        visited: Sequence[Path] = (),
    ) -> tuple[RelatedContent, ...]:
        """Relaciona membros de formatos de diretório e auxiliares da plataforma.

        A regra é declarativa e independente de Vita: qualquer manifesto que
        introduza um ``directoryFormat`` reconhecido ganha a mesma relação.
        Conteúdo auxiliar sem proprietário inequívoco continua agrupado na
        plataforma, sem ser falsamente anexado a outro jogo.
        """
        directory_owners = tuple(
            candidate.path
            for candidate in candidates
            if candidate.content_kind == "base" and candidate.path.is_dir()
        )
        related: dict[Path, RelatedContent] = {}
        selected_paths = {candidate.path for candidate in selected}
        selected_by_key = {
            PlatformDirectoryInventory._game_key(candidate, root, multi_disc_sets): candidate.path
            for candidate in selected
        }
        if visited:
            owners = set(directory_owners)
            for member in visited:
                owner = next(
                    (ancestor for ancestor in member.parents if ancestor in owners),
                    None,
                )
                if owner is None or member.is_symlink() or not member.exists():
                    continue
                if member.is_file() or member.is_dir():
                    related[member] = RelatedContent(
                        path=member,
                        relation="directory-member",
                        content_kind="internal",
                        owner_path=owner,
                    )
        else:
            for owner in directory_owners:
                try:
                    members: list[Path] = []
                    for directory, child_dirs, files in os.walk(owner, followlinks=False):
                        current = Path(directory)
                        child_dirs[:] = [
                            name for name in child_dirs if not (current / name).is_symlink()
                        ]
                        members.extend(current / name for name in (*child_dirs, *files))
                    members.sort(key=lambda item: item.as_posix().casefold())
                except OSError:
                    members = []
                for member in members:
                    if member.is_symlink() or not member.exists():
                        continue
                    if member.is_file() or member.is_dir():
                        related[member] = RelatedContent(
                            path=member,
                            relation="directory-member",
                            content_kind="internal",
                            owner_path=owner,
                        )
        for candidate in candidates:
            if candidate.path in selected_paths:
                continue
            if any(
                candidate.path == owner or owner in candidate.path.parents
                for owner in directory_owners
            ):
                continue
            if candidate.content_kind == "base":
                owner_path = selected_by_key.get(
                    PlatformDirectoryInventory._game_key(candidate, root, multi_disc_sets)
                )
                if owner_path is None:
                    continue
                related.setdefault(
                    candidate.path,
                    RelatedContent(
                        path=candidate.path,
                        relation="game-member",
                        content_kind="internal",
                        owner_path=owner_path,
                    ),
                )
                continue
            related.setdefault(
                candidate.path,
                RelatedContent(
                    path=candidate.path,
                    relation="auxiliary-content",
                    content_kind=candidate.content_kind,
                    owner_path=None,
                ),
            )
        return tuple(sorted(related.values(), key=lambda item: item.path.as_posix().casefold()))

    def _directory_game_candidates(self, root: Path, platform_id: str) -> tuple[Path, ...]:
        """Recognize declared game directories without indexing their internals."""
        if "vita3k-app" not in self._scanner.directory_formats_for(platform_id):
            return ()
        candidates: list[Path] = []

        def add(candidate: Path) -> None:
            if (
                candidate.is_symlink()
                or not candidate.is_dir()
                or not re.fullmatch(r"[A-Z]{4}[0-9]{5}", candidate.name)
                or not (candidate / "sce_sys" / "param.sfo").is_file()
                or not (candidate / "eboot.bin").is_file()
            ):
                return
            candidates.append(candidate)

        add(root)
        try:
            app_roots = [root / "app"]
            app_roots.extend(child / "app" for child in root.iterdir() if child.is_dir())
            for app_root in app_roots:
                if app_root.is_symlink() or not app_root.is_dir():
                    continue
                for child in sorted(app_root.iterdir(), key=lambda item: item.name.casefold()):
                    add(child)
        except OSError:
            return tuple(candidates)
        return tuple(dict.fromkeys(candidates))

    def _auxiliary_kind(self, platform_id: str, directory: str) -> str | None:
        policy = self._auxiliary.get(platform_id, "none")
        name = directory.casefold()
        if name in {"update", "updates", "patch", "patches"} and policy in {"update", "both"}:
            return "update"
        if name in {"dlc", "dlcs"} and policy in {"dlc", "both"}:
            return "dlc"
        return None

    def _resolve_multidisc(
        self, candidates: list[RomCandidate], platform_id: str
    ) -> tuple[MultiDiscResolution, ...]:
        manifest = self._scanner.multi_disc_manifest_for(platform_id)
        if not manifest:
            return ()
        files = [
            candidate.path
            for candidate in candidates
            if candidate.content_kind == "base"
            and candidate.path.suffix.casefold() not in {".zip", ".7z"}
        ]
        loose = resolve_multidisc(
            platform_id, self._scanner.system_for(platform_id), files, manifest
        )
        archives = [
            candidate.path
            for candidate in candidates
            if candidate.content_kind == "base"
            and candidate.path.suffix.casefold() in {".zip", ".7z"}
        ]
        archive_sets = ArchiveAwareMultiDiscResolver(manifest).resolve(
            platform_id, self._scanner.system_for(platform_id), archives
        )
        return (*loose, *archive_sets)

    @staticmethod
    def _game_key(
        candidate: RomCandidate,
        root: Path,
        multi_disc_sets: Sequence[MultiDiscResolution] = (),
    ) -> str:
        for logical_set in multi_disc_sets:
            if logical_set.state == "needs-platform-contract":
                continue
            if any(part.path == candidate.path for part in logical_set.parts):
                return f"multi:{logical_set.set_id}"
        base_title, disc_number = disc_group(candidate.path.stem)
        if disc_number is not None:
            normalized_base = re.sub(r"\s+", " ", base_title.casefold()).strip()
            for logical_set in multi_disc_sets:
                if logical_set.state == "needs-platform-contract":
                    continue
                if logical_set.normalized_title == normalized_base:
                    return f"multi:{logical_set.set_id}"
        parent = candidate.path.parent.relative_to(root).as_posix().casefold()
        # Without a declared set contract, every marked file remains visible
        # for review; a filename marker alone is never a logical association.
        title_key = (
            candidate.path.stem.casefold() if disc_number is not None else base_title.casefold()
        )
        return f"{parent}:{title_key}"

    @classmethod
    def _unique_games(
        cls,
        candidates: list[RomCandidate],
        root: Path,
        multi_disc_sets: Sequence[MultiDiscResolution] = (),
    ) -> list[RomCandidate]:
        chosen: dict[str, RomCandidate] = {}
        archive_paths: set[Path] = set()
        for logical_set in multi_disc_sets:
            archive_parts = [part for part in logical_set.parts if part.archive_path is not None]
            if not archive_parts:
                continue
            archive_paths.update(part.archive_path for part in archive_parts if part.archive_path)
            source = next(
                (candidate for candidate in candidates if candidate.path == archive_parts[0].path),
                None,
            )
            if source is None:
                continue
            first = archive_parts[0]
            chosen[f"multi:{logical_set.set_id}"] = RomCandidate(
                path=source.path,
                format=source.format,
                platform=source.platform,
                content_kind="base",
                evidence=f"archive-multidisc-{logical_set.state}",
                member_path=first.member_path,
                multi_disc_set_id=logical_set.set_id,
                multi_disc_state=logical_set.state,
            )
        # CUE/M3U descrevem o conjunto; BIN é só um membro e nunca deve ocupar
        # uma posição extra no carrossel. A ordem posterior mantém o resultado
        # determinístico quando não há descritor preferido.
        priority = {"m3u": 0, "cue": 1, "chd": 2, "iso": 3, "bin": 9}
        for candidate in candidates:
            if candidate.content_kind != "base" or candidate.platform is None:
                continue
            if candidate.path in archive_paths:
                continue
            key = cls._game_key(candidate, root, multi_disc_sets)
            current = chosen.get(key)
            if current is None or (
                priority.get(candidate.format, 5),
                candidate.path.name.casefold(),
            ) < (priority.get(current.format, 5), current.path.name.casefold()):
                chosen[key] = candidate
        return [chosen[key] for key in sorted(chosen)]

    @classmethod
    def _unique_game_count(
        cls,
        candidates: list[RomCandidate],
        root: Path,
        multi_disc_sets: Sequence[MultiDiscResolution] = (),
    ) -> int:
        return len(cls._unique_games(candidates, root, multi_disc_sets))


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
