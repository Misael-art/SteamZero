# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Orquestração da central Switch: lifecycle, biblioteca e conteúdo local."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from steamzero.adapters.converters import (
    NszConverter,
    NszToolManager,
    SwitchRomConversionService,
    ToolRegistry,
    nsz_tool_manifest,
)
from steamzero.adapters.engine import AdapterEngine, HttpsArtifactPort, PreparedComponent
from steamzero.adapters.registry import AdapterRegistry
from steamzero.adapters.steam_shortcuts import SteamShortcutManager
from steamzero.api import contracts
from steamzero.core import fs, ids, journal, paths, safezip, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain.emulation_workspace import build_switch_workspace
from steamzero.domain.switch_content import SwitchContentManager
from steamzero.domain.switch_library import SwitchLibraryScanner

StoreFactory = Callable[[], StateStore]
RegistryFactory = Callable[[], AdapterRegistry]
Spawn = Callable[[Sequence[str]], int | None]

_MANAGED_EMULATORS = frozenset({"eden", "citron", "ryubing"})

_EMULATOR_PRESENTATION = {
    "eden": ("Eden", "../assets/eden.svg"),
    "citron": ("Citron", "../assets/citron.svg"),
    "ryubing": ("Ryubing", "../assets/ryubing.png"),
}
_TITLE_ID = re.compile(r"^[0-9A-F]{16}$")
_FIRMWARE_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){0,3}$")
_KEY_LINE = re.compile(r"^\s*([a-z0-9_]+)\s*=\s*([0-9a-fA-F]{32,})\s*$")
_MASTER_KEY = re.compile(r"^master_key_([0-9a-f]{2})$")
_MAX_IMPORT_FILES = 10_000
_MAX_IMPORT_BYTES = 2 * 1024**3


@dataclass(frozen=True)
class _PendingMutation:
    kind: str
    metadata: Mapping[str, Any]


