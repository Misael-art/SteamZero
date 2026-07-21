# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Orquestração da central Switch: lifecycle, biblioteca e conteúdo local."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from steamzero.adapters.engine import AdapterEngine, HttpsArtifactPort, PreparedComponent
from steamzero.adapters.registry import AdapterRegistry
from steamzero.api import contracts
from steamzero.core import fs, ids, paths, safezip, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain.emulation_workspace import build_switch_workspace
from steamzero.domain.switch_content import SwitchContentManager
from steamzero.domain.switch_library import SwitchLibraryScanner

StoreFactory = Callable[[], StateStore]
RegistryFactory = Callable[[], AdapterRegistry]
Spawn = Callable[[Sequence[str]], None]

_MANAGED_EMULATORS = frozenset({"eden", "citron"})
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


def _spawn_detached(argv: Sequence[str]) -> None:
    subprocess.Popen(  # noqa: S603
        list(argv),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


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
    ) -> None:
        self._store_factory = store_factory
        self._registry_factory = registry_factory
        self._artifacts = artifacts or HttpsArtifactPort()
        self._which = which
        self._spawn = spawn
        self._prepared_emulators: dict[str, PreparedComponent] = {}
        self._pending: dict[str, _PendingMutation] = {}
        self._content = SwitchContentManager(paths.data_home() / "switch-content")

    @property
    def _roots_path(self) -> Path:
        return paths.config_home() / "emulation-library-v1.json"

    @property
    def _library_cache_path(self) -> Path:
        return paths.data_home() / "emulation-library-cache-v1.json"

    def snapshot(self, desktop_status: Mapping[str, Any]) -> dict[str, Any]:
        emulator_rows = self._emulator_rows()
        games, unidentified = self._load_library_cache()
        roots = self.library_roots()
        key_status, firmware_status = self._requirements()
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
        self._spawn((str(payload),))
        return {"status": "started", "emulatorId": emulator_id}

    def library_roots(self) -> list[str]:
        candidates = [
            paths.roms_dir(),
            Path.home() / "Emulation" / "roms",
            Path.home() / "Games" / "ROMs",
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
        unidentified = 0
        errors: list[str] = []
        for raw_root in self.library_roots():
            root = Path(raw_root)
            try:
                matches = scanner.scan(root)
            except (OSError, SteamZeroError) as exc:
                errors.append(f"{root}: {exc}")
                continue
            for match in matches:
                if match.title_id is None:
                    unidentified += 1
                    continue
                discovered[match.sha256] = {
                    "id": match.sha256[:16],
                    "titleId": match.title_id,
                    "name": match.canonical_name or match.path.stem,
                    "state": "ready",
                    "statusLabel": match.format.upper(),
                    "emulatorId": None,
                    "path": str(match.path),
                    "sha256": match.sha256,
                    "format": match.format,
                }
        game_rows = sorted(discovered.values(), key=lambda game: str(game["name"]).casefold())
        payload = {
            "schemaVersion": 1,
            "games": game_rows,
            "unidentified": unidentified,
            "errors": errors[:20],
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
        }

    def plan_action(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        action = self._required_string(payload, "actionId")
        if action == "library.root.add":
            plan = self._plan_root_add(Path(self._required_string(payload, "path")))
        elif action == "keys.import":
            plan = self._plan_keys(Path(self._required_string(payload, "path")))
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
        else:
            raise SteamZeroError("E-API-SCHEMA", detail="ação de emulação não permitida")
        return self._plan_view(plan, action)

    def apply_action(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        plan = transaction.load_plan(plan_id)
        if plan.kind == "switch-content.import":
            result = self._content.apply_import(plan_id, confirm_token)
        elif plan.kind == "switch-content.state":
            result = self._content.apply_state(plan_id, confirm_token)
        elif plan.kind == "switch-content.recover":
            result = self._content.apply_recovery(plan_id, confirm_token)
        elif plan.kind.startswith("emulation."):
            result = transaction.apply(plan_id, confirm_token)
        else:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano não pertence à emulação")
        pending = self._pending.pop(plan_id, None)
        if pending is not None:
            self._persist_import(pending)
        return {"status": result.status, "operationId": result.operation_id}

    def _emulator_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        registry = self._registry_factory()
        with self._store_factory() as store:
            store.migrate()
            engine = AdapterEngine(store, registry, self._artifacts)
            for emulator_id, name in (("eden", "Eden"), ("citron", "Citron")):
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
                rows.append(
                    {
                        "id": emulator_id,
                        "displayName": name,
                        "name": name,
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
        detected = self._which("ryujinx") is not None
        rows.append(
            {
                "id": "ryujinx",
                "displayName": "Ryujinx",
                "name": "Ryujinx",
                "platform": "switch",
                "state": "ready" if detected else "unavailable",
                "statusLabel": "Detectado externamente" if detected else "Fonte descontinuada",
                "installState": "installed" if detected else "not-installed",
                "sourceState": "end-of-life",
                "installable": False,
                "specialty": (
                    "Instalação externa detectável; nenhuma fonte não verificada é promovida"
                ),
                "capabilities": [],
                "actions": [],
                "action": self._action(
                    "emulator.unavailable:ryujinx",
                    "Indisponível",
                    enabled=False,
                    reason="A fonte original está descontinuada.",
                ),
            }
        )
        return rows

    def _requirements(self) -> tuple[dict[str, Any], dict[str, Any]]:
        with self._store_factory() as store:
            store.migrate()
            keys = store.list_firmware_key_items("switch", kind="key")
            firmwares = store.list_firmware_key_items("switch", kind="firmware")
        revisions = [int(row["revision"]) for row in keys if row.get("revision") is not None]
        versions = [str(row["version"]) for row in firmwares if row.get("version")]
        key_revision = max(revisions) if revisions else None
        firmware_version = max(versions, key=self._version_tuple) if versions else None
        key = {
            "kind": "keys",
            "status": "ok" if key_revision is not None else "missing",
            "required": None,
            "installed": f"rev{key_revision}" if key_revision is not None else None,
            "detail": "Keys próprias validadas localmente."
            if key_revision is not None
            else "Importe seu arquivo prod.keys.",
            "blocksPlay": key_revision is None,
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
                            "keys.import", "Importar arquivo/pasta/ZIP", confirmation=True
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
                            "A conversão só é liberada quando uma ferramenta local verificada "
                            "estiver configurada."
                        ),
                        "attention",
                        "Ferramenta necessária",
                    ),
                    self._card(
                        "operations",
                        "Operações",
                        "Instalações e imports usam preview, confirmação e rollback.",
                        "ready",
                        "Auditável",
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
        data = {"schemaVersion": 1, "roots": [str(root) for root in sorted(roots, key=str)]}
        return transaction.plan_write_files(
            {self._roots_path: json.dumps(data, sort_keys=True, ensure_ascii=False).encode()},
            root=paths.config_home(),
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
        if target.exists() and fs.hash_file(target, algo="sha256") == digest:
            plan = transaction.plan_write_files(
                {}, root=paths.keys_dir(), kind="emulation.keys-import"
            )
        else:
            plan = transaction.plan_copy_files(
                {source: target}, root=paths.keys_dir(), kind="emulation.keys-import"
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

    def _plan_firmware(self, selected: Path, version: str) -> transaction.Plan:
        if not _FIRMWARE_VERSION.fullmatch(version):
            raise SteamZeroError("E-API-SCHEMA", detail="versão de firmware inválida")
        candidates = self._selected_files(selected, suffixes={".nca"}, allow_single_any=True)
        total = sum(path.stat().st_size for path in candidates)
        if not candidates or len(candidates) > _MAX_IMPORT_FILES or total > _MAX_IMPORT_BYTES:
            raise SteamZeroError(
                "E-CONTENT-UNSAFE-ARCHIVE", detail="conjunto de firmware fora dos limites"
            )
        copies: dict[Path, Path] = {}
        for source in candidates:
            digest = fs.hash_file(source, algo="sha256")
            target = paths.firmware_dir() / "switch" / version / f"{digest}.nca"
            if not target.exists():
                copies[source] = target
            elif target.is_symlink() or fs.hash_file(target, algo="sha256") != digest:
                raise SteamZeroError("E-CONTENT-FW-INCOMPAT", detail="firmware existente diverge")
        digest_set = hashlib.sha256(
            "".join(sorted(path.name for path in copies.values())).encode()
        ).hexdigest()
        plan = (
            transaction.plan_copy_files(
                copies, root=paths.firmware_dir(), kind="emulation.firmware-import"
            )
            if copies
            else transaction.plan_write_files(
                {}, root=paths.firmware_dir(), kind="emulation.firmware-import"
            )
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

    def _load_library_cache(self) -> tuple[list[dict[str, Any]], int]:
        if not self._library_cache_path.is_file() or self._library_cache_path.is_symlink():
            return [], 0
        try:
            data = json.loads(self._library_cache_path.read_text(encoding="utf-8"))
            games = data.get("games", [])
            unidentified = int(data.get("unidentified", 0))
            if data.get("schemaVersion") != 1 or not isinstance(games, list):
                return [], 0
            valid = [
                game
                for game in games
                if isinstance(game, dict) and _TITLE_ID.fullmatch(str(game.get("titleId", "")))
            ]
            return valid, max(0, unidentified)
        except (OSError, ValueError, json.JSONDecodeError):
            return [], 0

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
