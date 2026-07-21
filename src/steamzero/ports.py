# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Portas de capacidade (contratos) — camada neutra de inversão de dependência.

Protocols + DTOs que ``domain.*`` consome e ``adapters.*`` implementa. Vive aqui
(não em domain) para que os adapters NÃO importem domain (MODULE-BOUNDARIES:
"adapters dependem de core.*, nunca de domain.* nem api.*"). Depende apenas de
stdlib. A composição (steamzero.runtime) injeta as implementações concretas.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


# --- Device (DMI) ----------------------------------------------------------
class DevicePort(Protocol):
    """Leitura de identificação de hardware (DMI/sysfs)."""

    def read_dmi(self) -> dict[str, str]:
        """Campos DMI: product_name, sys_vendor, board_name (valores crus)."""
        ...


# --- Display ---------------------------------------------------------------
@dataclass(frozen=True)
class DisplayProfile:
    label: str  # degrau da cadeia (target, no-hdr, ..., internal)
    output: str  # internal | external
    width: int
    height: int
    refresh_hz: int
    hdr: bool
    vrr: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "output": self.output,
            "width": self.width,
            "height": self.height,
            "refreshHz": self.refresh_hz,
            "hdr": self.hdr,
            "vrr": self.vrr,
        }


class DisplayPort(Protocol):
    """Aplica um perfil de display e confirma sinal válido."""

    def apply(self, profile: DisplayProfile) -> bool: ...


# --- Storage ---------------------------------------------------------------
@dataclass(frozen=True)
class VolumeInfo:
    uuid: str
    label: str | None
    fstype: str | None
    role: str  # internal | microsd | usb
    mountpoint: str | None  # None = não montado
    capacity: int | None = None
    free: int | None = None


class StoragePort(Protocol):
    """Enumeração de volumes por UUID (/dev/disk/by-uuid + /proc/mounts)."""

    def list_volumes(self) -> list[VolumeInfo]: ...


# --- Session ---------------------------------------------------------------
class SessionPort(Protocol):
    """Controle do processo/emulador em execução."""

    def launch(self, game_id: str) -> bool: ...
    def is_alive(self) -> bool: ...
    def flush_save(self) -> bool: ...
    def signal_close(self) -> None: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...


# --- Cloud sync ------------------------------------------------------------
class CloudPort(Protocol):
    """Sincronização remota (fila/rate limit aplicados pela porta)."""

    def available(self) -> bool: ...
    def upload(self, digest: str, data: bytes) -> str: ...
    def fetch_divergent(self, game_id: str, local_digest: str) -> bytes | None: ...


# --- Conversão -------------------------------------------------------------
class ConversionTimeout(Exception):
    """A ferramenta de conversão excedeu o tempo limite."""


class ConverterPort(Protocol):
    """Ferramenta de conversão. Escreve ``dst``; True=ok; pode levantar ConversionTimeout."""

    def convert(self, src: Path, dst: Path, target_format: str) -> bool: ...


# --- Mod management (Switch emulators) -------------------------------------
@dataclass(frozen=True)
class ModIdentity:
    """Identificação de um mod no catálogo remoto.

    ``source`` descreve a origem (``ns-emu-mod-downloader``, ``semdb``,
    ``github:stevensnd``, ``github:fl4sh9174``).
    """

    name: str
    mod_type: str
    source: str
    source_url: str
    version: str | None = None
    description: str | None = None
    author: str | None = None
    requirements: str | None = None


@dataclass(frozen=True)
class ModCandidate:
    """Candidato a mod retornado por uma fonte de catálogo.

    ``match_confidence`` (0.0-1.0): 1.0 se Title ID + Build ID casaram,
    <1.0 se apenas Title ID ou match fuzzy por nome.
    """

    title_id: str
    build_id: str | None
    identity: ModIdentity
    match_confidence: float = 1.0


@dataclass(frozen=True)
class InstalledModView:
    """Visão de um mod instalado para a UI / CLI."""

    mod_id: str
    game_id: str
    title_id: str
    build_id: str | None
    name: str
    mod_type: str
    state: str
    emulator_id: str | None
    install_path: str | None
    source: str
    version: str | None


