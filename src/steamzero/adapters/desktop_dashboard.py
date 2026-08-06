# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Read model e ações allowlisted do dashboard Desktop.

O dashboard agrega capacidades existentes sem transformar a UI em um segundo
núcleo: lifecycle de emuladores continua no executor Flatpak transacional,
diagnóstico continua no doctor e Steam é uma integração opcional. Ausência de
qualquer provider degrada somente a linha correspondente.
"""

from __future__ import annotations

import contextlib
import logging
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from steamzero.adapters.cast_orchestrator import CastOrchestrator
from steamzero.adapters.desktop_contracts import handheld_ui_contracts
from steamzero.adapters.desktop_kde import (
    high_contrast_enabled,
    input_method_status,
    reduced_motion_enabled,
)
from steamzero.adapters.diagnostics import DiagnosticsService
from steamzero.adapters.emulation import EmulationController
from steamzero.adapters.flatpak import FlatpakCLI
from steamzero.adapters.lifecycle import ComponentLifecycle, route_for
from steamzero.adapters.registry import AdapterManifest, AdapterRegistry
from steamzero.adapters.resource_probe import ResourceProbe
from steamzero.adapters.steam_gameplay import SteamGameplayController
from steamzero.adapters.theme_catalog import ThemeCatalog
from steamzero.core import log
from steamzero.core.errors import SteamZeroError
from steamzero.core.secret import Secret
from steamzero.core.session_state import SESSION_OWNER
from steamzero.core.state import StateStore
from steamzero.diagnostics.doctor import run_doctor
from steamzero.domain.collections import CollectionManager
from steamzero.domain.emulation_workspace import build_switch_workspace
from steamzero.domain.operation_history import OperationHistory
from steamzero.domain.playtime import PlaytimeCatalog
from steamzero.domain.theme_editor import ThemeEditorManager
from steamzero.domain.theme_preferences import ThemePreferenceManager
from steamzero.ports import CaptureConsent

Spawn = Callable[[Sequence[str]], None]
StoreFactory = Callable[[], StateStore]
RegistryFactory = Callable[[], AdapterRegistry]
DoctorRunner = Callable[[], tuple[dict[str, Any], list[dict[str, str]]]]
EmulationBuilder = Callable[..., dict[str, Any]]
ReducedMotionProbe = Callable[[], bool]
HighContrastProbe = Callable[[], bool]
_log = logging.getLogger(__name__)


def _daemon_pid_provider() -> Callable[[], int | None]:
    def provider() -> int | None:
        from steamzero.service.client import daemon_pid

        return daemon_pid()

    return provider


def _session_emulator_provider(
    store_factory: StoreFactory,
) -> Callable[[], list[tuple[int, int | None]]]:
    def provider() -> list[tuple[int, int | None]]:
        with store_factory() as store:
            store.migrate()
            rows = store.active_game_sessions(SESSION_OWNER)
        processes: list[tuple[int, int | None]] = []
        for row in rows:
            pid = row.get("pid")
            ticks = row.get("start_ticks")
            if isinstance(pid, int) and pid > 1:
                processes.append((pid, ticks if isinstance(ticks, int) else None))
        return processes

    return provider


_COMPONENT_LABELS: dict[str, tuple[str, str, str]] = {
    "dolphin": ("Dolphin", "Emulador de Wii e GameCube", "dolphin-emu"),
    "duckstation": ("DuckStation", "Emulador de PlayStation", "duckstation"),
    "retroarch": ("RetroArch", "Plataforma multi-emulador", "retroarch"),
}
_PLATFORM_LABELS = {
    "gamecube": "GameCube",
    "wii": "Wii",
    "psx": "PlayStation",
    "multi": "Múltiplos",
}
_STEAM_TARGETS = {
    "home": "steam://open/main",
    "library": "steam://open/games",
    "big-picture": "steam://open/bigpicture",
}


def _spawn_detached(argv: Sequence[str]) -> None:
    subprocess.Popen(  # noqa: S603
        list(argv),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _steam_process_running(proc_root: Path | None = None) -> bool:
    """Detecta Steam sem depender de pgrep, DBus ou serviço systemd.

    ``proc_root`` injetável: sem ele o ramo positivo só executa quando há Steam
    aberto na máquina, e a cobertura passa a depender do que está rodando.
    """
    proc = proc_root if proc_root is not None else Path("/proc")
    # Iteração dentro do try: ``iterdir`` é preguiçoso em Python 3.11/3.12 e o
    # OSError escaparia de um try posto só na chamada.
    try:
        entries = list(proc.iterdir())
    except OSError:
        return False
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            name = (entry / "comm").read_text(encoding="utf-8").strip().casefold()
        except OSError:
            continue
        if name in {"steam", "steamwebhelper"}:
            return True
    return False


class SteamDesktopController:
    """Integração mínima e opcional com o cliente Steam instalado no host."""

    def __init__(
        self,
        *,
        which: Callable[[str], str | None] = shutil.which,
        running_probe: Callable[[], bool] = _steam_process_running,
        spawn: Spawn = _spawn_detached,
    ) -> None:
        self._which = which
        self._running_probe = running_probe
        self._spawn = spawn

    def rows(self, desktop_status: dict[str, Any]) -> list[dict[str, Any]]:
        context = desktop_status.get("context")
        context_dict = context if isinstance(context, dict) else {}
        raw_capabilities = context_dict.get("capabilities", [])
        capabilities = (
            {value for value in raw_capabilities if isinstance(value, str)}
            if isinstance(raw_capabilities, list)
            else set()
        )
        raw_conflicts = context_dict.get("conflicts", [])
        conflicted = bool(raw_conflicts) if isinstance(raw_conflicts, list) else False
        installed = self._which("steam") is not None
        running = installed and self._running_probe()

        client_state = "running" if running else "installed" if installed else "missing"
        client_label = "Em execução" if running else "Instalado" if installed else "Não instalado"
        input_state = "blocked" if conflicted else "available" if installed else "missing"
        input_label = (
            "Bloqueado por conflito"
            if conflicted
            else "Disponível"
            if installed
            else "Steam ausente"
        )
        keyboard_available = "steam-keyboard" in capabilities

        return [
            {
                "id": "steam-client",
                "name": "Cliente Steam",
                "description": "Cliente oficial e modo Big Picture",
                "iconName": "steam",
                "state": client_state,
                "statusLabel": client_label,
                "versionLabel": "Cliente do sistema" if installed else "—",
                "detail": (
                    "O Steam está pronto para abrir sua biblioteca."
                    if installed
                    else "Instale o cliente Steam pelos repositórios da sua distribuição."
                ),
                "action": {
                    "kind": "steam-open",
                    "target": "home",
                    "label": "Abrir" if installed else "Indisponível",
                    "enabled": installed,
                },
            },
            {
                "id": "steam-library",
                "name": "Biblioteca Steam",
                "description": "Jogos Steam e atalhos não-Steam",
                "iconName": "applications-games",
                "state": "available" if installed else "missing",
                "statusLabel": "Disponível" if installed else "Steam ausente",
                "versionLabel": "Biblioteca local",
                "detail": "Abre diretamente a biblioteca do cliente Steam.",
                "action": {
                    "kind": "steam-open",
                    "target": "library",
                    "label": "Abrir biblioteca" if installed else "Indisponível",
                    "enabled": installed,
                },
            },
            {
                "id": "steam-input",
                "name": "Steam Input",
                "description": "Perfis de controle durante os jogos",
                "iconName": "input-gaming",
                "state": input_state,
                "statusLabel": input_label,
                "versionLabel": "Owner exclusivo por modo",
                "detail": (
                    "Resolva o conflito de controle antes de alterar perfis de entrada."
                    if conflicted
                    else (
                        "No modo de jogo, o Steam pode assumir os controles sem duplicar o Desktop."
                    )
                ),
                "action": {
                    "kind": "detail",
                    "target": "steam-input",
                    "label": "Ver integração",
                    "enabled": True,
                },
            },
            {
                "id": "steam-keyboard",
                "name": "Teclado da Steam",
                "description": "Fallback de teclado virtual",
                "iconName": "input-keyboard-virtual",
                "state": "available" if keyboard_available else "missing",
                "statusLabel": "Disponível" if keyboard_available else "Indisponível",
                "versionLabel": "Fallback opcional",
                "detail": "O SteamZero usa este teclado somente quando providers nativos falham.",
                "action": {
                    "kind": "keyboard",
                    "target": "steam-keyboard",
                    "label": "Abrir teclado" if keyboard_available else "Indisponível",
                    "enabled": keyboard_available,
                },
            },
        ]

    def open(self, target: str) -> dict[str, Any]:
        uri = _STEAM_TARGETS.get(target)
        executable = self._which("steam")
        if uri is None:
            raise SteamZeroError("E-API-SCHEMA", detail="destino Steam não permitido")
        if executable is None:
            raise SteamZeroError("E-COMPONENT-DEGRADED", detail="cliente Steam não encontrado")
        self._spawn((executable, uri))
        return {"status": "started", "target": target, "uri": uri}

    def open_game(self, game_id: str) -> dict[str, Any]:
        if not game_id.isdigit() or len(game_id) > 32:
            raise SteamZeroError("E-API-SCHEMA", detail="gameId Steam inválido")
        executable = self._which("steam")
        if executable is None:
            raise SteamZeroError("E-COMPONENT-DEGRADED", detail="cliente Steam não encontrado")
        uri = f"steam://rungameid/{game_id}"
        self._spawn((executable, uri))
        return {"status": "started", "gameId": game_id, "uri": uri}

    def open_controller_config(self, game_id: str) -> dict[str, Any]:
        if not game_id.isdigit() or len(game_id) > 32:
            raise SteamZeroError("E-API-SCHEMA", detail="gameId inválido")
        executable = self._which("steam")
        if executable is None:
            raise SteamZeroError("E-COMPONENT-DEGRADED", detail="cliente Steam não encontrado")
        uri = f"steam://controllerconfig/{game_id}"
        self._spawn((executable, uri))
        return {"status": "started", "gameId": game_id, "uri": uri}


def _unreadable_workspace() -> dict[str, Any]:
    """Central de emulação quando a composição real falhou.

    O estado é ``unverified``, que significa "não sabemos" — mas o detalhe diz
    que a LEITURA falhou, não que falta importar keys. A distinção importa: um
    usuário que vê "importe suas keys" quando as keys estão instaladas conclui
    que os dados foram perdidos.
    """
    payload = build_switch_workspace()
    for platform in payload["platforms"]:
        requirements = platform.get("requirements")
        if not isinstance(requirements, dict):
            continue
        for requirement in requirements.values():
            requirement["detail"] = (
                "Não foi possível consultar o ambiente agora. "
                "Nenhum dado foi alterado; tente novamente."
            )
    return payload


class DesktopDashboard:
    """Compõe o read model da central e delega mutações aos serviços existentes."""

    def __init__(
        self,
        *,
        store_factory: StoreFactory = StateStore,
        registry_factory: RegistryFactory = AdapterRegistry.bundled,
        flatpak_factory: Callable[[], FlatpakCLI] = FlatpakCLI,
        doctor_runner: DoctorRunner = run_doctor,
        steam: SteamDesktopController | None = None,
        gameplay: SteamGameplayController | None = None,
        emulation_builder: EmulationBuilder | None = None,
        emulation: EmulationController | None = None,
        which: Callable[[str], str | None] = shutil.which,
        spawn: Spawn = _spawn_detached,
        reduced_motion_probe: ReducedMotionProbe = reduced_motion_enabled,
        high_contrast_probe: HighContrastProbe = high_contrast_enabled,
        diagnostics: DiagnosticsService | None = None,
        playtime: PlaytimeCatalog | None = None,
        collections: CollectionManager | None = None,
        cast_orchestrator: CastOrchestrator | None = None,
        theme_editor: ThemeEditorManager | None = None,
        resources: ResourceProbe | None = None,
    ) -> None:
        self._store_factory = store_factory
        self._registry_factory = registry_factory
        self._flatpak_factory = flatpak_factory
        self._doctor_runner = doctor_runner
        self._steam = steam or SteamDesktopController(which=which, spawn=spawn)
        self._gameplay = gameplay or SteamGameplayController(
            which=which, store_factory=store_factory
        )
        self._emulation_builder = emulation_builder
        # Último snapshot de emulação que foi realmente composto. Ver o
        # tratamento de falha em snapshot(): rebaixar keys/firmware verificados
        # para "unverified" por causa de uma exceção é como dados válidos
        # "somem" da UI sem terem sido apagados.
        self._last_emulation: dict[str, Any] | None = None
        self._emulation = emulation or EmulationController(
            store_factory=store_factory,
            registry_factory=registry_factory,
            which=which,
            spawn=spawn,
        )
        self._which = which
        self._spawn = spawn
        self._reduced_motion_probe = reduced_motion_probe
        self._high_contrast_probe = high_contrast_probe
        self._operation_history = OperationHistory(
            store_factory,
            component_rollback=self._rollback_component_for_history,
        )
        self._diagnostics = diagnostics or DiagnosticsService(
            store_factory, self._operation_history
        )
        self._playtime = playtime or PlaytimeCatalog(store_factory)
        self._collections = collections or CollectionManager()
        self._cast = cast_orchestrator
        self._theme_catalog = ThemeCatalog()
        self._theme_prefs = ThemePreferenceManager()
        self._theme_editor = theme_editor or ThemeEditorManager()
        self._resources = resources or ResourceProbe(
            own_class="ui",
            daemon_pid=_daemon_pid_provider(),
            emulator_processes=_session_emulator_provider(store_factory),
            media_job_processes=lambda: [],
        )

    def close_request_context(self) -> None:
        """Libera recursos locais à thread usados pelo read model."""
        close = getattr(self._emulation, "close_request_context", None)
        if callable(close):
            close()

    def snapshot(self, desktop_status: dict[str, Any]) -> dict[str, Any]:
        conflicts = self._conflicts(desktop_status)
        registry = self._registry_factory()
        components: list[dict[str, Any]] = []
        sync: dict[str, Any] = {
            "state": "unavailable",
            "mode": "read-only",
            "pending": 0,
            "conflicted": 0,
            "done": 0,
            "items": [],
            "provider": {
                "configured": False,
                "name": None,
                "health": "unavailable",
                "detail": "Nenhum CloudPort foi configurado na bridge Desktop.",
            },
            "capabilities": {
                "retry": False,
                "cancel": False,
                "resolveConflict": False,
            },
            "dependency": (
                "Publicar um CloudPort autenticado e contratos transacionais allowlisted "
                "para retry, cancelamento e resolução de conflito."
            ),
        }
        try:
            with self._store_factory() as store:
                store.migrate()
                lifecycle = ComponentLifecycle(
                    store,
                    registry,
                    flatpak_factory=self._flatpak_factory,
                    which=self._which,
                    spawn=self._spawn,
                )
                components = [
                    self._component_row(manifest, lifecycle, conflicts=bool(conflicts))
                    for manifest in registry.list()
                    if manifest.id in _COMPONENT_LABELS
                ]
                queue = store.list_sync_queue()
                items: list[dict[str, Any]] = []
                for row in queue:
                    save = store.get_save_entry(str(row.get("save_entry_id", "")))
                    items.append(
                        {
                            "id": str(row.get("id", "")),
                            "saveEntryId": str(row.get("save_entry_id", "")),
                            "gameId": str(save.get("game_id", "")) if save else None,
                            "direction": str(row.get("direction") or "unknown"),
                            "state": str(row.get("state") or "unknown"),
                            "lastAttempt": None,
                            "error": None,
                            "conflict": (
                                {
                                    "preserved": True,
                                    "group": save.get("conflict_group") if save else None,
                                }
                                if row.get("state") == "conflicted"
                                else None
                            ),
                        }
                    )
                sync.update(
                    {
                        "state": "attention"
                        if any(row.get("state") == "conflicted" for row in queue)
                        else "pending"
                        if any(row.get("state") in {"pending", "in-flight"} for row in queue)
                        else "idle",
                        "pending": sum(
                            row.get("state") in {"pending", "in-flight"} for row in queue
                        ),
                        "conflicted": sum(row.get("state") == "conflicted" for row in queue),
                        "done": sum(row.get("state") == "done" for row in queue),
                        "items": items,
                    }
                )
        except Exception as exc:
            components = [
                self._degraded_component_row(manifest, exc)
                for manifest in registry.list()
                if manifest.id in _COMPONENT_LABELS
            ]
            sync["detail"] = "Não foi possível ler a fila de sincronização."

        try:
            doctor_data, doctor_checks = self._doctor_runner()
            doctor_state = (
                "failed"
                if any(check.get("status") == "fail" for check in doctor_checks)
                else "attention"
                if any(check.get("status") == "warn" for check in doctor_checks)
                else "healthy"
            )
            doctor = {"state": doctor_state, "data": doctor_data, "checks": doctor_checks}
        except Exception as exc:
            doctor = {
                "state": "failed",
                "data": {},
                "checks": [{"name": "doctor", "status": "fail", "message": str(exc)[:240]}],
            }

        try:
            steam_gameplay = self._gameplay.snapshot(desktop_status)
        except Exception:
            steam_gameplay = {
                "games": [],
                "environment": [],
                "readiness": {
                    "percent": 0,
                    "title": "Gameplay Steam temporariamente indisponível",
                    "detail": "O restante da central continua disponível.",
                },
                "truthState": "degraded",
            }

        try:
            im_status = input_method_status()
        except Exception as exc:
            im_status = {
                "state": "unknown",
                "detail": str(exc)[:240],
                "configuredInputMethod": None,
                "preferredInputMethod": None,
                "serverRunning": False,
            }

        try:
            if self._emulation_builder is not None:
                emulation = self._emulation_builder(
                    probe=lambda emulator_id: self._which(emulator_id) is not None
                )
            else:
                emulation = self._emulation.snapshot(desktop_status)
            self._last_emulation = emulation
        except Exception as exc:
            # Um provider defeituoso não derruba o dashboard — mas também não
            # pode reescrever a verdade. O builder sem argumentos produz
            # keys/firmware "unverified" e biblioteca vazia: para o usuário isso
            # é indistinguível de "minhas keys sumiram", que foi exatamente o
            # sintoma relatado na a37.
            #
            # Preservar a última composição real mantém a UI honesta; a causa vai
            # para o log em vez de ser engolida (AGENTS.md §8).
            log.get_logger().warning(
                "dashboard.emulation-snapshot-failed", error=type(exc).__name__
            )
            if self._last_emulation is not None:
                emulation = self._last_emulation
            else:
                # Primeira composição já falhou: não há verdade a preservar. O
                # estado vazio é legítimo aqui, e o detalhe diz que a leitura
                # falhou, não que o usuário precisa importar algo.
                emulation = _unreadable_workspace()
        try:
            library_health = self._emulation.library_health()
        except Exception:
            library_health = {
                "schemaVersion": 1,
                "generatedAt": None,
                "state": "unchecked",
                "lastRun": None,
                "counts": {
                    "verified": 0,
                    "suspect": 0,
                    "missing": 0,
                    "error": 0,
                    "unavailable": 0,
                    "unchecked": 0,
                },
                "items": [],
                "activeJobs": [],
                "limits": {"maxFiles": 8, "maxBytes": 2 * 1024**3, "maxSeconds": 20},
            }

        # Sondas de acessibilidade são read-only e degradam para o padrão: a
        # ausência da preferência no host nunca impede o dashboard de responder.
        try:
            reduced_motion = self._reduced_motion_probe()
        except Exception:
            reduced_motion = False

        try:
            high_contrast = self._high_contrast_probe()
        except Exception:
            high_contrast = False

        try:
            diagnostics = self._diagnostics.snapshot(doctor=doctor, desktop_status=desktop_status)
        except Exception as exc:
            diagnostics = {
                "operations": {"page": 1, "pageSize": 20, "total": 0, "items": []},
                "adminHealth": {"available": False, "mode": "health-only"},
                "session": {"state": "unknown", "recoveryRequired": False},
                "sessionRecovery": {"available": False, "reason": str(exc)[:240]},
                "exports": {
                    "state": False,
                    "supportBundle": False,
                    "previewRequired": True,
                    "destinationRequired": True,
                },
            }

        try:
            playtime = self._playtime.list(limit=12)
            self._enrich_playtime(
                playtime,
                steam_games=steam_gameplay.get("games", []),
                emulation=emulation,
            )
        except Exception:
            playtime = {
                "schemaVersion": 1,
                "generatedAt": None,
                "totalPlayedSeconds": 0,
                "games": [],
                "page": {"limit": 12, "hasMore": False, "nextCursor": None},
                "state": "degraded",
                "detail": "O histórico de sessões está temporariamente indisponível.",
            }
        try:
            collections = self._collections.state(
                self._collection_games(
                    steam_games=steam_gameplay.get("games", []),
                    emulation=emulation,
                )
            )
            self._enrich_collection_state(playtime, collections)
        except Exception:
            collections = {
                "schemaVersion": 1,
                "generatedAt": None,
                "revision": 0,
                "tags": [],
                "favorites": [],
                "assignments": [],
                "collections": [],
                "state": "degraded",
            }

        try:
            if self._cast is not None:
                cast = {
                    "state": "available",
                    "status": self._cast.session_status(),
                    "activeSessions": self._cast.active_sessions(),
                    "detail": None,
                }
            else:
                cast = {
                    "state": "unavailable",
                    "status": None,
                    "activeSessions": [],
                    "detail": "O orquestrador de compartilhamento não foi configurado.",
                }
        except Exception as exc:
            cast = {
                "state": "degraded",
                "status": None,
                "activeSessions": [],
                "detail": str(exc)[:240],
            }

        try:
            theme = self._theme_state()
        except Exception:
            theme = {
                "activeId": "org.steamzero.default",
                "activeName": "Padrão",
                "available": [],
                "state": "degraded",
                "detail": "Catálogo de temas temporariamente indisponível.",
            }

        resources = self._resources.snapshot()
        current = desktop_status.get("current") if isinstance(desktop_status, dict) else {}
        profile = current.get("profile") if isinstance(current, dict) else {}
        touch_mode = bool(profile.get("touchMode")) if isinstance(profile, dict) else False
        return {
            "uiContracts": handheld_ui_contracts(),
            "theme": theme,
            "accessibility": {
                "reducedMotion": reduced_motion,
                "highContrast": high_contrast,
            },
            "components": components,
            "steam": self._steam.rows(desktop_status),
            "steamGameplay": steam_gameplay,
            "sync": sync,
            "doctor": doctor,
            "diagnostics": diagnostics,
            "inputMethod": im_status,
            "emulation": emulation,
            "playtime": playtime,
            "collections": collections,
            "libraryHealth": library_health,
            "cast": cast,
            "resources": resources,
            "touchMode": touch_mode,
        }

    def plan_emulation_emulator(self, emulator_id: str, action: str) -> dict[str, Any]:
        return self._emulation.plan_emulator(emulator_id, action)

    def apply_emulation_emulator(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        return self._emulation.apply_emulator(plan_id, confirm_token)

    def launch_emulation_emulator(self, emulator_id: str) -> dict[str, Any]:
        return self._emulation.launch_emulator(emulator_id)

    def stop_emulation_emulator(self, emulator_id: str) -> dict[str, Any]:
        return self._emulation.stop_emulator(emulator_id)

    def launch_emulation_game(self, game_id: str) -> dict[str, Any]:
        return self._emulation.launch_game(game_id)

    def launch_cloud_platform(self, platform_id: str) -> dict[str, Any]:
        return self._emulation.launch_cloud(platform_id)

    def plan_emulation_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._emulation.plan_action(payload)

    def apply_emulation_action(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        return self._emulation.apply_action(plan_id, confirm_token)

    def rollback_emulation_action(self, operation_id: str) -> dict[str, Any]:
        return self._emulation.rollback_action(operation_id)

    def bios_scan(self, source: str) -> dict[str, Any]:
        return self._emulation.bios_scan(Path(source))

    def bios_scan_status(self, scan_id: str) -> dict[str, Any]:
        return self._emulation.bios_scan_status(scan_id)

    def bios_import_plan(self, scan_id: str, selection: list[str] | None = None) -> dict[str, Any]:
        return self._emulation.bios_import_plan(scan_id, selection)

    def bios_import_apply(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        return self._emulation.bios_import_apply(plan_id, confirm_token)

    def bios_import_rollback(self, operation_id: str) -> dict[str, Any]:
        return self._emulation.bios_import_rollback(operation_id)

    def bios_status(self, platform_id: str | None = None) -> dict[str, Any]:
        return self._emulation.bios_status(platform_id)

    def bios_audit(self) -> dict[str, Any]:
        return self._emulation.bios_audit()

    def scan_emulation_library(self) -> dict[str, Any]:
        return self._emulation.scan_library()

    def get_emulation_job_status(self, job_id: str) -> dict[str, Any] | None:
        return self._emulation.get_job_status(job_id)

    def list_emulation_jobs(self) -> list[dict[str, Any]]:
        return self._emulation.list_jobs()

    def cancel_emulation_job(self, job_id: str) -> dict[str, Any]:
        return self._emulation.cancel_job(job_id)

    def retry_emulation_job(self, job_id: str) -> dict[str, Any]:
        return self._emulation.retry_job(job_id)

    def credential_status(self) -> dict[str, Any]:
        return self._emulation.credential_status()

    def save_credential(self, provider: str, credentials: dict[str, str]) -> dict[str, Any]:
        return self._emulation.save_credential(provider, credentials)

    def test_credential(self, provider: str) -> dict[str, Any]:
        return self._emulation.test_credential(provider)

    def delete_credential(self, provider: str) -> dict[str, Any]:
        return self._emulation.delete_credential(provider)

    def scraping_provider_link(self, provider: str, link: str) -> dict[str, str]:
        return self._emulation.provider_link(provider, link)

    def operations_history(self, page: int, page_size: int) -> dict[str, Any]:
        return self._diagnostics.operations(page=page, page_size=page_size)

    def operation_detail(self, operation_id: str) -> dict[str, Any]:
        return self._operation_history.get(operation_id)

    def plan_operation_rollback(self, operation_id: str) -> dict[str, Any]:
        return self._operation_history.plan_rollback(operation_id)

    def apply_operation_rollback(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        return self._operation_history.apply_rollback(plan_id, confirm_token)

    def collection_state(self) -> dict[str, Any]:
        return self._collections.state()

    def plan_collection_action(self, action: dict[str, Any]) -> dict[str, Any]:
        return self._collections.plan(action)

    def apply_collection_action(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        return self._collections.apply(plan_id, confirm_token)

    def library_health(self) -> dict[str, Any]:
        return self._emulation.library_health()

    def plan_library_health(self) -> dict[str, Any]:
        return self._emulation.plan_library_health()

    def apply_library_health(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        return self._emulation.apply_action(plan_id, confirm_token)

    def cast_discover(self, timeout_ms: int = 5000) -> list[dict[str, Any]]:
        if self._cast is None:
            return []
        return self._cast.discover_receivers(timeout_ms=timeout_ms)

    def cast_pair(self, receiver_id: str, pin: str | None = None) -> dict[str, Any]:
        if self._cast is None:
            raise SteamZeroError("E-CAST-UNAVAILABLE", detail="Orquestrador não configurado.")
        secret_pin = Secret(pin) if pin is not None else None
        paired = self._cast.pair_receiver(receiver_id, pin=secret_pin)
        return {"paired": paired, "receiverId": receiver_id}

    def cast_start(
        self,
        receiver_id: str,
        profile_id: str = "balanced",
        mode: str = "game",
        consent: CaptureConsent | None = None,
    ) -> dict[str, Any]:
        if self._cast is None:
            raise SteamZeroError("E-CAST-UNAVAILABLE", detail="Orquestrador não configurado.")
        return self._cast.start_stream(
            receiver_id,
            profile_id=profile_id,
            mode=mode,
            consent=consent,
        )

    def cast_stop(self) -> dict[str, Any]:
        if self._cast is None:
            raise SteamZeroError("E-CAST-UNAVAILABLE", detail="Orquestrador não configurado.")
        self._cast.stop_stream()
        return {"stopped": True}

    def cast_status(self) -> dict[str, Any]:
        if self._cast is None:
            return {"state": "unavailable", "detail": "Orquestrador não configurado."}
        result = self._cast.session_status()
        if result is None:
            return {"state": "idle", "detail": "Nenhuma sessão ativa."}
        return result

    def cast_sessions(self) -> list[dict[str, Any]]:
        if self._cast is None:
            return []
        return list(self._cast.active_sessions())

    def _rollback_component_for_history(self, operation_id: str) -> Any:
        with self._store_factory() as store:
            store.migrate()
            registry = self._registry_factory()
            lifecycle = ComponentLifecycle(
                store,
                registry,
                flatpak_factory=self._flatpak_factory,
                which=self._which,
                spawn=self._spawn,
            )
            return lifecycle.rollback(operation_id)

    def plan_diagnostics_export(
        self, destination: Path, kind: str, desktop_status: dict[str, Any]
    ) -> dict[str, Any]:
        doctor_data, doctor_checks = self._doctor_runner()
        plan, preview = self._diagnostics.plan_export(
            destination,
            kind=kind,
            doctor={"data": doctor_data, "checks": doctor_checks},
            desktop_status=desktop_status,
            resources=self._resources.snapshot(),
        )
        return {
            "plan": {
                "planId": plan.plan_id,
                "confirmToken": plan.confirm_token,
                "preview": plan.preview,
                "rollbackGuarantee": plan.rollback_guarantee,
                "requirements": plan.requirements,
            },
            "contentPreview": preview,
        }

    def apply_diagnostics_export(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        result = self._diagnostics.apply_export(plan_id, confirm_token)
        return {
            "status": result.status,
            "operationId": result.operation_id,
        }

    def admin_health(self) -> dict[str, Any]:
        return self._diagnostics.admin_health()

    def plan_steam_gameplay(
        self, payload: dict[str, Any], desktop_status: dict[str, Any]
    ) -> dict[str, Any]:
        return self._gameplay.plan(payload, desktop_status)

    def hud_presets(self) -> dict[str, Any]:
        return self._gameplay.hud_presets()

    def apply_steam_gameplay(
        self,
        plan_id: str,
        confirm_token: str,
        desktop_status: dict[str, Any],
    ) -> dict[str, Any]:
        return self._gameplay.apply(plan_id, confirm_token, desktop_status)

    def rollback_steam_gameplay(self, operation_id: str) -> dict[str, Any]:
        return self._gameplay.rollback_profile(operation_id)

    def recover_steam_gameplay(self, game_id: str) -> dict[str, Any]:
        return self._gameplay.recover_launcher(game_id)

    def plan_steam_launch_options(self, game_id: str) -> dict[str, Any]:
        return self._gameplay.plan_launch_options(game_id)

    def apply_steam_launch_options(
        self, plan_id: str, confirm_token: str, game_id: str
    ) -> dict[str, Any]:
        return self._gameplay.apply_launch_options(plan_id, confirm_token, game_id)

    def rollback_steam_launch_options(self, operation_id: str) -> dict[str, Any]:
        return self._gameplay.rollback_launch_options(operation_id)

    def plan_steam_maintenance(self, game_id: str, categories: Sequence[str]) -> dict[str, Any]:
        return self._gameplay.plan_maintenance(game_id, categories)

    def apply_steam_maintenance(
        self, plan_id: str, confirm_token: str, confirm_phrase: str
    ) -> dict[str, Any]:
        return self._gameplay.apply_maintenance(plan_id, confirm_token, confirm_phrase)

    def recover_steam_maintenance(self) -> dict[str, Any]:
        return self._gameplay.recover_maintenance()

    def plan_steam_media(self, game_id: str, account_id: str, package_dir: Path) -> dict[str, Any]:
        return self._gameplay.plan_media(game_id, account_id, package_dir)

    def apply_steam_media(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        return self._gameplay.apply_media(plan_id, confirm_token)

    def rollback_steam_media(self, operation_id: str) -> dict[str, Any]:
        return self._gameplay.rollback_media(operation_id)

    def plan_lsfg_install(self) -> dict[str, Any]:
        return self._gameplay.plan_lsfg_install()

    def apply_lsfg_install(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        return self._gameplay.apply_lsfg_install(plan_id, confirm_token)

    def rollback_lsfg_install(self, operation_id: str) -> dict[str, Any]:
        return self._gameplay.rollback_lsfg_install(operation_id)

    def list_components(self) -> list[dict[str, Any]]:
        """Publica somente os fatos de lifecycle que já são seguros de ler."""
        with self._store_factory() as store:
            store.migrate()
            lifecycle = ComponentLifecycle(
                store,
                self._registry_factory(),
                flatpak_factory=self._flatpak_factory,
                which=self._which,
                spawn=self._spawn,
            )
            return lifecycle.status_all()

    def component_status(self, component_id: str) -> dict[str, Any]:
        with self._store_factory() as store:
            store.migrate()
            lifecycle = ComponentLifecycle(
                store,
                self._registry_factory(),
                flatpak_factory=self._flatpak_factory,
                which=self._which,
                spawn=self._spawn,
            )
            return lifecycle.status(component_id)

    def verify_component(self, component_id: str) -> dict[str, Any]:
        """Verificação é leitura: não pede token nem produz uma operação."""
        with self._store_factory() as store:
            store.migrate()
            lifecycle = ComponentLifecycle(
                store,
                self._registry_factory(),
                flatpak_factory=self._flatpak_factory,
                which=self._which,
                spawn=self._spawn,
            )
            return lifecycle.verify(component_id)

    def component_capability_matrix(self) -> dict[str, Any]:
        """Matriz sanitizada; capabilities vêm dos manifests, não da UI."""
        registry = self._registry_factory()
        statuses = {item["id"]: item for item in self.list_components()}
        return {
            "components": [
                {
                    "componentId": manifest.id,
                    "kind": manifest.kind,
                    "capabilities": list(manifest.capabilities),
                    "status": statuses.get(manifest.id, {"state": "unavailable"}),
                }
                for manifest in registry.list()
            ]
        }

    def component_open_config_matrix(self) -> dict[str, Any]:
        """Decisão comprovável de configuração sem revelar argv ou paths.

        Nenhum dos emuladores ativos declara hoje um argumento upstream para
        abrir diretamente a tela de configuração.  A matriz deixa isso claro:
        a UI pode oferecer o lançamento normal como ``main-ui``, mas jamais
        rotulá-lo como ``open-config``.  A versão é a fonte já pinada pelo
        manifesto; a evidência aponta somente ao upstream público.
        """
        rows: list[dict[str, Any]] = []
        for manifest in self._registry_factory().list():
            if manifest.kind != "emulator":
                continue
            source = manifest.preferred_source(None, allow_eol=True)
            declared = manifest.raw.get("openConfig")
            arguments = declared.get("arguments") if isinstance(declared, dict) else None
            direct = isinstance(arguments, list) and bool(arguments)
            rows.append(
                {
                    "componentId": manifest.id,
                    "strategy": "direct" if direct else "main-ui",
                    "applicableStates": ["installed", "outdated"],
                    "action": "component.open-config" if direct else "component.launch",
                    "executor": route_for(manifest).executor,
                    "evidence": {
                        "upstream": manifest.upstream,
                        "version": source.version,
                    },
                    "reason": (
                        "O manifesto declara argumento atômico validado pelo upstream."
                        if direct
                        else (
                            "Nenhum argumento direto foi comprovado para a fonte pinada; "
                            "abra a UI principal."
                        )
                    ),
                }
            )
        return {"decisions": rows, "count": len(rows)}

    def plan_component(self, adapter_id: str, action: str) -> dict[str, Any]:
        with self._store_factory() as store:
            store.migrate()
            registry = self._registry_factory()
            lifecycle = ComponentLifecycle(
                store,
                registry,
                flatpak_factory=self._flatpak_factory,
                which=self._which,
                spawn=self._spawn,
            )
            return lifecycle.plan(adapter_id, action).to_dict()

    def apply_component(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        with self._store_factory() as store:
            store.migrate()
            registry = self._registry_factory()
            lifecycle = ComponentLifecycle(
                store,
                registry,
                flatpak_factory=self._flatpak_factory,
                which=self._which,
                spawn=self._spawn,
            )
            return lifecycle.apply(plan_id, confirm_token)

    def launch_component(self, adapter_id: str) -> dict[str, Any]:
        with self._store_factory() as store:
            store.migrate()
            registry = self._registry_factory()
            lifecycle = ComponentLifecycle(
                store,
                registry,
                flatpak_factory=self._flatpak_factory,
                which=self._which,
                spawn=self._spawn,
            )
            return lifecycle.launch(adapter_id)

    def component_operation_history(self, adapter_id: str) -> dict[str, Any]:
        """Histórico limitado a operações cujo dono é o componente solicitado."""
        with self._store_factory() as store:
            store.migrate()
            lifecycle = ComponentLifecycle(
                store,
                self._registry_factory(),
                flatpak_factory=self._flatpak_factory,
                which=self._which,
                spawn=self._spawn,
            )
            lifecycle.status(adapter_id)  # valida o id pelo registro, sem mutação
            history = self._operation_history.list(limit=100)
            items: list[dict[str, Any]] = []
            for item in history["items"]:
                try:
                    owner = lifecycle._operation_adapter_id(str(item["operationId"]))
                except SteamZeroError:
                    # Histórico corrompido não é evidência de pertencimento.
                    # A tela continua útil e o item permanece acessível apenas
                    # pelo diagnóstico global que mostra sua integridade.
                    continue
                if owner == adapter_id:
                    items.append(item)
        return {"componentId": adapter_id, "operations": items, "count": len(items)}

    def plan_component_rollback(self, adapter_id: str, operation_id: str) -> dict[str, Any]:
        """Planeja rollback somente da operação auditável do componente pedido."""
        with self._store_factory() as store:
            store.migrate()
            lifecycle = ComponentLifecycle(
                store,
                self._registry_factory(),
                flatpak_factory=self._flatpak_factory,
                which=self._which,
                spawn=self._spawn,
            )
            owner = lifecycle._operation_adapter_id(operation_id)
        if owner != adapter_id:
            raise SteamZeroError(
                "E-API-SCHEMA",
                detail="operationId não pertence ao componente solicitado",
                operation_id=operation_id,
            )
        return self._operation_history.plan_rollback(operation_id)

    def apply_component_rollback(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        return self._operation_history.apply_rollback(plan_id, confirm_token)

    def open_steam(self, target: str) -> dict[str, Any]:
        return self._steam.open(target)

    def launch_steam_game(self, game_id: str) -> dict[str, Any]:
        return self._steam.open_game(game_id)

    def open_steam_input(self, game_id: str) -> dict[str, Any]:
        return self._steam.open_controller_config(game_id)

    def _enrich_playtime(
        self,
        playtime: dict[str, Any],
        *,
        steam_games: object,
        emulation: object,
    ) -> None:
        catalog: dict[tuple[str, str], dict[str, str]] = {}
        if isinstance(steam_games, list):
            for game in steam_games:
                if not isinstance(game, dict):
                    continue
                game_id = game.get("id")
                if isinstance(game_id, str):
                    catalog[("steam", game_id)] = {
                        "title": str(game.get("name") or ""),
                        "coverUrl": str(game.get("coverUrl") or ""),
                    }
        if isinstance(emulation, dict):
            platforms = emulation.get("platforms")
            if isinstance(platforms, list):
                for platform in platforms:
                    if not isinstance(platform, dict):
                        continue
                    games = platform.get("games")
                    if not isinstance(games, list):
                        continue
                    for game in games:
                        if not isinstance(game, dict):
                            continue
                        game_id = game.get("id")
                        if isinstance(game_id, str):
                            catalog[("emulation", game_id)] = {
                                "title": str(game.get("name") or ""),
                                "coverUrl": str(
                                    game.get("coverUrl") or game.get("bannerAsset") or ""
                                ),
                            }
        games = playtime.get("games")
        if not isinstance(games, list):
            return
        for game in games:
            if not isinstance(game, dict):
                continue
            enrichment = catalog.get((str(game.get("source") or ""), str(game.get("gameId") or "")))
            if enrichment is None:
                continue
            if enrichment["title"]:
                game["title"] = enrichment["title"][:160]
            if enrichment["coverUrl"]:
                game["coverUrl"] = enrichment["coverUrl"][:4096]
            if game.get("source") != "steam" or game.get("continueState") != "in-progress":
                continue
            status_reader = getattr(self._gameplay, "session_status", None)
            if not callable(status_reader):
                continue
            try:
                status = status_reader(str(game.get("gameId") or ""))
            except Exception as exc:
                _log.debug("playtime.session-status-unavailable", exc_info=exc)
                continue
            if isinstance(status, dict) and status.get("recoveryRequired") is True:
                game["continueState"] = "interrupted"
                game["action"] = {
                    "kind": "steam-recover",
                    "target": str(game.get("gameId") or ""),
                    "label": "Recuperar sessão",
                    "enabled": True,
                    "reason": "",
                }

    @staticmethod
    def _collection_games(*, steam_games: object, emulation: object) -> list[dict[str, Any]]:
        games: list[dict[str, Any]] = []
        if isinstance(steam_games, list):
            for game in steam_games:
                if isinstance(game, dict) and isinstance(game.get("id"), str):
                    games.append(
                        {
                            "gameRef": f"steam:{game['id']}",
                            "source": "steam",
                            "platformId": "steam",
                            "title": str(game.get("name") or ""),
                        }
                    )
        if isinstance(emulation, dict) and isinstance(emulation.get("platforms"), list):
            for platform in emulation["platforms"]:
                if not isinstance(platform, dict) or not isinstance(platform.get("games"), list):
                    continue
                platform_id = str(platform.get("id") or "unknown")
                for game in platform["games"]:
                    if isinstance(game, dict) and isinstance(game.get("id"), str):
                        games.append(
                            {
                                "gameRef": f"emulation:{game['id']}",
                                "source": "emulation",
                                "platformId": platform_id,
                                "title": str(game.get("name") or ""),
                            }
                        )
        return games

    @staticmethod
    def _enrich_collection_state(playtime: dict[str, Any], collections: dict[str, Any]) -> None:
        favorites = set(collections.get("favorites", []))
        assignments = {
            item["gameRef"]: item["tagIds"]
            for item in collections.get("assignments", [])
            if isinstance(item, dict)
        }
        games = playtime.get("games")
        if not isinstance(games, list):
            return
        for game in games:
            if not isinstance(game, dict):
                continue
            game_ref = f"{game.get('source', '')}:{game.get('gameId', '')}"
            game["gameRef"] = game_ref
            game["favorite"] = game_ref in favorites
            game["tagIds"] = assignments.get(game_ref, [])

    def _component_row(
        self, manifest: AdapterManifest, lifecycle: ComponentLifecycle, *, conflicts: bool
    ) -> dict[str, Any]:
        try:
            status = lifecycle.status(manifest.id)
        except Exception as exc:
            return self._degraded_component_row(manifest, exc)
        raw_state = str(status["state"])
        installed = raw_state in {"installed", "degraded"}
        version = status.get("version")
        target_version = status.get("targetVersion")
        pinned = bool(version and version == target_version)
        end_of_life = bool(status.get("endOfLife"))

        if end_of_life and not installed:
            state = "unsupported"
            status_label = "Fonte descontinuada"
        elif raw_state == "missing":
            state = "missing"
            status_label = "Não instalado"
        elif raw_state == "degraded":
            state = "attention"
            status_label = "Reparar"
        elif raw_state == "unavailable":
            state = "attention"
            status_label = "Indisponível"
        else:
            state = "installed"
            status_label = "Instalado"

        installable = bool(status.get("installable"))

        if state == "unsupported":
            action = {"kind": "detail", "label": "Indisponível", "enabled": False}
            blocked_reason = "A origem pinada está end-of-life e não será promovida."
        elif state in {"missing", "attention"}:
            action = {
                "kind": "component-plan",
                "label": (
                    "Instalar"
                    if state == "missing"
                    else "Reparar"
                    if raw_state == "degraded"
                    else "Verificar"
                ),
                "enabled": not conflicts and installable,
                "operation": "repair" if raw_state == "degraded" else "install",
            }
            blocked_reason = (
                "Resolva o conflito de controle antes de alterar o componente."
                if conflicts
                else str(status.get("detail") or "")
                if raw_state == "unavailable"
                else "O componente não declara fonte instalável."
                if not installable
                else ""
            )
        else:
            action = {
                "kind": "component-launch",
                "label": "Configurar" if "configure" in manifest.capabilities else "Abrir",
                "enabled": True,
            }
            blocked_reason = ""

        label, description, icon_name = _COMPONENT_LABELS.get(
            manifest.id, (manifest.id.title(), "Componente de emulação", "applications-games")
        )
        current = str(version) if version else "—"
        target = str(target_version) if target_version else "—"
        return {
            "id": manifest.id,
            "name": label,
            "description": description,
            "iconName": icon_name,
            "systems": [_PLATFORM_LABELS.get(value, value) for value in manifest.platforms],
            "state": state,
            "statusLabel": status_label,
            "versionLabel": current[:8],
            "targetVersion": target[:8],
            "pinned": pinned,
            "endOfLife": end_of_life,
            "detail": (
                "A configuração e os dados do emulador são preservados durante rollback."
                if not end_of_life
                else (
                    "A fonte atual está descontinuada; o SteamZero não instala versões "
                    "sem origem validada."
                )
            ),
            "blockedReason": blocked_reason,
            "action": action,
        }

    def _degraded_component_row(
        self, manifest: AdapterManifest, error: Exception
    ) -> dict[str, Any]:
        label, description, icon_name = _COMPONENT_LABELS.get(
            manifest.id, (manifest.id.title(), "Componente de emulação", "applications-games")
        )
        return {
            "id": manifest.id,
            "name": label,
            "description": description,
            "iconName": icon_name,
            "systems": [_PLATFORM_LABELS.get(value, value) for value in manifest.platforms],
            "state": "attention",
            "statusLabel": "Verificação indisponível",
            "versionLabel": "—",
            "targetVersion": "—",
            "pinned": False,
            "endOfLife": False,
            "detail": str(error)[:240],
            "blockedReason": "Verifique o runtime Flatpak antes de continuar.",
            "action": {"kind": "detail", "label": "Ver detalhes", "enabled": True},
        }

    def _theme_state(self) -> dict[str, Any]:
        catalog = self._theme_catalog.list_catalog()
        preference = self._theme_prefs._read_preference()
        active_id: str = str(preference.get("themeId")) if preference else "org.steamzero.default"
        active_name = active_id
        for entry in catalog:
            if entry["id"] == active_id and entry["state"] == "available":
                active_name = entry["name"]
                break
        available = [
            {
                "id": e["id"],
                "name": e["name"],
                "version": e["version"],
                "author": e["author"],
                "origin": e["origin"],
                "state": e["state"],
                "compatible": e["compatible"],
                "active": e["id"] == active_id,
            }
            for e in catalog
        ]
        high_contrast = False
        reduced_motion = False
        with contextlib.suppress(Exception):
            high_contrast = self._high_contrast_probe()
        with contextlib.suppress(Exception):
            reduced_motion = self._reduced_motion_probe()
        try:
            resolved = self._theme_catalog.resolve(
                active_id, high_contrast=high_contrast, reduced_motion=reduced_motion
            )
        except Exception:
            qml_object = None
            return {
                "activeId": active_id,
                "activeName": active_name,
                "available": available,
                "resolved": None,
                "state": "ready",
                "detail": None,
            }
        qml_object = resolved.to_theme_qml_object()
        return {
            "activeId": active_id,
            "activeName": active_name,
            "available": available,
            "resolved": qml_object,
            "state": "ready",
            "detail": None,
        }

    def theme_list(self) -> list[dict[str, Any]]:
        return self._theme_catalog.list_catalog()

    # -- theme editor --------------------------------------------------

    def editor_load(self, theme_id: str) -> dict[str, object]:
        return self._theme_editor.load(theme_id)

    def editor_create(self, name: str, extends: str = "org.steamzero.default") -> dict[str, object]:
        return self._theme_editor.create(name, extends)

    def editor_set_tokens(
        self, session_id: str, category: str, values: dict[str, object]
    ) -> dict[str, object]:
        return self._theme_editor.set_tokens(session_id, category, values)

    def editor_set_metadata(
        self, session_id: str, meta_field: str, value: object
    ) -> dict[str, object]:
        return self._theme_editor.set_metadata(session_id, meta_field, value)

    def editor_preview(
        self, session_id: str, *, high_contrast: bool = False, reduced_motion: bool = False
    ) -> dict[str, object]:
        return self._theme_editor.preview(
            session_id, high_contrast=high_contrast, reduced_motion=reduced_motion
        )

    def editor_save(self, session_id: str, *, overwrite: bool = False) -> dict[str, str]:
        return self._theme_editor.save(session_id, overwrite=overwrite)

    def editor_export_zip(self, session_id: str) -> bytes:
        return self._theme_editor.export_zip(session_id)

    def editor_cancel(self, session_id: str) -> dict[str, str]:
        return self._theme_editor.cancel(session_id)

    def plan_theme_apply(self, theme_id: str) -> dict[str, Any]:
        previous = self._theme_prefs._read_preference()
        version = "1.0.0"
        for entry in self._theme_catalog.list_catalog():
            if entry["id"] == theme_id and entry["compatible"]:
                version = entry["version"]
                break
        else:
            raise SteamZeroError(
                "E-THEME-NOT-FOUND",
                detail=f"tema {theme_id} não encontrado ou incompatível",
            )
        plan = self._theme_prefs.plan_activate(theme_id, version, previous=previous)
        return {
            "planId": plan.plan_id,
            "confirmToken": plan.confirm_token,
            "preview": plan.preview,
            "rollbackGuarantee": plan.rollback_guarantee,
        }

    @staticmethod
    def apply_theme_preference(plan_id: str, confirm_token: str) -> dict[str, Any]:
        result = ThemePreferenceManager().apply(plan_id, confirm_token)
        return {"status": result.status, "operationId": result.operation_id}

    @staticmethod
    def rollback_theme(operation_id: str) -> dict[str, Any]:
        result = ThemePreferenceManager().rollback(operation_id)
        return {"status": result.status, "operationId": result.operation_id}

    @staticmethod
    def _conflicts(desktop_status: dict[str, Any]) -> list[str]:
        context = desktop_status.get("context")
        if not isinstance(context, dict):
            return []
        conflicts = context.get("conflicts")
        if not isinstance(conflicts, list):
            return []
        return [value for value in conflicts if isinstance(value, str)]
