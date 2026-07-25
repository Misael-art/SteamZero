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

from steamzero.core.secret import Secret


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
    title_id: str
    build_id: str | None
    identity: ModIdentity
    match_confidence: float = 1.0


@dataclass(frozen=True)
class InstalledModView:
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
    def search_by_title_id(self, title_id: str) -> list[ModCandidate]: ...
    def search_by_build_id(self, title_id: str, build_id: str) -> list[ModCandidate]: ...
    def refresh_catalog(self) -> int: ...


class ModInstallerPort(Protocol):
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
    def scan_game(self, game_id: str) -> list[str]: ...
    def scan_rom_file(self, rom_path: Path) -> list[str]: ...


# --- Cheat management (Switch emulators) ------------------------------------
@dataclass(frozen=True)
class CheatIdentity:
    name: str
    cheat_type: str
    source: str
    source_url: str
    description: str | None = None
    author: str | None = None
    version: str | None = None


@dataclass(frozen=True)
class CheatCandidate:
    title_id: str
    build_id: str | None
    identity: CheatIdentity
    codes: tuple[str, ...] = ()
    match_confidence: float = 1.0


@dataclass(frozen=True)
class InstalledCheatView:
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
    def search_by_title_id(self, title_id: str) -> list[CheatCandidate]: ...
    def search_by_build_id(self, title_id: str, build_id: str) -> list[CheatCandidate]: ...
    def refresh_catalog(self) -> int: ...


class CheatInstallerPort(Protocol):
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
    def list_installed(
        self,
        title_id: str,
        emulator_id: str,
    ) -> list[InstalledCheatView]: ...
    def edit_codes(
        self,
        title_id: str,
        build_id: str,
        emulator_id: str,
        codes: tuple[str, ...],
    ) -> bool: ...


# --- Native ROM metadata / icon extraction (Switch) -------------------------
@dataclass(frozen=True)
class RomMetadata:
    title_id: str
    title: str
    developer: str | None = None
    version: str | None = None
    languages: tuple[str, ...] = ()
    icon_bytes: bytes | None = None
    icon_format: str = ""
    source: str = ""


class RomMetadataPort(Protocol):
    def extract_metadata(self, rom_path: Path) -> RomMetadata | None: ...
    def extract_icon(self, rom_path: Path) -> tuple[bytes, str] | None: ...


class EmulatorCachePort(Protocol):
    def find_icon(self, title_id: str) -> Path | None: ...
    def find_title(self, title_id: str) -> str | None: ...


# --- ROM discovery / format parsers ----------------------------------------
@dataclass(frozen=True)
class RomDiscoveryResult:
    path: Path
    fmt: str
    title_id: str | None
    content_kind: str  # base | update | dlc
    size_bytes: int
    parent_title_id: str | None = None
    version: str | None = None


class RomFormatParser(Protocol):
    def supports(self, path: Path) -> bool: ...
    def parse_title_id(self, path: Path) -> str | None: ...
    def parse_content_kind(self, path: Path) -> str: ...  # base | update | dlc
    def parse_version(self, path: Path) -> str | None: ...


class RomRootDiscoveryPort(Protocol):
    def discover(self, root: Path) -> list[RomDiscoveryResult]: ...


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


class SecretStorePort(Protocol):
    """Armazenamento seguro de credenciais.

    Implementação concreta deve usar Secret Service / KWallet / keyring
    do sistema. O valor nunca aparece em logs, plans, jobs ou snapshots.
    """

    def store(self, provider: str, key_name: str, secret: Secret) -> None: ...

    def retrieve(self, provider: str, key_name: str) -> Secret | None: ...

    def delete(self, provider: str, key_name: str) -> None: ...

    def is_available(self) -> bool:
        """True se o serviço de credencial do sistema está operacional."""
        ...


# --- Compartilhamento de tela (ADR-0022) -----------------------------------
@dataclass(frozen=True)
class CastCapabilities:
    """Capacidades OBSERVADAS de um lado do enlace — nunca presumidas.

    Zero/vazio significa "não observado", não "ausente": o domínio trata isso
    como desconhecido e recusa prometer o modo. Marca, modelo e ano do receptor
    não entram aqui de propósito: não são evidência de capacidade.
    """

    full_screen: bool = False
    application_window: bool = False
    system_audio: bool = False
    input_back_channel: bool = False
    protected_content: bool = False
    requires_receiver_app: bool = False
    receiver_app_present: bool = False
    hardware_encoder: bool = False
    max_width: int = 0
    max_height: int = 0
    max_frame_rate: int = 0
    video_codecs: tuple[str, ...] = ()
    audio_codecs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReceiverDescriptor:
    """Receptor anunciado por um provedor, já normalizado.

    ``display_name`` e ``address`` são para a UI local; jamais entram em
    contrato público, log ou telemetria (SR-14 / spec §17).
    """

    receiver_id: str
    display_name: str
    protocol: str  # game-stream | steam-remote-play | screen-mirror | media-cast
    address: str
    transport: str  # wired | lan | wifi-direct | unknown
    paired: bool
    capabilities: CastCapabilities


@dataclass(frozen=True)
class LinkSample:
    """Amostra de saúde do enlace. Nunca carrega conteúdo de tela ou áudio."""

    rtt_ms: int = 0
    jitter_ms: int = 0
    packet_loss_pct: float = 0.0
    decoder_queue_frames: int = 0
    encoder_ms: float = 0.0
    dropped_frames: int = 0


@dataclass(frozen=True)
class CaptureConsent:
    """Autorização de captura concedida pelo usuário via portal do compositor.

    Sem ``granted`` não existe sessão: o produto nunca captura em silêncio.
    """

    granted: bool = False
    scope: str = "none"  # none | monitor | window | virtual
    audio: bool = False


class ScreenCastProviderPort(Protocol):
    """Contrato de uma via de compartilhamento (Miracast, motor de jogo, Cast...).

    O provedor é dono do plano de mídia; o domínio é dono da decisão. Toda
    resposta é evidência observada — um provedor que não sabe responder devolve
    capacidade vazia em vez de otimismo.
    """

    @property
    def protocol(self) -> str:
        """Id estável da via (ex.: ``game-stream``)."""
        ...

    def local_capabilities(self) -> CastCapabilities:
        """O que ESTE host consegue capturar/codificar agora."""
        ...

    def preflight(self) -> tuple[bool, str]:
        """(pronto, motivo estável quando não pronto) — ex.: ``engine-missing``."""
        ...

    def discover(self, timeout_ms: int) -> Sequence[ReceiverDescriptor]: ...

    def pair(self, receiver_id: str, pin: Secret | None) -> bool: ...

    def start(
        self,
        receiver_id: str,
        profile_id: str,
        mode: str,
        consent: CaptureConsent,
    ) -> str:
        """Inicia a sessão e devolve o id opaco dela."""
        ...

    def sample(self, session_id: str) -> LinkSample | None: ...

    def apply_stream(self, session_id: str, profile_id: str, bitrate_kbps: int) -> bool: ...

    def request_keyframe(self, session_id: str) -> bool: ...

    def stop(self, session_id: str) -> None:
        """Idempotente: parar duas vezes não é erro (spec §19)."""
        ...
