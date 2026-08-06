# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Orquestração da central Switch: lifecycle, biblioteca e conteúdo local."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar
from urllib.parse import unquote, urlsplit

from steamzero.adapters import lifecycle
from steamzero.adapters.cheats.cheat_installer import FsCheatInstaller
from steamzero.adapters.cheats.nsecm_source import NsecmSource
from steamzero.adapters.cheats.state_store_cheats import StateStoreCheatsAdapter
from steamzero.adapters.converters import (
    NszConverter,
    NszToolManager,
    SwitchRomConversionService,
    ToolRegistry,
    nsz_tool_manifest,
)
from steamzero.adapters.engine import AdapterEngine, HttpsArtifactPort, PreparedComponent
from steamzero.adapters.flatpak import FlatpakCLI, FlatpakExecutor
from steamzero.adapters.lifecycle import ComponentLifecycle
from steamzero.adapters.mods.build_id_scanner import BuildIdScanner
from steamzero.adapters.mods.composite_catalog import CompositeModCatalog
from steamzero.adapters.mods.github_mod_source import GithubModSource
from steamzero.adapters.mods.mod_installer import FilesystemModInstaller
from steamzero.adapters.mods.ns_emu_mod_downloader import NsEmuModDownloaderSource
from steamzero.adapters.mods.semd_source import SemdSource
from steamzero.adapters.mods.state_store_mods import StateStoreModsAdapter
from steamzero.adapters.preservation import PreservationService, PreservationTarget
from steamzero.adapters.registry import AdapterRegistry
from steamzero.adapters.resource_probe import parse_stat as parse_proc_stat
from steamzero.adapters.rom_metadata.emulator_cache import EmulatorCacheReader
from steamzero.adapters.scraping.registry import ProviderRegistry
from steamzero.adapters.scraping.screenscraper import ScreenScraperAdapter
from steamzero.adapters.scraping.steamgriddb import SteamGridDbAdapter
from steamzero.adapters.secret_service import SecretServiceStore
from steamzero.adapters.state_store_media import StateStoreGameMediaAdapter
from steamzero.adapters.state_store_provider_health import StateStoreProviderHealthAdapter
from steamzero.adapters.steam_shortcuts import SteamShortcutManager
from steamzero.api import contracts
from steamzero.core import fs, ids, journal, paths, safezip, transaction
from steamzero.core.errors import SteamZeroError, provider_error_category
from steamzero.core.net import NetworkFailure, fetch_bytes
from steamzero.core.secret import Secret
from steamzero.core.session_state import SESSION_OWNER
from steamzero.core.state import StateStore
from steamzero.domain.bios_catalog import BiosLibrary
from steamzero.domain.bitrot import BitrotManager, BitrotTarget
from steamzero.domain.cloud_platforms import CloudPlatformService
from steamzero.domain.emulation_workspace import (
    build_global_management,
    build_switch_workspace,
    compute_readiness,
)
from steamzero.domain.input_profiles import InputProfileManager
from steamzero.domain.launch_profile import LaunchProfile, build_argv, find_core, parse_launch
from steamzero.domain.library import PlatformDirectoryInventory, PlatformRomScanner
from steamzero.domain.media_pipeline import MediaPipeline
from steamzero.domain.platform_composer import EmulatorFacts
from steamzero.domain.platforms import PlatformRegistry
from steamzero.domain.scraping_providers import PROVIDERS, allowed_external_url, provider_by_id
from steamzero.domain.switch_cheats import (
    CheatType,
    InstalledCheat,
    SwitchCheatManager,
    validate_cheat_codes,
)
from steamzero.domain.switch_content import SwitchContentManager
from steamzero.domain.switch_library import SwitchLibraryScanner
from steamzero.domain.switch_media import GameMediaManager, GameMediaState
from steamzero.domain.switch_mods import InstalledMod, ModType, SwitchModManager
from steamzero.domain.switch_roots import (
    SwitchRootManager,
    root_id,
    sanitize_display_path,
    validate_rom_root,
)
from steamzero.domain.switch_runtime import resolve_switch_runtime_profile
from steamzero.jobs.manager import JobContext, JobManager
from steamzero.jobs.models import Job
from steamzero.ports import (
    CheatCandidate,
    CheatCatalogPort,
    GameIdentity,
    MediaCandidate,
    MediaProviderPort,
    ModCandidate,
    ModCatalogPort,
    SecretStorePort,
)

StoreFactory = Callable[[], StateStore]
RegistryFactory = Callable[[], AdapterRegistry]
_log = logging.getLogger(__name__)
Spawn = Callable[[Sequence[str]], int | None]
ProcessWaiter = Callable[[int], int]


def editorial_platform_index(
    registry: PlatformRegistry, games: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Projeta todos os manifestos para a navegação editorial, sem inferências.

    A central técnica continua centrada no workspace Switch. Esta projeção
    separada torna cada plataforma canônica navegável no tema, mesmo quando não
    há ROM publicada, e só associa jogos cujo ``platform`` já foi determinado
    pela varredura de biblioteca.
    """
    by_platform: dict[str, list[dict[str, Any]]] = {}
    for game in games:
        platform_id = game.get("platform")
        if not isinstance(platform_id, str):
            continue
        by_platform.setdefault(platform_id, []).append(dict(game))

    rows: list[dict[str, Any]] = []
    for manifest in registry.list():
        platform_games = by_platform.get(manifest.id, [])
        has_games = bool(platform_games)
        rows.append(
            {
                "id": manifest.id,
                "name": manifest.name,
                "shortName": manifest.short_name,
                "games": platform_games,
                "state": "ready" if has_games else "unverified",
                "statusLabel": ("Jogos inventariados" if has_games else "Nenhum jogo inventariado"),
                "readiness": {"percent": 100 if has_games else 0},
                "requirements": {},
                "subsystems": [],
            }
        )
    return rows


class SessionSecretStore:
    """SecretStorePort em memória (sessão atual apenas).

    Preferir implementação com Secret Service / KWallet quando disponível.
    """

    def __init__(self) -> None:
        self._secrets: dict[tuple[str, str], Secret] = {}

    def store(self, provider: str, key_name: str, secret: Secret) -> None:
        self._secrets[(provider, key_name)] = secret

    def retrieve(self, provider: str, key_name: str) -> Secret | None:
        return self._secrets.get((provider, key_name))

    def delete(self, provider: str, key_name: str) -> None:
        self._secrets.pop((provider, key_name), None)

    def is_available(self) -> bool:
        return True


#: Emuladores com lifecycle operacional COMPLETO hoje: instalação transacional
#: por AppImage, projeção de keys/firmware e launch verificado. Não é a lista do
#: que existe — o registry declara 16 adapters — é a lista do que já funciona de
#: ponta a ponta. Habilitar um id aqui sem o lifecycle correspondente produz
#: exatamente a ação que termina em stub, proibida por AGENTS.md.
#:
#: N5 e N6 movem os demais para cá conforme cada lifecycle fica real.
#: A ORDEM é a de exibição na central. Era acidental antes — vinha da ordem de
#: inserção de um dict literal — e passar a derivar do registry a teria trocado
#: por ordem alfabética, mudando a UI sem intenção. Declarada aqui, é decisão.
_MANAGED_EMULATORS: tuple[str, ...] = ("eden", "citron", "ryubing")

#: Emuladores com lifecycle completo (instalar, atualizar, reparar, abrir,
#: fechar, requisitos) exibidos na central. Cada id aqui tem fonte instalável
#: e perfil de launch declarado; os demais continuam fora das linhas até que
#: cada família fique real (LAUNCH-E2E-02 B e C).
_EMULATOR_ROWS_ORDER: tuple[str, ...] = (
    *_MANAGED_EMULATORS,
    "dolphin",
    "ppsspp",
    "melonds",
    "azahar",
    "retroarch",
    "flycast",
    "cemu",
    "rpcs3",
    "xemu",
    "xenia-canary",
)


def _emulator_presentation(
    registry: AdapterRegistry | None = None,
) -> dict[str, tuple[str, str]]:
    """Nome e ícone de cada emulador operacional, lidos do CONTRATO.

    Antes isto era um dict Python paralelo ao manifesto, o que fazia dele uma
    allowlist implícita: um adapter declarado mas ausente do dict apareceria sem
    nome e sem ícone, sem nada falhar. Agora a fonte é
    ``AdapterManifest.presentation``, versionada em ``adapter-v1.schema.json`` e
    verificada contra a allowlist de assets empacotados.
    """
    source = registry or AdapterRegistry.bundled()
    by_id = {manifest.id: manifest for manifest in source.list()}
    rows: dict[str, tuple[str, str]] = {}
    # Percorre na ordem declarada, não na do registry: a ordem é contrato de UI.
    for emulator_id in _EMULATOR_ROWS_ORDER:
        manifest = by_id.get(emulator_id)
        if manifest is None or manifest.presentation is None:
            continue
        rows[emulator_id] = (
            manifest.presentation.display_name,
            manifest.presentation.icon_asset,
        )
    return rows


def _resolve_primary_emulator(
    rows: Sequence[Mapping[str, Any]],
    configured_id: str | None,
) -> tuple[str | None, str]:
    installed = [
        str(row["id"])
        for row in rows
        if row.get("installState") == "installed" and isinstance(row.get("id"), str)
    ]
    if configured_id in installed:
        return configured_id, "configured"
    if configured_id is not None and any(row.get("id") == configured_id for row in rows):
        return configured_id, "configured-unavailable"
    if installed:
        return installed[0], "precedence"
    return None, "none"


_TITLE_ID = re.compile(r"^[0-9A-F]{16}$")
_FIRMWARE_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){0,3}$")
_KEY_LINE = re.compile(r"^\s*([a-z0-9_]+)\s*=\s*([0-9a-fA-F]{32,})\s*$")
_MASTER_KEY = re.compile(r"^master_key_([0-9a-f]{2})$")
_MAX_IMPORT_FILES = 10_000
_MAX_IMPORT_BYTES = 2 * 1024**3
#: BIOS reais cabem folgadamente abaixo de 16 MiB; o teto é um guarda-corpo.
_MAX_BIOS_BYTES = 64 * 1024**2
_MAX_MOD_BYTES = 512 * 1024**2
_BUILD_ID = re.compile(r"^[0-9A-Fa-f]{16,64}$")
_REMOTE_MOD_SUFFIXES = frozenset({".zip", ".ips", ".bps", ".pchtxt", ".txt", ".bin"})


@dataclass(frozen=True)
class _PendingMutation:
    kind: str
    metadata: Mapping[str, Any]


_MEDIA_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_MAX_MEDIA_BYTES = 32 * 1024 * 1024  # 32 MiB
_MAX_MEDIA_DIMENSION = 8192
_RETRYABLE_SCRAPE_ERRORS = frozenset(
    {
        "E-SCRAPE-PROVIDER-UNREACHABLE",
        "E-SCRAPE-RATE-LIMITED",
        "E-SCRAPE-DOWNLOAD-FAILED",
        "E-SUPPLY-OFFLINE",
        "E-SUPPLY-REMOTE-FAILED",
    }
)


def _validate_mime(path: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="arquivo de mídia inválido")
    size = path.stat().st_size
    if size > _MAX_MEDIA_BYTES:
        raise SteamZeroError(
            "E-CONTENT-LIMIT",
            detail=f"arquivo excede 32 MiB: {size} bytes",
        )
    data = path.read_bytes()[:512]
    mime = _guess_mime(data)
    if mime not in _MEDIA_MIME_TYPES:
        raise SteamZeroError(
            "E-CONTENT-UNSUPPORTED",
            detail=f"tipo MIME não suportado: {mime}",
        )


def _guess_mime(header: bytes) -> str:
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"RIFF") and b"WEBP" in header[:12]:
        return "image/webp"
    raise SteamZeroError("E-CONTENT-UNSUPPORTED", detail="tipo de arquivo não reconhecido")


def _spawn_environment() -> dict[str, str]:
    """Ambiente dos processos de emulador iniciados pelo SteamZero.

    O marcador ``STEAMZERO_CLASS=emulator`` fica no environ do processo (e é
    herdado pelos filhos); é a evidência efêmera que o probe de recursos
    (GAP-G30) usa para classificar emulador/filho sem ler command line. Filhos
    são distinguidos pela cadeia de PPID, nunca pelo marcador sozinho.
    """
    return {**os.environ, "APPIMAGELAUNCHER_DISABLE": "true", "STEAMZERO_CLASS": "emulator"}


def _spawn_detached(argv: Sequence[str]) -> int:
    process = subprocess.Popen(  # noqa: S603
        list(argv),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=_spawn_environment(),
    )
    return process.pid


def _process_alive(pid: int) -> bool:
    """O processo ainda existe? Sondagem sem efeito colateral."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _read_proc_start_ticks(pid: int) -> int | None:
    """Start-time (campo 22 de /proc/<pid>/stat) no instante do spawn.

    Compõe com o PID a identidade efêmera da sessão de jogo; ``None`` quando o
    processo já saiu ou o procfs está restrito — o probe então verifica o
    marcador do environ como segunda evidência.
    """
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    parsed = parse_proc_stat(text)
    if parsed is None:
        return None
    return parsed.get("starttime")


def _wait_pid(pid: int) -> int:
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status)


