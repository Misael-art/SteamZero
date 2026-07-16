# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Read model e ações allowlisted do dashboard Desktop.

O dashboard agrega capacidades existentes sem transformar a UI em um segundo
núcleo: lifecycle de emuladores continua no executor Flatpak transacional,
diagnóstico continua no doctor e Steam é uma integração opcional. Ausência de
qualquer provider degrada somente a linha correspondente.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from steamzero.adapters.flatpak import FlatpakCLI, FlatpakExecutor
from steamzero.adapters.registry import AdapterManifest, AdapterRegistry
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.diagnostics.doctor import run_doctor

Spawn = Callable[[Sequence[str]], None]
StoreFactory = Callable[[], StateStore]
RegistryFactory = Callable[[], AdapterRegistry]
DoctorRunner = Callable[[], tuple[dict[str, Any], list[dict[str, str]]]]

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


def _steam_process_running() -> bool:
    """Detecta Steam sem depender de pgrep, DBus ou serviço systemd."""
    proc = Path("/proc")
    try:
        entries = proc.iterdir()
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
                "versionLabel": "Gerenciado pelo BigLinux" if installed else "—",
                "detail": (
                    "O Steam está pronto para abrir sua biblioteca."
                    if installed
                    else "Instale o cliente Steam pelos repositórios do BigLinux."
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
        which: Callable[[str], str | None] = shutil.which,
        spawn: Spawn = _spawn_detached,
    ) -> None:
        self._store_factory = store_factory
        self._registry_factory = registry_factory
        self._flatpak_factory = flatpak_factory
        self._doctor_runner = doctor_runner
        self._steam = steam or SteamDesktopController(which=which, spawn=spawn)
        self._which = which
        self._spawn = spawn

    def snapshot(self, desktop_status: dict[str, Any]) -> dict[str, Any]:
        conflicts = self._conflicts(desktop_status)
        registry = self._registry_factory()
        components: list[dict[str, Any]] = []
        sync = {"state": "unavailable", "pending": 0, "conflicted": 0, "done": 0}
        try:
            with self._store_factory() as store:
                store.migrate()
                executor = FlatpakExecutor(store, registry, self._flatpak_factory())
                components = [
                    self._component_row(manifest, executor, conflicts=bool(conflicts))
                    for manifest in registry.list()
                ]
                queue = store.list_sync_queue()
                sync = {
                    "state": "attention"
                    if any(row.get("state") == "conflicted" for row in queue)
                    else "pending"
                    if any(row.get("state") in {"pending", "in-flight"} for row in queue)
                    else "idle",
                    "pending": sum(row.get("state") in {"pending", "in-flight"} for row in queue),
                    "conflicted": sum(row.get("state") == "conflicted" for row in queue),
                    "done": sum(row.get("state") == "done" for row in queue),
                }
        except Exception as exc:
            components = [
                self._degraded_component_row(manifest, exc) for manifest in registry.list()
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

        return {
            "components": components,
            "steam": self._steam.rows(desktop_status),
            "sync": sync,
            "doctor": doctor,
        }

    def plan_component(self, adapter_id: str) -> dict[str, Any]:
        with self._store_factory() as store:
            store.migrate()
            registry = self._registry_factory()
            executor = FlatpakExecutor(store, registry, self._flatpak_factory())
            return executor.plan_install(adapter_id).to_dict()

    def apply_component(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        with self._store_factory() as store:
            store.migrate()
            registry = self._registry_factory()
            executor = FlatpakExecutor(store, registry, self._flatpak_factory())
            return executor.apply(plan_id, confirm_token).to_dict()

    def launch_component(self, adapter_id: str) -> dict[str, Any]:
        with self._store_factory() as store:
            store.migrate()
            registry = self._registry_factory()
            executor = FlatpakExecutor(store, registry, self._flatpak_factory())
            status = executor.status(adapter_id)
            if status["state"] == "missing":
                raise SteamZeroError(
                    "E-COMPONENT-DEGRADED", detail=f"{adapter_id} não está instalado"
                )
            manifest = registry.get(adapter_id)
            source = manifest.preferred_source("flatpak")
            executable = self._which("flatpak")
            if executable is None or source.ref is None:
                raise SteamZeroError("E-COMPONENT-DEGRADED", detail="runtime Flatpak indisponível")
            self._spawn((executable, "run", "--user", source.ref))
            return {"status": "started", "componentId": adapter_id}

    def open_steam(self, target: str) -> dict[str, Any]:
        return self._steam.open(target)

    def _component_row(
        self, manifest: AdapterManifest, executor: FlatpakExecutor, *, conflicts: bool
    ) -> dict[str, Any]:
        try:
            status = executor.status(manifest.id)
        except Exception as exc:
            return self._degraded_component_row(manifest, exc)
        source = manifest.preferred_source("flatpak")
        raw_state = str(status["state"])
        installed = raw_state != "missing"
        pinned = bool(status.get("pinned"))
        end_of_life = bool(status.get("endOfLife"))

        if end_of_life and not installed:
            state = "unsupported"
            status_label = "Fonte descontinuada"
        elif raw_state == "missing":
            state = "missing"
            status_label = "Não instalado"
        elif raw_state == "degraded":
            state = "attention"
            status_label = "Atualização disponível"
        else:
            state = "installed"
            status_label = "Instalado"

        if state == "unsupported":
            action = {"kind": "detail", "label": "Indisponível", "enabled": False}
            blocked_reason = "A origem pinada está end-of-life e não será promovida."
        elif state in {"missing", "attention"}:
            action = {
                "kind": "component-plan",
                "label": "Instalar" if state == "missing" else "Atualizar",
                "enabled": not conflicts,
            }
            blocked_reason = (
                "Resolva o conflito de controle antes de alterar o componente." if conflicts else ""
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
        commit = status.get("commit")
        version = str(commit)[:8] if isinstance(commit, str) and commit else "—"
        target_version = source.version[:8]
        return {
            "id": manifest.id,
            "name": label,
            "description": description,
            "iconName": icon_name,
            "systems": [_PLATFORM_LABELS.get(value, value) for value in manifest.platforms],
            "state": state,
            "statusLabel": status_label,
            "versionLabel": version,
            "targetVersion": target_version,
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

    @staticmethod
    def _conflicts(desktop_status: dict[str, Any]) -> list[str]:
        context = desktop_status.get("context")
        if not isinstance(context, dict):
            return []
        conflicts = context.get("conflicts")
        if not isinstance(conflicts, list):
            return []
        return [value for value in conflicts if isinstance(value, str)]