class ModCatalogPort(Protocol):
    """Busca mods disponíveis em fontes remotas por Title ID / Build ID."""

    def search_by_title_id(self, title_id: str) -> list[ModCandidate]: ...

    def search_by_build_id(self, title_id: str, build_id: str) -> list[ModCandidate]: ...

    def refresh_catalog(self) -> int:
        """Atualiza o catálogo local de todas as fontes; retorna total de entradas."""
        ...


class ModInstallerPort(Protocol):
    """Instala / remove / ativa / desativa mods no diretório do emulador."""

    def install(
        self,
        candidate: ModIdentity,
        game_title_id: str,
        emulator_id: str,
        files: Sequence[tuple[str, bytes]],
    ) -> Path: ...

    def remove(self, install_path: Path) -> bool: ...

    def activate(self, install_path: Path) -> bool: ...

    def deactivate(self, install_path: Path) -> bool: ...

    def list_installed_mods(self, title_id: str, emulator_id: str) -> list[InstalledModView]: ...


class BuildIdProviderPort(Protocol):
    """Extrai Build IDs de ROMs / NCAs instaladas."""

    def scan_game(self, game_id: str) -> list[str]: ...

    def scan_rom_file(self, rom_path: Path) -> list[str]: ...


# --- Cheat management (Switch emulators) ------------------------------------
@dataclass(frozen=True)
class CheatIdentity:
    """Identificação de um cheat no catálogo remoto.

    ``source`` descreve a origem (``nsecm``, ``cheatslips``, ``gba_temp``,
    ``github:tomad``).
    """

    name: str
    cheat_type: str
    source: str
    source_url: str
    description: str | None = None
    author: str | None = None
    version: str | None = None


@dataclass(frozen=True)
class CheatCandidate:
    """Candidato a cheat retornado por uma fonte de catálogo.

    ``match_confidence`` (0.0-1.0): 1.0 se Title ID + Build ID casaram.
    ``codes`` são as linhas de código Asm / Atmosphere.
    """

    title_id: str
    build_id: str | None
    identity: CheatIdentity
    codes: tuple[str, ...] = ()
    match_confidence: float = 1.0


@dataclass(frozen=True)
class InstalledCheatView:
    """Visão de um cheat instalado para a UI / CLI."""

    cheat_id: str
    game_id: str
    title_id: str
    build_id: str | None
    name: str
    cheat_type: str
    state: str
    emulator_id: str | None
    install_path: str | None
    source: str
    version: str | None
    code_count: int = 0
    enabled: bool = False


class CheatCatalogPort(Protocol):
    """Busca cheats disponíveis em fontes remotas por Title ID / Build ID."""

    def search_by_title_id(self, title_id: str) -> list[CheatCandidate]: ...

    def search_by_build_id(self, title_id: str, build_id: str) -> list[CheatCandidate]: ...

    def refresh_catalog(self) -> int:
        """Atualiza o catálogo local de todas as fontes; retorna total de entradas."""
        ...


class CheatInstallerPort(Protocol):
    """Instala / remove / ativa / desativa cheats no diretório do emulador.

    Cheats do Switch usam a estrutura ``contents/<title_id>/cheats/<build_id>.txt``
    no diretório ``load/`` do emulador (padrão Atmosphere).
    """

    def install(
        self,
        title_id: str,
        build_id: str | None,
        name: str,
        codes: tuple[str, ...],
        emulator_id: str,
    ) -> Path: ...

    def remove(self, title_id: str, build_id: str, emulator_id: str) -> bool: ...

    def enable(self, title_id: str, build_id: str, emulator_id: str) -> bool: ...

    def disable(self, title_id: str, build_id: str, emulator_id: str) -> bool: ...

    def list_installed(self, title_id: str, emulator_id: str) -> list[InstalledCheatView]: ...

    def edit_codes(
        self,
        title_id: str,
        build_id: str,
        emulator_id: str,
        codes: tuple[str, ...],
    ) -> bool:
        """Substitui os códigos de um cheat instalado."""
        ...