class EmulationController:
    """Fachada allowlisted usada pela bridge Desktop.

    Conteúdo protegido nunca é obtido da rede. A interface aceita somente
    caminhos escolhidos pelo usuário e todas as escritas passam por plano,
    confirmação, verificação e rollback do núcleo transacional.
    """

    def __init__(
        self,
        *,
        store_factory: StoreFactory = StateStore,
        registry_factory: RegistryFactory = AdapterRegistry.bundled,
        artifacts: HttpsArtifactPort | None = None,
        which: Callable[[str], str | None] = shutil.which,
        spawn: Spawn = _spawn_detached,
        process_waiter: ProcessWaiter | None = None,
        read_start_ticks: Callable[[int], int | None] = _read_proc_start_ticks,
        monotonic: Callable[[], float] = time.monotonic,
        shortcuts: SteamShortcutManager | None = None,
        job_manager: JobManager | None = None,
        secret_store: SecretStorePort | None = None,
        media_providers: Sequence[MediaProviderPort] | None = None,
        media_candidate_fetcher: Callable[[str], bytes] | None = None,
        media_optimizer_tool: Callable[[Path, Path, str], bool] | None = None,
        media_retry_delay: Callable[[float], None] = time.sleep,
        preservation_targets: Sequence[PreservationTarget] | None = None,
        mod_catalog: ModCatalogPort | None = None,
        cheat_catalog: CheatCatalogPort | None = None,
        input_profiles: InputProfileManager | None = None,
        cloud_platforms: CloudPlatformService | None = None,
        flatpak_factory: Callable[[], FlatpakCLI] = FlatpakCLI,
    ) -> None:
        self._store_factory = store_factory
        self._registry_factory = registry_factory
        self._artifacts = artifacts or HttpsArtifactPort()
        self._flatpak_factory = flatpak_factory
        self._which = which
        self._spawn = spawn
        self._read_start_ticks = read_start_ticks
        self._process_waiter = (
            process_waiter
            if process_waiter is not None
            else _wait_pid
            if spawn is _spawn_detached
            else None
        )
        self._monotonic = monotonic
        self._shortcuts = shortcuts or SteamShortcutManager()
        self._secret_store = secret_store or SecretServiceStore()
        self._media_providers = tuple(media_providers) if media_providers is not None else None
        self._media_candidate_fetcher = media_candidate_fetcher
        self._media_optimizer_tool = media_optimizer_tool
        self._media_retry_delay = media_retry_delay
        self._mod_catalog = mod_catalog or CompositeModCatalog(
            [
                GithubModSource(
                    cache_path=paths.data_home() / "catalog-cache" / "switch-mods.json"
                ),
                SemdSource(),
                NsEmuModDownloaderSource(),
            ]
        )
        self._cheat_catalog = cheat_catalog or NsecmSource()
        self._input_profiles = input_profiles or InputProfileManager(
            paths.config_home() / "input-profiles"
        )
        self._cloud = cloud_platforms or CloudPlatformService(
            self._shortcuts,
            which=which,
            spawn=spawn,
        )
        self._bitrot = BitrotManager(monotonic=monotonic)
        self._credential_health: dict[str, dict[str, str | None]] = {}
        self._emulator_versions: dict[str, str] = {}
        self._nsz = NszToolManager()
        self._prepared_emulators: dict[str, PreparedComponent] = {}
        self._pending: dict[str, _PendingMutation] = {}
        self._bios_library = BiosLibrary()
        self._running_pids: dict[str, int] = {}
        self._background_lock = threading.Lock()
        self._background_runners: dict[str, JobManager] = {}
        self._background_threads: dict[str, threading.Thread] = {}
        # DesktopControlServer atende cada pedido numa thread diferente. Uma
        # conexão SQLite criada aqui, na thread que sobe a UI, não pode ser
        # reutilizada pelo handler HTTP (sqlite3.ProgrammingError). O manager
        # próprio é portanto criado sob demanda por thread e liberado no fim da
        # requisição. Managers injetados continuam sob responsabilidade do
        # chamador, preservando o contrato de testes e integrações.
        self._provided_job_manager = job_manager
        self._job_context = threading.local()
        if job_manager is not None:
            self._register_job_handlers(job_manager)
        self._content = SwitchContentManager(paths.data_home() / "switch-content")
        self._preservation = PreservationService(
            self._content,
            targets=preservation_targets,
            emulator_version=lambda emulator_id: self._emulator_versions.get(
                emulator_id, "unknown"
            ),
        )

    @property
    def _jobs(self) -> JobManager:
        if self._provided_job_manager is not None:
            return self._provided_job_manager
        manager: JobManager | None = getattr(self._job_context, "manager", None)
        if manager is None:
            store = self._store_factory()
            store.migrate()
            manager = JobManager(store)
            self._register_job_handlers(manager)
            self._job_context.store = store
            self._job_context.manager = manager
        return manager

    @_jobs.setter
    def _jobs(self, manager: JobManager) -> None:
        """Mantém a injeção histórica usada por integrações e testes."""
        self.close_request_context()
        self._provided_job_manager = manager

    def _register_job_handlers(self, manager: JobManager) -> None:
        manager.register("media.search", self._media_search_job_handler)
        manager.register("media.global", self._media_global_job_handler)
        manager.register("extras.catalog.search", self._extra_catalog_search_job_handler)
        manager.register("mod.catalog.prepare", self._mod_catalog_prepare_job_handler)
        manager.register("rom.scan", self._rom_scan_job_handler)
        manager.register("library.scan", self._library_scan_job_handler)
        manager.register("library.bitrot", self._bitrot_job_handler)
        for job_type in ("content.import", "nsz.convert", "steam.publish"):
            manager.register(job_type, self._completed_operation_job_handler)

    def close_request_context(self) -> None:
        """Fecha o State Store pertencente à thread HTTP atual."""
        if self._provided_job_manager is not None:
            return
        store: StateStore | None = getattr(self._job_context, "store", None)
        if store is not None:
            store.close()
            del self._job_context.store
        if hasattr(self._job_context, "manager"):
            del self._job_context.manager

    def close(self) -> None:
        self.close_request_context()

    # -- BIOS v2 -----------------------------------------------------------
    # These endpoints are intentionally separate from ``plan_action``: scan is
    # read-only and import plans carry their own source/catalog fingerprints.
    def bios_scan(self, source: Path) -> dict[str, Any]:
        return self._bios_library.scan(source)

    def bios_scan_status(self, scan_id: str) -> dict[str, Any]:
        return self._bios_library.scan_status(scan_id)

    def bios_import_plan(self, scan_id: str, selection: list[str] | None = None) -> dict[str, Any]:
        return self._bios_library.import_plan(scan_id, selection)

    def bios_import_apply(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        return self._bios_library.import_apply(plan_id, confirm_token)

    def bios_import_rollback(self, operation_id: str) -> dict[str, Any]:
        return self._bios_library.import_rollback(operation_id)

    def bios_import_rollback_plan(self, operation_id: str) -> dict[str, Any]:
        return self._bios_library.rollback_plan(operation_id)

    def bios_import_rollback_apply(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        return self._bios_library.rollback_apply(plan_id, confirm_token)

    def bios_status(self, platform_id: str | None = None) -> dict[str, Any]:
        return self._bios_library.status(platform_id)

    def bios_audit(self) -> dict[str, Any]:
        return self._bios_library.audit()

    @property
    def _roots_path(self) -> Path:
        return paths.config_home() / "emulation-library-v1.json"

    @property
    def _library_cache_path(self) -> Path:
        return paths.data_home() / "emulation-library-cache-v1.json"

    @property
    def _game_settings_path(self) -> Path:
        return paths.config_home() / "emulation-games-v1.json"

    @property
    def _media_audit_path(self) -> Path:
        return paths.state_home() / "media-audit-v1.json"

    def snapshot(self, desktop_status: Mapping[str, Any]) -> dict[str, Any]:
        emulator_rows = self._emulator_rows()
        self._emulator_versions = {
            str(row["id"]): str(row.get("version") or row.get("installedVersion") or "unknown")
            for row in emulator_rows
        }
        games, unidentified = self._load_library_cache()
        roots = self.library_roots()
        key_status, firmware_status = self._requirements(emulator_rows)
        games = self._enrich_games(games, emulator_rows, key_status, firmware_status)
        games = self._enrich_preservation(games)
        games = self._enrich_controls(games)
        content = self._content.list_records()
        integrity = self._content.integrity_report()
        physical_dock = self._physical_dock(desktop_status)
        controllers = self._controller_count()
        input_profile_status = self._input_profiles.status("switch")

        workspace = build_switch_workspace(
            probe=lambda emulator_id: next(
                (
                    row["installState"] == "installed"
                    for row in emulator_rows
                    if row["id"] == emulator_id
                ),
                None,
            ),
            keys=key_status,
            firmware=firmware_status,
            games=games,
            emulator_facts=self._platform_facts_provider(self._registry_factory()),
            core_present=self._core_present,
            bios_present=self._bios_present_for,
        )
        composed_cloud = {row["id"]: row for row in self._cloud.platforms()}
        workspace["platforms"] = [
            composed_cloud.get(str(row["id"]), row) for row in workspace["platforms"]
        ]
        # O workspace técnico preserva a superfície Switch. A biblioteca
        # editorial recebe em paralelo o índice completo de manifests e nunca
        # precisa criar plataformas a partir dos nomes de diretórios locais.
        workspace["editorialPlatforms"] = editorial_platform_index(
            PlatformRegistry.bundled(), games
        )
        global_settings = self._load_global_settings()
        platform = workspace["platforms"][0]
        platform["emulators"] = emulator_rows
        # G27: o probe do catálogo só sabe "instalado ou não"; a prontidão
        # global precisa das linhas observadas do host, senão um emulador
        # degradado produz 100% mesmo com drift.
        truth_state, truth_label, readiness = compute_readiness(
            {"keys": key_status, "firmware": firmware_status}, emulator_rows
        )
        platform["state"] = truth_state
        platform["statusLabel"] = truth_label
        platform["readiness"] = readiness
        configured_default = global_settings.get("defaultEmulatorId")
        primary_id, primary_source = _resolve_primary_emulator(
            emulator_rows,
            str(configured_default) if configured_default is not None else None,
        )
        primary_row = next(
            (row for row in emulator_rows if row["id"] == primary_id),
            None,
        )
        platform["configuredDefaultEmulatorId"] = configured_default
        platform["defaultEmulatorId"] = configured_default or primary_id
        platform["primaryEmulator"] = {
            "id": primary_id,
            "name": str(primary_row["name"]) if primary_row is not None else "",
            "state": str(primary_row["state"]) if primary_row is not None else "unavailable",
            "statusLabel": (
                str(primary_row["statusLabel"])
                if primary_row is not None
                else "Nenhum emulador instalado"
            ),
            "source": primary_source,
        }
        for emulator in emulator_rows:
            install_state = emulator["installState"]
            degraded = install_state == "degraded"
            installed = install_state in {"installed", "degraded"}
            is_default = emulator["id"] == primary_id
            emulator["isDefault"] = is_default
            health = emulator["health"]
            health["firmwareReady"] = firmware_status["status"] == "ok"
            if degraded:
                # O motivo do drift vem da linha (status real); recomputar aqui
                # derrubaria em "Pendente: instalação" — mentira sobre o host.
                health["state"] = "degraded"
            else:
                ready = bool(
                    installed
                    and health["versionCurrent"]
                    and health["keysReady"]
                    and health["firmwareReady"]
                )
                health["state"] = "ready" if ready else "degraded" if installed else "unavailable"
                missing: list[str] = []
                if not installed:
                    missing.append("instalação")
                if installed and not health["versionCurrent"]:
                    missing.append("atualização")
                if installed and not health["keysReady"]:
                    missing.append("keys")
                if not health["firmwareReady"]:
                    missing.append("firmware")
                health["reason"] = (
                    "Emulador, versão, keys e firmware verificados."
                    if ready
                    else f"Pendente: {', '.join(missing)}."
                )
            if installed and not is_default:
                emulator["actions"].insert(
                    1 if degraded else 0,
                    self._action(
                        "game.emulator.default",
                        "Definir como padrão",
                        confirmation=True,
                    )
                    | {"emulatorId": emulator["id"]},
                )
                emulator["action"] = emulator["actions"][0]
        # These preferences are published with the workspace so QML never has to
        # invent an optimistic value for a durable setting.
        platform["globalSettings"] = global_settings
        platform["runtimeProfiles"] = self._runtime_profiles(
            desktop_status, physical_dock, controllers
        )
        platform["areaData"] = self._area_data(
            emulator_rows,
            games,
            unidentified,
            roots,
            content,
            integrity,
            physical_dock,
            controllers,
            key_status,
            firmware_status,
            input_profile_status,
        )
        for area in platform["areas"]:
            area_id = area["id"]
            area["state"] = (
                "ready" if area_id in {"overview", "controls", "storage"} else "attention"
            )
            area["statusLabel"] = {
                "overview": "Estado verificado",
                "keysFirmware": "Importação local",
                "updatesDlc": "Gestão por jogo",
                "modsCheats": "Conteúdo por jogo",
                "graphicsPerformance": "Perfil observado",
                "controls": f"{controllers} controle(s)",
                "saves": "Backup local",
                "shaderCache": "Cache por jogo",
                "media": f"{len(roots)} diretório(s)",
                "storage": str(integrity["state"]),
                "advanced": "Ferramentas locais",
            }[area_id]
        media_area = platform["areaData"]["media"]
        media_area["providerCredentials"] = self.credential_status()["providers"]
        workspace["globalManagement"] = build_global_management(
            platforms=workspace["platforms"],
            editorial_platforms=workspace["editorialPlatforms"],
            canonical_experiences=workspace["canonicalExperiences"],
            truth_state=truth_state,
            emulators=emulator_rows,
            directories=media_area.get("libraryRoots", []),
            media_providers=media_area["providerCredentials"],
        )
        workspace["jobs"] = self.list_jobs()
        contracts.validate(workspace, "emulation-workspace-v1.schema.json")
        return workspace

    def _platform_facts_provider(self, registry: AdapterRegistry) -> Callable[[str], EmulatorFacts]:
        """Fatos reais de cada adapter, para o composer de plataforma.

        A rota de lifecycle diz se é instalável e por quê; o manifesto diz nome e
        ícone. Status de instalação só é consultado para quem tem executor — para
        os demais o motivo já é a resposta, e sondar o host seria trabalho inútil.
        """
        by_id = {manifest.id: manifest for manifest in registry.list()}
        cache: dict[str, EmulatorFacts] = {}

        def provide(adapter_id: str) -> EmulatorFacts:
            if adapter_id in cache:
                return cache[adapter_id]
            manifest = by_id.get(adapter_id)
            if manifest is None:
                facts = EmulatorFacts(
                    adapter_id=adapter_id,
                    reason="componente não declarado no registry de adapters",
                )
            else:
                route = lifecycle.route_for(manifest)
                presentation = manifest.presentation
                facts = EmulatorFacts(
                    adapter_id=adapter_id,
                    display_name=presentation.display_name if presentation else None,
                    icon_asset=presentation.icon_asset if presentation else None,
                    installable=route.installable,
                    installed=self._adapter_installed(adapter_id, route),
                    reason=route.reason,
                )
            cache[adapter_id] = facts
            return facts

        return provide

    def _adapter_installed(self, adapter_id: str, route: lifecycle.LifecycleRoute) -> bool:
        """Instalação real, consultada pelo executor da família da fonte.

        Falha de sondagem devolve False em vez de propagar: um componente que não
        respondeu não é um componente instalado, e derrubar a central inteira por
        causa de um adapter seria degradação pior que a informação faltante.
        """
        if not route.installable:
            return False
        try:
            with self._store_factory() as store:
                store.migrate()
                registry = self._registry_factory()
                if route.executor == "flatpak":
                    executor = FlatpakExecutor(store, registry, self._flatpak_factory())
                    return str(executor.status(adapter_id).get("state")) == "installed"
                engine = AdapterEngine(store, registry, self._artifacts)
                return str(engine.status(adapter_id).get("state")) == "installed"
        except Exception:
            _log.warning("status do adapter %s não pôde ser consultado", adapter_id)
            return False

    @staticmethod
    def _core_present(core: str) -> bool:
        """Se o core libretro existe no host. Ausência não é erro: é motivo."""
        try:
            return find_core(core) is not None
        except SteamZeroError:
            return False

    @staticmethod
    def _bios_present_for(platform_id: str, adapter_id: str, name: str) -> bool:
        """Se a BIOS exigida existe no store central, por nome (nunca conteúdo).

        A ausência por falha de leitura trata-se como ausente: a leitura que
        falhou não prova presença, e sondar não pode derrubar a central
        (AGENTS.md §8).
        """
        try:
            target = fs.resolve_within(paths.bios_dir(), paths.bios_dir() / platform_id / name)
        except SteamZeroError:
            return False
        try:
            return target.is_file()
        except OSError:
            return False

    def _plan_flatpak_emulator(
        self, store: StateStore, registry: AdapterRegistry, emulator_id: str, action: str
    ) -> dict[str, Any]:
        """Planeja via FlatpakExecutor, preservando o formato de plano da UI."""
        if action not in {"install", "update"}:
            # Desinstalação Flatpak existe no executor, mas ainda não tem
            # verificação de propriedade equivalente à do caminho portátil.
            # Recusar declarado é melhor que oferecer meia operação.
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail=f"ação '{action}' ainda não disponível para componentes Flatpak",
            )
        executor = FlatpakExecutor(store, registry, self._flatpak_factory())
        plan = executor.plan_install(emulator_id)
        payload = plan.to_dict()
        payload["action"] = f"emulator.{action}"
        return payload

    def plan_emulator(self, emulator_id: str, action: str) -> dict[str, Any]:
        self._require_known_emulator(emulator_id)
        with self._store_factory() as store:
            store.migrate()
            registry = self._registry_factory()
            # A família da fonte decide o executor. Antes o caminho de emulador
            # ia direto para o engine portátil, e uma fonte Flatpak morria em
            # "executor ainda não está habilitado" — apesar de FlatpakExecutor
            # existir, testado, e já ser usado pela superfície de componentes.
            route = lifecycle.route_for(registry.get(emulator_id))
            if not route.installable:
                raise SteamZeroError(
                    "E-COMPONENT-DEGRADED",
                    detail=route.reason or "componente sem executor de lifecycle",
                )
            if route.executor == "flatpak":
                return self._plan_flatpak_emulator(store, registry, emulator_id, action)
            engine = AdapterEngine(store, registry, self._artifacts)
            if action in {"install", "update"}:
                prepared = engine.plan_install(emulator_id)
            elif action == "uninstall":
                prepared = engine.plan_uninstall(emulator_id)
            else:
                raise SteamZeroError("E-API-SCHEMA", detail="ação de emulador não permitida")
        self._prepared_emulators[prepared.plan.plan_id] = prepared
        return self._plan_view(prepared.plan, f"emulator.{action}")

    def apply_emulator(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        prepared = self._prepared_emulators.get(plan_id)
        if prepared is None:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano de emulador expirado")
        with self._store_factory() as store:
            store.migrate()
            engine = AdapterEngine(store, self._registry_factory(), self._artifacts)

            def smoke() -> None:
                command = [str(engine.payload_path(prepared.manifest.id))]
                command.extend(prepared.manifest.verify_smoke_test)
                try:
                    result = subprocess.run(  # noqa: S603
                        command,
                        check=False,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        env={**os.environ, "APPIMAGELAUNCHER_DISABLE": "1"},
                        timeout=20,
                    )
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise SteamZeroError(
                        "E-COMPONENT-DEGRADED", detail=f"smoke test falhou: {exc}"
                    ) from exc
                if result.returncode != 0:
                    raise SteamZeroError(
                        "E-COMPONENT-DEGRADED",
                        detail=f"smoke test retornou código {result.returncode}",
                    )

            result = engine.apply(
                prepared,
                confirm_token,
                smoke=None if prepared.plan.kind == "component.uninstall" else smoke,
            )
        self._prepared_emulators.pop(plan_id, None)
        return {"status": result.status, "operationId": result.operation_id}

    def _require_launchable_emulator(self, emulator_id: str) -> None:
        # Emuladores Switch legados têm launch completo e são sempre aceitos.
        if emulator_id in _MANAGED_EMULATORS:
            return
        # Demais emuladores só são lançáveis se forem realmente instaláveis e
        # instalados — nunca oferecer um Flap para um componente que não existe.
        registry = self._registry_factory()
        manifest = registry.get(emulator_id)
        route = lifecycle.route_for(manifest)
        if not route.installable or not self._adapter_installed(emulator_id, route):
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=f"{emulator_id} não está instalado ou não tem fonte lançável",
            )

    def _primary_platform_for(self, emulator_id: str) -> str:
        registry = PlatformRegistry.bundled()
        for platform in registry.list():
            for emulator in platform.emulators:
                if emulator["adapterId"] == emulator_id and emulator.get("role") == "primary":
                    return platform.id
        return "multi"

    def _launch_profile_for(self, platform_id: str, adapter_id: str) -> LaunchProfile | None:
        registry = PlatformRegistry.bundled()
        try:
            platform = registry.get(platform_id)
        except KeyError:
            return None
        for emulator in platform.emulators:
            if emulator["adapterId"] == adapter_id:
                return parse_launch(platform_id, adapter_id, emulator.get("launch"))
        return None

    def _emulator_source(self, emulator_id: str) -> tuple[str, str | None, Path | None]:
        """Fonte escolhida: (source_type, flatpak_ref, payload_path).

        Para fontes portáteis (appimage/native) o payload é o caminho do
        binário; para Flatpak o ref pinado. Retorna sempre a fonte declarada,
        mesmo EOL — um emulador já instalado continua lançável.
        """
        registry = self._registry_factory()
        manifest = registry.get(emulator_id)
        source = manifest.preferred_source(None, allow_eol=True)
        source_type = str(source.type)
        if source_type == "flatpak":
            return source_type, str(source.ref), None
        with self._store_factory() as store:
            store.migrate()
            engine = AdapterEngine(store, registry, self._artifacts)
            return source_type, None, engine.payload_path(emulator_id)

    def _build_exec_argv(
        self,
        profile: LaunchProfile,
        *,
        source_type: str,
        flatpak_ref: str | None,
        payload: Path | None,
        rom: Path | None = None,
        core_path: Path | None = None,
    ) -> list[str]:
        """Monta o argv do executor derivado da fonte fixada.

        ``build_argv`` resolve placeholders allowlisted positionally; a ROM é
        sempre um argumento atômico. Flatpak → ``flatpak run --user <ref> args``;
        portátil → wrapper AppImage + payload + args. Nunca é shell.
        """
        applied = list(build_argv(profile, "EXEC", rom=rom, core_path=core_path))
        args = applied[1:]
        if source_type == "flatpak":
            if not flatpak_ref:
                raise SteamZeroError(
                    "E-API-SCHEMA", detail=f"perfil Flatpak sem ref: {profile.adapter_id}"
                )
            return ["flatpak", "run", "--user", flatpak_ref, *args]
        if payload is None:
            raise SteamZeroError(
                "E-API-SCHEMA", detail=f"fonte portátil sem payload: {profile.adapter_id}"
            )
        return list(self._appimage_argv(payload, *args))

    def launch_emulator(self, emulator_id: str) -> dict[str, Any]:
        self._require_launchable_emulator(emulator_id)
        platform = self._primary_platform_for(emulator_id)
        source_type, flatpak_ref, payload = self._emulator_source(emulator_id)
        profile: LaunchProfile | None
        if platform == "multi":
            # Emulador multi-plataforma (RetroArch): "Abrir" é o executor base,
            # sem perfil de plataforma — cada jogo decide o core.
            profile = LaunchProfile(platform_id="multi", adapter_id=emulator_id, game_args=())
        else:
            profile = self._launch_profile_for(platform, emulator_id)
            if profile is None:
                raise SteamZeroError(
                    "E-API-SCHEMA", detail=f"{emulator_id} não declara perfil de launch"
                )
        argv = self._build_exec_argv(
            profile,
            source_type=source_type,
            flatpak_ref=flatpak_ref,
            payload=payload,
        )
        if payload is not None and self._managed_process_groups(payload):
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail=f"{emulator_id} já está em execução"
            )
        pid = self._spawn(argv)
        if isinstance(pid, int) and pid > 1:
            self._running_pids[emulator_id] = pid
        return {"status": "started", "emulatorId": emulator_id, "pid": pid}

    def stop_emulator(self, emulator_id: str) -> dict[str, Any]:
        self._require_known_emulator(emulator_id)
        source_type, _flatpak_ref, _payload = self._emulator_source(emulator_id)
        groups: set[int] = set()
        if source_type == "flatpak":
            # O spawn usa start_new_session, então o pid registrado é o líder
            # do grupo; derrubar o grupo derruba o wrapper e o aplicativo.
            pid = self._running_pids.get(emulator_id)
            if pid is not None and _process_alive(pid):
                try:
                    os.killpg(pid, signal.SIGTERM)
                except OSError:
                    pass
                else:
                    groups.add(pid)
        else:
            with self._store_factory() as store:
                store.migrate()
                engine = AdapterEngine(store, self._registry_factory(), self._artifacts)
                groups = self._managed_process_groups(engine.payload_path(emulator_id))
            for process_group in groups:
                os.killpg(process_group, signal.SIGTERM)
        self._running_pids.pop(emulator_id, None)
        return {
            "status": "stopping" if groups else "not-running",
            "emulatorId": emulator_id,
            "processGroups": len(groups),
        }

    def launch_game(self, game_id: str) -> dict[str, Any]:
        game = self._current_game(game_id)
        settings = self._load_game_settings(strict=True)
        game_settings = self._settings_for_game_with_global(game, settings)
        emulator_id = game_settings.get("emulatorId")
        if not isinstance(emulator_id, str):
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail="defina o emulador padrão deste jogo"
            )
        self._require_launchable_emulator(emulator_id)
        platform_id = str(game.get("platformId") or "switch")
        rom = Path(str(game["path"]))

        # Switch: classificação base/update/dlc e keys são restritos ao Switch.
        # Jogo não-Switch nunca exige prod.keys e nunca passa pelo scanner
        # Switch (a ROM já foi validada/classificada no scan da biblioteca).
        if platform_id == "switch":
            classification = SwitchLibraryScanner.classify(
                rom,
                root=self._root_for_game(rom.resolve(strict=True)),
                fmt=str(game.get("format", rom.suffix.lstrip(".").casefold())),
                title_id=str(game["titleId"]) if game.get("titleId") else None,
            )
            if classification[0] != "base" or game.get("contentKind", "base") != "base":
                raise SteamZeroError(
                    "E-CONTENT-FW-INCOMPAT",
                    detail="updates e DLCs não podem ser iniciados; selecione a ROM base",
                )
            self._require_key_projection(emulator_id)

        profile = self._launch_profile_for(platform_id, emulator_id)
        if profile is None:
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail=(
                    f"plataforma {platform_id} não declara um perfil de launch para {emulator_id}"
                ),
            )
        source_type, flatpak_ref, payload = self._emulator_source(emulator_id)
        if payload is not None and self._managed_process_groups(payload):
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail=f"{emulator_id} já está em execução"
            )
        core_path: Path | None = None
        if profile.requires_core:
            # Core ausente → nunca "Jogar": o usuário precisa instalar/verificar
            # o core primeiro; não se oferece um botão que falha depois.
            core_path = find_core(profile.core or "")
            if core_path is None:
                raise SteamZeroError(
                    "E-CONTENT-UNSUPPORTED",
                    detail=f"o core {profile.core} não está instalado no RetroArch; "
                    "instale/verifique o core antes de jogar",
                )
        argv = self._build_exec_argv(
            profile,
            source_type=source_type,
            flatpak_ref=flatpak_ref,
            payload=payload,
            rom=rom,
            core_path=core_path,
        )

        session_id: str | None = None
        started_monotonic = self._monotonic()
        if self._process_waiter is not None:
            session_id = self._create_tracked_game_session(game, emulator_id, platform_id)
        try:
            pid = self._spawn(argv)
        except Exception:
            if session_id is not None:
                self._finish_tracked_game_session(
                    session_id,
                    target="failed",
                    started_monotonic=started_monotonic,
                    failure_code="E-SESSION-LAUNCH-FAILED",
                )
            raise
        if isinstance(pid, int) and pid > 1:
            self._running_pids[emulator_id] = pid
            if session_id is not None:
                with self._store_factory() as store:
                    store.migrate()
                    store.transition_game_session(
                        session_id,
                        "running",
                        pid=pid,
                        start_ticks=self._read_start_ticks(pid),
                    )
                watcher = threading.Thread(
                    target=self._watch_tracked_game,
                    args=(
                        session_id,
                        emulator_id,
                        pid,
                        started_monotonic,
                        str(game["id"]),
                        str(game["titleId"]) if isinstance(game.get("titleId"), str) else None,
                    ),
                    name=f"steamzero-game-{session_id[-8:]}",
                    daemon=True,
                )
                watcher.start()
        elif session_id is not None:
            self._finish_tracked_game_session(
                session_id,
                target="failed",
                started_monotonic=started_monotonic,
                failure_code="E-SESSION-LAUNCH-FAILED",
            )
            raise SteamZeroError(
                "E-SESSION-LAUNCH-FAILED",
                detail="o launcher não publicou um PID observável",
            )
        return {
            "status": "started",
            "gameId": game_id,
            "platformId": platform_id,
            "emulatorId": emulator_id,
            "name": str(game["name"]),
            "pid": pid,
            "sessionId": session_id,
            "argv": argv,
        }

    def cloud_platforms(self) -> list[dict[str, Any]]:
        return self._cloud.platforms()

    def launch_cloud(self, platform_id: str) -> dict[str, Any]:
        return self._cloud.launch(platform_id)

    def _create_tracked_game_session(
        self, game: Mapping[str, Any], emulator_id: str, platform_id: str
    ) -> str:
        session_id = ids.new_ulid()
        metadata = json.dumps(
            {
                "source": "emulation",
                "title": str(game.get("name") or "")[:160],
                "platformId": platform_id,
                "coverUrl": str(game.get("coverUrl") or game.get("bannerAsset") or "")[:4096],
                "emulatorId": emulator_id,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        try:
            with self._store_factory() as store:
                store.migrate()
                store.create_game_session(
                    {
                        "id": session_id,
                        "game_id": str(game["id"]),
                        "state": "launching",
                        "owner": SESSION_OWNER,
                        "metadata_json": metadata,
                    }
                )
        except sqlite3.IntegrityError as exc:
            raise SteamZeroError(
                "E-TX-LOCKED",
                detail="outra sessão de jogo gerenciada ainda está ativa",
            ) from exc
        return session_id

    def _watch_tracked_game(
        self,
        session_id: str,
        emulator_id: str,
        pid: int,
        started_monotonic: float,
        game_id: str,
        title_id: str | None,
    ) -> None:
        waiter = self._process_waiter
        if waiter is None:
            return
        try:
            exit_code = waiter(pid)
        except Exception:
            self._finish_tracked_game_session(
                session_id,
                target="failed",
                started_monotonic=started_monotonic,
                failure_code="E-SESSION-INTERRUPTED",
            )
        else:
            with suppress(Exception), self._store_factory() as store:
                store.migrate()
                store.transition_game_session(session_id, "closing")
            self._finish_tracked_game_session(
                session_id,
                target="closed",
                started_monotonic=started_monotonic,
                exit_code=exit_code,
            )
        finally:
            self._running_pids.pop(emulator_id, None)
            if title_id is not None:
                self._session_save_checkpoint(game_id, title_id, emulator_id)

    def _finish_tracked_game_session(
        self,
        session_id: str,
        *,
        target: str,
        started_monotonic: float,
        exit_code: int | None = None,
        failure_code: str | None = None,
    ) -> None:
        with suppress(Exception), self._store_factory() as store:
            store.migrate()
            store.transition_game_session(
                session_id,
                target,
                pid=None,
                finished_at=datetime.now(UTC).isoformat(),
                exit_code=exit_code,
                failure_code=failure_code,
                played_seconds=max(0, int(self._monotonic() - started_monotonic)),
                duration_source="observed-monotonic",
            )

    _SPECIAL_ROOT_NAMES = frozenset(
        {
            "firmware",
            "keys",
            "bios",
            "saves",
            "cache",
            "media",
            "screenshots",
            "mods",
            "cheats",
            "dlc",
            "updates",
            "patches",
            "shader",
            "nand",
            "system",
        }
    )

    def library_roots(self) -> list[str]:
        configured, excluded = self._root_config()
        candidates = [
            paths.roms_dir(),
            Path.home() / "Emulation" / "roms",
            Path.home() / "emulation" / "roms",
            Path.home() / "Games" / "ROMs",
            Path.home() / "Games" / "roms",
            Path.home() / "ROMs",
            Path.home() / "roms",
        ]
        candidates.extend(configured)
        result: list[str] = []
        seen: set[Path] = set()
        for candidate in candidates:
            try:
                resolved = candidate.resolve(strict=True)
            except OSError:
                continue
            if (
                resolved in seen
                or resolved in excluded
                or candidate.is_symlink()
                or any(parent.is_symlink() for parent in candidate.absolute().parents)
                or not resolved.is_dir()
            ):
                continue
            if resolved.name.casefold() in self._SPECIAL_ROOT_NAMES:
                continue
            parent = resolved.parent
            if (
                parent.name.casefold() == "roms"
                and resolved.name.casefold() in self._SPECIAL_ROOT_NAMES
            ):
                continue
            seen.add(resolved)
            result.append(str(resolved))
        # Compact parent/child: keep only topmost ancestors
        compacted: list[str] = []
        for r in sorted(result, key=len):
            if not any(Path(c) != Path(r) and Path(r).is_relative_to(Path(c)) for c in result):
                compacted.append(r)
        return compacted

    def registered_library_roots(self) -> list[Path]:
        """Raízes ativas, incluindo as customizadas temporariamente inacessíveis."""
        configured, excluded = self._root_config()
        automatic = [
            paths.roms_dir(),
            Path.home() / "Emulation" / "roms",
            Path.home() / "emulation" / "roms",
            Path.home() / "Games" / "ROMs",
            Path.home() / "Games" / "roms",
            Path.home() / "ROMs",
            Path.home() / "roms",
        ]
        candidates = [
            *(candidate for candidate in automatic if candidate.exists()),
            *configured,
        ]
        result: list[Path] = []
        seen: set[Path] = set()
        for candidate in candidates:
            absolute = candidate.absolute()
            comparable = candidate.resolve(strict=False)
            if comparable in excluded or absolute in seen:
                continue
            seen.add(absolute)
            result.append(absolute)
        return result

    def scan_library(self) -> dict[str, Any]:
        job = self._jobs.create(
            "library.scan",
            params={"roots": self.library_roots()},
            priority="interactive",
            created_by="ui",
        )
        completed = self._jobs.run(job.id)
        result = dict(completed.result) if isinstance(completed.result, Mapping) else {}
        result.update({"jobId": completed.id, "job": self._job_view(completed)})
        return result

    def library_health(self) -> dict[str, Any]:
        active = [
            self._job_view(job)
            for job in self._jobs.list_jobs(
                states=["created", "queued", "blocked", "running", "paused", "cancelling"]
            )
            if job.type == "library.bitrot"
        ]
        return self._bitrot.status(self._bitrot_targets(), active_jobs=active)

    def plan_library_health(self) -> dict[str, Any]:
        return self.plan_action({"actionId": "library.health.scan"})

    def _scan_library_now(self, ctx: JobContext | None = None) -> dict[str, Any]:
        scanner = SwitchLibraryScanner()
        registry = PlatformRegistry.bundled()
        manifest_dicts = [{"id": m.id, "media": dict(m.media)} for m in registry.list()]
        platform_scanner = PlatformRomScanner.from_manifests(manifest_dicts)
        directory_inventory = PlatformDirectoryInventory.from_registry(registry)
        emulator_cache = EmulatorCacheReader(paths.data_home())
        discovered: dict[str, dict[str, Any]] = {}
        auxiliary: list[Any] = []
        unidentified = 0
        errors: list[str] = []
        roots = self.library_roots()
        scanned_at = datetime.now(UTC).isoformat()
        root_stats: dict[str, dict[str, Any]] = {}
        directory_report: list[dict[str, Any]] = []
        if ctx is not None:
            ctx.set_progress("scan", current=0, total=len(roots), unit="roots")
        for root_index, raw_root in enumerate(roots):
            root = Path(raw_root)
            counts = {"base": 0, "updates": 0, "dlcs": 0, "incompatible": 0, "errors": 0}
            if ctx is not None:
                ctx.safepoint()
                ctx.set_progress(
                    "scan",
                    current=root_index,
                    total=len(roots),
                    unit="roots",
                    current_item=root.name,
                )
            try:
                matches = scanner.inventory(root)
            except (OSError, SteamZeroError) as exc:
                errors.append(f"{root}: {exc}")
                counts["errors"] += 1
                root_stats[root_id(root)] = {"counts": counts, "lastScan": scanned_at}
                continue
            switch_base_count = sum(1 for m in matches if m.content_kind == "base")
            if switch_base_count == 0:
                plat_matches = platform_scanner.inventory(root)
                if not any(match.content_kind == "base" for match in plat_matches):
                    directory_rows = directory_inventory.inventory(root)
                    directory_report.extend(
                        {
                            "root": str(row.path),
                            "disposition": row.disposition,
                            "platformId": row.platform_id,
                            "gameCount": row.game_count,
                            "selectedCount": len(row.selected_games),
                            "skippedSymlinks": row.skipped_symlinks,
                        }
                        for row in directory_rows
                    )
                    plat_matches = [
                        game
                        for row in directory_rows
                        if row.disposition == "matched"
                        for game in row.selected_games
                    ]
                for pm in plat_matches:
                    if pm.content_kind != "base":
                        continue
                    counts["base"] += 1
                    try:
                        stat = pm.path.stat()
                    except OSError as exc:
                        errors.append(f"{pm.path}: {exc}")
                        counts["errors"] += 1
                        continue
                    fingerprint = hashlib.sha256(
                        f"{pm.path}\0{stat.st_size}\0{stat.st_mtime_ns}".encode()
                    ).hexdigest()
                    stable_id = hashlib.sha256(str(pm.path).encode()).hexdigest()[:24]
                    discovered[str(pm.path)] = {
                        "id": stable_id,
                        "titleId": None,
                        "name": pm.path.stem,
                        "state": "unverified",
                        "statusLabel": (
                            f"{pm.format.upper()} · Platform: {pm.platform}"
                            if pm.platform
                            else pm.format.upper()
                        ),
                        "emulatorId": None,
                        "path": str(pm.path),
                        "fingerprint": fingerprint,
                        "size": stat.st_size,
                        "format": pm.format,
                        "identityVerified": False,
                        "contentKind": "base",
                        "metadataSource": None,
                        "version": None,
                        "updateCount": 0,
                        "updateVersion": None,
                        "dlcCount": 0,
                        "bannerAsset": None,
                        "coverUrl": None,
                        "mediaSource": None,
                        "platform": pm.platform,
                        "evidence": pm.evidence,
                    }
                root_stats[root_id(root)] = {"counts": counts, "lastScan": scanned_at}
                continue
            for match in matches:
                if match.content_kind == "base":
                    counts["base"] += 1
                elif match.content_kind == "update":
                    counts["updates"] += 1
                elif match.content_kind == "dlc":
                    counts["dlcs"] += 1
                if match.content_kind != "base":
                    auxiliary.append(match)
                    continue
                try:
                    stat = match.path.stat()
                except OSError as exc:
                    errors.append(f"{match.path}: {exc}")
                    counts["errors"] += 1
                    continue
                fingerprint = hashlib.sha256(
                    f"{match.path}\0{stat.st_size}\0{stat.st_mtime_ns}".encode()
                ).hexdigest()
                identity_verified = match.title_id is not None
                if not identity_verified:
                    unidentified += 1
                stable_id = hashlib.sha256(str(match.path).encode()).hexdigest()[:24]
                banner_asset, media_source = self._cover_asset(match.title_id)
                cached_title = (
                    emulator_cache.find_title(match.title_id)
                    if match.title_id is not None
                    else None
                )
                discovered[str(match.path)] = {
                    "id": stable_id,
                    "titleId": match.title_id,
                    "name": cached_title or scanner.clean_display_name(match.path),
                    "state": "ready" if identity_verified else "unverified",
                    "statusLabel": (
                        match.format.upper()
                        if identity_verified
                        else f"{match.format.upper()} · Title ID não identificado"
                    ),
                    "emulatorId": None,
                    "path": str(match.path),
                    "fingerprint": fingerprint,
                    "size": stat.st_size,
                    "format": match.format,
                    "identityVerified": identity_verified,
                    "contentKind": "base",
                    "metadataSource": "emulator-cache" if cached_title else match.metadata_source,
                    "version": f"v{match.version}" if match.version is not None else None,
                    "updateCount": 0,
                    "updateVersion": None,
                    "dlcCount": 0,
                    "bannerAsset": banner_asset,
                    "coverUrl": banner_asset,
                    "mediaSource": media_source,
                }
            try:
                for candidate in root.rglob("*"):
                    if candidate.is_symlink():
                        counts["errors"] += 1
                    elif candidate.is_file() and candidate.suffix.casefold() in {
                        ".7z",
                        ".rar",
                        ".zip",
                    }:
                        counts["incompatible"] += 1
            except OSError:
                counts["errors"] += 1
            root_stats[root_id(root)] = {"counts": counts, "lastScan": scanned_at}
            if ctx is not None:
                ctx.set_progress(
                    "scan",
                    current=root_index + 1,
                    total=len(roots),
                    unit="roots",
                    current_item=root.name,
                )
        by_title_id = {
            str(game["titleId"]): game
            for game in discovered.values()
            if isinstance(game.get("titleId"), str)
        }
        by_name: dict[str, list[dict[str, Any]]] = {}
        for game in discovered.values():
            key = scanner.association_key(Path(str(game["path"])))
            if key:
                by_name.setdefault(key, []).append(game)
        associated_content: set[tuple[str, str]] = set()
        for item in auxiliary:
            parent = by_title_id.get(str(item.parent_title_id))
            if parent is None:
                name_matches = by_name.get(scanner.association_key(item.path), [])
                if len(name_matches) == 1:
                    parent = name_matches[0]
            if parent is None:
                continue
            identity = item.title_id or str(item.path)
            content_key = (item.content_kind, identity)
            if content_key in associated_content:
                continue
            associated_content.add(content_key)
            if item.content_kind == "update":
                parent["updateCount"] = int(parent["updateCount"]) + 1
                if item.version is not None:
                    current = parent.get("updateVersionNumber")
                    if not isinstance(current, int) or item.version > current:
                        parent["updateVersionNumber"] = item.version
                        parent["updateVersion"] = f"v{item.version}"
            elif item.content_kind == "dlc":
                parent["dlcCount"] = int(parent["dlcCount"]) + 1
        for game in discovered.values():
            game.pop("updateVersionNumber", None)
        game_rows = sorted(discovered.values(), key=lambda game: str(game["name"]).casefold())
        payload = {
            "schemaVersion": 1,
            "games": game_rows,
            "unidentified": unidentified,
            "errors": errors[:20],
            "ignoredAuxiliary": len(auxiliary),
            "rootStats": root_stats,
            "directoryInventory": directory_report,
            "scannedAt": scanned_at,
        }
        fs.write_atomic_text(
            self._library_cache_path,
            json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
        )
        if ctx is not None:
            ctx.set_progress("done", current=len(roots), total=len(roots), unit="roots")
        return {
            "status": "scanned",
            "games": len(game_rows),
            "unidentified": unidentified,
            "errors": errors[:20],
            "ignoredAuxiliary": len(auxiliary),
        }

    def plan_action(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        action = self._required_string(payload, "actionId")
        plan_extra: dict[str, Any] = {}
        if action == "library.health.scan":
            games, _unidentified = self._load_library_cache()
            if not games:
                raise SteamZeroError(
                    "E-CONTENT-INCOMPLETE",
                    detail="faça uma varredura da biblioteca antes do anti-bitrot",
                )
            plan = transaction.plan_write_files(
                {},
                root=paths.state_home(),
                kind="bitrot.scan",
                requirements_extra={
                    "maxFiles": 8,
                    "maxBytes": 2 * 1024**3,
                    "maxSeconds": 20,
                },
            )
            plan_extra["preview"] = (
                "Verificação somente leitura de até 8 arquivos, 2 GiB e 20 segundos. "
                "Divergências serão marcadas como suspect; nenhum conteúdo será "
                "reparado, removido ou substituído."
            )
        elif action == "library.projection.repair":
            plan, removed, total = self._projection_repair_plan()
            plan_extra["preview"] = (
                f"Reparo de projeção: {removed} de {total} jogos cujo arquivo sumiu "
                "do disco deixam o catálogo. Apenas o cache do SteamZero é reescrito; "
                "nenhum arquivo seu é apagado ou movido."
            )
        elif action == "bios.link":
            platform_id = self._required_string(payload, "platformId")
            adapter_id = self._required_string(payload, "adapterId")
            copies = self._bios_projection_copies(platform_id, adapter_id)
            root = self._compatible_root({candidate: b"" for _, candidate in copies})
            plan = (
                transaction.plan_copy_files(copies, root=root, kind="emulation.bios-link")
                if copies
                else transaction.plan_write_files({}, root=root, kind="emulation.bios-link")
            )
            targets = self._emulator_bios_targets(adapter_id)
            plan_extra["preview"] = (
                f"Projeta as BIOS de {platform_id} · {adapter_id} para "
                f"{' e '.join(str(target) for target in targets)}. Arquivos já "
                "presentes e idênticos são mantidos; divergências bloqueiam a projeção."
            )
        elif action == "library.root.add":
            plan = self._plan_root_add(Path(self._required_string(payload, "path")))
        elif action.startswith("library.root.open:"):
            selected_root = self._root_from_action(action)
            plan = transaction.plan_write_files(
                {}, root=paths.data_home(), kind="emulation.library-root-open"
            )
            self._pending[plan.plan_id] = _PendingMutation(
                "library-root-open", {"root": str(selected_root)}
            )
        elif action.startswith("library.root.scan:"):
            selected_root = self._root_from_action(action)
            plan = transaction.plan_write_files(
                {}, root=paths.data_home(), kind="emulation.library-root-scan"
            )
            self._pending[plan.plan_id] = _PendingMutation(
                "library-root-scan", {"root": str(selected_root)}
            )
        elif action.startswith("library.root.audit:"):
            selected_root = self._root_from_action(action)
            audit = SwitchRootManager(selected_root).audit()
            approved = payload.get("approvedPaths", [])
            if not isinstance(approved, list) or not all(
                isinstance(value, str) for value in approved
            ):
                raise SteamZeroError("E-API-SCHEMA", detail="approvedPaths deve ser uma lista")
            if approved:
                plan, quarantine_id = SwitchRootManager(selected_root).plan_quarantine(
                    audit, approved
                )
                self._pending[plan.plan_id] = _PendingMutation(
                    "library-root-quarantine",
                    {"root": str(selected_root), "quarantineId": quarantine_id},
                )
                plan_extra["quarantineId"] = quarantine_id
            else:
                plan = transaction.plan_write_files(
                    {}, root=paths.data_home(), kind="emulation.library-root-audit"
                )
                self._pending[plan.plan_id] = _PendingMutation(
                    "library-root-audit", {"root": str(selected_root), "audit": audit}
                )
            plan_extra["auditPreview"] = audit
            counts = audit["counts"]
            plan_extra["preview"] = (
                "Auditoria somente leitura; nenhum arquivo será apagado.\n"
                f"Base: {counts['base']} · updates: {counts['update']} · "
                f"DLC: {counts['dlc']} · duplicados: {counts['duplicate']} · "
                f"incompatíveis: {counts['incompatible']} · "
                f"corrompidos: {counts['corrupted']} · desconhecidos: {counts['unknown']}.\n"
                "Para higienizar, selecione explicitamente itens não jogáveis do preview; "
                "eles serão movidos para quarentena com manifesto, hashes e rollback."
            )
        elif action.startswith("library.root.rename:"):
            selected_root = self._root_from_action(action)
            games, _unidentified = self._load_library_cache()
            games_in_root = [
                game
                for game in games
                if isinstance(game.get("path"), str)
                and Path(str(game["path"])).is_relative_to(selected_root)
            ]
            plan = SwitchRootManager(selected_root).plan_rename(games_in_root)
        elif action.startswith("library.root.remove:"):
            selected_root = self._root_from_action(action, require_accessible=False)
            plan = self._plan_root_remove(selected_root)
        elif action == "keys.import":
            plan = self._plan_keys(Path(self._required_string(payload, "path")))
        elif action == "keys.repair":
            plan = self._plan_key_repair()
        elif action == "runtime.prepare":
            plan = self._plan_runtime_prepare()
        elif action == "firmware.import":
            plan = self._plan_firmware(
                Path(self._required_string(payload, "path")),
                self._required_string(payload, "version"),
            )
        elif action == "bios.import":
            plan = self._plan_bios_import(
                Path(self._required_string(payload, "path")),
                self._required_string(payload, "platformId"),
                self._required_string(payload, "adapterId"),
            )
        elif action in {"content.update.import", "content.dlc.import"}:
            kind = "update" if ".update." in action else "dlc"
            title_id = self._required_title_id(payload)
            decision = self._content.plan_import(
                Path(self._required_string(payload, "path")),
                kind=kind,
                title_id=title_id,
                version=self._optional_string(payload, "version"),
            )
            plan = decision.plan or transaction.plan_write_files(
                {}, root=paths.data_home() / "switch-content", kind="switch-content.import"
            )
        elif action in {"content.save.import", "content.shader.import"}:
            kind = "save" if ".save." in action else "shader-cache"
            decision = self._content.plan_import(
                Path(self._required_string(payload, "path")),
                kind=kind,
                title_id=self._required_title_id(payload),
                emulator_id=self._optional_string(payload, "emulatorId"),
            )
            plan = decision.plan or transaction.plan_write_files(
                {}, root=paths.data_home() / "switch-content", kind="switch-content.import"
            )
        elif action.startswith("game.save.backup:"):
            game_id = action.split(":", 1)[1]
            game, emulator_id, game_name = self._preservation_context(game_id)
            self._require_game_session_idle(emulator_id, game_id)
            prepared = self._preservation.plan_backup(
                game_id, str(game["titleId"]), emulator_id, "save", game_name=game_name
            )
            plan = prepared.plan
            self._pending[plan.plan_id] = _PendingMutation(
                "preservation-cleanup", {"staging_root": str(prepared.staging_root)}
            )
        elif action.startswith("game.save.restore:"):
            parts = action.split(":", 2)
            if len(parts) != 3:
                raise SteamZeroError("E-API-SCHEMA", detail="ação de restore inválida")
            game_id, record_key = parts[1], parts[2]
            game, emulator_id, game_name = self._preservation_context(game_id)
            self._require_game_session_idle(emulator_id, game_id)
            plan, plan_extra = self._plan_preservation_restore(
                game, game_id, game_name, emulator_id, "save", record_key
            )
        elif action.startswith("game.state.backup:"):
            game_id = action.split(":", 1)[1]
            game, emulator_id, game_name = self._preservation_context(game_id)
            self._require_game_session_idle(emulator_id, game_id)
            prepared = self._preservation.plan_backup(
                game_id, str(game["titleId"]), emulator_id, "state", game_name=game_name
            )
            plan = prepared.plan
            self._pending[plan.plan_id] = _PendingMutation(
                "preservation-cleanup", {"staging_root": str(prepared.staging_root)}
            )
        elif action.startswith("game.state.restore:"):
            parts = action.split(":", 2)
            if len(parts) != 3:
                raise SteamZeroError("E-API-SCHEMA", detail="ação de restore inválida")
            game_id, record_key = parts[1], parts[2]
            game, emulator_id, game_name = self._preservation_context(game_id)
            self._require_game_session_idle(emulator_id, game_id)
            plan, plan_extra = self._plan_preservation_restore(
                game, game_id, game_name, emulator_id, "state", record_key
            )
        elif action.startswith("game.shader.backup:"):
            game_id = action.split(":", 1)[1]
            game, emulator_id, _game_name = self._preservation_context(game_id)
            self._require_game_session_idle(emulator_id, game_id)
            prepared = self._preservation.plan_backup(
                game_id, str(game["titleId"]), emulator_id, "shader-cache"
            )
            plan = prepared.plan
            self._pending[plan.plan_id] = _PendingMutation(
                "preservation-cleanup", {"staging_root": str(prepared.staging_root)}
            )
        elif action.startswith("game.shader.restore:"):
            parts = action.split(":", 2)
            if len(parts) != 3:
                raise SteamZeroError("E-API-SCHEMA", detail="ação de restore inválida")
            game_id, record_key = parts[1], parts[2]
            game, emulator_id, _game_name = self._preservation_context(game_id)
            self._require_game_session_idle(emulator_id, game_id)
            plan, plan_extra = self._plan_preservation_restore(
                game, game_id, None, emulator_id, "shader-cache", record_key
            )
        elif action.startswith("game.shader.invalidate:"):
            game_id = action.split(":", 1)[1]
            game, emulator_id, _game_name = self._preservation_context(game_id)
            self._require_game_session_idle(emulator_id, game_id)
            plan = self._preservation.plan_shader_invalidation(
                game_id, str(game["titleId"]), emulator_id
            )
        elif action.startswith("content.state:"):
            parts = action.split(":")
            if len(parts) != 3 or re.fullmatch(r"[0-9a-f]{64}", parts[1]) is None:
                raise SteamZeroError("E-API-SCHEMA", detail="identificador de conteúdo inválido")
            plan = self._content.plan_set_active(parts[1], active=parts[2] == "on")
        elif action.startswith("content.remove:"):
            record_key = action.split(":", 1)[1]
            if re.fullmatch(r"[0-9a-f]{64}", record_key) is None:
                raise SteamZeroError("E-API-SCHEMA", detail="identificador de conteúdo inválido")
            plan = self._content.plan_remove(record_key)
        elif action == "storage.recover":
            plan = self._content.plan_recover_index()
        elif action == "nsz.install":
            plan = transaction.plan_write_files(
                {}, root=paths.data_home(), kind="emulation.nsz-install"
            )
            self._pending[plan.plan_id] = _PendingMutation("nsz", {})
        elif action == "nsz.convert":
            source = Path(self._required_string(payload, "path"))
            source_format = source.suffix.lstrip(".").casefold()
            target_format = "nsp" if source_format == "nsz" else "nsz"
            plan = self._nsz_conversion().plan_convert(source, target_format)
        elif action == "game.emulator.default":
            emulator_id = self._required_string(payload, "emulatorId")
            self._require_known_emulator(emulator_id)
            plan = self._plan_global_setting("defaultEmulatorId", emulator_id)
        elif action == "game.emulator.clear_default":
            plan = self._plan_global_setting("defaultEmulatorId", None)
        elif action == "emulation.global.set-auto-publish-steam":
            plan = self._plan_global_setting(
                "autoPublishSteam", self._required_bool(payload, "value")
            )
        elif action == "emulation.global.set-prefer-native-nca":
            plan = self._plan_global_setting(
                "preferNativeNca", self._required_bool(payload, "value")
            )
        elif action.startswith("controls.profile.activate:"):
            profile_id = action.split(":", 1)[1]
            scope = self._optional_string(payload, "scope") or "platform"
            scope_id = self._optional_string(payload, "scopeId")
            orientation = self._optional_string(payload, "orientation")
            if scope == "game":
                scope_subject = scope_id or self._optional_string(payload, "gameId")
                if not scope_subject:
                    raise SteamZeroError(
                        "E-API-SCHEMA", detail="scope game exige gameId ou scopeId"
                    )
                game = self._current_game(scope_subject)
                settings = self._settings_for_game_with_global(
                    game, self._load_game_settings(strict=False)
                )
                game_emulator = settings.get("emulatorId")
                if isinstance(game_emulator, str):
                    self._require_game_session_idle(game_emulator, scope_subject)
                plan = self._input_profiles.plan_activate(
                    platform_id="switch",
                    profile_id=profile_id,
                    scope=scope,
                    scope_id=scope_subject,
                    orientation=orientation,
                )
            else:
                plan = self._input_profiles.plan_activate(
                    platform_id="switch",
                    profile_id=profile_id,
                    scope=scope,
                    scope_id=scope_id,
                    orientation=orientation,
                )
            plan_extra["profileId"] = profile_id
            plan_extra["orientation"] = orientation or "landscape"
        elif action.startswith("controls.profile.clear:"):
            game_id = action.split(":", 1)[1]
            game = self._current_game(game_id)
            settings = self._settings_for_game_with_global(
                game, self._load_game_settings(strict=False)
            )
            game_emulator = settings.get("emulatorId")
            if isinstance(game_emulator, str):
                self._require_game_session_idle(game_emulator, game_id)
            plan = self._input_profiles.plan_clear(
                platform_id="switch",
                scope="game",
                scope_id=game_id,
            )
        elif action == "game.emulator.set":
            game_id = self._required_string(payload, "gameId")
            self._current_game(game_id)
            emulator_id = self._required_string(payload, "emulatorId")
            self._require_known_emulator(emulator_id)
            plan = self._plan_game_setting(
                game_id,
                "emulatorId",
                emulator_id,
                key_emulator_id=emulator_id,
            )
        elif action == "game.steam.set":
            game_id = self._required_string(payload, "gameId")
            self._current_game(game_id)
            selected = payload.get("selected")
            if not isinstance(selected, bool):
                raise SteamZeroError("E-API-SCHEMA", detail="campo booleano obrigatório: selected")
            plan = self._plan_game_setting(game_id, "steamSelected", selected)
        elif action.startswith("extras.catalog.search:"):
            game_id = action.split(":", 1)[1]
            game = self._catalog_game_context(game_id, payload)
            plan = transaction.plan_write_files(
                {},
                root=paths.data_home(),
                kind="emulation.extras-catalog-search",
            )
            self._pending[plan.plan_id] = _PendingMutation(
                "extras-catalog-search",
                {
                    "gameId": str(game["id"]),
                    "titleId": str(game["titleId"]),
                },
            )
        elif action.startswith("mod.catalog.prepare:"):
            catalog_id = self._catalog_action_id(action)
            game, _emulator_id = self._extra_context(payload)
            candidate = self._catalog_mod_candidate(catalog_id, str(game["titleId"]))
            if not self._remote_mod_url_supported(candidate.identity.source_url):
                raise SteamZeroError(
                    "E-MOD-DOWNLOAD-FAILED",
                    detail="a fonte não publicou um arquivo de mod suportado",
                )
            plan = transaction.plan_write_files(
                {},
                root=paths.data_home(),
                kind="emulation.mod-catalog-prepare",
            )
            self._pending[plan.plan_id] = _PendingMutation(
                "mod-catalog-prepare",
                {
                    "catalogId": catalog_id,
                    "gameId": str(game["id"]),
                    "titleId": str(game["titleId"]),
                },
            )
        elif action.startswith("mod.catalog.install:"):
            plan = self._plan_catalog_mod_install(action, payload)
        elif action.startswith("cheat.catalog.install:"):
            plan = self._plan_catalog_cheat_install(action, payload)
        elif action == "mod.import":
            plan = self._plan_mod_import(payload)
        elif action == "cheat.import":
            plan = self._plan_cheat_import(payload)
        elif action.startswith("mod.state:"):
            plan = self._plan_mod_state(action)
        elif action.startswith("cheat.state:"):
            plan = self._plan_cheat_state(action)
        elif action.startswith("mod.remove:"):
            plan = self._plan_extra_remove(action, kind="mod")
        elif action.startswith("cheat.remove:"):
            plan = self._plan_extra_remove(action, kind="cheat")
        elif action == "steam.shortcuts.sync":
            settings = self._load_game_settings(strict=True)
            games, _unidentified = self._load_library_cache()
            selected = [
                self._current_game(str(game["id"]))
                for game in games
                if self._settings_for_game(game, settings).get("steamSelected") is True
            ]
            plan = self._shortcuts.plan(selected)
        elif action == "cloud.shortcuts.sync":
            plan = self._cloud.plan_shortcuts()
            plan_extra["preview"] = (
                "Publica os três serviços cloud declarados como atalhos não-Steam. "
                "Atalhos Switch e de terceiros são preservados; a Steam deve permanecer fechada."
            )
        elif action == "game.delete":
            game_id = self._required_string(payload, "gameId")
            game = self._current_game(game_id)
            source = Path(str(game["path"])).resolve(strict=True)
            root = self._root_for_game(source)
            plan = transaction.plan_write_files(
                {}, root=root, removals={source}, kind=f"emulation.game-delete:{game_id}"
            )
        elif action.startswith("game.media.search:"):
            game_id = action.split(":", 1)[1]
            game = self._current_game(game_id)
            title_id = str(game.get("titleId", ""))
            plan = transaction.plan_write_files(
                {},
                root=paths.data_home(),
                kind=f"media.search:{game_id}",
            )
            self._pending[plan.plan_id] = _PendingMutation(
                kind="media-search",
                metadata={
                    "game_id": game_id,
                    "title_id": title_id,
                    "title": str(game.get("name", "")),
                    "media_kinds": payload.get("mediaKinds"),
                    "local_media_source": str(game.get("mediaSource", "fallback")),
                    "local_media_url": str(game.get("coverUrl", "")),
                },
            )
        elif action.startswith("game.media.import:"):
            game_id = action.split(":", 1)[1]
            game = self._current_game(game_id)
            src_path = Path(self._required_string(payload, "path"))
            title_id = str(game.get("titleId", ""))
            fingerprint = str(game.get("fingerprint", ""))
            name = str(game.get("name", ""))
            if not src_path.is_file() or src_path.is_symlink():
                raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="arquivo de mídia inválido")
            _validate_mime(src_path)
            plan = transaction.plan_write_files(
                {},
                root=paths.data_home(),
                kind=f"media.import:{game_id}",
            )
            self._pending[plan.plan_id] = _PendingMutation(
                kind="media-import",
                metadata={
                    "game_id": game_id,
                    "title_id": title_id,
                    "fingerprint": fingerprint,
                    "canonical_name": name,
                    "src_path": str(src_path),
                },
            )
        elif action.startswith("game.media.select:"):
            parts = action.split(":")
            if len(parts) < 3:
                raise SteamZeroError(
                    "E-API-SCHEMA",
                    detail="formato: game.media.select:<gameId>:<candidateIdx>",
                )
            game_id = parts[1]
            candidate_idx = int(parts[2])
            game = self._current_game(game_id)
            plan = transaction.plan_write_files(
                {},
                root=paths.data_home(),
                kind=f"media.select:{game_id}",
            )
            self._pending[plan.plan_id] = _PendingMutation(
                kind="media-select",
                metadata={
                    "game_id": game_id,
                    "candidate_idx": candidate_idx,
                    "title_id": str(game.get("titleId", "")),
                    "fingerprint": str(game.get("fingerprint", "")),
                    "canonical_name": str(game.get("name", "")),
                },
            )
        elif action.startswith("game.media.clear:"):
            game_id = action.split(":", 1)[1]
            plan = transaction.plan_write_files(
                {},
                root=paths.data_home(),
                kind=f"media.clear:{game_id}",
            )
            self._pending[plan.plan_id] = _PendingMutation(
                kind="media-clear",
                metadata={"game_id": game_id},
            )
        elif action.startswith("game.media.publish-steam:"):
            game_id = action.split(":", 1)[1]
            steam_user_id = self._required_string(payload, "steamUserId")
            app_id, grid_dir = self._steam_media_context(game_id, steam_user_id)
            with self._store_factory() as store:
                store.migrate()
                maybe_plan = self._media_manager(store).plan_publish_steam(
                    game_id,
                    steam_user_id,
                    app_id,
                    grid_dir=grid_dir,
                )
            if maybe_plan is None:
                raise SteamZeroError(
                    "E-CONTENT-INCOMPLETE",
                    detail="nenhuma mídia otimizada disponível para publicação",
                )
            plan = maybe_plan
            self._pending[plan.plan_id] = _PendingMutation(
                kind="media-publish-steam",
                metadata={
                    "game_id": game_id,
                    "steam_user_id": steam_user_id,
                    "steam_app_id": app_id,
                    "grid_dir": str(grid_dir),
                },
            )
        elif action.startswith("game.media.unpublish-steam:"):
            game_id = action.split(":", 1)[1]
            steam_user_id = self._required_string(payload, "steamUserId")
            app_id, grid_dir = self._steam_media_context(game_id, steam_user_id)
            with self._store_factory() as store:
                store.migrate()
                maybe_plan = self._media_manager(store).unpublish_steam(
                    game_id,
                    steam_user_id,
                    app_id,
                    grid_dir=grid_dir,
                )
            if maybe_plan is None:
                raise SteamZeroError(
                    "E-TX-STALE-PLAN", detail="nenhuma mídia Steam gerenciada para remover"
                )
            plan = maybe_plan
            self._pending[plan.plan_id] = _PendingMutation(
                kind="media-unpublish-steam",
                metadata={
                    "game_id": game_id,
                    "steam_user_id": steam_user_id,
                    "steam_app_id": app_id,
                    "grid_dir": str(grid_dir),
                },
            )
        elif action == "rom.scan":
            roots = self.library_roots()
            plan = transaction.plan_write_files(
                {},
                root=paths.data_home(),
                kind="rom.scan",
            )
            self._pending[plan.plan_id] = _PendingMutation(
                kind="rom-scan",
                metadata={"roots": roots},
            )
        elif action in {
            "media.audit",
            "media.global.search-missing",
            "media.global.refresh",
            "media.global.overwrite",
            "media.global.optimize",
        }:
            mode = {
                "media.audit": "audit",
                "media.global.search-missing": "search-missing",
                "media.global.refresh": "refresh",
                "media.global.overwrite": "overwrite",
                "media.global.optimize": "optimize",
            }[action]
            overwrite = mode == "overwrite"
            if overwrite and payload.get("overwrite") is not True:
                raise SteamZeroError(
                    "E-API-SCHEMA",
                    detail="overwrite=true é obrigatório para sobrescrever mídias",
                )
            plan = transaction.plan_write_files(
                {},
                root=paths.data_home(),
                kind=f"media.global:{mode}",
            )
            self._pending[plan.plan_id] = _PendingMutation(
                kind="media-global",
                metadata={"mode": mode, "overwrite": overwrite},
            )
        elif action == "media.cache.prune-orphans":
            with self._store_factory() as store:
                store.migrate()
                plan = self._media_manager(store).plan_prune_orphan_cache()
        elif action == "media.cache.open":
            plan = transaction.plan_write_files(
                {},
                root=paths.data_home(),
                kind="media.cache-open",
            )
            self._pending[plan.plan_id] = _PendingMutation(
                kind="media-cache-open",
                metadata={},
            )
        else:
            raise SteamZeroError("E-API-SCHEMA", detail="ação de emulação não permitida")
        return self._plan_view(plan, action, **plan_extra)

    def apply_action(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        """Aplica o plano confirmado e liquida os efeitos colaterais da operação.

        Erro levantado DEPOIS do commit da transação (persistência de import,
        jobs de mídia, publicação no Steam) herda o operationId da operação já
        comitada. Sem isso o ErrorCard não agrega a falha à operação que o
        usuário acabou de disparar e o rollback fica sem alvo visível na UI.
        """
        result, plan = self._apply_transaction(plan_id, confirm_token)
        try:
            return self._settle_apply(plan_id, plan, result)
        except SteamZeroError as exc:
            if exc.operation_id is None:
                exc.operation_id = result.operation_id
            raise

    def _apply_transaction(
        self, plan_id: str, confirm_token: str
    ) -> tuple[transaction.ApplyResult, transaction.Plan]:
        """Chain de despacho até o commit. Erros aqui já saem com operationId
        anexado pelo próprio ``transaction.apply`` quando ocorrem pós-op_id."""
        plan = transaction.load_plan(plan_id)
        pending = self._pending.get(plan_id)
        if pending is not None and pending.kind == "nsz":
            result = transaction.apply(plan_id, confirm_token)
            self._nsz.install()
        elif plan.kind == "library.convert":
            result = SwitchRomConversionService.apply(plan_id, confirm_token)
        elif plan.kind == "switch-content.import":
            result = self._content.apply_import(plan_id, confirm_token)
        elif plan.kind == "switch-content.state":
            result = self._content.apply_state(plan_id, confirm_token)
        elif plan.kind == "switch-content.remove":
            result = self._content.apply_remove(plan_id, confirm_token)
        elif plan.kind == "switch-content.recover":
            result = self._content.apply_recovery(plan_id, confirm_token)
        elif plan.kind == "switch-shader.invalidate":
            result = self._content.apply_shader_invalidation(plan_id, confirm_token)
        elif plan.kind.startswith("input-profile."):
            result = self._input_profiles.apply(plan_id, confirm_token)
        elif plan.kind.startswith("preservation."):
            result = transaction.apply(plan_id, confirm_token)
        elif plan.kind == "steam.shortcuts.sync":
            result = self._shortcuts.apply(plan_id, confirm_token)
        elif plan.kind == "steam.cloud-shortcuts.sync":
            result = self._shortcuts.apply_cloud(plan_id, confirm_token)
        elif (
            plan.kind.startswith("emulation.")
            or plan.kind
            in {
                "bitrot.scan",
                "rom.scan",
                "media.audit",
                "switch-library.rename",
                "switch-library.quarantine",
            }
            or plan.kind.startswith("media.")
        ):
            result = transaction.apply(plan_id, confirm_token)
        else:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não pertence à emulação")
        return result, plan

    def _settle_apply(
        self, plan_id: str, plan: transaction.Plan, result: transaction.ApplyResult
    ) -> dict[str, Any]:
        """Efeitos colaterais pós-commit. A transação já está comitada: falha
        aqui não sofre rollback automático, apenas herda o operationId."""
        pending = self._pending.pop(plan_id, None)
        response: dict[str, Any] = {
            "status": result.status,
            "operationId": result.operation_id,
        }
        if pending is not None:
            if pending.kind in {"key", "firmware"}:
                self._persist_import(pending)
            elif pending.kind == "bios":
                self._persist_bios_import(pending)
            elif pending.kind in {
                "mod-install",
                "cheat-install",
                "mod-state",
                "cheat-state",
                "mod-remove",
                "cheat-remove",
            }:
                self._persist_extra(pending)
            elif pending.kind == "media-import":
                self._apply_media_import(pending)
            elif pending.kind == "media-search":
                meta = pending.metadata
                job = self._jobs.create(
                    "media.search",
                    params={
                        "game_id": meta["game_id"],
                        "title_id": meta["title_id"],
                        "title": meta["title"],
                        "media_kinds": meta.get("media_kinds"),
                        "local_media_source": meta.get("local_media_source", "fallback"),
                        "local_media_url": meta.get("local_media_url", ""),
                    },
                    priority="interactive",
                    created_by="ui",
                )
                response["jobId"] = job.id
                try:
                    self._jobs.run(job.id)
                except SteamZeroError as exc:
                    response["error"] = exc.code
                    response["errorDetail"] = str(exc.detail)
            elif pending.kind == "media-select":
                self._apply_media_select(pending)
            elif pending.kind == "media-clear":
                self._apply_media_clear(pending)
            elif pending.kind == "media-publish-steam":
                self._apply_media_publish_steam(pending)
            elif pending.kind == "media-unpublish-steam":
                self._apply_media_unpublish_steam(pending)
            elif pending.kind == "media-global":
                job = self._jobs.create(
                    "media.global",
                    params={
                        "mode": pending.metadata["mode"],
                        "overwrite": pending.metadata["overwrite"],
                    },
                    priority="maintenance",
                    created_by="ui",
                )
                self._start_background_job(job.id)
                response["jobId"] = job.id
                response["job"] = self._job_view(self._jobs.get(job.id) or job)
            elif pending.kind == "extras-catalog-search":
                job = self._jobs.create(
                    "extras.catalog.search",
                    params={
                        "game_id": pending.metadata["gameId"],
                        "title_id": pending.metadata["titleId"],
                    },
                    priority="interactive",
                    created_by="ui",
                )
                self._start_background_job(job.id)
                response["jobId"] = job.id
                response["job"] = self._job_view(self._jobs.get(job.id) or job)
            elif pending.kind == "mod-catalog-prepare":
                job = self._jobs.create(
                    "mod.catalog.prepare",
                    params={
                        "catalog_id": pending.metadata["catalogId"],
                        "game_id": pending.metadata["gameId"],
                        "title_id": pending.metadata["titleId"],
                    },
                    priority="interactive",
                    created_by="ui",
                )
                self._start_background_job(job.id)
                response["jobId"] = job.id
                response["job"] = self._job_view(self._jobs.get(job.id) or job)
            elif pending.kind == "media-cache-open":
                response.update(self._open_media_cache())
            elif pending.kind == "library-root-open":
                response.update(self._open_library_root(Path(str(pending.metadata["root"]))))
            elif pending.kind == "library-root-scan":
                response.update(self._scan_library_now())
            elif pending.kind == "library-root-audit":
                response["auditPreview"] = pending.metadata["audit"]
            elif pending.kind == "library-root-quarantine":
                response["quarantineId"] = pending.metadata["quarantineId"]
            elif pending.kind == "projection-repair":
                ghosts_after = self._count_projection_ghosts()
                response["verify"] = {
                    "ghostsAfterApply": ghosts_after,
                    "userFilesUntouched": True,
                }
                response["projectionRepair"] = pending.metadata
            elif pending.kind == "rom-scan":
                roots = pending.metadata.get("roots", [])
                job = self._jobs.create(
                    "rom.scan",
                    params={"roots": roots},
                    priority="background",
                    created_by="ui",
                )
                response["jobId"] = job.id
                self._jobs.run(job.id)
            elif pending.kind == "preservation-cleanup":
                self._preservation.cleanup(Path(str(pending.metadata["staging_root"])))
            elif pending.kind == "preservation-conflict-restore":
                self._preservation.cleanup(Path(str(pending.metadata["staging_root"])))
                restore = self._preservation.plan_restore(
                    str(pending.metadata["game_id"]),
                    str(pending.metadata["title_id"]),
                    str(pending.metadata["emulator_id"]),
                    str(pending.metadata["kind"]),
                    str(pending.metadata["record_key"]),
                    game_name=pending.metadata.get("game_name"),
                )
                restored = transaction.apply(restore.plan.plan_id, restore.plan.confirm_token)
                self._preservation.cleanup(restore.staging_root)
                response["restoreApplied"] = True
                response["operationId"] = restored.operation_id
        tracked_type: str | None = None
        if plan.kind == "library.convert":
            tracked_type = "nsz.convert"
        elif plan.kind in {"steam.shortcuts.sync", "steam.cloud-shortcuts.sync"} or (
            pending is not None and pending.kind in {"media-publish-steam", "media-unpublish-steam"}
        ):
            tracked_type = "steam.publish"
        elif plan.kind == "switch-content.import" or (
            pending is not None
            and pending.kind in {"key", "firmware", "mod-install", "cheat-install", "media-import"}
        ):
            tracked_type = "content.import"
        if tracked_type is not None:
            tracked = self._jobs.create(
                tracked_type,
                params={"operation_id": result.operation_id},
                priority="interactive",
                created_by="ui",
            )
            completed = self._jobs.run(tracked.id)
            response["jobId"] = completed.id
            response["job"] = self._job_view(completed)
        if plan.kind == "bitrot.scan":
            limits = plan.requirements
            job = self._jobs.create(
                "library.bitrot",
                params={
                    "max_files": int(limits.get("maxFiles", 8)),
                    "max_bytes": int(limits.get("maxBytes", 2 * 1024**3)),
                    "max_seconds": float(limits.get("maxSeconds", 20)),
                },
                priority="maintenance",
                created_by="ui",
                constraints={"forbiddenDuringGameplay": True},
            )
            completed = self._jobs.run(job.id)
            response["jobId"] = completed.id
            response["job"] = self._job_view(completed)
            response["health"] = self.library_health()
        if plan.kind == "emulation.library-roots" or plan.kind.startswith("emulation.game-delete:"):
            response["library"] = self.scan_library()
        if pending is not None and pending.kind.startswith("media-"):
            response["library"] = self.scan_library()
        return response

    def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        job = self._jobs.get(job_id)
        return self._job_view(job) if job is not None else None

    @staticmethod
    def _job_view(job: Job) -> dict[str, Any]:
        state = {
            "created": "queued",
            "queued": "queued",
            "blocked": "queued",
            "paused": "queued",
            "running": "running",
            "cancelling": "running",
            "rolling-back": "running",
            "interrupted": "running",
            "completed": "succeeded",
            "cancelled": "cancelled",
            "failed": "failed",
            "rolled-back": "failed",
            "rollback-failed": "failed",
        }.get(job.state, "failed")
        return {
            "jobId": job.id,
            "type": job.type,
            "state": state,
            "rawState": job.state,
            "priority": job.priority,
            "progress": job.progress,
            "errorCode": job.error_code,
            "result": job.result,
            "canCancel": job.state in {"queued", "blocked", "paused", "running"},
            "canRetry": job.state in {"cancelled", "rolled-back", "rollback-failed"},
            "createdAt": job.created_at,
            "updatedAt": job.updated_at,
        }

    def list_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        jobs = self._jobs.list_jobs()
        return [self._job_view(job) for job in jobs[-max(1, min(limit, 100)) :]][::-1]

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        with self._background_lock:
            runner = self._background_runners.get(job_id)
        if runner is not None:
            runner.request_cancel(job_id)
            current = self._jobs.get(job_id)
            if current is None:
                raise SteamZeroError("E-API-SCHEMA", detail=f"job inexistente: {job_id}")
            return self._job_view(current)
        return self._job_view(self._jobs.cancel(job_id))

    def retry_job(self, job_id: str) -> dict[str, Any]:
        previous = self._jobs.get(job_id)
        if previous is None:
            raise SteamZeroError("E-API-SCHEMA", detail=f"job inexistente: {job_id}")
        if previous.state not in {"cancelled", "rolled-back", "rollback-failed"}:
            raise SteamZeroError(
                "E-API-SCHEMA", detail=f"job não repetível no estado {previous.state}"
            )
        replacement = self._jobs.create(
            previous.type,
            params=dict(previous.params),
            priority=previous.priority,
            created_by="ui",
            constraints=dict(previous.constraints),
            correlation_id=previous.correlation_id,
        )
        if replacement.type in {
            "media.global",
            "extras.catalog.search",
            "mod.catalog.prepare",
        }:
            self._start_background_job(replacement.id)
        else:
            self._jobs.run(replacement.id)
        return self._job_view(self._jobs.get(replacement.id) or replacement)

    def _start_background_job(self, job_id: str) -> None:
        with self._background_lock:
            existing = self._background_threads.get(job_id)
            if existing is not None and existing.is_alive():
                raise SteamZeroError("E-API-SCHEMA", detail="job já possui executor ativo")
            thread = threading.Thread(
                target=self._run_background_job,
                args=(job_id,),
                name=f"steamzero-media-{job_id[:8]}",
                daemon=True,
            )
            self._background_threads[job_id] = thread
            thread.start()

    def _run_background_job(self, job_id: str) -> None:
        with self._store_factory() as store:
            store.migrate()
            runner = JobManager(store)
            runner.register("media.global", self._media_global_job_handler)
            runner.register("extras.catalog.search", self._extra_catalog_search_job_handler)
            runner.register("mod.catalog.prepare", self._mod_catalog_prepare_job_handler)
            with self._background_lock:
                self._background_runners[job_id] = runner
            try:
                job = runner.get(job_id)
                if job is not None and job.state in {"queued", "paused"}:
                    runner.run(job_id)
            finally:
                with self._background_lock:
                    self._background_runners.pop(job_id, None)
                    self._background_threads.pop(job_id, None)

    def _is_credential_configured(self, provider: str) -> bool:
        definition = provider_by_id(provider)
        if not definition.enabled or not definition.credential_fields:
            return False
        try:
            return all(
                self._secret_store.retrieve(provider, field.id) is not None
                for field in definition.credential_fields
                if field.required
            )
        except Exception:
            return False

    def _provider_credential_status(self, provider: str) -> dict[str, object]:
        definition = provider_by_id(provider)
        try:
            vault_available = self._secret_store.is_available()
        except Exception:
            vault_available = False
        required = tuple(field.id for field in definition.credential_fields if field.required)
        if not vault_available:
            configured = False
            missing = required
            state = "vaultUnavailable"
        elif not definition.enabled:
            configured = False
            missing = required
            state = "unavailable"
        elif not definition.credential_fields:
            configured = True
            missing = ()
            state = "local"
        else:
            try:
                missing = tuple(
                    field_id
                    for field_id in required
                    if self._secret_store.retrieve(provider, field_id) is None
                )
                configured = not missing
                recorded = self._credential_health.get(provider, {})
                state = str(recorded.get("state") or "stored") if configured else "notConfigured"
            except Exception:
                configured = False
                missing = required
                state = "vaultUnavailable"
        health = {
            "notConfigured": "notConfigured",
            "stored": "configured",
            "validated": "ready",
            "rejected": "rejected",
            "vaultUnavailable": "unavailable",
            "local": "ready",
            "unavailable": "unavailable",
        }.get(state, "unknown")
        recorded = self._credential_health.get(provider, {})
        return definition.public_dict(
            configured=configured,
            health_status=health,
            last_validated_at=recorded.get("lastValidatedAt"),
            credential_state=state,
            missing_required_fields=missing,
        )

    def credential_status(self) -> dict[str, Any]:
        try:
            vault_available = self._secret_store.is_available()
        except Exception:
            vault_available = False
        return {
            "providers": [
                self._provider_credential_status(definition.id) for definition in PROVIDERS
            ],
            "secretStoreAvailable": vault_available,
        }

    def save_credential(
        self, provider: str, credentials: Mapping[str, str] | str
    ) -> dict[str, Any]:
        definition = provider_by_id(provider)
        if not definition.enabled or not definition.credential_fields:
            raise SteamZeroError("E-API-SCHEMA", detail="provedor não aceita credenciais")
        if not self._secret_store.is_available():
            raise SteamZeroError(
                "E-SCRAPE-VAULT-UNAVAILABLE",
                detail="cofre de credenciais indisponível",
            )
        values = {"api_key": credentials} if isinstance(credentials, str) else dict(credentials)
        allowed = {field.id for field in definition.credential_fields}
        invalid_value = any(
            not isinstance(value, str) or not value.strip() for value in values.values()
        )
        if set(values) - allowed or invalid_value:
            raise SteamZeroError("E-API-SCHEMA", detail="campos de credencial inválidos")
        required = {field.id for field in definition.credential_fields if field.required}
        missing = sorted(required - set(values))
        if missing:
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail=f"campos obrigatórios ausentes: {', '.join(missing)}",
            )
        previous = {
            key_name: self._secret_store.retrieve(provider, key_name) for key_name in values
        }
        written: list[str] = []
        try:
            for key_name, value in values.items():
                self._secret_store.store(provider, key_name, Secret(value.strip()))
                written.append(key_name)
            for key_name, expected in values.items():
                verified = self._secret_store.retrieve(provider, key_name)
                if verified is None or verified.reveal() != expected.strip():
                    raise SteamZeroError(
                        "E-SCRAPE-VAULT-UNAVAILABLE",
                        detail="o cofre não confirmou a persistência",
                    )
        except Exception:
            for key_name in reversed(written):
                old = previous[key_name]
                with suppress(Exception):
                    if old is None:
                        self._secret_store.delete(provider, key_name)
                    else:
                        self._secret_store.store(provider, key_name, old)
            raise
        self._credential_health[provider] = {
            "state": "stored",
            "lastValidatedAt": None,
        }
        provider_status = self._provider_credential_status(provider)
        return {
            "provider": provider,
            "configured": True,
            "state": "stored",
            "providerStatus": provider_status,
        }

    def delete_credential(self, provider: str) -> dict[str, Any]:
        definition = provider_by_id(provider)
        if not definition.enabled or not definition.credential_fields:
            raise SteamZeroError("E-API-SCHEMA", detail="provedor não usa credenciais")
        if not self._secret_store.is_available():
            raise SteamZeroError(
                "E-SCRAPE-VAULT-UNAVAILABLE",
                detail="cofre de credenciais indisponível",
            )
        previous = {
            field.id: self._secret_store.retrieve(provider, field.id)
            for field in definition.credential_fields
        }
        deleted: list[str] = []
        try:
            for field in definition.credential_fields:
                self._secret_store.delete(provider, field.id)
                deleted.append(field.id)
            remaining = [
                field.id
                for field in definition.credential_fields
                if self._secret_store.retrieve(provider, field.id) is not None
            ]
            if remaining:
                raise SteamZeroError(
                    "E-SCRAPE-VAULT-UNAVAILABLE",
                    detail="o cofre não confirmou a revogação",
                )
        except Exception:
            for key_name in deleted:
                old = previous[key_name]
                if old is not None:
                    with suppress(Exception):
                        self._secret_store.store(provider, key_name, old)
            raise
        self._credential_health[provider] = {
            "state": "notConfigured",
            "lastValidatedAt": None,
        }
        return {
            "provider": provider,
            "configured": False,
            "state": "notConfigured",
            "providerStatus": self._provider_credential_status(provider),
        }

    def revoke_credential(self, provider: str) -> dict[str, Any]:
        return self.delete_credential(provider)

    def test_credential(self, provider: str) -> dict[str, Any]:
        definition = provider_by_id(provider)
        if not definition.enabled or not definition.credential_test_supported:
            raise SteamZeroError("E-API-SCHEMA", detail="teste não disponível para este provedor")
        if not self._secret_store.is_available():
            raise SteamZeroError(
                "E-SCRAPE-VAULT-UNAVAILABLE",
                detail="cofre de credenciais indisponível",
            )
        credentials = {
            field.id: secret.reveal()
            for field in definition.credential_fields
            if (secret := self._secret_store.retrieve(provider, field.id)) is not None
        }
        missing = [
            field.id
            for field in definition.credential_fields
            if field.required and field.id not in credentials
        ]
        if missing:
            self._credential_health[provider] = {
                "state": "notConfigured",
                "lastValidatedAt": None,
            }
            return {
                "provider": provider,
                "valid": False,
                "state": "notConfigured",
                "error": "E-SCRAPE-CREDENTIAL-MISSING",
                "missingRequiredFields": missing,
                "providerStatus": self._provider_credential_status(provider),
            }
        try:
            if provider == "steamgriddb":
                adapter: SteamGridDbAdapter | ScreenScraperAdapter = SteamGridDbAdapter(
                    api_key=credentials["api_key"]
                )
            elif provider == "screenscraper":
                adapter = ScreenScraperAdapter(
                    devid=credentials["devid"],
                    devpassword=credentials["devpassword"],
                    ssid=credentials.get("ssid"),
                    sspassword=credentials.get("sspassword"),
                )
            else:
                raise SteamZeroError(
                    "E-API-SCHEMA",
                    detail="teste não implementado para este provedor",
                )
            result = adapter.test_connection()
            state = "validated" if result else "rejected"
            self._credential_health[provider] = {
                "state": state,
                "lastValidatedAt": datetime.now(UTC).isoformat(),
            }
            return {
                "provider": provider,
                "valid": result,
                "state": state,
                "providerStatus": self._provider_credential_status(provider),
            }
        except SteamZeroError as exc:
            self._credential_health[provider] = {
                "state": "rejected",
                "lastValidatedAt": datetime.now(UTC).isoformat(),
            }
            return {
                "provider": provider,
                "valid": False,
                "state": "rejected",
                "error": exc.code,
                "providerStatus": self._provider_credential_status(provider),
            }
        except Exception:
            self._credential_health[provider] = {
                "state": "rejected",
                "lastValidatedAt": datetime.now(UTC).isoformat(),
            }
            return {
                "provider": provider,
                "valid": False,
                "state": "rejected",
                "error": "E-INTERNAL-UNEXPECTED",
                "providerStatus": self._provider_credential_status(provider),
            }

    def provider_link(self, provider: str, link: str) -> dict[str, Any]:
        """Abre somente destinos HTTPS declarados pelo catálogo local."""
        url = allowed_external_url(provider, link)
        executable = self._which("xdg-open")
        if executable is None:
            raise SteamZeroError(
                "E-DESKTOP-VERIFY",
                detail="xdg-open não está disponível para abrir o navegador",
            )
        try:
            self._spawn((executable, url))
        except Exception as exc:
            raise SteamZeroError(
                "E-DESKTOP-VERIFY",
                detail="não foi possível abrir o link no navegador",
            ) from exc
        return {"provider": provider, "link": link, "opened": True}

    def rollback_action(self, operation_id: str) -> dict[str, Any]:
        if not ids.is_ulid(operation_id):
            raise SteamZeroError("E-API-SCHEMA", detail="operationId inválido")
        records = journal.read_records(operation_id)
        begins = [record for record in records if record.get("type") == "operation.begin"]
        kind = str(begins[0].get("kind", "")) if len(begins) == 1 else ""
        allowed = (
            kind.startswith("emulation.game-delete:")
            or kind.startswith("input-profile.")
            or kind in {"steam.shortcuts.sync", "steam.cloud-shortcuts.sync"}
            or kind in {"switch-library.rename", "switch-library.quarantine"}
            or kind in {"emulation.bios-link", "emulation.library-projection-repair"}
        )
        if not allowed:
            raise SteamZeroError(
                "E-TX-STALE-PLAN",
                detail=(
                    "operação não pertence à exclusão, organização, atalho Steam "
                    "ou perfil reversível de emulação"
                ),
            )
        result = (
            self._input_profiles.rollback(operation_id)
            if kind.startswith("input-profile.")
            else transaction.rollback(operation_id, reason="emulation-user-request")
        )
        response: dict[str, Any] = {
            "status": result.status,
            "operationId": result.operation_id,
            "restored": result.restored,
        }
        if kind.startswith("emulation.game-delete:") or kind == "switch-library.rename":
            response["library"] = self.scan_library()
        return response

    def _emulator_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        registry = self._registry_factory()
        roots = self.library_roots()
        try:
            self._current_key_source()
            keys_cataloged = True
        except SteamZeroError:
            keys_cataloged = False
        with self._store_factory() as store:
            store.migrate()
            engine = AdapterEngine(store, registry, self._artifacts)
            lifecycle = ComponentLifecycle(store, registry, artifacts=self._artifacts)
            for emulator_id, (name, icon_asset) in _emulator_presentation(registry).items():
                manifest = registry.get(emulator_id)
                status = lifecycle.status(emulator_id)
                state = str(status["state"])
                degraded = state == "degraded"
                installed = state in {"installed", "degraded"}
                try:
                    source = manifest.preferred_source(None, allow_eol=False)
                except SteamZeroError:
                    # Fonte declarada, porém ausente ou EOL: a linha continua com
                    # estado real, sem versão-alvo — o motivo fica no status.
                    source = None
                flatpak = source is not None and str(source.type) == "flatpak"
                current = str(status.get("version") or "—")
                up_to_date = installed and source is not None and current == source.version
                running = False
                if installed:
                    # Degradado não trava o snapshot: payload ausente derruba o
                    # processo do jogo, mas a central continua navegável.
                    try:
                        if flatpak:
                            pid = self._running_pids.get(emulator_id)
                            running = pid is not None and _process_alive(pid)
                        else:
                            running = bool(
                                self._managed_process_groups(engine.payload_path(emulator_id))
                            )
                    except SteamZeroError:
                        running = False
                keys_ready = bool(installed and self._key_projection_valid(emulator_id))
                if state == "installed":
                    row_state, status_label, source_state = "ready", "Instalado", "verified"
                elif degraded:
                    row_state, status_label, source_state = "attention", "Reparar", "degraded"
                elif state == "missing":
                    row_state, status_label, source_state = (
                        "unavailable",
                        "Não instalado",
                        "verified",
                    )
                else:
                    row_state, status_label, source_state = (
                        "unverified",
                        "Não verificado",
                        "unverified",
                    )
                install_state = (
                    "installed"
                    if state == "installed"
                    else "degraded"
                    if degraded
                    else "not-installed"
                )
                actions = (
                    [
                        self._action(
                            f"emulator.repair:{emulator_id}",
                            "Reparar",
                            confirmation=True,
                        )
                    ]
                    if degraded
                    else []
                )
                if installed:
                    if not degraded:
                        actions.append(self._action(f"emulator.launch:{emulator_id}", "Abrir"))
                    actions.extend(
                        [
                            self._action(
                                f"emulator.update:{emulator_id}",
                                "Verificar atualização" if up_to_date else "Atualizar",
                                confirmation=True,
                            ),
                            self._action(
                                f"emulator.uninstall:{emulator_id}",
                                "Desinstalar",
                                confirmation=True,
                            ),
                        ]
                    )
                else:
                    actions.append(
                        self._action(
                            f"emulator.install:{emulator_id}", "Instalar", confirmation=True
                        )
                    )
                if installed and not keys_ready:
                    actions.append(
                        self._action(
                            "keys.repair" if keys_cataloged else "keys.import",
                            "Reparar keys" if keys_cataloged else "Importar keys",
                            confirmation=True,
                        )
                    )
                if installed and not roots:
                    actions.append(
                        self._action(
                            "library.root.add",
                            "Adicionar diretório de jogos",
                            confirmation=True,
                        )
                    )
                if running:
                    actions.append(
                        self._action(
                            f"emulator.stop:{emulator_id}",
                            "Fechar",
                            confirmation=False,
                        )
                    )
                rows.append(
                    {
                        "id": emulator_id,
                        "displayName": name,
                        "name": name,
                        "iconAsset": icon_asset,
                        "platform": self._primary_platform_for(emulator_id),
                        "state": row_state,
                        "statusLabel": status_label,
                        "installState": install_state,
                        "sourceState": source_state,
                        "installable": bool(status["installable"]),
                        "version": current,
                        "targetVersion": status.get("targetVersion"),
                        "running": running,
                        "isDefault": False,
                        "libraryRootCount": len(roots),
                        "health": {
                            "state": "degraded" if installed else "unavailable",
                            "versionCurrent": up_to_date,
                            "keysReady": keys_ready,
                            "firmwareReady": False,
                            "reason": (
                                status.get("detail")
                                or (
                                    "Aguardando verificação completa da plataforma."
                                    if installed
                                    else "Pendente: instalação e firmware."
                                )
                            ),
                        },
                        "specialty": (
                            "Flatpak do flathub, sandbox do aplicativo preservado"
                            if flatpak
                            else "AppImage verificado, configuração e dados preservados"
                        ),
                        "capabilities": [],
                        "actions": actions,
                        "action": actions[0],
                    }
                )
        return rows

    def _requirements(
        self, emulators: Sequence[Mapping[str, Any]]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        with self._store_factory() as store:
            store.migrate()
            keys = store.list_firmware_key_items("switch", kind="key")
            firmwares = store.list_firmware_key_items("switch", kind="firmware")
        revisions = [int(row["revision"]) for row in keys if row.get("revision") is not None]
        versions = [str(row["version"]) for row in firmwares if row.get("version")]
        key_revision = max(revisions) if revisions else None
        firmware_version = max(versions, key=self._version_tuple) if versions else None
        installed_emulators = [
            str(row["id"]) for row in emulators if row.get("installState") == "installed"
        ]
        missing_projections = [
            emulator_id
            for emulator_id in installed_emulators
            if not self._key_projection_valid(emulator_id)
        ]
        key_status = (
            "missing" if key_revision is None else "unverified" if missing_projections else "ok"
        )
        key = {
            "kind": "keys",
            "status": key_status,
            "required": None,
            "installed": f"rev{key_revision}" if key_revision is not None else None,
            "detail": (
                "Keys próprias validadas e disponíveis nos emuladores instalados."
                if key_status == "ok"
                else (
                    "Sincronize as keys com: " + ", ".join(missing_projections) + "."
                    if key_revision is not None
                    else "Importe seu arquivo prod.keys."
                )
            ),
            "blocksPlay": key_status != "ok",
        }
        firmware = {
            "kind": "firmware",
            "status": "ok" if firmware_version is not None else "missing",
            "required": None,
            "installed": firmware_version,
            "detail": "Firmware próprio catalogado."
            if firmware_version
            else "Importe um arquivo, pasta ou ZIP de firmware.",
            "blocksPlay": firmware_version is None,
        }
        return key, firmware

    _PRESERVATION_PREFIX: ClassVar[dict[str, str]] = {
        "save": "game.save",
        "state": "game.state",
        "shader-cache": "game.shader",
    }

    def _preservation_cards(self, games: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
        is_shader = kind == "shader-cache"
        target_key = {
            "save": "saveTarget",
            "state": "stateTarget",
            "shader-cache": "shaderTarget",
        }[kind]
        backups_key = {
            "save": "saveBackups",
            "state": "stateBackups",
            "shader-cache": "shaderBackups",
        }[kind]
        action_prefix = self._PRESERVATION_PREFIX[kind]
        cards: list[dict[str, Any]] = []
        for game in games:
            game_id = str(game.get("id", ""))
            target = game.get(target_key, {})
            backups = game.get(backups_key, [])
            confirmed = isinstance(target, dict) and target.get("confirmed") is True
            actions: list[dict[str, Any]] = []
            if confirmed and int(target.get("fileCount", 0)) > 0:
                actions.append(
                    self._action(
                        f"{action_prefix}.backup:{game_id}",
                        "Criar backup",
                        confirmation=True,
                    )
                )
                if is_shader and int(target.get("fileCount", 0)) > 0:
                    actions.append(
                        self._action(
                            f"game.shader.invalidate:{game_id}",
                            "Invalidar com segurança",
                            confirmation=True,
                        )
                    )
            cards.append(
                self._card(
                    f"preservation-{kind}-{game_id}",
                    str(game.get("name", "Jogo")),
                    (
                        f"Destino {target.get('destination')} · "
                        f"{int(target.get('fileCount', 0))} arquivo(s) · "
                        f"{int(target.get('size', 0)) / (1024 * 1024):.1f} MiB · "
                        f"emulador {target.get('emulatorVersion', 'unknown')}"
                        if confirmed
                        else str(target.get("reason", "destino seguro não confirmado"))
                    ),
                    "ready" if confirmed else "attention",
                    "Destino confirmado" if confirmed else "Indisponível",
                    actions=actions,
                )
            )
            for backup in backups if isinstance(backups, list) else []:
                if not isinstance(backup, dict):
                    continue
                record_key = str(backup.get("recordKey", ""))
                current_fingerprint = str(target.get("compatibilityFingerprint", ""))
                backup_fingerprint = str(backup.get("compatibilityFingerprint", ""))
                compatible = not is_shader or (
                    confirmed
                    and bool(current_fingerprint)
                    and backup_fingerprint == current_fingerprint
                )
                restore = self._action(
                    f"{action_prefix}.restore:{game_id}:{record_key}",
                    "Restaurar",
                    enabled=confirmed and compatible,
                    reason=(
                        None
                        if confirmed and compatible
                        else "Fingerprint do driver/emulador incompatível"
                        if is_shader and confirmed
                        else "Destino seguro não confirmado"
                    ),
                    confirmation=True,
                )
                cards.append(
                    self._card(
                        f"backup-{record_key[:12]}",
                        f"Backup de {game.get('name', 'jogo')}",
                        (
                            f"{backup.get('createdAt', 'sem horário')} · "
                            f"{int(backup.get('size', 0)) / 1024:.1f} KiB · "
                            f"integridade {backup.get('integrity', 'unknown')}"
                        ),
                        "ready" if compatible else "attention",
                        "Compatível" if compatible else "Incompatível",
                        actions=[restore],
                    )
                )
        if cards:
            return cards
        return [
            self._card(
                f"preservation-{kind}-empty",
                "Shader cache" if is_shader else "Saves",
                "Adicione e selecione um jogo antes de detectar o destino operacional.",
                "attention",
                "Sem jogo",
            )
        ]

    def _media_pipeline_summary(self, games: list[dict[str, Any]]) -> dict[str, Any]:
        sources = {
            "custom": 0,
            "rom": 0,
            "emulatorCache": 0,
            "remote": 0,
            "fallback": 0,
        }
        pending_candidates = 0
        provider_errors: dict[str, int] = {}
        for game in games:
            source = str(game.get("mediaSource") or "fallback")
            if source == "custom":
                sources["custom"] += 1
            elif source in {"nca", "rom", "rom-extracted"}:
                sources["rom"] += 1
            elif source == "emulator-cache":
                sources["emulatorCache"] += 1
            elif source in {"scraper", "scraped", "remote"}:
                sources["remote"] += 1
            else:
                sources["fallback"] += 1
            pending_candidates += int(game.get("mediaCandidateCount") or 0)
            errors = game.get("mediaErrors")
            if isinstance(errors, Mapping):
                for provider in errors:
                    provider_errors[str(provider)] = provider_errors.get(str(provider), 0) + 1

        cache_bytes = 0
        media_root = paths.media_dir()
        try:
            if media_root.is_dir() and not media_root.is_symlink():
                for candidate in media_root.rglob("*"):
                    if candidate.is_file() and not candidate.is_symlink():
                        cache_bytes += candidate.stat().st_size
        except OSError:
            cache_bytes = 0

        provider_details: dict[str, dict[str, Any]] = {}
        try:
            with self._store_factory() as store:
                store.migrate()
                health_rows = StateStoreProviderHealthAdapter(store.adapter_connection()).list_all()
        except Exception:
            health_rows = []
        health_by_provider = {row.provider: row for row in health_rows}
        for provider, affected in provider_errors.items():
            health = health_by_provider.get(provider)
            provider_details[provider] = {
                "gamesAffected": affected,
                "code": health.last_error_code if health else None,
                "category": health.last_error_category if health else None,
                "state": health.state if health else "active",
                "lastErrorAt": health.last_error if health else None,
                "errorCount": health.error_count if health else 0,
                "consecutiveFailures": health.consecutive_failures if health else 0,
                "totalRequests": health.total_requests if health else 0,
            }
        # A falha pode sobreviver ao jogo que a originou (por exemplo, após uma
        # nova varredura). O diagnóstico persistido ainda precisa aparecer: a
        # ausência de jogos com erro não é prova de que a quota voltou.
        for provider, health in health_by_provider.items():
            if provider in provider_details or not (
                health.last_error_code or health.last_error_category
            ):
                continue
            provider_details[provider] = {
                "gamesAffected": 0,
                "code": health.last_error_code,
                "category": health.last_error_category,
                "state": health.state,
                "lastErrorAt": health.last_error,
                "errorCount": health.error_count,
                "consecutiveFailures": health.consecutive_failures,
                "totalRequests": health.total_requests,
            }

        last_scan: str | None = None
        try:
            if self._library_cache_path.is_file() and not self._library_cache_path.is_symlink():
                last_scan = datetime.fromtimestamp(
                    self._library_cache_path.stat().st_mtime,
                    tz=UTC,
                ).isoformat()
        except OSError:
            pass
        last_audit: str | None = None
        try:
            if (
                self._media_audit_path.is_file()
                and not self._media_audit_path.is_symlink()
                and self._media_audit_path.stat().st_size <= 1024 * 1024
            ):
                payload = json.loads(self._media_audit_path.read_text(encoding="utf-8"))
                if payload.get("schemaVersion") == 1 and isinstance(payload.get("checkedAt"), str):
                    last_audit = str(payload["checkedAt"])
        except (OSError, UnicodeError, json.JSONDecodeError, AttributeError):
            pass
        active_jobs = [
            self._job_view(job)
            for job in self._jobs.list_jobs(
                states=["created", "queued", "blocked", "running", "paused", "cancelling"]
            )
            if job.type in {"media.search", "media.global"}
        ]
        return {
            "totalGames": len(games),
            "customMedia": sources["custom"],
            "romExtracted": sources["rom"],
            "emulatorCache": sources["emulatorCache"],
            "remoteMedia": sources["remote"],
            "fallbacks": sources["fallback"],
            "pendingCandidates": pending_candidates,
            "providerErrors": provider_errors,
            "providerDetails": provider_details,
            "lastAudit": last_audit,
            "lastScan": last_scan,
            "cacheBytes": cache_bytes,
            "activeJobs": active_jobs,
            "overwriteDefault": False,
            "mediaKinds": [
                {"id": "boxart", "available": True},
                {"id": "gridPortrait", "available": True},
                {"id": "gridLandscape", "available": True},
                {"id": "hero", "available": True},
                {"id": "logo", "available": True},
                {"id": "icon", "available": True},
                {"id": "screenshot", "available": True},
                {"id": "manual", "available": self._is_credential_configured("screenscraper")},
                {"id": "video", "available": False},
            ],
        }

    def _library_root_rows(self, games: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        stats: Mapping[str, Any] = {}
        try:
            if self._library_cache_path.is_file() and not self._library_cache_path.is_symlink():
                cached = json.loads(self._library_cache_path.read_text(encoding="utf-8"))
                if isinstance(cached.get("rootStats"), Mapping):
                    stats = cached["rootStats"]
        except (OSError, json.JSONDecodeError, AttributeError):
            stats = {}

        rows: list[dict[str, Any]] = []
        for root in self.registered_library_roots():
            identifier = root_id(root)
            try:
                safe_root = validate_rom_root(root)
                accessible = True
            except SteamZeroError:
                safe_root = root.absolute()
                accessible = False
            raw_stats = stats.get(identifier, {})
            raw_counts = raw_stats.get("counts", {}) if isinstance(raw_stats, Mapping) else {}
            counts = {
                "base": int(raw_counts.get("base", 0)),
                "updates": int(raw_counts.get("updates", 0)),
                "dlcs": int(raw_counts.get("dlcs", 0)),
                "incompatible": int(raw_counts.get("incompatible", 0)),
                "errors": int(raw_counts.get("errors", 0)),
            }
            last_scan = raw_stats.get("lastScan") if isinstance(raw_stats, Mapping) else None
            root_games = [
                game
                for game in games
                if isinstance(game.get("path"), str)
                and Path(str(game["path"])).is_relative_to(safe_root)
            ]
            unavailable_reason = "A raiz registrada está ausente ou não é um caminho real."
            actions = [
                self._action(
                    f"library.root.open:{identifier}",
                    "Abrir pasta",
                    enabled=accessible,
                    reason=None if accessible else unavailable_reason,
                ),
                self._action(
                    f"library.root.scan:{identifier}",
                    "Varrer agora",
                    enabled=accessible,
                    reason=None if accessible else unavailable_reason,
                    confirmation=True,
                ),
                self._action(
                    f"library.root.audit:{identifier}",
                    "Auditar/higienizar",
                    enabled=accessible,
                    reason=None if accessible else unavailable_reason,
                    confirmation=True,
                ),
                self._action(
                    f"library.root.rename:{identifier}",
                    "Corrigir nomes",
                    enabled=accessible and bool(root_games),
                    reason=(
                        None
                        if accessible and root_games
                        else unavailable_reason
                        if not accessible
                        else "Faça uma varredura antes de corrigir nomes."
                    ),
                    confirmation=True,
                ),
                self._action(
                    f"library.root.remove:{identifier}",
                    "Remover da biblioteca",
                    confirmation=True,
                ),
            ]
            if root_games:
                actions.append(
                    self._action(
                        f"game.media.import:{root_games[0]['id']}",
                        "Adicionar mídia para um jogo",
                        confirmation=True,
                    )
                )
            else:
                actions.append(
                    self._action(
                        f"library.root.media-unavailable:{identifier}",
                        "Adicionar mídia para um jogo",
                        enabled=False,
                        reason="Nenhum jogo desta raiz está disponível após a varredura.",
                    )
                )
            rows.append(
                self._card(
                    f"library-root-{identifier}",
                    "Diretório de ROMs",
                    (
                        f"{sanitize_display_path(root)} · {counts['base']} base(s), "
                        f"{counts['updates']} update(s), {counts['dlcs']} DLC(s), "
                        f"{counts['incompatible']} incompatível(is), "
                        f"{counts['errors']} erro(s) · última varredura: "
                        f"{last_scan or 'nunca'}"
                    ),
                    "ready" if accessible and counts["errors"] == 0 else "attention",
                    "Acessível" if accessible else "Inacessível",
                    actions=actions,
                )
                | {
                    "rootId": identifier,
                    "displayPath": sanitize_display_path(root),
                    "accessible": accessible,
                    "counts": counts,
                    "lastScan": last_scan,
                }
            )
        return rows

    def _area_data(
        self,
        emulators: list[dict[str, Any]],
        games: list[dict[str, Any]],
        unidentified: int,
        roots: list[str],
        records: list[Any],
        integrity: Mapping[str, Any],
        dock: bool,
        controllers: int,
        keys: Mapping[str, Any],
        firmware: Mapping[str, Any],
        input_profile_status: Mapping[str, Any],
    ) -> dict[str, Any]:
        updates = [record for record in records if record.kind == "update"]
        dlcs = [record for record in records if record.kind == "dlc"]
        missing_records = set(integrity.get("missingRecords", []))
        game_names = {
            str(game.get("titleId")): str(game.get("name", game.get("titleId")))
            for game in games
            if game.get("titleId")
        }
        has_game = bool(games)
        selected_reason = (
            None if has_game else "Adicione diretórios, faça a varredura e selecione um jogo."
        )
        nsz = self._nsz.status()
        nsz_ready = bool(nsz["available"])
        nsz_reason = (
            None
            if not nsz_ready
            else (
                None if keys["status"] == "ok" else "Importe prod.keys antes de converter com NSZ."
            )
        )
        media_pipeline = self._media_pipeline_summary(games)
        library_root_rows = self._library_root_rows(games)
        return {
            "overview": {
                "cards": [
                    self._card(
                        "emulators",
                        "Emuladores",
                        (
                            f"{sum(row['installState'] == 'installed' for row in emulators)} "
                            "instalado(s)."
                        ),
                        "ready",
                        "Gerenciados",
                    ),
                    self._card(
                        "library",
                        "Biblioteca Switch",
                        f"{len(games)} identificado(s); {unidentified} sem Title ID no nome.",
                        "ready" if games else "attention",
                        f"{len(roots)} diretório(s)",
                        action=self._action("library.root.add", "Adicionar diretório"),
                    ),
                ],
                "primaryAction": self._action("library.scan", "Varrer biblioteca"),
            },
            "keysFirmware": {
                "cards": [
                    self._card(
                        "keys",
                        "Keys",
                        str(keys["detail"]),
                        "ready" if keys["status"] == "ok" else "blocked",
                        str(keys["installed"] or "Ausentes"),
                        action=self._action(
                            "keys.repair" if keys["status"] == "unverified" else "keys.import",
                            (
                                "Sincronizar com emuladores"
                                if keys["status"] == "unverified"
                                else "Importar arquivo/pasta/ZIP"
                            ),
                            confirmation=True,
                        ),
                    ),
                    self._card(
                        "firmware",
                        "Firmware",
                        str(firmware["detail"]),
                        "ready" if firmware["status"] == "ok" else "blocked",
                        str(firmware["installed"] or "Ausente"),
                        action=self._action(
                            "firmware.import", "Importar arquivo/pasta/ZIP", confirmation=True
                        ),
                    ),
                ],
                "primaryAction": self._action("requirements.verify", "Validar novamente"),
            },
            "updatesDlc": {
                "cards": [
                    self._card(
                        "updates",
                        "Updates",
                        f"{len(updates)} update(s) catalogado(s).",
                        "ready",
                        f"{len(updates)}",
                        action=self._action(
                            "content.update.import",
                            "Importar update",
                            enabled=has_game,
                            reason=selected_reason,
                            confirmation=True,
                        ),
                    ),
                    self._card(
                        "dlc",
                        "DLC",
                        f"{len(dlcs)} DLC(s) catalogado(s).",
                        "ready",
                        f"{len(dlcs)}",
                        action=self._action(
                            "content.dlc.import",
                            "Importar DLC",
                            enabled=has_game,
                            reason=selected_reason,
                            confirmation=True,
                        ),
                    ),
                ]
                + [
                    self._card(
                        f"content-{record.record_key[:12]}",
                        "Update" if record.kind == "update" else "DLC",
                        (
                            f"{game_names.get(str(record.title_id), 'Jogo não catalogado')} · "
                            f"Title ID {record.title_id} · versão "
                            f"{record.version or 'não informada'} · "
                            f"{record.size / (1024 * 1024):.1f} MiB"
                        ),
                        (
                            "failed"
                            if record.record_key in missing_records
                            else "ready"
                            if record.state == "active"
                            else "attention"
                        ),
                        (
                            "Arquivo ausente"
                            if record.record_key in missing_records
                            else "Ativo"
                            if record.state == "active"
                            else "Inativo"
                        ),
                        actions=[
                            self._action(
                                (
                                    f"content.state:{record.record_key}:off"
                                    if record.state == "active"
                                    else f"content.state:{record.record_key}:on"
                                ),
                                "Desativar" if record.state == "active" else "Ativar",
                                enabled=record.record_key not in missing_records,
                                reason=(
                                    "O arquivo não passou pela validação de integridade."
                                    if record.record_key in missing_records
                                    else None
                                ),
                                confirmation=True,
                            ),
                            self._action(
                                f"content.remove:{record.record_key}",
                                "Remover",
                                confirmation=True,
                            ),
                        ],
                    )
                    for record in (updates + dlcs)[:8]
                ],
                "primaryAction": self._action("library.scan", "Atualizar jogos"),
            },
            "modsCheats": {
                "cards": [
                    self._card(
                        "mods",
                        "Mods instalados",
                        "Importe uma pasta ou ZIP local; cada mudança é revisada antes de aplicar.",
                        "ready",
                        str(sum(int(game.get("modsCount", 0)) for game in games)),
                        action=self._action(
                            "mod.import",
                            "Importar mod",
                            enabled=has_game,
                            reason=selected_reason,
                            confirmation=True,
                        ),
                    ),
                    self._card(
                        "cheats",
                        "Cheats Atmosphere",
                        "Arquivos são vinculados ao Title ID, Build ID e emulador do jogo.",
                        "ready",
                        str(sum(int(game.get("cheatsCount", 0)) for game in games)),
                        action=self._action(
                            "cheat.import",
                            "Importar cheat",
                            enabled=has_game,
                            reason=selected_reason,
                            confirmation=True,
                        ),
                    ),
                ],
                "primaryAction": self._action("emulation.refresh", "Atualizar inventário"),
            },
            "graphicsPerformance": {
                "cards": [
                    self._card(
                        "display-mode",
                        "Dock ↔ portátil",
                        (
                            "O perfil acompanha o estado físico observado sem sobrescrever "
                            "ajustes do jogo."
                        ),
                        "ready",
                        "Dock" if dock else "Portátil",
                    ),
                    self._card(
                        "integer-scaling",
                        "Escala inteira normativa",
                        "Tabela de resolucao 1280x800 com escalonamento 1x, 2x e 3x "
                        "conforme a experiencia retro declarativa.",
                        "ready" if has_game else "attention",
                        "1280x800",
                        action=self._action(
                            "emulation.refresh",
                            "Ver tabela",
                            enabled=True,
                        ),
                    ),
                ],
                "primaryAction": self._action("emulation.refresh", "Atualizar detecção"),
            },
            "controls": {
                "cards": [
                    self._card(
                        "controllers",
                        "Controles",
                        "Detecção local limitada a quatro jogadores.",
                        "ready",
                        f"{controllers} / 4",
                    ),
                    self._card(
                        "input-profile",
                        "Perfil de input",
                        (
                            f"{input_profile_status['active']['id']} · revisão "
                            f"{input_profile_status['active']['revision']} · "
                            f"{input_profile_status['active']['orientation']}"
                            if isinstance(input_profile_status.get("active"), Mapping)
                            else "Nenhum perfil foi selecionado para esta plataforma."
                        ),
                        str(input_profile_status["state"]),
                        str(input_profile_status["statusLabel"]),
                        actions=[
                            self._action(
                                f"controls.profile.activate:{row['id']}",
                                str(row["label"]),
                                confirmation=True,
                            )
                            for row in input_profile_status["available"]
                            if isinstance(row, Mapping)
                        ],
                    ),
                ],
                "primaryAction": self._action(
                    "controls.profile.activate:standard-gamepad",
                    "Selecionar perfil padrão",
                    confirmation=True,
                ),
            },
            "saves": {
                "cards": self._preservation_cards(games, "save"),
                "primaryAction": self._action("emulation.refresh", "Verificar integridade"),
            },
            "saveStates": {
                "cards": self._preservation_cards(games, "state"),
                "primaryAction": self._action("emulation.refresh", "Verificar integridade"),
            },
            "shaderCache": {
                "cards": self._preservation_cards(games, "shader-cache"),
                "primaryAction": self._action("emulation.refresh", "Verificar compatibilidade"),
            },
            "media": {
                "cards": [
                    *(
                        library_root_rows
                        if library_root_rows
                        else [
                            self._card(
                                "roots-empty",
                                "Diretórios de ROMs",
                                "Nenhum diretório registrado.",
                                "attention",
                                "Aguardando diretório",
                                action=self._action("library.root.add", "Adicionar diretório"),
                            )
                        ]
                    ),
                    self._card(
                        "identified",
                        "Identificação",
                        (
                            "A varredura combina conteúdo base, Title ID e metadados "
                            "já gerados pelos emuladores."
                        ),
                        "ready" if games else "attention",
                        f"{len(games)}",
                    ),
                    self._card(
                        "media-pipeline",
                        "Pipeline de mídias",
                        (
                            f"{media_pipeline['customMedia']} customizada(s); "
                            f"{media_pipeline['romExtracted']} extraída(s) da ROM; "
                            f"{media_pipeline['emulatorCache']} do cache de emulador; "
                            f"{media_pipeline['remoteMedia']} remota(s); "
                            f"{media_pipeline['fallbacks']} fallback(s)."
                        ),
                        "ready" if media_pipeline["totalGames"] else "attention",
                        f"{media_pipeline['totalGames']} jogo(s)",
                        actions=[
                            self._action(
                                "media.audit",
                                "Auditar mídias",
                                confirmation=True,
                            ),
                            self._action(
                                "media.global.search-missing",
                                "Buscar somente ausentes",
                                confirmation=True,
                            ),
                            self._action(
                                "media.global.refresh",
                                "Atualizar todas",
                                confirmation=True,
                            ),
                            self._action(
                                "media.global.overwrite",
                                "Atualizar e sobrescrever",
                                confirmation=True,
                            )
                            | {"overwrite": True},
                            self._action(
                                "media.global.optimize",
                                "Reotimizar formatos",
                                confirmation=True,
                            ),
                        ],
                    ),
                    self._card(
                        "media-cache",
                        "Cache canônico",
                        (
                            f"{media_pipeline['cacheBytes']} byte(s); "
                            f"{media_pipeline['pendingCandidates']} candidato(s) pendente(s); "
                            f"último audit: {media_pipeline['lastAudit'] or 'nunca'}."
                        ),
                        "ready" if not media_pipeline["providerErrors"] else "attention",
                        f"{len(media_pipeline['activeJobs'])} job(s) ativo(s)",
                        actions=[
                            self._action("media.cache.open", "Abrir pasta do cache"),
                            self._action(
                                "media.cache.prune-orphans",
                                "Limpar somente cache órfão",
                                confirmation=True,
                            ),
                            (
                                self._action(
                                    f"game.media.import:{games[0]['id']}",
                                    "Importar mídia manual",
                                    confirmation=True,
                                )
                                if games
                                else self._action(
                                    "media.import.unavailable",
                                    "Importar mídia manual",
                                    enabled=False,
                                    reason="Adicione um jogo antes de importar mídia.",
                                )
                            ),
                        ],
                    ),
                    self._card(
                        "credential",
                        "SteamGridDB",
                        (
                            "Configure sua chave de API para buscar capas automaticamente."
                            if not self._is_credential_configured("steamgriddb")
                            else "Credencial configurada. Teste a conexão."
                        ),
                        "ready" if self._is_credential_configured("steamgriddb") else "attention",
                        "Configurado"
                        if self._is_credential_configured("steamgriddb")
                        else "Não configurado",
                        action=self._action(
                            "open-credential-dialog",
                            "Configurar chave"
                            if not self._is_credential_configured("steamgriddb")
                            else "Gerenciar",
                        ),
                    ),
                ],
                "primaryAction": self._action("library.scan", "Varrer agora"),
                "mediaPipeline": media_pipeline,
                "libraryRoots": library_root_rows,
            },
            "storage": {
                "cards": [
                    self._card(
                        "integrity",
                        "Conteúdo compartilhado",
                        (
                            f"{integrity['validRecords']} registro(s) íntegro(s); "
                            f"{len(integrity['missingRecords'])} ausente(s)."
                        ),
                        "ready" if integrity["state"] == "ready" else "attention",
                        str(integrity["state"]),
                    )
                ],
                "primaryAction": self._action(
                    "storage.recover", "Reconciliar índice", confirmation=True
                ),
            },
            "advanced": {
                "cards": [
                    self._card(
                        "nsz",
                        "Conversão NSZ",
                        (
                            "NSZ é instalado em ambiente privado e pinado por hash; "
                            "as keys locais continuam necessárias para converter."
                        ),
                        "ready" if nsz_ready and keys["status"] == "ok" else "attention",
                        (
                            "Pronto"
                            if nsz_ready and keys["status"] == "ok"
                            else "Instalar ferramenta"
                            if not nsz_ready
                            else "Aguardando keys"
                        ),
                        action=self._action(
                            "nsz.install" if not nsz_ready else "nsz.convert",
                            "Instalar ferramenta" if not nsz_ready else "Selecionar arquivo",
                            enabled=not nsz_ready or keys["status"] == "ok",
                            reason=nsz_reason,
                            confirmation=True,
                        ),
                    ),
                    self._card(
                        "operations",
                        "Operações",
                        "Instalações e imports usam preview, confirmação e rollback.",
                        "ready",
                        "Auditável",
                        action=self._action(
                            "runtime.prepare",
                            "Preparar lançamento direto",
                            confirmation=True,
                        ),
                    ),
                ],
                "primaryAction": self._action("emulation.refresh", "Atualizar diagnóstico"),
            },
        }

    def _plan_mod_import(self, payload: Mapping[str, Any]) -> transaction.Plan:
        game, emulator_id = self._extra_context(payload)
        title_id = str(game["titleId"])
        selected = Path(self._required_string(payload, "path"))
        files, source_root = self._selected_mod_tree(selected)
        relative_files = {path.relative_to(source_root).as_posix() for path in files}
        conflicts = self._active_mod_conflicts(str(game["id"]), emulator_id, relative_files)
        if conflicts:
            raise SteamZeroError(
                "E-MOD-INSTALL-FAILED",
                detail="destinos de mod em conflito com: " + ", ".join(conflicts),
            )
        mod_id = ids.new_ulid()
        mod_name = self._safe_extra_name(selected.stem if selected.is_file() else selected.name)
        target_dir = self._mod_install_dir(emulator_id, title_id, mod_name, mod_id)
        copies = [(source, target_dir / source.relative_to(source_root)) for source in files]
        root = self._extra_transaction_root(target_dir)
        plan = transaction.plan_copy_files(copies, root=root, kind="emulation.mod-import")
        self._pending[plan.plan_id] = _PendingMutation(
            "mod-install",
            {
                "id": mod_id,
                "gameId": str(game["id"]),
                "titleId": title_id,
                "name": mod_name,
                "emulatorId": emulator_id,
                "installPath": str(target_dir),
            },
        )
        return plan

    def _plan_cheat_import(self, payload: Mapping[str, Any]) -> transaction.Plan:
        game, emulator_id = self._extra_context(payload)
        selected = Path(self._required_string(payload, "path"))
        if selected.is_symlink() or not selected.is_file() or selected.suffix.casefold() != ".txt":
            raise SteamZeroError("E-CHEAT-CODE-INVALID", detail="selecione um arquivo .txt regular")
        if selected.stat().st_size > 4 * 1024**2:
            raise SteamZeroError("E-CHEAT-CODE-INVALID", detail="arquivo de cheat excede 4 MiB")
        build_id = selected.stem.upper()
        if _BUILD_ID.fullmatch(build_id) is None:
            raise SteamZeroError(
                "E-CHEAT-BUILD-ID-MISMATCH",
                detail="nomeie o arquivo com o Build ID hexadecimal (16 a 64 dígitos)",
            )
        try:
            codes = tuple(selected.read_text(encoding="utf-8").splitlines())
        except (OSError, UnicodeError) as exc:
            raise SteamZeroError("E-CHEAT-CODE-INVALID", detail="arquivo ilegível") from exc
        has_code = any(
            re.match(r"^[0-9A-Fa-f]{8}(?:\s+[0-9A-Fa-f]{8})+", line.strip()) for line in codes
        )
        if not has_code or not validate_cheat_codes(codes):
            raise SteamZeroError(
                "E-CHEAT-CODE-INVALID", detail="nenhum código Atmosphere válido foi encontrado"
            )
        title_id = str(game["titleId"])
        target = self._cheat_dir(emulator_id, title_id) / f"{build_id}.txt"
        plan = transaction.plan_copy_files(
            [(selected, target)],
            root=self._extra_transaction_root(target),
            kind="emulation.cheat-import",
        )
        cheat_id = ids.new_ulid()
        self._pending[plan.plan_id] = _PendingMutation(
            "cheat-install",
            {
                "id": cheat_id,
                "gameId": str(game["id"]),
                "titleId": title_id,
                "name": selected.stem,
                "buildId": build_id,
                "emulatorId": emulator_id,
                "installPath": str(target),
                "codeCount": sum(
                    1
                    for line in codes
                    if line.strip() and not line.lstrip().startswith(("//", "#", "["))
                ),
            },
        )
        return plan

    def _catalog_game_context(self, game_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        requested = self._optional_string(payload, "gameId")
        if requested and requested != game_id:
            raise SteamZeroError(
                "E-TX-STALE-PLAN",
                detail="o jogo selecionado mudou; atualize a tela e tente novamente",
            )
        game = self._current_game(game_id)
        title_id = game.get("titleId")
        if not isinstance(title_id, str) or _TITLE_ID.fullmatch(title_id) is None:
            raise SteamZeroError(
                "E-MOD-TITLE-ID-NOT-FOUND",
                detail="Title ID não identificado para buscar catálogos",
            )
        return game

    @staticmethod
    def _catalog_action_id(action: str) -> str:
        catalog_id = action.split(":", 1)[1] if ":" in action else ""
        if re.fullmatch(r"[0-9a-f]{64}", catalog_id) is None:
            raise SteamZeroError("E-API-SCHEMA", detail="candidato de catálogo inválido")
        return catalog_id

    def _catalog_mod_candidate(self, catalog_id: str, title_id: str) -> ModCandidate:
        with self._store_factory() as store:
            store.migrate()
            candidate = StateStoreModsAdapter(store.adapter_connection()).get_catalog(catalog_id)
        if candidate is None or candidate.title_id != title_id:
            raise SteamZeroError(
                "E-TX-STALE-PLAN",
                detail="candidato de mod expirou ou pertence a outro jogo",
            )
        return candidate

    @staticmethod
    def _remote_mod_url_supported(url: str) -> bool:
        parsed = urlsplit(url)
        suffix = Path(unquote(parsed.path)).suffix.casefold()
        return (
            parsed.scheme.casefold() == "https"
            and bool(parsed.hostname)
            and suffix in _REMOTE_MOD_SUFFIXES
        )

    @staticmethod
    def _mod_package_root(catalog_id: str) -> Path:
        return paths.data_home() / "catalog-packages" / catalog_id

    def _prepared_mod_package(
        self, catalog_id: str
    ) -> tuple[dict[str, Any], list[Path], Path] | None:
        if re.fullmatch(r"[0-9a-f]{64}", catalog_id) is None:
            return None
        base = self._mod_package_root(catalog_id)
        if base.is_symlink() or not base.is_dir():
            return None
        for digest_dir in sorted(base.iterdir(), key=lambda item: item.name, reverse=True):
            if (
                digest_dir.is_symlink()
                or not digest_dir.is_dir()
                or re.fullmatch(r"[0-9a-f]{64}", digest_dir.name) is None
            ):
                continue
            manifest_path = digest_dir / "manifest.json"
            if manifest_path.is_symlink() or not manifest_path.is_file():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                manifest.get("schemaVersion") != 1
                or manifest.get("catalogId") != catalog_id
                or manifest.get("contentSha256") != digest_dir.name
                or not isinstance(manifest.get("files"), list)
            ):
                continue
            tree = digest_dir / "tree"
            files: list[Path] = []
            valid = True
            for item in manifest["files"]:
                if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                    valid = False
                    break
                try:
                    relative = fs.validate_relative_entry(item["path"])
                    source = fs.resolve_within(tree, tree / relative)
                except (SteamZeroError, OSError):
                    valid = False
                    break
                if (
                    source.is_symlink()
                    or not source.is_file()
                    or source.stat().st_size != item.get("size")
                ):
                    valid = False
                    break
                files.append(source)
            if valid and files:
                return manifest, files, tree
        return None

    def _plan_catalog_mod_install(
        self, action: str, payload: Mapping[str, Any]
    ) -> transaction.Plan:
        catalog_id = self._catalog_action_id(action)
        game, emulator_id = self._extra_context(payload)
        candidate = self._catalog_mod_candidate(catalog_id, str(game["titleId"]))
        prepared = self._prepared_mod_package(catalog_id)
        if prepared is None:
            raise SteamZeroError(
                "E-MOD-CATALOG-STALE",
                detail="prepare e valide o pacote remoto antes de instalar",
            )
        manifest, files, tree = prepared
        relative_files: set[str] = set()
        total = 0
        for item, source in zip(manifest["files"], files, strict=True):
            relative = str(item["path"])
            if fs.hash_file(source, algo="sha256") != item.get("sha256"):
                raise SteamZeroError(
                    "E-MOD-CATALOG-STALE",
                    detail=f"arquivo preparado divergiu: {relative}",
                )
            relative_files.add(relative)
            total += source.stat().st_size
        if len(files) > _MAX_IMPORT_FILES or total > _MAX_MOD_BYTES:
            raise SteamZeroError(
                "E-MOD-INSTALL-FAILED",
                detail="pacote preparado excede os limites de segurança",
            )
        conflicts = self._active_mod_conflicts(str(game["id"]), emulator_id, relative_files)
        if conflicts:
            raise SteamZeroError(
                "E-MOD-INSTALL-FAILED",
                detail="destinos de mod em conflito com: " + ", ".join(conflicts),
            )
        mod_id = ids.new_ulid()
        name = self._safe_extra_name(candidate.identity.name)
        target_dir = self._mod_install_dir(emulator_id, candidate.title_id, name, mod_id)
        copies = [(source, target_dir / source.relative_to(tree)) for source in files]
        plan = transaction.plan_copy_files(
            copies,
            root=self._extra_transaction_root(target_dir),
            kind="emulation.mod-catalog-install",
        )
        self._pending[plan.plan_id] = _PendingMutation(
            "mod-install",
            {
                "id": mod_id,
                "catalogId": catalog_id,
                "gameId": str(game["id"]),
                "titleId": candidate.title_id,
                "buildId": candidate.build_id,
                "name": name,
                "modType": candidate.identity.mod_type,
                "source": candidate.identity.source,
                "version": candidate.identity.version,
                "emulatorId": emulator_id,
                "installPath": str(target_dir),
            },
        )
        return plan

    def _plan_catalog_cheat_install(
        self, action: str, payload: Mapping[str, Any]
    ) -> transaction.Plan:
        catalog_id = self._catalog_action_id(action)
        game, emulator_id = self._extra_context(payload)
        with self._store_factory() as store:
            store.migrate()
            candidate = StateStoreCheatsAdapter(store.adapter_connection()).get_catalog(catalog_id)
        if candidate is None or candidate.title_id != game["titleId"]:
            raise SteamZeroError(
                "E-TX-STALE-PLAN",
                detail="candidato expirou ou pertence a outro jogo",
            )
        build_id = candidate.build_id
        if build_id is None or _BUILD_ID.fullmatch(build_id) is None:
            raise SteamZeroError(
                "E-CHEAT-BUILD-ID-MISMATCH",
                detail="o catálogo não publicou um Build ID instalável",
            )
        if not candidate.codes or not validate_cheat_codes(candidate.codes):
            raise SteamZeroError(
                "E-CHEAT-CODE-INVALID",
                detail="o catálogo não publicou códigos Atmosphere válidos",
            )
        name = self._safe_extra_name(candidate.identity.name)
        content = (
            f"// {name}\n// BuildID: {build_id}\n" + "\n".join(candidate.codes) + "\n"
        ).encode("utf-8")
        target = self._cheat_dir(emulator_id, candidate.title_id) / f"{build_id}.txt"
        plan = transaction.plan_write_files(
            {target: content},
            root=self._extra_transaction_root(target),
            kind="emulation.cheat-catalog-install",
        )
        self._pending[plan.plan_id] = _PendingMutation(
            "cheat-install",
            {
                "id": ids.new_ulid(),
                "catalogId": catalog_id,
                "gameId": str(game["id"]),
                "titleId": candidate.title_id,
                "name": name,
                "buildId": build_id,
                "emulatorId": emulator_id,
                "installPath": str(target),
                "codeCount": sum(
                    1
                    for line in candidate.codes
                    if line.strip() and not line.lstrip().startswith(("//", "#", "["))
                ),
                "source": candidate.identity.source,
                "version": candidate.identity.version,
                "cheatType": candidate.identity.cheat_type,
            },
        )
        return plan

    def _plan_mod_state(self, action: str) -> transaction.Plan:
        parts = action.split(":")
        if len(parts) != 3 or parts[2] not in {"on", "off"}:
            raise SteamZeroError("E-API-SCHEMA", detail="ação de mod inválida")
        mod = self._extra_record("mod", parts[1])
        if not isinstance(mod, InstalledMod) or not mod.install_path or not mod.emulator_id:
            raise SteamZeroError("E-MOD-INSTALL-FAILED", detail="mod instalado não encontrado")
        source_dir = Path(mod.install_path)
        if parts[2] == "off":
            target_dir = self._disabled_mod_dir(mod.emulator_id, mod.title_id, mod.id)
            new_state = "inactive"
        else:
            target_dir = self._mod_install_dir(mod.emulator_id, mod.title_id, mod.name, mod.id)
            new_state = "active"
            relative_files = self._mod_relative_files(source_dir)
            conflicts = self._active_mod_conflicts(
                mod.game_id, mod.emulator_id, relative_files, exclude_id=mod.id
            )
            if conflicts:
                raise SteamZeroError(
                    "E-MOD-INSTALL-FAILED",
                    detail="ativação conflita com: " + ", ".join(conflicts),
                )
        moves = self._tree_moves(source_dir, target_dir)
        plan = transaction.plan_move_files(
            moves,
            root=self._extra_transaction_root(target_dir),
            kind="emulation.mod-state",
        )
        self._pending[plan.plan_id] = _PendingMutation(
            "mod-state", {"id": mod.id, "state": new_state, "installPath": str(target_dir)}
        )
        return plan

    def _plan_cheat_state(self, action: str) -> transaction.Plan:
        parts = action.split(":")
        if len(parts) != 3 or parts[2] not in {"on", "off"}:
            raise SteamZeroError("E-API-SCHEMA", detail="ação de cheat inválida")
        cheat = self._extra_record("cheat", parts[1])
        if not isinstance(cheat, InstalledCheat) or not cheat.install_path:
            raise SteamZeroError("E-CHEAT-INSTALL-FAILED", detail="cheat instalado não encontrado")
        source = Path(cheat.install_path)
        if parts[2] == "off":
            target = source.with_name(source.name + ".disabled")
            state, enabled = "inactive", False
        else:
            if not source.name.endswith(".disabled"):
                raise SteamZeroError("E-CHEAT-INSTALL-FAILED", detail="cheat já está ativo")
            target = source.with_name(source.name.removesuffix(".disabled"))
            state, enabled = "active", True
        plan = transaction.plan_move_files(
            {source: target},
            root=self._extra_transaction_root(target),
            kind="emulation.cheat-state",
        )
        self._pending[plan.plan_id] = _PendingMutation(
            "cheat-state",
            {"id": cheat.id, "state": state, "enabled": enabled, "installPath": str(target)},
        )
        return plan

    def _plan_extra_remove(self, action: str, *, kind: str) -> transaction.Plan:
        record_id = action.split(":", 1)[1] if ":" in action else ""
        record = self._extra_record(kind, record_id)
        install_path = getattr(record, "install_path", None)
        if not isinstance(install_path, str):
            raise SteamZeroError("E-TX-STALE-PLAN", detail="conteúdo instalado não encontrado")
        source = Path(install_path)
        removals = set(fs.iter_files(source)) if source.is_dir() else {source}
        if not removals:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="conteúdo já está ausente")
        plan = transaction.plan_write_files(
            {},
            root=self._extra_transaction_root(source),
            removals=removals,
            kind=f"emulation.{kind}-remove",
        )
        self._pending[plan.plan_id] = _PendingMutation(f"{kind}-remove", {"id": record_id})
        return plan

    def _extra_context(self, payload: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
        game = self._current_game(self._required_string(payload, "gameId"))
        if not isinstance(game.get("titleId"), str):
            raise SteamZeroError("E-MOD-TITLE-ID-NOT-FOUND", detail="Title ID não identificado")
        settings = self._settings_for_game_with_global(game, self._load_game_settings(strict=True))
        emulator_id = settings.get("emulatorId")
        if not isinstance(emulator_id, str):
            raise SteamZeroError(
                "E-MOD-EMULATOR-NOT-FOUND", detail="defina o emulador deste jogo primeiro"
            )
        self._require_managed_emulator(emulator_id)
        requested = self._optional_string(payload, "emulatorId")
        if requested and requested != emulator_id:
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="o emulador mudou; atualize a tela e tente novamente"
            )
        return game, emulator_id

    @staticmethod
    def _mod_relative_files(root: Path) -> set[str]:
        if root.is_symlink() or not root.is_dir():
            raise SteamZeroError("E-MOD-INSTALL-FAILED", detail="diretório de mod inválido")
        result: set[str] = set()
        for path in fs.iter_files(root):
            if path.is_symlink() or not path.is_file():
                raise SteamZeroError("E-MOD-INSTALL-FAILED", detail="mod contém symlink")
            result.add(path.relative_to(root).as_posix())
        return result

    def _active_mod_conflicts(
        self,
        game_id: str,
        emulator_id: str,
        relative_files: set[str],
        *,
        exclude_id: str | None = None,
    ) -> list[str]:
        with self._store_factory() as store:
            store.migrate()
            mods = StateStoreModsAdapter(store.adapter_connection()).list_installed(game_id)
        conflicts: list[str] = []
        for installed in mods:
            if (
                installed.id == exclude_id
                or installed.state != "active"
                or installed.emulator_id != emulator_id
                or not installed.install_path
            ):
                continue
            if relative_files.intersection(self._mod_relative_files(Path(installed.install_path))):
                conflicts.append(installed.name)
        return sorted(conflicts, key=str.casefold)

    def _mod_conflict_map(self, mods: Sequence[InstalledMod]) -> dict[str, list[str]]:
        file_sets: dict[str, set[str]] = {}
        for mod in mods:
            if not mod.install_path:
                file_sets[mod.id] = set()
                continue
            try:
                file_sets[mod.id] = self._mod_relative_files(Path(mod.install_path))
            except SteamZeroError:
                file_sets[mod.id] = set()
        result: dict[str, list[str]] = {mod.id: [] for mod in mods}
        for index, left in enumerate(mods):
            for right in mods[index + 1 :]:
                if left.emulator_id != right.emulator_id:
                    continue
                if file_sets[left.id].intersection(file_sets[right.id]):
                    result[left.id].append(right.name)
                    result[right.id].append(left.name)
        return result

    def _preservation_context(self, game_id: str) -> tuple[dict[str, Any], str, str | None]:
        game = self._current_game(game_id)
        title_id = game.get("titleId")
        if not isinstance(title_id, str) or _TITLE_ID.fullmatch(title_id) is None:
            raise SteamZeroError("E-CONTENT-INCOMPLETE", detail="Title ID não identificado")
        settings = self._settings_for_game_with_global(game, self._load_game_settings(strict=True))
        emulator_id = settings.get("emulatorId")
        if not isinstance(emulator_id, str):
            raise SteamZeroError(
                "E-CONTENT-UNSUPPORTED",
                detail="defina um emulador para confirmar o destino",
            )
        self._require_managed_emulator(emulator_id)
        return game, emulator_id, self._rom_stem(game)

    @staticmethod
    def _rom_stem(game: Mapping[str, Any]) -> str | None:
        raw = game.get("path")
        return Path(str(raw)).stem if isinstance(raw, str) and raw else None

    def _plan_preservation_restore(
        self,
        game: Mapping[str, Any],
        game_id: str,
        game_name: str | None,
        emulator_id: str,
        kind: str,
        record_key: str,
    ) -> tuple[transaction.Plan, dict[str, Any]]:
        prepared = self._preservation.plan_restore(
            game_id, str(game["titleId"]), emulator_id, kind, record_key, game_name=game_name
        )
        if not prepared.conflict:
            plan = prepared.plan
            self._pending[plan.plan_id] = _PendingMutation(
                "preservation-cleanup", {"staging_root": str(prepared.staging_root)}
            )
            return plan, {}
        conflict = self._preservation.plan_backup(
            game_id, str(game["titleId"]), emulator_id, kind, game_name=game_name
        )
        plan = conflict.plan
        self._pending[plan.plan_id] = _PendingMutation(
            "preservation-conflict-restore",
            {
                "staging_root": str(conflict.staging_root),
                "kind": kind,
                "record_key": record_key,
                "game_id": game_id,
                "title_id": str(game["titleId"]),
                "emulator_id": emulator_id,
                "game_name": game_name,
            },
        )
        return plan, {
            "preview": (
                "O estado atual diverge do backup escolhido: ele será preservado "
                "como um novo backup antes do restore; o restore é aplicado na "
                "sequência, com rollback próprio."
            )
        }

    def _require_game_session_idle(self, emulator_id: str, game_id: str) -> None:
        pid = self._running_pids.get(emulator_id)
        if pid is not None and _process_alive(pid):
            raise SteamZeroError(
                "E-CONTENT-BUSY",
                detail="o jogo está em execução; encerre a sessão antes de alterar conteúdo",
            )

    def _session_save_checkpoint(self, game_id: str, title_id: str, emulator_id: str) -> None:
        """Checkpoint automático do save ao encerrar a sessão; nunca interrompe
        o encerramento (falha é silenciosa, como o padrão do watcher)."""
        with suppress(Exception):
            status = self._preservation.target_status(game_id, title_id, emulator_id, "save")
            if status.get("confirmed") is not True:
                return
            last = self._preservation.backups(title_id, emulator_id, "save")
            expected = str(status.get("integrity", ""))[:20]
            if expected and last and str(last[0].get("treeDigest", "")) == expected:
                return
            prepared = self._preservation.plan_backup(game_id, title_id, emulator_id, "save")
            transaction.apply(prepared.plan.plan_id, prepared.plan.confirm_token)
            self._preservation.cleanup(prepared.staging_root)
            self._trim_save_backups(title_id, emulator_id, "save", keep=8)

    def _trim_save_backups(self, title_id: str, emulator_id: str, kind: str, *, keep: int) -> None:
        rows = self._preservation.backups(title_id, emulator_id, kind)
        if len(rows) <= keep:
            return
        for row in rows[keep:]:
            record_key = str(row.get("recordKey", ""))
            if not record_key:
                continue
            plan = self._content.plan_remove(record_key)
            transaction.apply(plan.plan_id, plan.confirm_token)

    def _selected_mod_tree(self, selected: Path) -> tuple[list[Path], Path]:
        if selected.is_symlink() or not selected.exists():
            raise SteamZeroError("E-MOD-INSTALL-FAILED", detail="origem local inválida")
        if selected.is_file() and selected.suffix.casefold() == ".zip":
            files = safezip.extract_safe(selected, ids.new_ulid())
            if not files:
                raise SteamZeroError("E-MOD-INSTALL-FAILED", detail="ZIP de mod vazio")
            source_root = Path(os.path.commonpath([str(path.parent) for path in files]))
        elif selected.is_dir():
            source_root = selected.resolve(strict=True)
            files = list(fs.iter_files(source_root))
        else:
            raise SteamZeroError("E-MOD-INSTALL-FAILED", detail="selecione uma pasta ou ZIP de mod")
        total = sum(path.stat().st_size for path in files)
        if not files or len(files) > _MAX_IMPORT_FILES or total > _MAX_MOD_BYTES:
            raise SteamZeroError(
                "E-MOD-INSTALL-FAILED", detail="mod vazio ou fora dos limites de segurança"
            )
        if any(path.is_symlink() or not path.is_file() for path in files):
            raise SteamZeroError("E-MOD-INSTALL-FAILED", detail="mod contém origem insegura")
        return files, source_root

    @staticmethod
    def _tree_moves(source_dir: Path, target_dir: Path) -> dict[Path, Path]:
        if source_dir.is_symlink() or not source_dir.is_dir():
            raise SteamZeroError("E-TX-STALE-PLAN", detail="diretório do mod não está acessível")
        moves = {
            source: target_dir / source.relative_to(source_dir)
            for source in fs.iter_files(source_dir)
        }
        if not moves:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="mod não contém arquivos")
        return moves

    @staticmethod
    def _safe_extra_name(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9 _.-]", "_", value).strip(" .")[:80] or "mod"

    @staticmethod
    def _real_emulator_roots() -> bool:
        return paths.data_home().resolve().is_relative_to(Path.home().resolve())

    def _mod_base(self, emulator_id: str) -> Path:
        if not self._real_emulator_roots():
            return paths.data_home() / "emulators" / emulator_id / "mods"
        home = Path.home()
        return {
            "eden": home / ".local/share/eden/load",
            "citron": home / ".local/share/citron/load",
            "ryubing": home / ".config/Ryujinx/mods/contents",
        }[emulator_id]

    def _mod_install_dir(self, emulator_id: str, title_id: str, name: str, mod_id: str) -> Path:
        directory = f"{self._safe_extra_name(name)}-{mod_id[:8]}"
        return self._mod_base(emulator_id) / title_id / directory

    @staticmethod
    def _disabled_mod_dir(emulator_id: str, title_id: str, mod_id: str) -> Path:
        return paths.data_home() / "switch-mods-disabled" / emulator_id / title_id / mod_id

    def _cheat_dir(self, emulator_id: str, title_id: str) -> Path:
        return self._mod_base(emulator_id) / title_id / "cheats"

    @staticmethod
    def _extra_transaction_root(target: Path) -> Path:
        home = Path.home().resolve()
        return home if target.is_relative_to(home) else paths.data_home().resolve()

    def _extra_record(self, kind: str, record_id: str) -> InstalledMod | InstalledCheat | None:
        with self._store_factory() as store:
            store.migrate()
            if kind == "mod":
                return StateStoreModsAdapter(store.adapter_connection()).get_by_id(record_id)
            return StateStoreCheatsAdapter(store.adapter_connection()).get_by_id(record_id)

    def _plan_root_add(self, selected: Path) -> transaction.Plan:
        resolved = validate_rom_root(
            selected,
            managed_roots=(
                paths.keys_dir(),
                paths.firmware_dir(),
                paths.media_dir(),
                paths.data_home() / "cache",
            ),
        )
        roots, excluded = self._root_config()
        if resolved not in roots:
            roots.append(resolved)
        excluded.discard(resolved)
        ordered_roots = sorted(roots, key=str)
        data = {
            "schemaVersion": 1,
            "roots": [str(root) for root in ordered_roots],
            "excludedRoots": [str(root) for root in sorted(excluded, key=str)],
        }
        writes = {self._roots_path: json.dumps(data, sort_keys=True, ensure_ascii=False).encode()}
        writes.update(self._emulator_game_directory_writes(self._configured_game_roots(resolved)))
        root = self._compatible_root(writes)
        return transaction.plan_write_files(
            writes,
            root=root,
            kind="emulation.library-roots",
        )

    def _plan_root_remove(self, selected: Path) -> transaction.Plan:
        roots, excluded = self._root_config()
        roots = [
            root for root in roots if root.resolve(strict=False) != selected.resolve(strict=False)
        ]
        excluded.add(selected.resolve(strict=False))
        data = {
            "schemaVersion": 1,
            "roots": [str(root) for root in sorted(roots, key=str)],
            "excludedRoots": [str(root) for root in sorted(excluded, key=str)],
        }
        active_roots = tuple(
            Path(raw)
            for raw in self.library_roots()
            if Path(raw).resolve(strict=False) != selected.resolve(strict=False)
        )
        writes = {self._roots_path: json.dumps(data, sort_keys=True, ensure_ascii=False).encode()}
        writes.update(self._emulator_game_directory_writes(active_roots))
        return transaction.plan_write_files(
            writes,
            root=self._compatible_root(writes),
            kind="emulation.library-roots",
        )

    def _projection_repair_plan(self) -> tuple[transaction.Plan, int, int]:
        """Reconcilia o cache de biblioteca com o disco sem tocar na origem.

        Jogos cujo arquivo sumiu ou virou symlink deixam a projeção; o cache é
        reescrito de forma transacional (rollback automático restaura o cache
        anterior). Nenhum arquivo do usuário é apagado, movido ou reescrito.
        """
        cache_path = self._library_cache_path
        if not cache_path.is_file() or cache_path.is_symlink():
            raise SteamZeroError(
                "E-CONTENT-INCOMPLETE",
                detail="faça uma varredura da biblioteca antes do reparo de projeção",
            )
        try:
            data = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise SteamZeroError(
                "E-CONTENT-INCOMPLETE",
                detail="cache de biblioteca ilegível; faça uma varredura",
            ) from exc
        games = data.get("games")
        if not isinstance(games, list):
            raise SteamZeroError(
                "E-CONTENT-INCOMPLETE",
                detail="cache de biblioteca sem catálogo; faça uma varredura",
            )
        ghosts: list[str] = []
        kept: list[dict[str, Any]] = []
        for game in games:
            if not isinstance(game, dict):
                ghosts.append("<inválido>")
                continue
            path_value = game.get("path")
            candidate = Path(path_value) if isinstance(path_value, str) else None
            if candidate is None or candidate.is_symlink() or not candidate.is_file():
                ghosts.append(str(path_value))
                continue
            kept.append(game)
        reconciled = dict(data)
        reconciled["games"] = kept
        if ghosts:
            payload = json.dumps(
                reconciled, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            ).encode()
            plan = transaction.plan_write_files(
                {cache_path: payload},
                root=paths.data_home(),
                kind="emulation.library-projection-repair",
            )
        else:
            plan = transaction.plan_write_files(
                {}, root=paths.data_home(), kind="emulation.library-projection-repair"
            )
        self._pending[plan.plan_id] = _PendingMutation(
            "projection-repair",
            {"removed": len(ghosts), "total": len(games), "ghostPaths": ghosts[:20]},
        )
        return plan, len(ghosts), len(games)

    def _plan_keys(self, selected: Path) -> transaction.Plan:
        candidates = self._selected_files(selected, suffixes={".keys"})
        exact = [path for path in candidates if path.name.casefold() == "prod.keys"]
        if len(exact) == 1:
            source = exact[0]
        elif len(candidates) == 1:
            source = candidates[0]
        else:
            raise SteamZeroError(
                "E-CONTENT-KEYS-INCOMPAT", detail="selecione uma origem com um único prod.keys"
            )
        revision = self._validate_keys(source)
        digest = fs.hash_file(source, algo="sha256")
        target = paths.keys_dir() / "switch" / f"prod-{digest[:12]}.keys"
        projections = (
            self._key_projection_targets()
            if paths.data_home().resolve().is_relative_to(Path.home().resolve())
            else ()
        )
        targets = [target, *projections]
        copies = self._new_copy_targets(source, targets, digest)
        title_sources = [path for path in candidates if path.name.casefold() == "title.keys"]
        if len(title_sources) > 1:
            raise SteamZeroError(
                "E-CONTENT-KEYS-INCOMPAT", detail="mais de um arquivo title.keys encontrado"
            )
        if title_sources:
            title_source = title_sources[0]
            self._validate_title_keys(title_source)
            title_digest = fs.hash_file(title_source, algo="sha256")
            title_target = paths.keys_dir() / "switch" / f"title-{title_digest[:12]}.keys"
            title_targets = [
                title_target,
                *(
                    self._title_key_projection_targets()
                    if paths.data_home().resolve().is_relative_to(Path.home().resolve())
                    else ()
                ),
            ]
            copies.extend(self._new_copy_targets(title_source, title_targets, title_digest))
        root = self._compatible_root({candidate: b"" for _, candidate in copies})
        plan = (
            transaction.plan_copy_files(copies, root=root, kind="emulation.keys-import")
            if copies
            else transaction.plan_write_files({}, root=root, kind="emulation.keys-import")
        )
        self._pending[plan.plan_id] = _PendingMutation(
            "key",
            {
                "revision": revision,
                "digest": digest,
                "relpath": str(target.relative_to(paths.keys_dir())),
            },
        )
        return plan

    def _plan_key_repair(self) -> transaction.Plan:
        source = self._current_key_source()
        digest = fs.hash_file(source, algo="sha256")
        copies: list[tuple[Path, Path]] = []
        for target in self._key_projection_targets():
            if not target.exists() and not target.is_symlink():
                copies.append((source, target))
                continue
            if target.is_file() and fs.hash_file(target, algo="sha256") == digest:
                continue
            raise SteamZeroError(
                "E-CONTENT-KEYS-INCOMPAT",
                detail=f"key existente diverge; revise manualmente antes de substituir: {target}",
            )
        title_source = self._current_title_key_source()
        if title_source is not None:
            title_digest = fs.hash_file(title_source, algo="sha256")
            copies.extend(
                self._new_copy_targets(
                    title_source, self._title_key_projection_targets(), title_digest
                )
            )
        if not copies:
            return transaction.plan_write_files({}, root=Path.home(), kind="emulation.keys-repair")
        return transaction.plan_copy_files(copies, root=Path.home(), kind="emulation.keys-repair")

    def _plan_runtime_prepare(self) -> transaction.Plan:
        writes = self._runtime_config_writes()
        copies: list[tuple[Path, Path]] = []
        for emulator_id in _MANAGED_EMULATORS:
            copies.extend(self._key_projection_copies(emulator_id))
        copies.extend(self._firmware_projection_copies(tuple(_MANAGED_EMULATORS)))
        if copies:
            return transaction.plan_copy_files(
                copies,
                root=Path.home(),
                kind="emulation.runtime-prepare",
                writes=writes,
            )
        return transaction.plan_write_files(
            writes, root=Path.home(), kind="emulation.runtime-prepare"
        )

    def _plan_firmware(self, selected: Path, version: str) -> transaction.Plan:
        if not _FIRMWARE_VERSION.fullmatch(version):
            raise SteamZeroError("E-API-SCHEMA", detail="versão de firmware inválida")
        candidates = self._selected_files(selected, suffixes={".nca"}, allow_single_any=True)
        total = sum(path.stat().st_size for path in candidates)
        if not candidates or len(candidates) > _MAX_IMPORT_FILES or total > _MAX_IMPORT_BYTES:
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-ARCHIVE", detail="conjunto de firmware fora dos limites"
            )
        copies: list[tuple[Path, Path]] = []
        for source in candidates:
            digest = fs.hash_file(source, algo="sha256")
            targets = [
                paths.firmware_dir() / "switch" / version / f"{digest}.nca",
                *(
                    self._firmware_projection_targets(digest)
                    if paths.data_home().resolve().is_relative_to(Path.home().resolve())
                    else ()
                ),
            ]
            copies.extend(self._new_copy_targets(source, targets, digest))
        digest_set = hashlib.sha256(
            "".join(sorted(target.name for _, target in copies)).encode()
        ).hexdigest()
        root = self._compatible_root({target: b"" for _, target in copies})
        plan = (
            transaction.plan_copy_files(copies, root=root, kind="emulation.firmware-import")
            if copies
            else transaction.plan_write_files({}, root=root, kind="emulation.firmware-import")
        )
        self._pending[plan.plan_id] = _PendingMutation(
            "firmware", {"version": version, "digest": digest_set, "relpath": f"switch/{version}"}
        )
        return plan

    def _plan_bios_import(
        self, selected: Path, platform_id: str, adapter_id: str
    ) -> transaction.Plan:
        """Importa uma BIOS do usuário para o store central (REQUIREMENTS-E2E).

        Segura por construção: só são aceitos arquivos cujo NOME está declarado
        no perfil de launch da plataforma (``requiresBios``) — o mesmo contrato
        que a projeção de requisitos consome. Nada é baixado; o hash completo
        nunca vai para log (SR-14), e arquivo existente divergente recusa em vez
        de sobrescrever.
        """
        profile = self._launch_profile_for(platform_id, adapter_id)
        if profile is None or not profile.requires_bios:
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail=f"{platform_id} · {adapter_id} não declara BIOS exigida",
            )
        if selected.is_symlink() or not selected.is_file():
            raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="origem local inválida")
        if selected.name not in profile.requires_bios:
            raise SteamZeroError(
                "E-CONTENT-FW-INCOMPAT",
                detail=(
                    f"arquivo não corresponde a nenhuma BIOS exigida por "
                    f"{platform_id} · {adapter_id}: {', '.join(profile.requires_bios)}"
                ),
            )
        if not (0 < selected.stat().st_size <= _MAX_BIOS_BYTES):
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-ARCHIVE", detail="arquivo de BIOS fora dos limites"
            )
        digest = fs.hash_file(selected, algo="sha256")
        dest = fs.resolve_within(paths.bios_dir(), paths.bios_dir() / platform_id / selected.name)
        copies = self._new_copy_targets(selected, [dest], digest)
        root = self._compatible_root({candidate: b"" for _, candidate in copies})
        plan = (
            transaction.plan_copy_files(copies, root=root, kind="emulation.bios-import")
            if copies
            else transaction.plan_write_files({}, root=root, kind="emulation.bios-import")
        )
        self._pending[plan.plan_id] = _PendingMutation(
            "bios",
            {
                "platform": platform_id,
                "name": selected.name,
                "digest": digest,
            },
        )
        return plan

    def _selected_files(
        self, selected: Path, *, suffixes: set[str], allow_single_any: bool = False
    ) -> list[Path]:
        if selected.is_symlink() or not selected.exists():
            raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="origem local inválida")
        if selected.is_file() and selected.suffix.casefold() == ".zip":
            candidates = safezip.extract_safe(selected, ids.new_ulid())
        elif selected.is_dir():
            candidates = list(fs.iter_files(selected))
        elif selected.is_file():
            candidates = [selected.resolve(strict=True)]
        else:
            candidates = []
        filtered = [
            path
            for path in candidates
            if not path.is_symlink()
            and path.is_file()
            and (path.suffix.casefold() in suffixes or (allow_single_any and len(candidates) == 1))
        ]
        if not filtered:
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-PATH", detail="nenhum arquivo compatível encontrado"
            )
        return filtered

    def _validate_keys(self, source: Path) -> int:
        try:
            text = source.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise SteamZeroError(
                "E-CONTENT-KEYS-INCOMPAT", detail="arquivo de keys ilegível"
            ) from exc
        names: set[str] = set()
        revisions: list[int] = []
        for line in text.splitlines():
            match = _KEY_LINE.fullmatch(line)
            if match is None:
                continue
            name = match.group(1)
            if name in names:
                raise SteamZeroError(
                    "E-CONTENT-KEYS-INCOMPAT", detail="identificador de key duplicado"
                )
            names.add(name)
            master = _MASTER_KEY.fullmatch(name)
            if master is not None:
                revisions.append(int(master.group(1), 16))
        if len(names) < 4 or not revisions:
            raise SteamZeroError(
                "E-CONTENT-KEYS-INCOMPAT", detail="keyset prod incompleto ou inválido"
            )
        return max(revisions)

    @staticmethod
    def _validate_title_keys(source: Path) -> None:
        try:
            lines = source.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError) as exc:
            raise SteamZeroError("E-CONTENT-KEYS-INCOMPAT", detail="title.keys ilegível") from exc
        names: set[str] = set()
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = _KEY_LINE.fullmatch(line)
            if match is None or re.fullmatch(r"[0-9a-f]{32}", match.group(1)) is None:
                raise SteamZeroError(
                    "E-CONTENT-KEYS-INCOMPAT", detail="entrada inválida em title.keys"
                )
            if match.group(1) in names:
                raise SteamZeroError(
                    "E-CONTENT-KEYS-INCOMPAT", detail="Title ID duplicado em title.keys"
                )
            names.add(match.group(1))
        if not names:
            raise SteamZeroError("E-CONTENT-KEYS-INCOMPAT", detail="title.keys está vazio")

    def _persist_import(self, pending: _PendingMutation) -> None:
        metadata = pending.metadata
        with self._store_factory() as store:
            store.migrate()
            store.save_platform({"id": "switch", "name": "Nintendo Switch"})
            store.save_firmware_key_item(
                {
                    "id": ids.new_ulid(),
                    "kind": pending.kind,
                    "platform_id": "switch",
                    "hash_truncated": str(metadata["digest"])[:12],
                    "state": "present",
                    "keyset": "prod" if pending.kind == "key" else None,
                    "revision": metadata.get("revision"),
                    "version": metadata.get("version"),
                    "relpath": metadata["relpath"],
                    "last_validated": datetime.now(UTC).isoformat(),
                }
            )

    def _persist_bios_import(self, pending: _PendingMutation) -> None:
        """Registra a BIOS no state (hash completo é dado persistido, não log)."""
        metadata = pending.metadata
        platform_id = str(metadata["platform"])
        try:
            platform_name = PlatformRegistry.bundled().get(platform_id).name
        except KeyError:
            platform_name = platform_id
        with self._store_factory() as store:
            store.migrate()
            store.save_platform({"id": platform_id, "name": platform_name})
            store.save_bios_item(
                {
                    "id": ids.new_ulid(),
                    "platform_id": platform_id,
                    "relpath": f"{platform_id}/{metadata['name']}",
                    "hash": str(metadata["digest"]),
                    "region": None,
                    "version": None,
                    "state": "present",
                    "last_validated": datetime.now(UTC).isoformat(),
                }
            )

    def _persist_extra(self, pending: _PendingMutation) -> None:
        metadata = pending.metadata
        with self._store_factory() as store:
            store.migrate()
            mods = StateStoreModsAdapter(store.adapter_connection())
            cheats = StateStoreCheatsAdapter(store.adapter_connection())
            if pending.kind in {"mod-install", "cheat-install"}:
                game = self._current_game(str(metadata["gameId"]))
                store.save_platform({"id": "switch", "name": "Nintendo Switch"})
                store.save_game(
                    {
                        "id": str(game["id"]),
                        "platform_id": "switch",
                        "title": str(game["name"]),
                        "canonical_path_id": str(game["path"]),
                        "state": "ready",
                    }
                )
            if pending.kind == "mod-install":
                mods.save_installed_mod(
                    InstalledMod(
                        id=str(metadata["id"]),
                        game_id=str(metadata["gameId"]),
                        catalog_id=(
                            str(metadata["catalogId"])
                            if metadata.get("catalogId") is not None
                            else None
                        ),
                        title_id=str(metadata["titleId"]),
                        build_id=(
                            str(metadata["buildId"])
                            if metadata.get("buildId") is not None
                            else None
                        ),
                        name=str(metadata["name"]),
                        mod_type=ModType(str(metadata.get("modType") or "other")),
                        source=str(metadata.get("source") or "local-user"),
                        version=(
                            str(metadata["version"])
                            if metadata.get("version") is not None
                            else None
                        ),
                        state="active",
                        install_path=str(metadata["installPath"]),
                        emulator_id=str(metadata["emulatorId"]),
                    )
                )
            elif pending.kind == "cheat-install":
                cheats.save_installed_cheat(
                    InstalledCheat(
                        id=str(metadata["id"]),
                        game_id=str(metadata["gameId"]),
                        title_id=str(metadata["titleId"]),
                        build_id=str(metadata["buildId"]),
                        name=str(metadata["name"]),
                        cheat_type=CheatType(str(metadata.get("cheatType") or "other")),
                        source=str(metadata.get("source") or "local-user"),
                        version=(
                            str(metadata["version"])
                            if metadata.get("version") is not None
                            else None
                        ),
                        state="active",
                        install_path=str(metadata["installPath"]),
                        emulator_id=str(metadata["emulatorId"]),
                        code_count=int(metadata["codeCount"]),
                        enabled=True,
                    )
                )
            elif pending.kind == "mod-state":
                mods.update_location_state(
                    str(metadata["id"]), str(metadata["state"]), str(metadata["installPath"])
                )
            elif pending.kind == "cheat-state":
                cheats.update_location_state(
                    str(metadata["id"]),
                    str(metadata["state"]),
                    str(metadata["installPath"]),
                    enabled=bool(metadata["enabled"]),
                )
            elif pending.kind == "mod-remove":
                mods.remove_installed_mod(str(metadata["id"]))
            elif pending.kind == "cheat-remove":
                cheats.remove_installed_cheat(str(metadata["id"]))

    # --- Job handler para busca de mídia (executado via JobManager) ---

    def _library_scan_job_handler(self, _job: Job, ctx: JobContext) -> dict[str, Any]:
        return self._scan_library_now(ctx)

    def _bitrot_job_handler(self, job: Job, ctx: JobContext) -> dict[str, Any]:
        return self._bitrot.verify_sample(
            self._bitrot_targets(),
            max_files=int(job.params.get("max_files", 8)),
            max_bytes=int(job.params.get("max_bytes", 2 * 1024**3)),
            max_seconds=float(job.params.get("max_seconds", 20)),
            safepoint=ctx.safepoint,
            progress=lambda current, total, item: ctx.set_progress(
                "rehash",
                current=current,
                total=total,
                unit="files",
                current_item=item or None,
            ),
        )

    def _bitrot_targets(self) -> list[BitrotTarget]:
        games, _unidentified = self._load_library_cache()
        targets: list[BitrotTarget] = []
        for game in games:
            game_id = game.get("id")
            title = game.get("name")
            raw_path = game.get("path")
            size = game.get("size")
            if (
                not isinstance(game_id, str)
                or not isinstance(title, str)
                or not isinstance(raw_path, str)
                or not isinstance(size, int)
                or size < 0
            ):
                continue
            targets.append(
                BitrotTarget(
                    asset_id=f"emulation:{game_id}",
                    title=title,
                    platform_id=str(game.get("platformId") or "switch"),
                    path=Path(raw_path),
                    size=size,
                )
            )
        return targets

    @staticmethod
    def _completed_operation_job_handler(job: Job, ctx: JobContext) -> dict[str, Any]:
        ctx.set_progress("commit", current=1, total=1, unit="operation")
        return {"operationId": job.params.get("operation_id")}

    def _extra_catalog_search_job_handler(self, job: Job, ctx: JobContext) -> dict[str, Any]:
        game_id = str(job.params.get("game_id") or "")
        title_id = str(job.params.get("title_id") or "")
        if not game_id or _TITLE_ID.fullmatch(title_id) is None:
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail="job de catálogo requer jogo e Title ID válidos",
            )
        errors: dict[str, str] = {}
        ctx.set_progress("mods", current=0, total=2, unit="catalogs")
        with self._store_factory() as store:
            store.migrate()
            mod_store = StateStoreModsAdapter(store.adapter_connection())
            cheat_store = StateStoreCheatsAdapter(store.adapter_connection())
            mod_manager = SwitchModManager(
                self._mod_catalog,
                FilesystemModInstaller(
                    Path.home() / ".local" / "share",
                    config_home=Path.home() / ".config",
                ),
                BuildIdScanner(),
                mod_store,
            )
            cheat_manager = SwitchCheatManager(
                self._cheat_catalog,
                FsCheatInstaller(
                    Path.home() / ".local" / "share",
                    config_home=Path.home() / ".config",
                ),
                cheat_store,
            )
            try:
                mods = mod_manager.list_candidates(title_id)
            except SteamZeroError as exc:
                mods = []
                errors["mods"] = exc.code
            except Exception:
                mods = []
                errors["mods"] = "E-MOD-SOURCE-UNREACHABLE"
            if mods:
                mod_store.replace_catalog(title_id, mods)
            cached_mods = mod_store.list_catalog(title_id)
            ctx.safepoint()
            ctx.set_progress("cheats", current=1, total=2, unit="catalogs")
            try:
                cheats = cheat_manager.list_candidates(title_id)
            except SteamZeroError as exc:
                cheats = []
                errors["cheats"] = exc.code
            except Exception:
                cheats = []
                errors["cheats"] = "E-CHEAT-SOURCE-UNREACHABLE"
            if cheats:
                cheat_store.replace_catalog(title_id, cheats)
            cached_cheats = cheat_store.list_catalog(title_id)
        ctx.set_progress("done", current=2, total=2, unit="catalogs")
        return {
            "game_id": game_id,
            "title_id": title_id,
            "mods_found": len(mods),
            "cheats_found": len(cheats),
            "mods_cached": len(cached_mods),
            "cheats_cached": len(cached_cheats),
            "errors": errors,
        }

    def _mod_catalog_prepare_job_handler(self, job: Job, ctx: JobContext) -> dict[str, Any]:
        catalog_id = str(job.params.get("catalog_id") or "")
        title_id = str(job.params.get("title_id") or "")
        candidate = self._catalog_mod_candidate(catalog_id, title_id)
        url = candidate.identity.source_url
        if not self._remote_mod_url_supported(url):
            raise SteamZeroError(
                "E-MOD-DOWNLOAD-FAILED",
                detail="a fonte não publicou um arquivo de mod suportado",
            )
        ctx.set_progress("download", current=0, total=1, unit="package")
        try:
            payload = fetch_bytes(
                url,
                max_bytes=64 * 1024**2,
                timeout_seconds=30,
                headers={"User-Agent": "SteamZero/0.1"},
                allowed_redirect_hosts={
                    "github.com",
                    "objects.githubusercontent.com",
                    "raw.githubusercontent.com",
                },
            )
        except NetworkFailure as exc:
            raise SteamZeroError(
                "E-MOD-DOWNLOAD-FAILED",
                detail=exc.code,
            ) from exc
        ctx.safepoint()
        digest = hashlib.sha256(payload).hexdigest()
        existing = self._prepared_mod_package(catalog_id)
        if existing is not None and existing[0].get("contentSha256") == digest:
            ctx.set_progress("done", current=1, total=1, unit="package")
            return {
                "catalog_id": catalog_id,
                "content_sha256": digest,
                "file_count": len(existing[1]),
                "cached": True,
            }

        parsed = urlsplit(url)
        suffix = Path(unquote(parsed.path)).suffix.casefold()
        extraction_id = f"{job.id}-mod"
        package_id = f"{job.id}-package"
        extracted: list[Path] = []
        try:
            if suffix == ".zip":
                package = fs.stage_bytes(package_id, "package.zip", payload)
                extracted = safezip.extract_safe(
                    package,
                    extraction_id,
                    limits=safezip.SafeZipLimits(
                        max_entries=_MAX_IMPORT_FILES,
                        max_total_bytes=_MAX_MOD_BYTES,
                        max_entry_bytes=_MAX_MOD_BYTES,
                        max_depth=16,
                        max_ratio=200,
                    ),
                )
            else:
                filename = self._safe_extra_name(Path(unquote(parsed.path)).name)
                if Path(filename).suffix.casefold() not in _REMOTE_MOD_SUFFIXES:
                    raise SteamZeroError(
                        "E-MOD-DOWNLOAD-FAILED",
                        detail="extensão do arquivo remoto não é suportada",
                    )
                extracted = [fs.stage_bytes(extraction_id, filename, payload)]
            if not extracted:
                raise SteamZeroError(
                    "E-MOD-INSTALL-FAILED",
                    detail="pacote remoto não contém arquivos",
                )
            source_root = Path(os.path.commonpath([str(source.parent) for source in extracted]))
            total = sum(source.stat().st_size for source in extracted)
            if len(extracted) > _MAX_IMPORT_FILES or total > _MAX_MOD_BYTES:
                raise SteamZeroError(
                    "E-MOD-INSTALL-FAILED",
                    detail="pacote remoto excede os limites de segurança",
                )
            cache_root = self._mod_package_root(catalog_id) / digest
            tree = cache_root / "tree"
            manifest_files: list[dict[str, object]] = []
            ctx.set_progress("inspect", current=0, total=len(extracted), unit="files")
            for index, source in enumerate(extracted):
                ctx.safepoint()
                relative = source.relative_to(source_root)
                target = tree / relative
                fs.copy_file_atomic(source, target)
                manifest_files.append(
                    {
                        "path": relative.as_posix(),
                        "size": target.stat().st_size,
                        "sha256": fs.hash_file(target, algo="sha256"),
                    }
                )
                ctx.set_progress(
                    "inspect",
                    current=index + 1,
                    total=len(extracted),
                    unit="files",
                    current_item=relative.as_posix(),
                )
            manifest = {
                "schemaVersion": 1,
                "catalogId": catalog_id,
                "titleId": title_id,
                "contentSha256": digest,
                "source": candidate.identity.source,
                "preparedAt": datetime.now(UTC).isoformat(),
                "files": manifest_files,
            }
            fs.write_atomic_text(
                cache_root / "manifest.json",
                json.dumps(
                    manifest,
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
        finally:
            fs.remove_tree(paths.staging_for(extraction_id))
            fs.remove_tree(paths.staging_for(package_id))
        ctx.set_progress("done", current=1, total=1, unit="package")
        return {
            "catalog_id": catalog_id,
            "content_sha256": digest,
            "file_count": len(extracted),
            "cached": False,
        }

    def _get_provider_api_key(self, provider_name: str) -> str | None:
        secret = self._secret_store.retrieve(provider_name, "api_key")
        return secret.reveal() if secret is not None else None

    def _get_provider_credentials(self, provider_name: str) -> dict[str, str]:
        definition = provider_by_id(provider_name)
        result: dict[str, str] = {}
        for field in definition.credential_fields:
            secret = self._secret_store.retrieve(provider_name, field.id)
            if secret is not None:
                result[field.id] = secret.reveal()
        return result

    def _media_search_job_handler(self, job: Job, ctx: JobContext) -> dict[str, Any]:
        with self._store_factory() as store:
            store.migrate()
            return self._execute_media_search(store, job, ctx)

    def _execute_media_search(
        self,
        store: StateStore,
        job: Job,
        ctx: JobContext,
        *,
        skip_providers: set[str] | None = None,
    ) -> dict[str, Any]:
        mgr = self._media_manager(store)
        health = StateStoreProviderHealthAdapter(store.adapter_connection())
        params = job.params
        game_id = params["game_id"]
        title_id = params["title_id"]
        title = params["title"]
        platform_slug = str(params.get("platform_slug") or "switch")
        media_kinds = params.get("media_kinds")
        kinds = media_kinds or [
            "grid",
            "hero",
            "logo",
            "icon",
            "boxart",
            "screenshot",
            "manual",
        ]
        if not isinstance(kinds, list) or not all(isinstance(kind, str) for kind in kinds):
            raise SteamZeroError("E-API-SCHEMA", detail="mediaKinds precisa ser lista de strings")
        state = mgr._store.load(game_id) or GameMediaState(
            game_id=game_id,
            title_id=title_id,
            title=title,
        )
        local_source = str(params.get("local_media_source") or state.media_source or "fallback")
        local_url = str(params.get("local_media_url") or "")
        if local_source != "fallback":
            state.media_source = local_source
        state.metadata_state = "searching"
        mgr._store.save(state)
        identity = GameIdentity(
            game_id=game_id,
            title=title,
            platform_slug=platform_slug,
            title_id=title_id,
        )
        all_candidates: list[MediaCandidate] = []
        provider_errors: dict[str, str] = {}
        providers = self._ordered_media_providers(mgr._providers, kinds)
        if skip_providers:
            providers = [p for p in providers if p.name not in skip_providers]
        total_providers = len(providers)
        ctx.set_progress("search", current=0, total=total_providers, unit="providers")
        for idx, provider_item in enumerate(providers):
            ctx.safepoint()
            supported_kinds = [kind for kind in kinds if kind in provider_item.supported_kinds()]
            try:
                results = self._search_provider_with_retry(
                    provider_item,
                    identity,
                    supported_kinds,
                    ctx,
                )
                all_candidates.extend(results)
                health.record_success(provider_item.name)
            except SteamZeroError as exc:
                provider_errors[provider_item.name] = exc.code
                health.record_failure(provider_item.name, error_code=exc.code)
            except Exception:
                provider_errors[provider_item.name] = "E-SCRAPE-PROVIDER-UNREACHABLE"
                health.record_failure(
                    provider_item.name,
                    error_code="E-SCRAPE-PROVIDER-UNREACHABLE",
                )
            ctx.set_progress(
                "search",
                current=idx + 1,
                total=total_providers,
                unit="providers",
                current_item=provider_item.name,
            )
        all_candidates.sort(key=lambda c: (-c.confidence, c.media_kind))
        candidates_data = [
            {
                "url": c.url,
                "mediaKind": c.media_kind,
                "provider": c.provider,
                "confidence": c.confidence,
                "width": c.width,
                "height": c.height,
                "region": c.region,
                "license": c.license,
                "attribution": c.attribution,
            }
            for c in all_candidates
        ]
        state.candidates = candidates_data
        state.candidate_count = len(candidates_data)
        if provider_errors:
            state.errors = provider_errors
        else:
            state.errors = {}
            state.reason = ""
        if candidates_data:
            state.metadata_state = "candidates-found"
            state.reason = (
                f"mídia local preservada: {local_source}"
                if local_source != "fallback" or local_url
                else ""
            )
        elif provider_errors or not providers:
            state.metadata_state = "degraded"
            if not providers:
                if skip_providers:
                    state.reason = (
                        "Providers interrompidos por quota nesta execução; mídia "
                        "local/cache e ícone seguro da plataforma foram preservados."
                    )
                else:
                    state.reason = (
                        "Nenhum provider remoto configurado; mídia local/cache e "
                        "ícone seguro da plataforma foram preservados."
                    )
            else:
                state.reason = (
                    "Providers remotos falharam; mídia local/cache e fallback "
                    "continuam disponíveis."
                )
        else:
            state.metadata_state = "no-results"
            state.reason = (
                "Nenhum resultado remoto; mídia local/cache e fallback foram preservados."
            )
        state.checked_at = datetime.now(UTC).isoformat()
        state.selected_candidate_idx = -1
        mgr._store.save(state)
        ctx.set_progress(
            "done",
            current=len(candidates_data),
            total=len(candidates_data),
            unit="candidates",
        )
        return {
            "candidate_count": len(candidates_data),
            "provider_errors": provider_errors,
            "remote_state": state.metadata_state,
            "fallback_source": local_source if local_source != "fallback" else "platform-icon",
        }

    @staticmethod
    def _ordered_media_providers(
        providers: Sequence[MediaProviderPort], media_kinds: Sequence[str]
    ) -> list[MediaProviderPort]:
        registry = ProviderRegistry()
        for provider in providers:
            registry.register(provider)
        ordered: list[MediaProviderPort] = []
        seen: set[str] = set()
        for kind in media_kinds:
            for provider in registry.providers_for_kind(kind):
                if provider.name not in seen:
                    seen.add(provider.name)
                    ordered.append(provider)
        return ordered

    def _search_provider_with_retry(
        self,
        provider: MediaProviderPort,
        identity: GameIdentity,
        media_kinds: list[str],
        ctx: JobContext,
    ) -> list[MediaCandidate]:
        for attempt in range(3):
            ctx.safepoint()
            try:
                return provider.search(identity, media_kinds)
            except SteamZeroError as exc:
                if exc.code not in _RETRYABLE_SCRAPE_ERRORS or attempt == 2:
                    raise
                ctx.checkpoint(
                    {
                        "provider": provider.name,
                        "attempt": attempt + 1,
                        "errorCode": exc.code,
                    }
                )
                self._media_retry_delay(0.25 * (2**attempt))
        return []

    def _media_global_job_handler(self, job: Job, ctx: JobContext) -> dict[str, Any]:
        mode = str(job.params.get("mode") or "")
        overwrite = job.params.get("overwrite") is True
        if mode not in {"audit", "search-missing", "refresh", "overwrite", "optimize"}:
            raise SteamZeroError("E-API-SCHEMA", detail="modo global de mídia inválido")
        if mode == "overwrite" and not overwrite:
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail="job de sobrescrita requer overwrite=true",
            )
        if mode == "audit":
            with self._store_factory() as store:
                store.migrate()
                report = self._media_manager(store).audit().to_dict()
            checked_at = datetime.now(UTC).isoformat()
            fs.write_atomic_text(
                self._media_audit_path,
                json.dumps(
                    {"schemaVersion": 1, "checkedAt": checked_at, "report": report},
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
            ctx.set_progress("done", current=1, total=1, unit="audit")
            return {"mode": mode, "checked_at": checked_at, "report": report}

        games, _unidentified = self._load_library_cache()
        total = len(games)
        processed = 0
        skipped = 0
        updated = 0
        failures = 0
        no_candidates = 0
        provider_errors: dict[str, str] = {}
        provider_details: dict[str, dict[str, Any]] = {}
        interrupted_providers: set[str] = set()
        ctx.set_progress("games", current=0, total=total, unit="games")
        with self._store_factory() as store:
            store.migrate()
            manager = self._media_manager(store)
            for index, game in enumerate(games):
                ctx.safepoint()
                game_id = str(game.get("id") or "")
                title_id = str(game.get("titleId") or "")
                title = str(game.get("name") or title_id or game_id)
                existing = manager._store.load(game_id)
                local_url = str(game.get("coverUrl") or "")
                if mode == "search-missing" and (
                    (existing is not None and bool(existing.media_path)) or bool(local_url)
                ):
                    skipped += 1
                elif mode == "optimize":
                    if existing is None or existing.master_state == "none":
                        skipped += 1
                    else:
                        result = manager.optimize_game(game_id)
                        updated += int(result.success)
                        failures += int(not result.success)
                        processed += 1
                else:
                    search_job = Job(
                        id=job.id,
                        type="media.search",
                        priority=job.priority,
                        state="running",
                        params={
                            "game_id": game_id,
                            "title_id": title_id,
                            "title": title,
                            "platform_slug": str(game.get("platform") or "switch"),
                            "media_kinds": None,
                            "local_media_source": str(game.get("mediaSource") or "fallback"),
                            "local_media_url": local_url,
                        },
                    )
                    search_result = self._execute_media_search(
                        store,
                        search_job,
                        ctx,
                        skip_providers=interrupted_providers,
                    )
                    for provider, code in search_result["provider_errors"].items():
                        provider_errors[str(provider)] = str(code)
                        details = provider_details.setdefault(
                            str(provider), {"code": str(code), "gamesAffected": 0}
                        )
                        details["code"] = str(code)
                        details["gamesAffected"] = int(details["gamesAffected"]) + 1
                        if code == "E-SCRAPE-QUOTA-EXCEEDED":
                            interrupted_providers.add(str(provider))
                    if (
                        int(search_result["candidate_count"]) == 0
                        and not search_result["provider_errors"]
                    ):
                        no_candidates += 1
                    processed += 1
                    if overwrite and int(search_result["candidate_count"]) > 0:
                        selected = manager.select_candidate(game_id, 0)
                        applied = (
                            manager.apply_selected_candidate(
                                game_id=game_id,
                                title_id=title_id,
                                fingerprint=str(game.get("fingerprint") or ""),
                                canonical_name=title,
                            )
                            if selected is not None
                            else None
                        )
                        if applied is not None:
                            manager.optimize_game(game_id)
                            updated += 1
                        else:
                            failures += 1
                ctx.checkpoint(
                    {
                        "gameId": game_id,
                        "index": index + 1,
                        "mode": mode,
                        "overwrite": overwrite,
                    }
                )
                ctx.set_progress(
                    "games",
                    current=index + 1,
                    total=total,
                    unit="games",
                    current_item=title,
                )
        outcome = "degraded" if provider_errors else "partial" if no_candidates else "success"
        return {
            "mode": mode,
            "overwrite": overwrite,
            "outcome": outcome,
            "total": total,
            "processed": processed,
            "skipped": skipped,
            "updated": updated,
            "failures": failures,
            "no_candidates": no_candidates,
            "provider_errors": provider_errors,
            "provider_details": {
                provider: {
                    "code": str(details["code"]),
                    "category": provider_error_category(str(details["code"])),
                    "gamesAffected": int(details["gamesAffected"]),
                }
                for provider, details in provider_details.items()
            },
            "interrupted_providers": sorted(interrupted_providers),
        }

    @staticmethod
    def _rom_scan_job_handler(job: Job, ctx: JobContext) -> dict[str, Any]:
        from steamzero.adapters.discovery.root_scanner import RomRootScanner

        roots = job.params.get("roots", [])
        scanner = RomRootScanner()
        all_results: dict[str, list[dict[str, Any]]] = {}
        total = len(roots)
        for idx, root_str in enumerate(roots):
            ctx.safepoint()
            root = Path(root_str)
            ctx.set_progress("scan", current=idx, total=total, unit="roots", current_item=root.name)
            results = scanner.discover_recursive(root)
            all_results[root_str] = [
                {
                    "path": str(r.path),
                    "fmt": r.fmt,
                    "titleId": r.title_id,
                    "contentKind": r.content_kind,
                    "sizeBytes": r.size_bytes,
                    "parentTitleId": r.parent_title_id,
                    "version": r.version,
                }
                for r in results
            ]
            ctx.set_progress(
                "scan",
                current=idx + 1,
                total=total,
                unit="roots",
                current_item=root.name,
            )
        ctx.set_progress("done", current=total, total=total, unit="roots")
        return {"roots_scanned": total, "total_files": sum(len(v) for v in all_results.values())}

    # --- Media apply helpers (executados em apply_action) ---

    def _with_store_and_media(self, fn: Callable[[Any, GameMediaManager], object]) -> object:
        with self._store_factory() as store:
            store.migrate()
            mgr = self._media_manager(store)
            return fn(store, mgr)

    def _apply_media_import(self, pending: _PendingMutation) -> None:
        meta = pending.metadata
        self._with_store_and_media(
            lambda s, mgr: mgr.import_custom_media(
                game_id=meta["game_id"],
                src_path=Path(meta["src_path"]),
                title_id=meta["title_id"],
                fingerprint=meta["fingerprint"],
                canonical_name=meta["canonical_name"],
            )
        )

    def _apply_media_select(self, pending: _PendingMutation) -> None:
        meta = pending.metadata
        with self._store_factory() as store:
            store.migrate()
            manager = self._media_manager(store)
            selected = manager.select_candidate(meta["game_id"], meta["candidate_idx"])
            if selected is None:
                raise SteamZeroError("E-TX-STALE-PLAN", detail="candidato de mídia expirou")
            applied = manager.apply_selected_candidate(
                game_id=meta["game_id"],
                title_id=meta["title_id"],
                fingerprint=meta["fingerprint"],
                canonical_name=meta["canonical_name"],
            )
            if applied is None:
                raise SteamZeroError(
                    "E-SCRAPE-DOWNLOAD-FAILED", detail="não foi possível persistir a arte"
                )
            manager.optimize_game(meta["game_id"])

    def _apply_media_clear(self, pending: _PendingMutation) -> None:
        self._with_store_and_media(lambda s, mgr: mgr.clear_media(pending.metadata["game_id"]))

    def _apply_media_publish_steam(self, pending: _PendingMutation) -> None:
        meta = pending.metadata
        self._with_store_and_media(
            lambda _store, manager: manager.refresh_steam_publication(
                meta["game_id"],
                meta["steam_app_id"],
                grid_dir=Path(meta["grid_dir"]),
            )
        )

    def _apply_media_unpublish_steam(self, pending: _PendingMutation) -> None:
        meta = pending.metadata
        self._with_store_and_media(
            lambda _store, manager: manager.refresh_steam_publication(
                meta["game_id"],
                meta["steam_app_id"],
                grid_dir=Path(meta["grid_dir"]),
            )
        )

    def _steam_media_context(self, game_id: str, account_id: str) -> tuple[int, Path]:
        game = self._current_game(game_id)
        settings = self._load_game_settings(strict=True)
        if self._settings_for_game(game, settings).get("steamSelected") is not True:
            raise SteamZeroError("E-API-SCHEMA", detail="jogo não está marcado para Steam")
        if game_id not in self._shortcuts.managed_game_ids():
            raise SteamZeroError("E-API-SCHEMA", detail="shortcut não foi sincronizado")
        app_id = self._shortcuts.resolve_app_id(game_id)
        if app_id is None:
            raise SteamZeroError("E-API-SCHEMA", detail="AppID não confirmado")
        return app_id, self._shortcuts.media_grid_dir(account_id)

    def _open_media_cache(self) -> dict[str, object]:
        root = paths.media_dir()
        try:
            resolved = root.resolve(strict=True)
            data_root = paths.data_home().resolve(strict=True)
        except OSError as exc:
            raise SteamZeroError(
                "E-DESKTOP-VERIFY",
                detail="a pasta do cache de mídia ainda não existe",
            ) from exc
        if root.is_symlink() or not resolved.is_dir() or not resolved.is_relative_to(data_root):
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-PATH",
                detail="pasta de mídia fora da raiz gerenciada",
            )
        executable = self._which("xdg-open")
        if executable is None:
            raise SteamZeroError("E-DESKTOP-VERIFY", detail="xdg-open indisponível")
        try:
            self._spawn((executable, str(resolved)))
        except Exception as exc:
            raise SteamZeroError(
                "E-DESKTOP-VERIFY",
                detail="não foi possível abrir a pasta do cache",
            ) from exc
        return {"opened": True, "target": "media-cache"}

    def _custom_roots(self) -> list[Path]:
        roots, _excluded = self._root_config()
        return roots

    def _root_config(self) -> tuple[list[Path], set[Path]]:
        if not self._roots_path.is_file() or self._roots_path.is_symlink():
            return [], set()
        try:
            data = json.loads(self._roots_path.read_text(encoding="utf-8"))
            if data.get("schemaVersion") != 1 or not isinstance(data.get("roots"), list):
                return [], set()
            roots = [
                Path(value)
                for value in data["roots"]
                if isinstance(value, str) and Path(value).is_absolute()
            ]
            raw_excluded = data.get("excludedRoots", [])
            excluded = {
                Path(value).resolve(strict=False)
                for value in raw_excluded
                if isinstance(value, str) and Path(value).is_absolute()
            }
            return roots, excluded
        except (OSError, json.JSONDecodeError, AttributeError):
            return [], set()

    def _root_from_action(self, action: str, *, require_accessible: bool = True) -> Path:
        candidate_id = action.rsplit(":", 1)[-1]
        if re.fullmatch(r"[0-9a-f]{24}", candidate_id) is None:
            raise SteamZeroError("E-API-SCHEMA", detail="identificador de raiz inválido")
        for candidate in self.registered_library_roots():
            if root_id(candidate) != candidate_id:
                continue
            if require_accessible:
                return validate_rom_root(candidate)
            return candidate.absolute()
        raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="raiz não registrada")

    def _open_library_root(self, selected: Path) -> dict[str, object]:
        registered = self._root_from_action(f"library.root.open:{root_id(selected)}")
        resolved = validate_rom_root(registered)
        executable = self._which("xdg-open")
        if executable is None:
            raise SteamZeroError("E-DESKTOP-VERIFY", detail="xdg-open indisponível")
        try:
            self._spawn((executable, str(resolved)))
        except Exception as exc:
            raise SteamZeroError(
                "E-DESKTOP-VERIFY",
                detail="não foi possível abrir a raiz registrada",
            ) from exc
        return {"opened": True, "target": "library-root", "rootId": root_id(resolved)}

    @staticmethod
    def _new_copy_targets(
        source: Path, targets: Sequence[Path], digest: str
    ) -> list[tuple[Path, Path]]:
        copies: list[tuple[Path, Path]] = []
        seen: set[Path] = set()
        for target in targets:
            if target in seen:
                continue
            seen.add(target)
            if not target.exists() and not target.is_symlink():
                copies.append((source, target))
                continue
            if (
                target.is_symlink()
                or not target.is_file()
                or fs.hash_file(target, algo="sha256") != digest
            ):
                raise SteamZeroError(
                    "E-CONTENT-FW-INCOMPAT",
                    detail=f"arquivo existente diverge: {target}",
                )
        return copies

    @staticmethod
    def _compatible_root(targets: Mapping[Path, bytes]) -> Path:
        """Usa a home apenas quando todos os alvos pertencem a ela.

        Testes podem redirecionar XDG para um diretório temporário; nesse caso
        as projeções para consumidores externos são omitidas, sem ampliar a raiz
        transacional para ``/``.
        """
        home = Path.home().resolve()
        if targets and all(target.is_relative_to(home) for target in targets):
            return home
        config_home = paths.config_home().resolve()
        if targets and all(target.is_relative_to(config_home) for target in targets):
            return config_home
        return paths.data_home().resolve()

    @staticmethod
    def _key_projection_targets() -> tuple[Path, ...]:
        home = Path.home()
        return (
            home / ".switch" / "prod.keys",
            home / ".local" / "share" / "eden" / "keys" / "prod.keys",
            home / ".local" / "share" / "citron" / "keys" / "prod.keys",
            home / ".config" / "citron" / "keys" / "prod.keys",
            home / ".config" / "Ryujinx" / "system" / "prod.keys",
            home / "Ryujinx" / "system" / "prod.keys",
        )

    @staticmethod
    def _title_key_projection_targets() -> tuple[Path, ...]:
        home = Path.home()
        return (
            home / ".switch" / "title.keys",
            home / ".local/share/eden/keys/title.keys",
            home / ".local/share/citron/keys/title.keys",
            home / ".config/citron/keys/title.keys",
            home / ".config/Ryujinx/system/title.keys",
            home / "Ryujinx/system/title.keys",
        )

    @staticmethod
    def _emulator_key_targets(emulator_id: str) -> tuple[Path, ...]:
        home = Path.home()
        return {
            "eden": (home / ".local/share/eden/keys/prod.keys",),
            "citron": (
                home / ".local/share/citron/keys/prod.keys",
                home / ".config/citron/keys/prod.keys",
            ),
            "ryubing": (
                home / ".config/Ryujinx/system/prod.keys",
                home / "Ryujinx/system/prod.keys",
            ),
        }.get(emulator_id, ())

    @staticmethod
    def _emulator_title_key_targets(emulator_id: str) -> tuple[Path, ...]:
        home = Path.home()
        return {
            "eden": (home / ".local/share/eden/keys/title.keys",),
            "citron": (
                home / ".local/share/citron/keys/title.keys",
                home / ".config/citron/keys/title.keys",
            ),
            "ryubing": (
                home / ".config/Ryujinx/system/title.keys",
                home / "Ryujinx/system/title.keys",
            ),
        }.get(emulator_id, ())

    @staticmethod
    def _emulator_bios_targets(adapter_id: str) -> tuple[Path, ...]:
        home = Path.home()
        return {
            "retroarch": (home / ".config/retroarch/system",),
            "duckstation": (home / ".config/duckstation/bios",),
            "pcsx2": (home / ".config/PCSX2/bios",),
            "melonds": (home / ".config/melonDS/bios",),
        }.get(adapter_id, ())

    def _bios_projection_copies(self, platform_id: str, adapter_id: str) -> list[tuple[Path, Path]]:
        """Projeta as BIOS do store central aos diretórios reais dos emuladores.

        Cada BIOS declarada no perfil de lançamento é copiada do store central
        (``bios_dir/<plataforma>/<nome>``) para os diretórios de BIOS de todos
        os consumidores gerenciados do emulador. Alvos idênticos já presentes
        são mantidos; divergências bloqueiam para nunca sobrescrever dados
        externos.
        """
        profile = self._launch_profile_for(platform_id, adapter_id)
        if profile is None or not profile.requires_bios:
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail=f"{platform_id} · {adapter_id} não declara BIOS para projetar",
            )
        targets = self._emulator_bios_targets(adapter_id)
        if not targets:
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail=f"{adapter_id} não possui diretório de BIOS gerenciado",
            )
        copies: list[tuple[Path, Path]] = []
        for name in profile.requires_bios:
            source = paths.bios_dir() / platform_id / name
            if source.is_symlink() or not source.is_file():
                raise SteamZeroError(
                    "E-CONTENT-BIOS-MISSING",
                    detail=f"importe a BIOS '{name}' de {platform_id} antes de projetar",
                )
            digest = fs.hash_file(source, algo="sha256")
            copies.extend(
                self._new_copy_targets(source, [target / name for target in targets], digest)
            )
        return copies

    def _key_projection_copies(self, emulator_id: str) -> list[tuple[Path, Path]]:
        """Projeta as keys centrais ao consumidor escolhido no mesmo plano.

        A preferência do jogo e os arquivos requeridos são confirmados juntos;
        assim o botão Jogar nunca depende de uma segunda jornada manual. Alvos
        divergentes continuam bloqueados para não sobrescrever dados externos.
        """
        try:
            source = self._current_key_source()
        except SteamZeroError:
            return []
        digest = fs.hash_file(source, algo="sha256")
        copies = self._new_copy_targets(source, self._emulator_key_targets(emulator_id), digest)
        title_source = self._current_title_key_source()
        if title_source is not None:
            title_digest = fs.hash_file(title_source, algo="sha256")
            copies.extend(
                self._new_copy_targets(
                    title_source,
                    self._emulator_title_key_targets(emulator_id),
                    title_digest,
                )
            )
        return copies

    def _firmware_projection_copies(self, emulator_ids: Sequence[str]) -> list[tuple[Path, Path]]:
        """Recupera o firmware central para os diretórios reais dos consumidores."""
        with self._store_factory() as store:
            store.migrate()
            rows = store.list_firmware_key_items("switch", kind="firmware")
        ranked = sorted(
            rows,
            key=lambda row: (
                self._version_tuple(str(row.get("version") or "0")),
                str(row.get("last_validated") or ""),
            ),
            reverse=True,
        )
        if not ranked or not isinstance(ranked[0].get("relpath"), str):
            return []
        root = paths.firmware_dir() / str(ranked[0]["relpath"])
        try:
            sources = [
                source
                for source in root.glob("*.nca")
                if source.is_file() and not source.is_symlink()
            ]
        except OSError:
            return []
        copies: list[tuple[Path, Path]] = []
        for source in sources:
            digest = fs.hash_file(source, algo="sha256")
            targets: list[Path] = []
            for emulator_id in emulator_ids:
                targets.extend(self._emulator_firmware_targets(emulator_id, digest))
            copies.extend(self._new_copy_targets(source, targets, digest))
        return copies

    def _current_key_source(self) -> Path:
        with self._store_factory() as store:
            store.migrate()
            rows = store.list_firmware_key_items("switch", kind="key")
        ranked = sorted(
            rows,
            key=lambda row: (int(row.get("revision") or -1), str(row.get("last_validated") or "")),
            reverse=True,
        )
        for row in ranked:
            relpath = row.get("relpath")
            if not isinstance(relpath, str):
                continue
            candidate = paths.keys_dir() / relpath
            if candidate.is_file() and not candidate.is_symlink():
                return candidate
        raise SteamZeroError(
            "E-CONTENT-KEYS-INCOMPAT",
            detail="a key catalogada não está disponível; importe prod.keys novamente",
        )

    @staticmethod
    def _current_title_key_source() -> Path | None:
        root = paths.keys_dir() / "switch"
        try:
            candidates = [
                path
                for path in root.glob("title-*.keys")
                if path.is_file() and not path.is_symlink()
            ]
            return max(candidates, key=lambda path: path.stat().st_mtime_ns, default=None)
        except OSError:
            return None

    def _key_projection_valid(self, emulator_id: str) -> bool:
        targets = self._emulator_key_targets(emulator_id)
        if not targets:
            # Emulador sem projeção de keys (não-Switch) não exige sincronia.
            return True
        try:
            source = self._current_key_source()
            digest = fs.hash_file(source, algo="sha256")
        except (OSError, SteamZeroError):
            return False
        for target in targets:
            try:
                if target.is_file() and fs.hash_file(target, algo="sha256") == digest:
                    return True
            except OSError:
                continue
        return False

    def _require_key_projection(self, emulator_id: str) -> None:
        if not self._key_projection_valid(emulator_id):
            raise SteamZeroError(
                "E-CONTENT-KEYS-INCOMPAT",
                detail=(
                    f"prod.keys não está sincronizada com {emulator_id}; "
                    "use Sincronizar com emuladores em Keys e firmware"
                ),
            )

    def _appimage_argv(self, payload: Path, *arguments: str) -> tuple[str, ...]:
        """Contorna interceptadores de integração sem depender de diálogo GUI."""
        detected = self._which("appimagelauncher-binfmt-bypass")
        fallback = Path("/usr/lib/appimagelauncher/binfmt-bypass")
        bypass = Path(detected) if detected else fallback
        if detected is None and self._which is not shutil.which:
            return (str(payload), *arguments)
        if bypass.is_file() and not bypass.is_symlink() and os.access(bypass, os.X_OK):
            return (str(bypass), str(payload), *arguments)
        return (str(payload), *arguments)

    @staticmethod
    def _managed_process_groups(payload: Path) -> set[int]:
        """Encontra somente grupos do usuário cujo argv contém o payload exato."""
        expected = os.fsencode(str(payload))
        groups: set[int] = set()
        try:
            entries = tuple(Path("/proc").iterdir())
        except OSError:
            return groups
        for entry in entries:
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            try:
                if entry.stat().st_uid != os.getuid():
                    continue
                argv = (entry / "cmdline").read_bytes().split(b"\0")
                if expected not in argv:
                    continue
                process_group = os.getpgid(pid)
                if process_group > 1:
                    groups.add(process_group)
            except (OSError, ProcessLookupError):
                continue
        return groups

    @staticmethod
    def _firmware_projection_targets(digest: str) -> tuple[Path, ...]:
        targets: list[Path] = []
        for emulator_id in ("eden", "citron", "ryubing"):
            targets.extend(EmulationController._emulator_firmware_targets(emulator_id, digest))
        return tuple(targets)

    @staticmethod
    def _emulator_firmware_targets(emulator_id: str, digest: str) -> tuple[Path, ...]:
        home = Path.home()
        filename = f"{digest}.nca"
        return {
            "eden": (home / ".local/share/eden/nand/system/Contents/registered" / filename,),
            "citron": (home / ".local/share/citron/nand/system/Contents/registered" / filename,),
            "ryubing": (home / ".config/Ryujinx/bis/system/Contents/registered" / filename / "00",),
        }.get(emulator_id, ())

    def _emulator_game_directory_writes(self, roots: Sequence[Path]) -> dict[Path, bytes]:
        home = Path.home()
        if not self._roots_path.is_relative_to(home.resolve()):
            return {}
        writes: dict[Path, bytes] = {}
        for ryubing in (
            home / ".config/Ryujinx/Config.json",
            home / "Ryujinx/Config.json",
        ):
            if ryubing.is_file() and not ryubing.is_symlink():
                try:
                    data = json.loads(ryubing.read_text(encoding="utf-8"))
                    current = data.get("game_dirs", [])
                    if not isinstance(current, list) or not all(
                        isinstance(path, str) for path in current
                    ):
                        raise ValueError("game_dirs inválido")
                    retained = [
                        path
                        for path in current
                        if Path(path).name.casefold() not in {"firmware", "keys"}
                    ]
                    data["game_dirs"] = list(
                        dict.fromkeys([*retained, *(str(root) for root in roots)])
                    )
                    writes[ryubing] = (
                        json.dumps(data, indent=2, ensure_ascii=False).encode() + b"\n"
                    )
                except (OSError, ValueError, json.JSONDecodeError):
                    pass
        for name in ("eden", "citron"):
            config = home / ".config" / name / "qt-config.ini"
            if config.is_file() and not config.is_symlink():
                with suppress(OSError, UnicodeError, ValueError):
                    writes[config] = self._merge_qsettings_game_dirs(
                        config.read_text(encoding="utf-8"), roots
                    ).encode()
        return writes

    def _configured_game_roots(self, *extra: Path) -> tuple[Path, ...]:
        roots = [*(Path(raw) for raw in self.library_roots()), *extra]
        filtered: list[Path] = []
        seen: set[Path] = set()
        for root in roots:
            if root.name.casefold() in {"firmware", "keys"} or root in seen:
                continue
            seen.add(root)
            filtered.append(root)
        return tuple(filtered)

    def _runtime_config_writes(self) -> dict[Path, bytes]:
        """Registra ROMs e desativa verificações interativas no boot."""
        home = Path.home()
        writes = self._emulator_game_directory_writes(self._configured_game_roots())
        for name in ("eden", "citron"):
            config = home / ".config" / name / "qt-config.ini"
            if not config.is_file() or config.is_symlink():
                continue
            try:
                content = writes.get(config, config.read_bytes()).decode("utf-8")
            except (OSError, UnicodeError):
                continue
            updated = re.sub(
                r"(?m)^(check_for_updates_on_start|enable_auto_update_check)(\\default)?=true$",
                r"\1\2=false",
                content,
            )
            writes[config] = updated.encode()
        for ryubing in (
            home / ".config/Ryujinx/Config.json",
            home / "Ryujinx/Config.json",
        ):
            if not ryubing.is_file() or ryubing.is_symlink():
                continue
            try:
                raw = writes.get(ryubing, ryubing.read_bytes())
                data = json.loads(raw.decode("utf-8"))
                data["check_updates_on_start"] = False
                writes[ryubing] = json.dumps(data, indent=2, ensure_ascii=False).encode() + b"\n"
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
                pass
        return writes

    @staticmethod
    def _merge_qsettings_game_dirs(content: str, roots: Sequence[Path]) -> str:
        section = "[UI]"
        start = content.find(section)
        if start < 0:
            raise ValueError("seção UI ausente")
        end = content.find("\n[", start + len(section))
        end = len(content) if end < 0 else end
        before, ui, after = content[:start], content[start:end], content[end:]
        existing = [
            path
            for path in re.findall(r"(?m)^Paths\\gamedirs\\\d+\\path=(.+)$", ui)
            if Path(path).name.casefold() not in {"firmware", "keys"}
        ]
        directories = list(dict.fromkeys([*existing, *(str(root) for root in roots)]))
        lines = [line for line in ui.splitlines() if not line.startswith("Paths\\gamedirs\\")]
        lines.append(f"Paths\\gamedirs\\size={len(directories)}")
        for index, directory in enumerate(directories, start=1):
            lines.extend(
                (
                    f"Paths\\gamedirs\\{index}\\path={directory}",
                    f"Paths\\gamedirs\\{index}\\deep_scan\\default=true",
                    f"Paths\\gamedirs\\{index}\\deep_scan=true",
                    f"Paths\\gamedirs\\{index}\\expanded\\default=true",
                    f"Paths\\gamedirs\\{index}\\expanded=true",
                )
            )
        return before + "\n".join(lines) + after

    def _nsz_conversion(self) -> SwitchRomConversionService:
        executable = self._nsz.executable
        registry = ToolRegistry(
            [nsz_tool_manifest()],
            which=lambda tool_id: (
                str(executable) if tool_id == "nsz" and self._nsz.status()["available"] else None
            ),
        )
        converter = NszConverter(
            which=lambda tool_id: (
                str(executable) if tool_id == "nsz" and self._nsz.status()["available"] else None
            ),
            executable=str(executable),
        )
        return SwitchRomConversionService(registry, converter=converter)

    @property
    def _global_settings_path(self) -> Path:
        return paths.config_home() / "emulation-global-v1.json"

    def _load_global_settings(self) -> dict[str, Any]:
        path = self._global_settings_path
        if not path.is_file() or path.is_symlink():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("schemaVersion") != 1 or not isinstance(data.get("settings"), dict):
                return {}
            parsed: dict[str, Any] = {}
            allowed = {"defaultEmulatorId", "autoPublishSteam", "preferNativeNca"}
            for key in allowed:
                value = data["settings"].get(key)
                if value is not None:
                    if key == "defaultEmulatorId" and not self._known_emulator(value):
                        continue
                    if key in {"autoPublishSteam", "preferNativeNca"} and not isinstance(
                        value, bool
                    ):
                        continue
                    parsed[key] = value
            return parsed
        except (OSError, json.JSONDecodeError):
            return {}

    def _plan_global_setting(self, key: str, value: str | bool | None) -> transaction.Plan:
        settings = self._load_global_settings()
        if value is None:
            settings.pop(key, None)
        else:
            settings[key] = value
        content = json.dumps(
            {"schemaVersion": 1, "settings": settings},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        writes = {self._global_settings_path: content}
        root = self._compatible_root(writes)
        return transaction.plan_write_files(writes, root=root, kind="emulation.global-settings")

    def _load_game_settings(self, *, strict: bool) -> dict[str, dict[str, Any]]:
        path = self._game_settings_path
        if not path.exists():
            return {}
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
                raise ValueError("arquivo ausente, symlink ou grande demais")
            data = json.loads(path.read_text(encoding="utf-8"))
            games = data.get("games")
            if data.get("schemaVersion") != 1 or not isinstance(games, dict):
                raise ValueError("schema inválido")
            parsed: dict[str, dict[str, Any]] = {}
            for game_id, raw in games.items():
                if not isinstance(game_id, str) or not isinstance(raw, dict):
                    raise ValueError("entrada inválida")
                allowed = {"emulatorId", "steamSelected"}
                if set(raw).difference(allowed):
                    raise ValueError("campo desconhecido")
                emulator_id = raw.get("emulatorId")
                selected = raw.get("steamSelected")
                if emulator_id is not None and not self._known_emulator(emulator_id):
                    raise ValueError("emulador inválido")
                if selected is not None and not isinstance(selected, bool):
                    raise ValueError("seleção Steam inválida")
                parsed[game_id] = dict(raw)
            return parsed
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            if strict:
                raise SteamZeroError(
                    "E-STATE-INTEGRITY", detail="preferências por jogo estão corrompidas"
                ) from exc
            return {}

    def _plan_game_setting(
        self,
        game_id: str,
        key: str,
        value: str | bool,
        *,
        key_emulator_id: str | None = None,
    ) -> transaction.Plan:
        settings = self._load_game_settings(strict=True)
        updated = {current: dict(raw) for current, raw in settings.items()}
        updated.setdefault(game_id, {})[key] = value
        content = json.dumps(
            {"schemaVersion": 1, "games": updated},
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        writes = {self._game_settings_path: content}
        if key_emulator_id is not None:
            writes.update(self._runtime_config_writes())
        copies = (
            [
                *self._key_projection_copies(key_emulator_id),
                *self._firmware_projection_copies((key_emulator_id,)),
            ]
            if key_emulator_id is not None
            else []
        )
        root = self._compatible_root({**writes, **{target: b"" for _source, target in copies}})
        if copies:
            return transaction.plan_copy_files(
                copies,
                root=root,
                kind=f"emulation.game-settings:{game_id}",
                writes=writes,
            )
        return transaction.plan_write_files(
            writes,
            root=root,
            kind=f"emulation.game-settings:{game_id}",
        )

    @staticmethod
    def _settings_for_game(
        game: Mapping[str, Any], settings: Mapping[str, dict[str, Any]]
    ) -> dict[str, Any]:
        """Resolve preferências canônicas e IDs legados sem exigir nova escolha.

        As primeiras versões usavam os 16 primeiros caracteres do fingerprint
        como ID. O ID atual é derivado do caminho e tem 24 caracteres; aceitar
        o alias antigo preserva seleção de emulador e publicação Steam depois
        de uma nova varredura ou atualização do runtime.
        """
        return EmulationController._resolve_settings(game, settings)

    @classmethod
    def _resolve_settings(
        cls, game: Mapping[str, Any], settings: Mapping[str, dict[str, Any]]
    ) -> dict[str, Any]:
        game_id = game.get("id")
        fingerprint = game.get("fingerprint")
        candidates = [game_id]
        if isinstance(fingerprint, str) and len(fingerprint) >= 16:
            candidates.append(fingerprint[:16])
        for candidate in candidates:
            if isinstance(candidate, str) and candidate in settings:
                return dict(settings[candidate])
        return {}

    def _settings_for_game_with_global(
        self, game: Mapping[str, Any], settings: Mapping[str, dict[str, Any]]
    ) -> dict[str, Any]:
        result = self._resolve_settings(game, settings)
        if "emulatorId" not in result:
            global_settings = self._load_global_settings()
            default_emu = global_settings.get("defaultEmulatorId")
            if default_emu is not None:
                result["emulatorId"] = default_emu
        return result

    def _media_manager(self, store: StateStore) -> GameMediaManager:
        conn = store.adapter_connection()
        if self._media_providers is None:
            api_key = self._get_provider_api_key("steamgriddb")
            providers: list[MediaProviderPort] = []
            if api_key:
                providers.append(SteamGridDbAdapter(api_key=api_key))
            screenscraper = self._get_provider_credentials("screenscraper")
            if {"devid", "devpassword"} <= screenscraper.keys():
                providers.append(
                    ScreenScraperAdapter(
                        devid=screenscraper["devid"],
                        devpassword=screenscraper["devpassword"],
                        ssid=screenscraper.get("ssid"),
                        sspassword=screenscraper.get("sspassword"),
                    )
                )
        else:
            providers = list(self._media_providers)
        pipeline = MediaPipeline(
            media_root=paths.media_dir(),
            providers=providers,
            optimizer_tool=self._media_optimizer_tool,
            candidate_fetcher=self._media_candidate_fetcher,
        )
        return GameMediaManager(
            store=StateStoreGameMediaAdapter(conn),
            pipeline=pipeline,
            providers=providers,
        )

    def _enrich_games(
        self,
        games: list[dict[str, Any]],
        emulators: list[dict[str, Any]],
        keys: Mapping[str, Any],
        firmware: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        settings = self._load_game_settings(strict=False)
        published = self._shortcuts.managed_game_ids()
        emulator_states = {
            str(row["id"]): str(row.get("installState") or "unverified") for row in emulators
        }
        enriched: list[dict[str, Any]] = []
        with self._store_factory() as store:
            store.migrate()
            mod_store = StateStoreModsAdapter(store.adapter_connection())
            cheat_store = StateStoreCheatsAdapter(store.adapter_connection())
            media_store = StateStoreGameMediaAdapter(store.adapter_connection())
            extras: dict[str, tuple[list[InstalledMod], list[InstalledCheat]]] = {}
            catalog_extras: dict[
                str,
                tuple[list[tuple[str, ModCandidate]], list[tuple[str, CheatCandidate]]],
            ] = {}
            for raw in games:
                game_id = str(raw.get("id", ""))
                _mods = mod_store.list_installed(game_id)
                _cheats = cheat_store.list_installed(game_id)
                extras[game_id] = (_mods, _cheats)
                title_id = raw.get("titleId")
                if isinstance(title_id, str):
                    catalog_extras[game_id] = (
                        mod_store.list_catalog(title_id),
                        cheat_store.list_catalog(title_id),
                    )
                else:
                    catalog_extras[game_id] = ([], [])
            for raw in games:
                game = dict(raw)
                game_id = str(game["id"])
                selected = self._settings_for_game_with_global(game, settings)
                emulator_id = selected.get("emulatorId")
                emulator_state = (
                    emulator_states.get(str(emulator_id), "unconfigured")
                    if isinstance(emulator_id, str)
                    else "unconfigured"
                )
                emulator_ready = emulator_state == "installed"
                keys_ready = bool(
                    emulator_ready
                    and isinstance(emulator_id, str)
                    and self._key_projection_valid(emulator_id)
                )
                firmware_ready = firmware.get("status") == "ok"
                launch_ready = emulator_ready and keys_ready and firmware_ready
                if emulator_state == "unconfigured":
                    play_reason = "Selecione um emulador para este jogo."
                elif emulator_state == "degraded":
                    play_reason = f"Repare o {emulator_id} antes de jogar."
                elif emulator_state == "not-installed":
                    play_reason = "Instale o emulador deste jogo antes de jogar."
                elif emulator_state == "unverified":
                    play_reason = "Emulador ainda não verificado neste contexto."
                elif not keys_ready:
                    play_reason = f"Sincronize prod.keys com {emulator_id}."
                elif not firmware_ready:
                    play_reason = "Importe e valide o firmware antes de jogar."
                else:
                    play_reason = None
                launch_readiness = {
                    "state": "ready" if launch_ready else "blocked",
                    "emulator": emulator_state,
                    "reason": play_reason,
                }
                mods, cheats = extras.get(game_id, ([], []))
                mod_candidates, cheat_candidates = catalog_extras.get(game_id, ([], []))
                title_id = game.get("titleId") or ""
                cover_url = ""
                media_source = "fallback"
                media_kind = "icon"
                media_candidate_count = 0
                media_candidate_idx = -1
                media_candidates: list[dict[str, Any]] = []
                media_errors: dict[str, str] = {}
                master_state = "none"
                optimized_state = "none"
                steam_view_state = "unpublished"
                steam_appid = (
                    self._shortcuts.resolve_app_id(game_id) if game_id in published else None
                )
                steam_artwork_kinds: list[str] = []
                if title_id:
                    existing = media_store.load(game_id)
                    if existing:
                        media_candidate_count = existing.candidate_count
                        media_candidate_idx = existing.selected_candidate_idx
                        media_candidates = existing.candidates
                        media_errors = existing.errors
                        master_state = existing.master_state
                        optimized_state = existing.optimized_state
                        steam_view_state = existing.steam_view_state
                        steam_appid = existing.steam_appid or steam_appid
                        steam_artwork_kinds = existing.steam_artwork_kinds
                        if existing.media_path:
                            try:
                                p = Path(existing.media_path)
                                if p.is_file() and not p.is_symlink():
                                    cover_url = p.resolve().as_uri()
                                    media_source = existing.media_source
                                    media_kind = existing.media_kind
                            except OSError:
                                pass
                    if not cover_url and game.get("bannerAsset"):
                        cover_url = str(game["bannerAsset"])
                        media_source = str(game.get("mediaSource", "fallback"))
                mod_conflicts = self._mod_conflict_map(mods)
                mod_list = [
                    {
                        "id": mod.id,
                        "name": mod.name,
                        "state": mod.state,
                        "emulatorId": mod.emulator_id,
                        "buildId": mod.build_id,
                        "type": mod.mod_type.value,
                        "source": mod.source,
                        "version": mod.version,
                        "priority": None,
                        "prioritySupported": False,
                        "conflicts": mod_conflicts.get(mod.id, []),
                        "compatibility": {
                            "state": "unknown",
                            "reason": (
                                "Build ID registrado; compatibilidade ainda não foi validada."
                                if mod.build_id
                                else "O backend não detectou Build ID para validar compatibilidade."
                            ),
                        },
                        "stateAction": self._action(
                            f"mod.state:{mod.id}:{'off' if mod.state == 'active' else 'on'}",
                            "Desativar" if mod.state == "active" else "Ativar",
                            confirmation=True,
                        ),
                        "removeAction": self._action(
                            f"mod.remove:{mod.id}", "Remover", confirmation=True
                        ),
                    }
                    for mod in mods
                ]
                cheat_list = [
                    {
                        "id": cheat.id,
                        "name": cheat.name,
                        "buildId": cheat.build_id,
                        "state": cheat.state,
                        "enabled": cheat.enabled,
                        "codeCount": cheat.code_count,
                        "type": cheat.cheat_type.value,
                        "source": cheat.source,
                        "version": cheat.version,
                        "compatibility": {
                            "state": "unverified" if cheat.build_id else "unknown",
                            "reason": (
                                "Build ID do arquivo foi validado; equivalência com o "
                                "jogo ainda não foi observada."
                                if cheat.build_id
                                else "Build ID ausente; compatibilidade não pode ser confirmada."
                            ),
                        },
                        "stateAction": self._action(
                            f"cheat.state:{cheat.id}:{'off' if cheat.enabled else 'on'}",
                            "Desativar" if cheat.enabled else "Ativar",
                            confirmation=True,
                        ),
                        "removeAction": self._action(
                            f"cheat.remove:{cheat.id}", "Remover", confirmation=True
                        ),
                    }
                    for cheat in cheats
                ]
                mod_candidate_list = []
                for catalog_id, mod_candidate in mod_candidates:
                    prepared = self._prepared_mod_package(catalog_id) is not None
                    supported_url = self._remote_mod_url_supported(
                        mod_candidate.identity.source_url
                    )
                    action_enabled = isinstance(emulator_id, str) and (prepared or supported_url)
                    if not isinstance(emulator_id, str):
                        reason = "Defina o emulador deste jogo antes de preparar o mod."
                    elif not prepared and not supported_url:
                        reason = (
                            "A fonte não publicou um arquivo ZIP/IPS/BPS/PCHTXT "
                            "instalável para este resultado."
                        )
                    else:
                        reason = None
                    action_kind = "install" if prepared else "prepare"
                    mod_candidate_list.append(
                        {
                            "id": catalog_id,
                            "name": mod_candidate.identity.name,
                            "buildId": mod_candidate.build_id,
                            "type": mod_candidate.identity.mod_type,
                            "source": mod_candidate.identity.source,
                            "version": mod_candidate.identity.version,
                            "description": mod_candidate.identity.description,
                            "matchConfidence": mod_candidate.match_confidence,
                            "prepared": prepared,
                            "installAction": self._action(
                                f"mod.catalog.{action_kind}:{catalog_id}",
                                ("Revisar e instalar" if prepared else "Baixar e inspecionar"),
                                enabled=action_enabled,
                                reason=reason,
                                confirmation=True,
                            )
                            | {
                                "gameId": game_id,
                                "emulatorId": emulator_id or "",
                            },
                        }
                    )
                cheat_candidate_list = []
                for catalog_id, cheat_candidate in cheat_candidates:
                    candidate_ready = (
                        isinstance(emulator_id, str)
                        and isinstance(cheat_candidate.build_id, str)
                        and _BUILD_ID.fullmatch(cheat_candidate.build_id) is not None
                        and bool(cheat_candidate.codes)
                        and validate_cheat_codes(cheat_candidate.codes)
                    )
                    if not isinstance(emulator_id, str):
                        reason = "Defina o emulador deste jogo antes de instalar."
                    elif not cheat_candidate.build_id:
                        reason = "O catálogo não publicou Build ID para este cheat."
                    elif not cheat_candidate.codes or not validate_cheat_codes(
                        cheat_candidate.codes
                    ):
                        reason = "O catálogo não publicou códigos Atmosphere válidos."
                    else:
                        reason = None
                    cheat_candidate_list.append(
                        {
                            "id": catalog_id,
                            "name": cheat_candidate.identity.name,
                            "buildId": cheat_candidate.build_id,
                            "type": cheat_candidate.identity.cheat_type,
                            "source": cheat_candidate.identity.source,
                            "version": cheat_candidate.identity.version,
                            "description": cheat_candidate.identity.description,
                            "codeCount": len(cheat_candidate.codes),
                            "matchConfidence": cheat_candidate.match_confidence,
                            "installAction": self._action(
                                f"cheat.catalog.install:{catalog_id}",
                                "Instalar cheat",
                                enabled=candidate_ready,
                                reason=reason,
                                confirmation=True,
                            )
                            | {
                                "gameId": game_id,
                                "emulatorId": emulator_id or "",
                            },
                        }
                    )
                game.update(
                    {
                        "platformId": "switch",
                        "fallbackArtworkUrl": "../assets/switch.svg",
                        "emulatorId": emulator_id,
                        "steamSelected": selected.get("steamSelected") is True,
                        "steamPublished": game_id in published,
                        "playAction": self._action(
                            f"game.launch:{game_id}",
                            "Jogar",
                            enabled=launch_readiness["state"] == "ready",
                            reason=launch_readiness["reason"],
                        ),
                        "launchReadiness": launch_readiness,
                        "deleteAction": self._action(
                            f"game.delete:{game_id}", "Excluir ROM", confirmation=True
                        ),
                        "modsCount": len(mods),
                        "cheatsCount": len(cheats),
                        "coverUrl": cover_url,
                        "mediaSource": media_source,
                        "mediaKind": media_kind,
                        "mediaCandidateCount": media_candidate_count,
                        "mediaCandidateIdx": media_candidate_idx,
                        "mediaCandidates": [
                            {
                                "url": c.get("url", ""),
                                "mediaKind": c.get("mediaKind", ""),
                                "width": c.get("width"),
                                "height": c.get("height"),
                                "provider": c.get("provider", ""),
                                "confidence": c.get("confidence", 0),
                            }
                            for c in media_candidates
                        ],
                        "mediaErrors": media_errors,
                        "mediaErrorCategories": {
                            str(provider): provider_error_category(str(code))
                            for provider, code in media_errors.items()
                        },
                        "masterState": master_state,
                        "optimizedState": optimized_state,
                        "steamViewState": steam_view_state,
                        "steamAppId": steam_appid,
                        "steamArtworkKinds": steam_artwork_kinds,
                        "mods": mod_list,
                        "cheats": cheat_list,
                        "modCandidates": mod_candidate_list,
                        "cheatCandidates": cheat_candidate_list,
                        "catalogSearchAction": self._action(
                            f"extras.catalog.search:{game_id}",
                            "Buscar mods e cheats",
                            enabled=bool(title_id),
                            reason=(
                                None
                                if title_id
                                else "Title ID não identificado para consultar catálogos."
                            ),
                            confirmation=True,
                        )
                        | {"gameId": game_id},
                        "modPriorityCapability": {
                            "supported": False,
                            "reason": (
                                "Eden, Citron e Ryubing não publicam uma ordem de sobreposição "
                                "estável que o backend possa verificar; controles de prioridade "
                                "permanecem ocultos."
                            ),
                        },
                    }
                )
                enriched.append(game)
        return enriched

    def _enrich_preservation(self, games: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for game in games:
            game_id = str(game.get("id", ""))
            title_id = game.get("titleId")
            emulator_id = game.get("emulatorId")
            if not isinstance(title_id, str) or not isinstance(emulator_id, str):
                unavailable = {
                    "confirmed": False,
                    "ambiguous": False,
                    "reason": "defina um emulador e confirme o Title ID",
                }
                game["saveTarget"] = unavailable
                game["stateTarget"] = unavailable
                game["shaderTarget"] = unavailable
                game["saveBackups"] = []
                game["stateBackups"] = []
                game["shaderBackups"] = []
                game["saveState"] = "Destino não confirmado"
                game["stateCount"] = 0
                game["shaderCount"] = 0
                continue
            game_name = self._rom_stem(game)
            for kind, target_key, backups_key in (
                ("save", "saveTarget", "saveBackups"),
                ("state", "stateTarget", "stateBackups"),
                ("shader-cache", "shaderTarget", "shaderBackups"),
            ):
                try:
                    target = self._preservation.target_status(
                        game_id, title_id, emulator_id, kind, game_name=game_name
                    )
                    backups = self._preservation.backups(title_id, emulator_id, kind)
                except SteamZeroError as exc:
                    target = {
                        "confirmed": False,
                        "ambiguous": False,
                        "reason": str(exc.detail or exc.code),
                    }
                    backups = []
                game[target_key] = target
                game[backups_key] = backups
            game["saveState"] = (
                f"{len(game['saveBackups'])} backup(s)"
                if game["saveTarget"].get("confirmed")
                else "Destino indisponível"
            )
            game["stateCount"] = len(game["stateBackups"])
            game["shaderCount"] = len(game["shaderBackups"])
        return games

    def _enrich_controls(self, games: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Perfil de input por jogo com herança game → plataforma e prontidão
        honesta de controles. A prontidão NUNCA bloqueia o launch: informa,
        não interdita (falha degrada, nunca trava)."""
        platform_status = self._input_profiles.status("switch")
        controllers = self._controller_count()
        for game in games:
            game_id = str(game.get("id", ""))
            game_status = self._input_profiles.status("switch", scope="game", scope_id=game_id)
            if game_status["state"] == "unverified":
                effective = platform_status
                source = "platform"
            else:
                effective = game_status
                source = "game"
            available = [row for row in effective["available"] if isinstance(row, Mapping)]
            activate_actions = [
                self._action(
                    f"controls.profile.activate:{row['id']}",
                    str(row.get("label") or row["id"]),
                    confirmation=True,
                )
                | {"gameId": game_id, "scope": "game", "scopeId": game_id}
                for row in available
            ]
            clear_action = (
                self._action(
                    f"controls.profile.clear:{game_id}",
                    "Voltar ao perfil da plataforma",
                    confirmation=True,
                )
                if source == "game"
                else None
            )
            active = effective.get("active")
            game["controlsProfile"] = {
                "state": str(effective.get("state") or "unverified"),
                "statusLabel": str(effective.get("statusLabel") or "Perfil não selecionado"),
                "source": source,
                "scope": (
                    str(active.get("scope", source)) if isinstance(active, Mapping) else source
                ),
                "active": active,
                "available": [
                    {
                        "id": str(row["id"]),
                        "revision": int(row.get("revision") or 0),
                        "label": str(row.get("label") or row["id"]),
                    }
                    for row in available
                ],
                "activateActions": activate_actions,
                "clearAction": clear_action,
            }
            profile_configured = isinstance(active, Mapping)
            reasons: list[str] = []
            if not profile_configured:
                reasons.append("Nenhum perfil de input ativo; o jogo usará os padrões do emulador.")
            if controllers == 0:
                reasons.append("Nenhum controle detectado no host.")
            ready = profile_configured and controllers > 0
            game["controlsReadiness"] = {
                "state": "ready" if ready else "attention",
                "reason": None if ready else " ".join(reasons),
                "profileConfigured": profile_configured,
                "controllers": controllers,
            }
        return games

    def _current_game(self, game_id: str) -> dict[str, Any]:
        games, _unidentified = self._load_library_cache()
        matches = [game for game in games if game.get("id") == game_id]
        if len(matches) != 1:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="jogo não encontrado na biblioteca")
        game = matches[0]
        try:
            source = Path(str(game["path"]))
            if source.is_symlink() or not source.is_file():
                raise OSError("arquivo não é regular")
            resolved = source.resolve(strict=True)
            self._root_for_game(resolved)
            stat = resolved.stat()
            fingerprint = hashlib.sha256(
                f"{source}\0{stat.st_size}\0{stat.st_mtime_ns}".encode()
            ).hexdigest()
        except OSError as exc:
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="arquivo do jogo mudou ou não está acessível"
            ) from exc
        if fingerprint != game.get("fingerprint"):
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="arquivo do jogo mudou; faça uma nova varredura"
            )
        return game

    def _root_for_game(self, source: Path) -> Path:
        roots = [Path(value).resolve(strict=True) for value in self.library_roots()]
        matches = [root for root in roots if source.is_relative_to(root)]
        if not matches:
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-PATH", detail="ROM está fora das bibliotecas permitidas"
            )
        return max(matches, key=lambda root: len(root.parts))

    def _load_library_cache(self) -> tuple[list[dict[str, Any]], int]:
        if not self._library_cache_path.is_file() or self._library_cache_path.is_symlink():
            return [], 0
        try:
            data = json.loads(self._library_cache_path.read_text(encoding="utf-8"))
            games = data.get("games", [])
            unidentified = int(data.get("unidentified", 0))
            if data.get("schemaVersion") != 1 or not isinstance(games, list):
                return [], 0
            valid = []
            for game in games:
                if not isinstance(game, dict):
                    continue
                title_id = game.get("titleId")
                if title_id is not None and _TITLE_ID.fullmatch(str(title_id)) is None:
                    continue
                if not all(isinstance(game.get(field), str) for field in ("id", "name", "state")):
                    continue
                path_value = game.get("path")
                if not isinstance(path_value, str):
                    continue
                candidate_path = Path(path_value)
                candidate_root = next(
                    (
                        Path(root)
                        for root in self.library_roots()
                        if candidate_path.is_relative_to(Path(root))
                    ),
                    candidate_path.parent,
                )
                fmt = str(game.get("format", candidate_path.suffix.lstrip(".").casefold()))
                kind, _parent, _version, _source = SwitchLibraryScanner.classify(
                    candidate_path,
                    root=candidate_root,
                    fmt=fmt,
                    title_id=str(title_id) if title_id is not None else None,
                )
                if kind != "base" or game.get("contentKind", "base") != "base":
                    continue
                normalized = dict(game)
                normalized["contentKind"] = "base"
                normalized["name"] = SwitchLibraryScanner.clean_display_name(candidate_path)
                valid.append(normalized)
            return valid, max(0, unidentified)
        except (OSError, ValueError, json.JSONDecodeError):
            return [], 0

    def _count_projection_ghosts(self) -> int:
        """Conta jogos do cache cujo arquivo sumiu (verificação pós-reparo)."""
        try:
            data = json.loads(self._library_cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return -1
        ghosts = 0
        for game in data.get("games", []):
            if not isinstance(game, dict):
                ghosts += 1
                continue
            path_value = game.get("path")
            candidate = Path(path_value) if isinstance(path_value, str) else None
            if candidate is None or candidate.is_symlink() or not candidate.is_file():
                ghosts += 1
        return ghosts

    @staticmethod
    def _cover_asset(title_id: str | None) -> tuple[str, str]:
        if title_id is None:
            return "", "fallback"
        home = Path.home()
        roots = (
            (paths.data_home() / "media/switch/custom", "custom"),
            (paths.data_home() / "cache/covers", "scraped"),
            (home / ".local/share/eden/icons", "emulator-cache"),
            (home / ".local/share/citron/icons", "emulator-cache"),
            (home / "Ryujinx/games" / title_id, "emulator-cache"),
        )
        names = (title_id, title_id.casefold(), "icon")
        suffixes = (".png", ".jpg", ".jpeg", ".webp")
        for root, source in roots:
            for name in names:
                for suffix in suffixes:
                    candidate = root / f"{name}{suffix}"
                    try:
                        if (
                            candidate.is_file()
                            and not candidate.is_symlink()
                            and candidate.stat().st_size <= 16 * 1024 * 1024
                        ):
                            return candidate.resolve(strict=True).as_uri(), source
                    except OSError:
                        continue
        cached = EmulatorCacheReader(paths.data_home()).find_icon(title_id)
        if cached is not None:
            try:
                if not cached.is_symlink() and cached.stat().st_size <= 16 * 1024 * 1024:
                    return cached.resolve(strict=True).as_uri(), "emulator-cache"
            except OSError:
                pass
        return "", "fallback"

    @staticmethod
    def _physical_dock(status: Mapping[str, Any]) -> bool:
        context = status.get("context")
        return bool(context.get("physicalDock")) if isinstance(context, Mapping) else False

    @staticmethod
    def _runtime_profiles(
        status: Mapping[str, Any], dock: bool, controllers: int
    ) -> dict[str, Any]:
        context = status.get("context")
        context_map = context if isinstance(context, Mapping) else {}
        displays = context_map.get("displays")
        display_rows = displays if isinstance(displays, list) else []
        external = next(
            (
                row
                for row in display_rows
                if isinstance(row, Mapping)
                and row.get("connected") is True
                and row.get("internal") is False
            ),
            None,
        )
        external_width = external.get("width") if isinstance(external, Mapping) else None
        external_height = external.get("height") if isinstance(external, Mapping) else None
        handheld = resolve_switch_runtime_profile(
            "handheld",
            connected_controllers=controllers,
            built_in_controller=(
                controllers == 0 and str(context_map.get("deviceKind", "")).startswith("deck-")
            ),
        ).to_dict()
        docked = resolve_switch_runtime_profile(
            "dock",
            connected_controllers=controllers,
            built_in_controller=False,
            external_width=external_width if isinstance(external_width, int) else None,
            external_height=external_height if isinstance(external_height, int) else None,
        ).to_dict()
        for profile in (handheld, docked):
            profile.update(
                {
                    "tdp": {"value": None, "source": "steam-game-profile"},
                    "fps": {"value": None, "source": "steam-game-profile"},
                    "graphics": {"value": None, "source": "per-game-or-emulator"},
                    "audio": {"value": None, "source": "system-inherited"},
                }
            )
        observed = "dock" if dock else "handheld"
        return {
            "activeScope": observed,
            "observedScope": observed,
            "desiredScope": None,
            "diverged": None,
            "autoTransition": {
                "supported": False,
                "reason": "A detecção é observada; transição automática ainda não possui executor.",
                "lastResult": None,
            },
            "handheld": handheld,
            "dock": docked,
        }

    @staticmethod
    def _controller_count() -> int:
        root = Path("/dev/input/by-id")
        try:
            names = {path.name for path in root.iterdir() if "-event-joystick" in path.name}
        except OSError:
            return 0
        return min(4, len(names))

    @staticmethod
    def _plan_view(
        plan: transaction.Plan,
        action: str,
        **extra: Any,
    ) -> dict[str, Any]:
        return {
            "planId": plan.plan_id,
            "confirmToken": plan.confirm_token,
            "action": action,
            "preview": plan.preview,
            "rollbackGuarantee": plan.rollback_guarantee,
            "requirements": plan.requirements,
            **extra,
        }

    @staticmethod
    def _action(
        action_id: str,
        label: str,
        *,
        enabled: bool = True,
        reason: str | None = None,
        confirmation: bool = False,
    ) -> dict[str, Any]:
        return {
            "id": action_id,
            "label": label,
            "enabled": enabled,
            "reason": reason,
            "requiresConfirmation": confirmation,
        }

    @staticmethod
    def _card(
        card_id: str,
        title: str,
        detail: str,
        state: str,
        status_label: str,
        *,
        action: dict[str, Any] | None = None,
        actions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": card_id,
            "title": title,
            "detail": detail,
            "state": state,
            "statusLabel": status_label,
        }
        if action is not None:
            result["action"] = action
        if actions:
            result["actions"] = actions
        return result

    @staticmethod
    def _required_string(payload: Mapping[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > 4096:
            raise SteamZeroError("E-API-SCHEMA", detail=f"campo obrigatório: {key}")
        return value.strip()

    @staticmethod
    def _optional_string(payload: Mapping[str, Any], key: str) -> str | None:
        value = payload.get(key)
        if value is None or value == "":
            return None
        if not isinstance(value, str) or len(value) > 256:
            raise SteamZeroError("E-API-SCHEMA", detail=f"campo inválido: {key}")
        return value

    @staticmethod
    def _required_bool(payload: Mapping[str, Any], key: str) -> bool:
        value = payload.get(key)
        if not isinstance(value, bool):
            raise SteamZeroError("E-API-SCHEMA", detail=f"campo booleano obrigatório: {key}")
        return value

    @classmethod
    def _required_title_id(cls, payload: Mapping[str, Any]) -> str:
        value = cls._required_string(payload, "titleId").upper()
        if _TITLE_ID.fullmatch(value) is None:
            raise SteamZeroError("E-API-SCHEMA", detail="Title ID inválido")
        return value

    @staticmethod
    def _version_tuple(value: str) -> tuple[int, ...]:
        try:
            return tuple(int(part) for part in value.split("."))
        except ValueError:
            return (0,)

    @staticmethod
    def _require_managed_emulator(emulator_id: str) -> None:
        if emulator_id not in _MANAGED_EMULATORS:
            raise SteamZeroError("E-API-SCHEMA", detail="emulador não gerenciado")

    @staticmethod
    def _require_known_emulator(emulator_id: str) -> None:
        """O emulador é declarado no registry de adapters (qualquer fonte).

        Seleção de preferência, instalação e parada aceitam todo adapter
        conhecido; lançar um jogo continua exigindo fonte instalável e instalada
        via ``_require_launchable_emulator``.
        """
        try:
            registry = AdapterRegistry.bundled()
            manifest = registry.get(emulator_id)
        except SteamZeroError:
            manifest = None
        if manifest is None:
            raise SteamZeroError("E-API-SCHEMA", detail="emulador não declarado")

    def _known_emulator(self, emulator_id: str) -> bool:
        try:
            registry = self._registry_factory()
            return registry.get(emulator_id) is not None
        except Exception:
            return False