def _spawn_detached(argv: Sequence[str]) -> int:
    process = subprocess.Popen(  # noqa: S603
        list(argv),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env={**os.environ, "APPIMAGELAUNCHER_DISABLE": "true"},
    )
    return process.pid


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
        shortcuts: SteamShortcutManager | None = None,
    ) -> None:
        self._store_factory = store_factory
        self._registry_factory = registry_factory
        self._artifacts = artifacts or HttpsArtifactPort()
        self._which = which
        self._spawn = spawn
        self._shortcuts = shortcuts or SteamShortcutManager()
        self._nsz = NszToolManager()
        self._prepared_emulators: dict[str, PreparedComponent] = {}
        self._pending: dict[str, _PendingMutation] = {}
        self._running_pids: dict[str, int] = {}
        self._content = SwitchContentManager(paths.data_home() / "switch-content")

    @property
    def _roots_path(self) -> Path:
        return paths.config_home() / "emulation-library-v1.json"

    @property
    def _library_cache_path(self) -> Path:
        return paths.data_home() / "emulation-library-cache-v1.json"

    @property
    def _game_settings_path(self) -> Path:
        return paths.config_home() / "emulation-games-v1.json"

    def snapshot(self, desktop_status: Mapping[str, Any]) -> dict[str, Any]:
        emulator_rows = self._emulator_rows()
        games, unidentified = self._load_library_cache()
        roots = self.library_roots()
        key_status, firmware_status = self._requirements(emulator_rows)
        games = self._enrich_games(games, emulator_rows, key_status, firmware_status)
        content = self._content.list_records()
        integrity = self._content.integrity_report()
        physical_dock = self._physical_dock(desktop_status)
        controllers = self._controller_count()

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
        )
        platform = workspace["platforms"][0]
        platform["emulators"] = emulator_rows
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
                "graphicsPerformance": "Perfil observado",
                "controls": f"{controllers} controle(s)",
                "saves": "Backup local",
                "shaderCache": "Cache por jogo",
                "media": f"{len(roots)} diretório(s)",
                "storage": str(integrity["state"]),
                "advanced": "Ferramentas locais",
            }[area_id]
        contracts.validate(workspace, "emulation-workspace-v1.schema.json")
        return workspace

    def plan_emulator(self, emulator_id: str, action: str) -> dict[str, Any]:
        self._require_managed_emulator(emulator_id)
        with self._store_factory() as store:
            store.migrate()
            engine = AdapterEngine(store, self._registry_factory(), self._artifacts)
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

    def launch_emulator(self, emulator_id: str) -> dict[str, Any]:
        self._require_managed_emulator(emulator_id)
        with self._store_factory() as store:
            store.migrate()
            engine = AdapterEngine(store, self._registry_factory(), self._artifacts)
            payload = engine.payload_path(emulator_id)
        if self._managed_process_groups(payload):
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail=f"{emulator_id} já está em execução"
            )
        pid = self._spawn(self._appimage_argv(payload))
        if isinstance(pid, int) and pid > 1:
            self._running_pids[emulator_id] = pid
        return {"status": "started", "emulatorId": emulator_id, "pid": pid}

    def stop_emulator(self, emulator_id: str) -> dict[str, Any]:
        self._require_managed_emulator(emulator_id)
        with self._store_factory() as store:
            store.migrate()
            engine = AdapterEngine(store, self._registry_factory(), self._artifacts)
            payload = engine.payload_path(emulator_id)
        groups = self._managed_process_groups(payload)
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
        game_settings = self._settings_for_game(game, settings)
        emulator_id = game_settings.get("emulatorId")
        if not isinstance(emulator_id, str):
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail="defina o emulador padrão deste jogo"
            )
        self._require_managed_emulator(emulator_id)
        with self._store_factory() as store:
            store.migrate()
            engine = AdapterEngine(store, self._registry_factory(), self._artifacts)
            payload = engine.payload_path(emulator_id)
        rom = Path(str(game["path"]))
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
        if self._managed_process_groups(payload):
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail=f"{emulator_id} já está em execução"
            )
        pid = self._spawn(self._launch_argv(emulator_id, payload, rom))
        if isinstance(pid, int) and pid > 1:
            self._running_pids[emulator_id] = pid
        return {
            "status": "started",
            "gameId": game_id,
            "emulatorId": emulator_id,
            "name": str(game["name"]),
            "pid": pid,
        }

    def library_roots(self) -> list[str]:
        candidates = [
            paths.roms_dir(),
            Path.home() / "Emulation" / "roms",
            Path.home() / "emulation" / "roms",
            Path.home() / "Games" / "ROMs",
            Path.home() / "Games" / "roms",
            Path.home() / "ROMs",
            Path.home() / "roms",
        ]
        candidates.extend(self._custom_roots())
        result: list[str] = []
        seen: set[Path] = set()
        for candidate in candidates:
            try:
                resolved = candidate.resolve(strict=True)
            except OSError:
                continue
            if resolved in seen or resolved.is_symlink() or not resolved.is_dir():
                continue
            seen.add(resolved)
            result.append(str(resolved))
        return result

    def scan_library(self) -> dict[str, Any]:
        scanner = SwitchLibraryScanner()
        discovered: dict[str, dict[str, Any]] = {}
        auxiliary: list[Any] = []
        unidentified = 0
        errors: list[str] = []
        for raw_root in self.library_roots():
            root = Path(raw_root)
            try:
                matches = scanner.inventory(root)
            except (OSError, SteamZeroError) as exc:
                errors.append(f"{root}: {exc}")
                continue
            for match in matches:
                if match.content_kind != "base":
                    auxiliary.append(match)
                    continue
                try:
                    stat = match.path.stat()
                except OSError as exc:
                    errors.append(f"{match.path}: {exc}")
                    continue
                fingerprint = hashlib.sha256(
                    f"{match.path}\0{stat.st_size}\0{stat.st_mtime_ns}".encode()
                ).hexdigest()
                identity_verified = match.title_id is not None
                if not identity_verified:
                    unidentified += 1
                stable_id = hashlib.sha256(str(match.path).encode()).hexdigest()[:24]
                banner_asset, media_source = self._cover_asset(match.title_id)
                discovered[str(match.path)] = {
                    "id": stable_id,
                    "titleId": match.title_id,
                    "name": scanner.clean_display_name(match.path),
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
                    "metadataSource": match.metadata_source,
                    "version": f"v{match.version}" if match.version is not None else None,
                    "updateCount": 0,
                    "updateVersion": None,
                    "dlcCount": 0,
                    "bannerAsset": banner_asset,
                    "mediaSource": media_source,
                }
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
        }
        fs.write_atomic_text(
            self._library_cache_path,
            json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")),
        )
        return {
            "status": "scanned",
            "games": len(game_rows),
            "unidentified": unidentified,
            "errors": errors[:20],
            "ignoredAuxiliary": len(auxiliary),
        }

    def plan_action(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        action = self._required_string(payload, "actionId")
        if action == "library.root.add":
            plan = self._plan_root_add(Path(self._required_string(payload, "path")))
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
        elif action.startswith("content.state:"):
            parts = action.split(":")
            if len(parts) != 3 or re.fullmatch(r"[0-9a-f]{64}", parts[1]) is None:
                raise SteamZeroError("E-API-SCHEMA", detail="identificador de conteúdo inválido")
            plan = self._content.plan_set_active(parts[1], active=parts[2] == "on")
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
        elif action == "game.emulator.set":
            game_id = self._required_string(payload, "gameId")
            self._current_game(game_id)
            emulator_id = self._required_string(payload, "emulatorId")
            self._require_managed_emulator(emulator_id)
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
        elif action == "steam.shortcuts.sync":
            settings = self._load_game_settings(strict=True)
            games, _unidentified = self._load_library_cache()
            selected = [
                self._current_game(str(game["id"]))
                for game in games
                if self._settings_for_game(game, settings).get("steamSelected") is True
            ]
            plan = self._shortcuts.plan(selected)
        elif action == "game.delete":
            game_id = self._required_string(payload, "gameId")
            game = self._current_game(game_id)
            source = Path(str(game["path"])).resolve(strict=True)
            root = self._root_for_game(source)
            plan = transaction.plan_write_files(
                {}, root=root, removals={source}, kind=f"emulation.game-delete:{game_id}"
            )
        else:
            raise SteamZeroError("E-API-SCHEMA", detail="ação de emulação não permitida")
        return self._plan_view(plan, action)

    def apply_action(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
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
        elif plan.kind == "switch-content.recover":
            result = self._content.apply_recovery(plan_id, confirm_token)
        elif plan.kind == "steam.shortcuts.sync":
            result = self._shortcuts.apply(plan_id, confirm_token)
        elif plan.kind.startswith("emulation."):
            result = transaction.apply(plan_id, confirm_token)
        else:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não pertence à emulação")
        pending = self._pending.pop(plan_id, None)
        if pending is not None:
            self._persist_import(pending)
        response: dict[str, Any] = {
            "status": result.status,
            "operationId": result.operation_id,
        }
        if plan.kind == "emulation.library-roots" or plan.kind.startswith(
            "emulation.game-delete:"
        ):
            response["library"] = self.scan_library()
        return response

    def rollback_action(self, operation_id: str) -> dict[str, Any]:
        if not ids.is_ulid(operation_id):
            raise SteamZeroError("E-API-SCHEMA", detail="operationId inválido")
        records = journal.read_records(operation_id)
        begins = [record for record in records if record.get("type") == "operation.begin"]
        if len(begins) != 1 or not str(begins[0].get("kind", "")).startswith(
            "emulation.game-delete:"
        ):
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail="operação não pertence à exclusão de ROM"
            )
        result = transaction.rollback(operation_id, reason="emulation-user-request")
        return {
            "status": result.status,
            "operationId": result.operation_id,
            "restored": result.restored,
            "library": self.scan_library(),
        }

    def _emulator_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        registry = self._registry_factory()
        with self._store_factory() as store:
            store.migrate()
            engine = AdapterEngine(store, registry, self._artifacts)
            for emulator_id, (name, icon_asset) in _EMULATOR_PRESENTATION.items():
                manifest = registry.get(emulator_id)
                status = engine.status(emulator_id)
                source = manifest.preferred_source("appimage", allow_eol=False)
                installed = status["state"] == "installed"
                current = str(status.get("version", "—"))
                up_to_date = installed and current == source.version
                actions = (
                    [
                        self._action(f"emulator.launch:{emulator_id}", "Abrir"),
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
                    if installed
                    else [
                        self._action(
                            f"emulator.install:{emulator_id}", "Instalar", confirmation=True
                        )
                    ]
                )
                if installed and self._managed_process_groups(engine.payload_path(emulator_id)):
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
                        "platform": "switch",
                        "state": "ready" if installed else "unavailable",
                        "statusLabel": "Instalado" if installed else "Não instalado",
                        "installState": "installed" if installed else "not-installed",
                        "sourceState": "verified",
                        "installable": True,
                        "version": current,
                        "targetVersion": source.version,
                        "specialty": "AppImage verificado, configuração e dados preservados",
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
            str(row["id"])
            for row in emulators
            if row.get("installState") == "installed"
        ]
        missing_projections = [
            emulator_id
            for emulator_id in installed_emulators
            if not self._key_projection_valid(emulator_id)
        ]
        key_status = (
            "missing"
            if key_revision is None
            else "unverified"
            if missing_projections
            else "ok"
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
    ) -> dict[str, Any]:
        updates = [record for record in records if record.kind == "update"]
        dlcs = [record for record in records if record.kind == "dlc"]
        saves = [record for record in records if record.kind == "save"]
        shaders = [record for record in records if record.kind == "shader-cache"]
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
                            f"Title ID {record.title_id} · versão "
                            f"{record.version or 'não informada'}"
                        ),
                        "ready" if record.state == "active" else "attention",
                        "Ativo" if record.state == "active" else "Inativo",
                        action=self._action(
                            (
                                f"content.state:{record.record_key}:off"
                                if record.state == "active"
                                else f"content.state:{record.record_key}:on"
                            ),
                            "Desativar" if record.state == "active" else "Ativar",
                            confirmation=True,
                        ),
                    )
                    for record in (updates + dlcs)[:8]
                ],
                "primaryAction": self._action("library.scan", "Atualizar jogos"),
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
                    )
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
                    )
                ],
                "primaryAction": self._action("emulation.refresh", "Detectar novamente"),
            },
            "saves": {
                "cards": [
                    self._card(
                        "saves",
                        "Backups de save",
                        f"{len(saves)} backup(s) por conteúdo.",
                        "ready",
                        f"{len(saves)}",
                        action=self._action(
                            "content.save.import",
                            "Importar backup",
                            enabled=has_game,
                            reason=selected_reason,
                            confirmation=True,
                        ),
                    )
                ],
                "primaryAction": self._action("emulation.refresh", "Verificar integridade"),
            },
            "shaderCache": {
                "cards": [
                    self._card(
                        "shaders",
                        "Shader cache",
                        f"{len(shaders)} cache(s) armazenado(s) por jogo.",
                        "ready",
                        f"{len(shaders)}",
                        action=self._action(
                            "content.shader.import",
                            "Importar cache",
                            enabled=has_game,
                            reason=selected_reason,
                            confirmation=True,
                        ),
                    )
                ],
                "primaryAction": self._action("emulation.refresh", "Verificar compatibilidade"),
            },
            "media": {
                "cards": [
                    self._card(
                        "roots",
                        "Diretórios de ROMs",
                        "\n".join(roots) if roots else "Nenhum diretório existente encontrado.",
                        "ready" if roots else "attention",
                        f"{len(roots)}",
                        action=self._action("library.root.add", "Adicionar diretório"),
                    ),
                    self._card(
                        "identified",
                        "Identificação",
                        "A varredura usa Title ID no nome; DAT local continua opcional.",
                        "ready" if games else "attention",
                        f"{len(games)}",
                    ),
                ],
                "primaryAction": self._action("library.scan", "Varrer agora"),
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

    def _plan_root_add(self, selected: Path) -> transaction.Plan:
        if selected.is_symlink() or not selected.is_dir():
            raise SteamZeroError("E-CONTENT-UNSAFE-PATH", detail="diretório de ROMs inválido")
        resolved = selected.resolve(strict=True)
        roots = self._custom_roots()
        if resolved not in roots:
            roots.append(resolved)
        ordered_roots = sorted(roots, key=str)
        data = {"schemaVersion": 1, "roots": [str(root) for root in ordered_roots]}
        writes = {self._roots_path: json.dumps(data, sort_keys=True, ensure_ascii=False).encode()}
        writes.update(self._emulator_game_directory_writes(self._configured_game_roots(resolved)))
        root = self._compatible_root(writes)
        return transaction.plan_write_files(
            writes,
            root=root,
            kind="emulation.library-roots",
        )

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
        title_sources = [
            path for path in candidates if path.name.casefold() == "title.keys"
        ]
        if len(title_sources) > 1:
            raise SteamZeroError(
                "E-CONTENT-KEYS-INCOMPAT", detail="mais de um arquivo title.keys encontrado"
            )
        if title_sources:
            title_source = title_sources[0]
            self._validate_title_keys(title_source)
            title_digest = fs.hash_file(title_source, algo="sha256")
            title_target = (
                paths.keys_dir() / "switch" / f"title-{title_digest[:12]}.keys"
            )
            title_targets = [
                title_target,
                *(
                    self._title_key_projection_targets()
                    if paths.data_home().resolve().is_relative_to(Path.home().resolve())
                    else ()
                ),
            ]
            copies.extend(
                self._new_copy_targets(title_source, title_targets, title_digest)
            )
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
            return transaction.plan_write_files(
                {}, root=Path.home(), kind="emulation.keys-repair"
            )
        return transaction.plan_copy_files(
            copies, root=Path.home(), kind="emulation.keys-repair"
        )

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
            raise SteamZeroError(
                "E-CONTENT-KEYS-INCOMPAT", detail="title.keys ilegível"
            ) from exc
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
            raise SteamZeroError(
                "E-CONTENT-KEYS-INCOMPAT", detail="title.keys está vazio"
            )

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

    def _custom_roots(self) -> list[Path]:
        if not self._roots_path.is_file() or self._roots_path.is_symlink():
            return []
        try:
            data = json.loads(self._roots_path.read_text(encoding="utf-8"))
            if data.get("schemaVersion") != 1 or not isinstance(data.get("roots"), list):
                return []
            return [
                Path(value)
                for value in data["roots"]
                if isinstance(value, str) and Path(value).is_absolute()
            ]
        except (OSError, json.JSONDecodeError, AttributeError):
            return []

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
        }[emulator_id]

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
        }[emulator_id]

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
        copies = self._new_copy_targets(
            source, self._emulator_key_targets(emulator_id), digest
        )
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

    def _firmware_projection_copies(
        self, emulator_ids: Sequence[str]
    ) -> list[tuple[Path, Path]]:
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
        try:
            source = self._current_key_source()
            digest = fs.hash_file(source, algo="sha256")
        except (OSError, SteamZeroError):
            return False
        for target in self._emulator_key_targets(emulator_id):
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

    def _launch_argv(self, emulator_id: str, payload: Path, rom: Path) -> tuple[str, ...]:
        """Monta argv sem shell; cada caminho permanece um argumento atômico."""
        if emulator_id in {"eden", "citron"}:
            return self._appimage_argv(payload, "-f", "-g", str(rom))
        if emulator_id == "ryubing":
            return self._appimage_argv(payload, "-f", "--hide-updates", str(rom))
        raise SteamZeroError("E-API-SCHEMA", detail="emulador não permitido")

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
            "eden": (
                home / ".local/share/eden/nand/system/Contents/registered" / filename,
            ),
            "citron": (
                home / ".local/share/citron/nand/system/Contents/registered" / filename,
            ),
            "ryubing": (
                home / ".config/Ryujinx/bis/system/Contents/registered" / filename,
            ),
        }[emulator_id]

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
                writes[ryubing] = (
                    json.dumps(data, indent=2, ensure_ascii=False).encode() + b"\n"
                )
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
                if emulator_id is not None and emulator_id not in _MANAGED_EMULATORS:
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
        root = self._compatible_root(
            {**writes, **{target: b"" for _source, target in copies}}
        )
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
        game_id = game.get("id")
        fingerprint = game.get("fingerprint")
        candidates = [game_id]
        if isinstance(fingerprint, str) and len(fingerprint) >= 16:
            candidates.append(fingerprint[:16])
        for candidate in candidates:
            if isinstance(candidate, str) and candidate in settings:
                return dict(settings[candidate])
        return {}

    def _enrich_games(
        self,
        games: list[dict[str, Any]],
        emulators: list[dict[str, Any]],
        keys: Mapping[str, Any],
        firmware: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        settings = self._load_game_settings(strict=False)
        published = self._shortcuts.managed_game_ids()
        installed = {
            str(row["id"])
            for row in emulators
            if row.get("installState") == "installed"
        }
        enriched: list[dict[str, Any]] = []
        for raw in games:
            game = dict(raw)
            game_id = str(game["id"])
            selected = self._settings_for_game(game, settings)
            emulator_id = selected.get("emulatorId")
            emulator_ready = isinstance(emulator_id, str) and emulator_id in installed
            keys_ready = bool(
                emulator_ready
                and isinstance(emulator_id, str)
                and self._key_projection_valid(emulator_id)
            )
            firmware_ready = firmware.get("status") == "ok"
            ready = emulator_ready and keys_ready and firmware_ready
            if not emulator_ready:
                play_reason = "Selecione um emulador instalado para este jogo."
            elif not keys_ready:
                play_reason = f"Sincronize prod.keys com {emulator_id}."
            elif not firmware_ready:
                play_reason = "Importe e valide o firmware antes de jogar."
            else:
                play_reason = None
            game.update(
                {
                    "emulatorId": emulator_id,
                    "steamSelected": selected.get("steamSelected") is True,
                    "steamPublished": game_id in published,
                    "playAction": self._action(
                        f"game.launch:{game_id}",
                        "Jogar",
                        enabled=ready,
                        reason=play_reason,
                    ),
                    "deleteAction": self._action(
                        f"game.delete:{game_id}", "Excluir ROM", confirmation=True
                    ),
                }
            )
            enriched.append(game)
        return enriched

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
        return "", "fallback"

    @staticmethod
    def _physical_dock(status: Mapping[str, Any]) -> bool:
        context = status.get("context")
        return bool(context.get("physicalDock")) if isinstance(context, Mapping) else False

    @staticmethod
    def _controller_count() -> int:
        root = Path("/dev/input/by-id")
        try:
            names = {path.name for path in root.iterdir() if "-event-joystick" in path.name}
        except OSError:
            return 0
        return min(4, len(names))

    @staticmethod
    def _plan_view(plan: transaction.Plan, action: str) -> dict[str, Any]:
        return {
            "planId": plan.plan_id,
            "confirmToken": plan.confirm_token,
            "action": action,
            "preview": plan.preview,
            "rollbackGuarantee": plan.rollback_guarantee,
            "requirements": plan.requirements,
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