# --- Native ROM metadata / icon extraction (Switch) -------------------------
@dataclass(frozen=True)
class RomMetadata:
    """Metadados extraídos nativamente de uma ROM de Switch.

    ``icon_bytes`` contém os bytes crus do ícone (JPEG ou PNG). ``icon_format``
    indica o formato da imagem. ``source`` descreve a origem (``nca``, ``nsp``,
    ``xci``, ``emulator-cache``, ``fallback``).
    """

    title_id: str
    title: str
    developer: str | None = None
    version: str | None = None
    languages: tuple[str, ...] = ()
    icon_bytes: bytes | None = None
    icon_format: str = ""
    source: str = ""


class RomMetadataPort(Protocol):
    """Extrai metadados e ícones nativos de arquivos de ROM Switch.

    Opera sem depender de chaves criptográficas: usa heurísticas de
    byte-scanning para JPEG/PNG no corpo do NCA e parsing de cabeçalho
    NCA (não criptografado) para Title ID e layout. Resultados podem
    ser parciais; o chamador aplica a cadeia de fallback.
    """

    def extract_metadata(self, rom_path: Path) -> RomMetadata | None: ...

    def extract_icon(self, rom_path: Path) -> tuple[bytes, str] | None:
        """Retorna (icon_bytes, icon_format) ou None se não encontrado."""
        ...


class EmulatorCachePort(Protocol):
    """Leitura de caches de ícones criados por emuladores Switch.

    Emuladores como Ryujinx e Yuzu/Eden geram thumbnails de jogos durante
    a varredura da biblioteca. Esta porta permite reaproveitar esse cache
    sem reprocessar a ROM.
    """

    def find_icon(self, title_id: str) -> Path | None:
        """Caminho do ícone em cache do emulador, ou None."""
        ...

    def find_title(self, title_id: str) -> str | None:
        """Nome do jogo do cache do emulador, ou None."""
        ...


# --- Scraping / media providers -------------------------------------------
@dataclass(frozen=True)
class GameIdentity:
    """O que sabemos sobre um jogo para buscar mídia.

    ``hashes`` mapeia algoritmo -> valor hex
    (ex.: ``{"sha1": "...", "md5": "...", "crc32": "..."}``).
    ``title_id`` e o ID numerico da plataforma (ex.: Title ID do Switch ``0100...``,
    serial SLUS- do PS1). ``serial`` e o codigo de catalogo (ex.: ``SLUS-12345``).
    """

    game_id: str
    title: str
    platform_slug: str
    title_id: str | None = None
    hashes: dict[str, str] = field(default_factory=dict)
    region: str | None = None
    serial: str | None = None


@dataclass(frozen=True)
class MediaCandidate:
    """Candidato a mídia retornado por um provider.

    ``confidence`` (0.0-1.0) reflete a qualidade do match (1.0 = match exato
    por hash ou title_id; <1.0 = match por nome com risco de falsa identificação).
    """

    url: str
    media_kind: str
    provider: str
    confidence: float
    width: int | None = None
    height: int | None = None
    language: str | None = None
    region: str | None = None
    license: str = ""
    attribution: str = ""
    hash: str | None = None
    etag: str | None = None
    expires_at: str | None = None


class MediaProviderPort(Protocol):
    """Contrato para provedores de mídia de jogos.

    Cada provider declara quais tipos de mídia e plataformas suporta.
    A ordem de fallback entre providers é definida pelo ``ProviderRegistry``,
    não pelo provider individual.
    """

    @property
    def name(self) -> str:
        """Nome estável do provider (ex.: ``screenscraper``, ``igdb``)."""
        ...

    def supported_kinds(self) -> frozenset[str]:
        """Tipos de mídia que este provider pode retornar
        (ex.: ``{"boxart", "screenshot", "wheel", "fanart"}``)."""
        ...

    def supported_platforms(self) -> frozenset[str]:
        """Slugs de plataforma que este provider conhece
        (ex.: ``{"switch", "psx", "snes", "megadrive"}``)."""
        ...

    def search(
        self,
        identity: GameIdentity,
        media_kinds: list[str],
        region_priority: list[str] | None = None,
    ) -> list[MediaCandidate]: ...
