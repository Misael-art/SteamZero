# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Read model e planos confirmados para gameplay da Steam no Desktop.

O adapter observa biblioteca e capacidades do host. Perfis são persistidos como
política do SteamZero; efeitos indisponíveis bloqueiam a aplicação em vez de serem
simulados. O launcher consome a política e sua Launch Option é configurada por uma
transação separada, explícita e reversível.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from steamzero.adapters.host_preparation import snapshot as host_preparation_snapshot
from steamzero.adapters.lsfg import LSFG_APP_ID, LsfgInstaller
from steamzero.adapters.steam_launch_options import SteamLaunchOptionsManager
from steamzero.adapters.steam_launcher import SteamGameLauncher
from steamzero.adapters.steam_maintenance import SteamMaintenance
from steamzero.adapters.steam_media import SteamMediaManager
from steamzero.adapters.steam_session import readiness as session_readiness
from steamzero.core import ids, journal, paths, transaction
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain.hud import hud_catalog

Which = Callable[[str], str | None]
StoreFactory = Callable[[], StateStore]

_SCOPES = frozenset({"global", "game", "portable", "dock"})
_PROFILES = frozenset({"economy", "balanced", "performance"})
_FPS = frozenset({30, 40, 60})
_MANGO = frozenset({"off", "basic", "detailed"})
_UPSCALING = frozenset({"native", "fsr2-quality", "fsr2-balanced", "gamescope-fsr"})
_GPU_MODES = frozenset({"auto", "manual"})
_FRAME_GENERATION = frozenset({"off", "lsfg-2x", "lsfg-3x", "lsfg-4x"})
_CONTROLLER_LAYOUTS = frozenset(
    {
        "steam-recommended",
        "official",
        "community",
        "steamzero-gamepad",
        "steamzero-kbm",
        "custom",
    }
)
_PLAN_TTL = timedelta(minutes=15)
_ACF_FIELD = re.compile(r'^\s*"(?P<key>appid|name)"\s+"(?P<value>.*)"\s*$')
_LIBRARY_PATH = re.compile(r'^\s*"path"\s+"(?P<value>.*)"\s*$')
_INSTALL_DIR = re.compile(r'^\s*"installdir"\s+"(?P<value>[^"\x00\r\n]+)"\s*$')


def _now() -> datetime:
    return datetime.now(UTC)


def _default_roots() -> tuple[Path, ...]:
    home = Path.home()
    return (
        home / ".local/share/Steam",
        home / ".steam/steam",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
    )


def _file_url(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.resolve().as_uri()
    except (OSError, ValueError):
        return ""


@dataclass(frozen=True)
class GameplayPlan:
    plan_id: str
    confirm_token: str
    created_at: datetime
    basis: str
    profile: dict[str, Any]
    changes: tuple[str, ...]
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "planId": self.plan_id,
            "confirmToken": self.confirm_token,
            "createdAt": self.created_at.isoformat(),
            "expiresAt": (self.created_at + _PLAN_TTL).isoformat(),
            "profile": self.profile,
            "changes": list(self.changes),
            "blockers": list(self.blockers),
            "rollbackGuarantee": "perfil anterior preservado no State Store",
        }


class SteamGameplayController:
    """Descobre jogos/capacidades e persiste políticas revisadas de gameplay."""

    def __init__(
        self,
        *,
        roots: Sequence[Path] | None = None,
        which: Which = shutil.which,
        store_factory: StoreFactory = StateStore,
        meminfo: Path = Path("/proc/meminfo"),
        lsfg_manifests: Sequence[Path] | None = None,
        lsfg_installer: LsfgInstaller | None = None,
        launcher: SteamGameLauncher | None = None,
        launch_options: SteamLaunchOptionsManager | None = None,
        maintenance: SteamMaintenance | None = None,
        media: SteamMediaManager | None = None,
    ) -> None:
        self._roots = tuple(roots) if roots is not None else _default_roots()
        self._which = which
        self._store_factory = store_factory
        self._meminfo = meminfo
        self._lsfg_manifests = (
            tuple(lsfg_manifests)
            if lsfg_manifests is not None
            else (
                Path.home()
                / ".local/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation.json",
                Path("/usr/local/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation.json"),
                Path("/usr/share/vulkan/implicit_layer.d/VkLayer_LS_frame_generation.json"),
            )
        )
        self._lsfg = lsfg_installer or LsfgInstaller(lossless_probe=self._has_lossless_scaling)
        self._launcher = launcher or SteamGameLauncher(
            roots=self._roots,
            which=which,
            store_factory=store_factory,
            lsfg_manifests=self._lsfg_manifests,
        )
        self._launch_options = launch_options or SteamLaunchOptionsManager(roots=self._roots)
        self._maintenance = maintenance or SteamMaintenance(roots=self._roots)
        self._media = media or SteamMediaManager(pipeline=None, roots=self._roots)
        self._plans: dict[str, GameplayPlan] = {}

    def snapshot(self, desktop_status: dict[str, Any]) -> dict[str, Any]:
        games = self._games()
        capabilities = self._capabilities()
        context = desktop_status.get("context")
        context_dict = context if isinstance(context, dict) else {}
        device_kind = str(context_dict.get("deviceKind", "linux"))
        displays = context_dict.get("displays", [])
        resolution = self._resolution(displays)
        selected_id = games[0]["id"] if games else ""
        saved = self._launcher.desired_profile(selected_id) if selected_id else None
        selected_profile = self._complete_profile(saved, selected_id)
        launcher = self._launcher.status(selected_id)
        if selected_id:
            launcher["configuration"] = self._launch_options.status(selected_id)
        environment = self._environment(capabilities)
        ready_count = sum(row["state"] == "ready" for row in environment if row["required"])
        required_count = sum(row["required"] for row in environment)
        readiness = round(100 * ready_count / required_count) if required_count else 100
        missing = sum(row["state"] != "ready" for row in environment)
        return {
            "games": games,
            "selectedGameId": selected_id,
            "environment": environment,
            "readiness": {
                "percent": readiness,
                "title": (
                    "Pronto para configurar"
                    if readiness == 100
                    else f"Pronto com {missing} ajuste(s) recomendado(s)"
                ),
                "detail": "Hardware compatível · Perfil seguro disponível",
            },
            "hardware": {
                "deviceLabel": "Deck LCD" if device_kind == "deck-lcd" else "Linux",
                "tdpMin": 3 if device_kind.startswith("deck-") else None,
                "tdpMax": 15 if device_kind.startswith("deck-") else None,
                "gpuMin": 200 if device_kind.startswith("deck-") else None,
                "gpuMax": 1600 if device_kind.startswith("deck-") else None,
                "refreshHz": self._refresh(displays),
                "memoryGb": self._memory_gb(),
                "withinSafeLimits": device_kind.startswith("deck-"),
            },
            "context": {
                "device": "Deck LCD" if device_kind == "deck-lcd" else "Linux",
                "battery": self._battery_percent(),
                "mode": "Modo Desktop",
            },
            "currentProfile": selected_profile,
            "truthState": (
                launcher["state"]
                if saved
                else "desired"
                if self._saved_controls(selected_id)
                else "recommended"
            ),
            "launcher": launcher,
            "impact": self._impact(selected_profile, resolution),
            "profiles": [
                {"id": "economy", "label": "Economia", "fps": 30},
                {"id": "balanced", "label": "Equilibrado", "fps": 40, "recommended": True},
                {"id": "performance", "label": "Desempenho", "fps": 60},
            ],
            "lsfgInstaller": self._lsfg.status(),
            "maintenance": self._maintenance.snapshot(selected_id),
            "media": self._media.snapshot(selected_id) if selected_id else {"accounts": []},
            "sessionManager": session_readiness(which=self._which),
            "hostPreparation": host_preparation_snapshot(device_kind, which=self._which),
            "hud": hud_catalog(mangohud_available=capabilities["mangohud"]),
        }

    def hud_presets(self) -> dict[str, Any]:
        return hud_catalog(mangohud_available=self._capabilities()["mangohud"])

    def session_status(self, game_id: str) -> dict[str, Any]:
        """Observa uma sessão específica sem expor comando ou ambiente."""
        return self._launcher.status(game_id)

    def plan_lsfg_install(self) -> dict[str, Any]:
        return self._lsfg.plan_install()

    def apply_lsfg_install(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        return self._lsfg.apply(plan_id, confirm_token)

    def rollback_lsfg_install(self, operation_id: str) -> dict[str, Any]:
        return self._lsfg.rollback(operation_id)

    def plan(self, payload: dict[str, Any], desktop_status: dict[str, Any]) -> dict[str, Any]:
        normalized = self._validate_profile(payload)
        basis = self._basis(desktop_status)
        capabilities = self._capabilities()
        games = {row["id"] for row in self._games()}
        blockers: list[str] = []
        game_id = normalized["gameId"]
        if normalized["scope"] == "game" and game_id not in games:
            blockers.append("O jogo selecionado não está mais instalado.")
        if not capabilities["steam"]:
            blockers.append("O cliente Steam não está disponível.")
        if normalized["gamescope"] and not capabilities["gamescope"]:
            blockers.append("Gamescope não está disponível; abra Sistema.")
        if normalized["gameMode"] and not capabilities["gamemode"]:
            blockers.append("Feral GameMode não está disponível; abra Sistema.")
        if normalized["mangoHud"] != "off" and not capabilities["mangohud"]:
            blockers.append("MangoHud não está disponível; abra Sistema.")
        if (
            normalized["mangoHud"] != "off"
            and normalized["gamescope"]
            and capabilities["gamescope"]
            and capabilities["mangohud"]
            and not capabilities["mangoapp"]
        ):
            blockers.append("MangoApp é necessário para usar o overlay dentro do Gamescope.")
        if normalized["frameGeneration"] != "off" and not capabilities["lsfg"]:
            blockers.append("LSFG-VK não está disponível; abra Sistema para preparar o componente.")
        if normalized["controllerLayout"] != "steam-recommended" and not capabilities["steam"]:
            blockers.append("Steam Input não está disponível para aplicar o layout escolhido.")
        context = desktop_status.get("context")
        context_dict = context if isinstance(context, dict) else {}
        is_deck = str(context_dict.get("deviceKind", "")).startswith("deck-")
        if normalized["tdp"] is not None and not is_deck:
            blockers.append("Controle de TDP não foi observado neste hardware.")
        current = self._complete_profile(
            self._launcher.desired_profile(game_id) if game_id else None,
            game_id,
        )
        changes = self._changes(current, normalized)
        tx_plan = transaction.plan_write_files(
            {},
            root=paths.state_home(),
            kind=f"steam.gameplay-profile:{self._profile_id(normalized['scope'], game_id)}",
        )
        plan = GameplayPlan(
            plan_id=tx_plan.plan_id,
            confirm_token=tx_plan.confirm_token,
            created_at=_now(),
            basis=basis,
            profile=normalized,
            changes=tuple(changes),
            blockers=tuple(blockers),
        )
        self._plans[plan.plan_id] = plan
        return plan.to_dict()

    def apply(
        self,
        plan_id: str,
        confirm_token: str,
        desktop_status: dict[str, Any],
    ) -> dict[str, Any]:
        plan = self._plans.get(plan_id)
        if plan is None or not secrets.compare_digest(plan.confirm_token, confirm_token):
            raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="plano Steam inválido")
        if _now() > plan.created_at + _PLAN_TTL or self._basis(desktop_status) != plan.basis:
            self._plans.pop(plan_id, None)
            raise SteamZeroError("E-TX-STALE-PLAN", detail="ambiente Steam mudou; revise novamente")
        if plan.blockers:
            raise SteamZeroError("E-COMPONENT-DEGRADED", detail="; ".join(plan.blockers))
        profile_id = self._profile_id(plan.profile["scope"], plan.profile["gameId"])
        with self._store_factory() as store:
            store.migrate()
            performance = dict(plan.profile)
            controller_layout = str(performance.pop("controllerLayout"))
            target_ids = [profile_id]
            if plan.profile["scope"] == "game" and plan.profile["gameId"]:
                target_ids.append(self._controls_profile_id(plan.profile["gameId"]))
            before = [
                row
                for target in target_ids
                if (row := store.get_profile(target)) is not None
            ]
            profiles = [
                {
                    "id": profile_id,
                    "scope": plan.profile["scope"],
                    "kind": "performance",
                    "payload_json": json.dumps(performance, sort_keys=True, separators=(",", ":")),
                    "priority": 100,
                    "profile_owner": "steamzero",
                }
            ]
            if plan.profile["scope"] == "game" and plan.profile["gameId"]:
                profiles.append(
                    {
                        "id": self._controls_profile_id(plan.profile["gameId"]),
                        "scope": "game",
                        "kind": "controls",
                        "payload_json": json.dumps(
                            {
                                "gameId": plan.profile["gameId"],
                                "layout": controller_layout,
                                "owner": "steam-input",
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                        "priority": 100,
                        "profile_owner": "steamzero",
                    }
                )
            result = transaction.apply(plan_id, confirm_token)
            undo_id = self._undo_profile_id(result.operation_id)
            profiles.append(
                {
                    "id": undo_id,
                    "scope": "game",
                    "kind": "performance",
                    "payload_json": json.dumps(
                        {"schemaVersion": 1, "targetIds": target_ids, "before": before},
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "priority": -100,
                    "profile_owner": "steamzero-undo",
                }
            )
            try:
                store.replace_profiles(profiles)
            except Exception:
                transaction.rollback(result.operation_id, reason="state-store-save-failed")
                raise
        self._plans.pop(plan_id, None)
        return {
            "status": "saved",
            "operationId": result.operation_id,
            "truthState": "desired",
            "profile": plan.profile,
            "launcher": self._launcher.status(str(plan.profile["gameId"])),
            "message": "Perfil salvo; configure a opção de lançamento gerenciado na Steam.",
        }

    def rollback_profile(self, operation_id: str) -> dict[str, Any]:
        if not ids.is_ulid(operation_id):
            raise SteamZeroError("E-API-SCHEMA", detail="operationId inválido")
        undo_id = self._undo_profile_id(operation_id)
        with self._store_factory() as store:
            store.migrate()
            undo = store.get_profile(undo_id)
            if undo is None or undo.get("profile_owner") != "steamzero-undo":
                raise SteamZeroError(
                    "E-TX-STALE-PLAN", detail="rollback do perfil Steam indisponível"
                )
            payload = self._parse_profile_undo(undo)
            target_ids = payload["targetIds"]
            before = payload["before"]
            current = [
                row for target in target_ids if (row := store.get_profile(target)) is not None
            ]
            before_ids = {str(row["id"]) for row in before}
            store.replace_profiles(
                before,
                delete_ids=[target for target in target_ids if target not in before_ids],
            )
            try:
                records = journal.read_records(operation_id)
                begin = next(
                    (row for row in records if row.get("type") == "operation.begin"),
                    None,
                )
                expected = f"steam.gameplay-profile:{target_ids[0]}"
                if not isinstance(begin, dict) or begin.get("kind") != expected:
                    raise SteamZeroError(
                        "E-TX-STALE-PLAN", detail="operação não pertence ao perfil Steam"
                    )
                result = transaction.rollback(operation_id, reason="gameplay-profile-user-request")
            except Exception:
                current_ids = {str(row["id"]) for row in current}
                store.replace_profiles(
                    current,
                    delete_ids=[target for target in target_ids if target not in current_ids],
                )
                raise
            store.replace_profiles([], delete_ids=[undo_id])
        return {"status": result.status, "operationId": operation_id}

    @staticmethod
    def _undo_profile_id(operation_id: str) -> str:
        return f"steam-gameplay-undo:{operation_id}"

    @staticmethod
    def _parse_profile_undo(row: dict[str, Any]) -> dict[str, Any]:
        try:
            payload = json.loads(str(row["payload_json"]))
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="rollback Steam corrompido") from exc
        if (
            not isinstance(payload, dict)
            or payload.get("schemaVersion") != 1
            or not isinstance(payload.get("targetIds"), list)
            or not 1 <= len(payload["targetIds"]) <= 2
            or not all(isinstance(value, str) and value for value in payload["targetIds"])
            or not isinstance(payload.get("before"), list)
            or not all(
                isinstance(value, dict) and value.get("id") in payload["targetIds"]
                for value in payload["before"]
            )
        ):
            raise SteamZeroError("E-STATE-INTEGRITY", detail="rollback Steam inválido")
        return payload

    def recover_launcher(self, game_id: str) -> dict[str, Any]:
        return self._launcher.recover(game_id)

    def plan_launch_options(self, game_id: str) -> dict[str, Any]:
        return self._launch_options.plan(game_id)

    def apply_launch_options(
        self, plan_id: str, confirm_token: str, game_id: str
    ) -> dict[str, Any]:
        return self._launch_options.apply(plan_id, confirm_token, game_id)

    def rollback_launch_options(self, operation_id: str) -> dict[str, Any]:
        return self._launch_options.rollback(operation_id)

    def plan_maintenance(self, game_id: str, categories: Sequence[str]) -> dict[str, Any]:
        return self._maintenance.plan(categories, game_id)

    def apply_maintenance(
        self, plan_id: str, confirm_token: str, confirm_phrase: str
    ) -> dict[str, Any]:
        return self._maintenance.apply(plan_id, confirm_token, confirm_phrase)

    def recover_maintenance(self) -> dict[str, Any]:
        return self._maintenance.recover()

    def plan_media(self, game_id: str, account_id: str, package_dir: Path) -> dict[str, Any]:
        return self._media.plan_package(game_id, account_id, package_dir)

    def apply_media(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        return self._media.apply(plan_id, confirm_token)

    def rollback_media(self, operation_id: str) -> dict[str, Any]:
        return self._media.rollback(operation_id)

    @staticmethod
    def safe_profile(game_id: str) -> dict[str, Any]:
        return {
            "gameId": game_id,
            "scope": "game" if game_id else "global",
            "profile": "balanced",
            "fps": 40,
            "tdp": 10,
            "gpuMode": "auto",
            "gpuClock": None,
            "gamescope": True,
            "gameMode": True,
            "mangoHud": "off",
            "upscaling": "fsr2-quality",
            "frameGeneration": "off",
            "controllerLayout": "steam-recommended",
        }

    def _complete_profile(self, saved: dict[str, Any] | None, game_id: str) -> dict[str, Any]:
        profile = self.safe_profile(game_id)
        if saved:
            profile.update(saved)
        controls = self._saved_controls(game_id)
        if controls is not None:
            profile["controllerLayout"] = controls.get("layout", profile["controllerLayout"])
        return profile

    def _saved_controls(self, game_id: str) -> dict[str, Any] | None:
        if not game_id:
            return None
        with self._store_factory() as store:
            store.migrate()
            row = store.get_profile(self._controls_profile_id(game_id))
        if row is None or row.get("kind") != "controls":
            return None
        try:
            value = json.loads(str(row["payload_json"]))
        except (KeyError, TypeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _profile_id(scope: str, game_id: str) -> str:
        target = game_id if scope == "game" and game_id else "default"
        return f"steam-gameplay:{scope}:{target}"

    @staticmethod
    def _controls_profile_id(game_id: str) -> str:
        return f"steam-controls:game:{game_id}"

    def _validate_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        game_id = payload.get("gameId", "")
        scope = payload.get("scope")
        profile = payload.get("profile")
        fps = payload.get("fps")
        tdp = payload.get("tdp")
        gpu_mode = payload.get("gpuMode")
        gpu_clock = payload.get("gpuClock")
        mango = payload.get("mangoHud")
        upscaling = payload.get("upscaling")
        frame_generation = payload.get("frameGeneration", "off")
        controller_layout = payload.get("controllerLayout", "steam-recommended")
        if not isinstance(game_id, str) or len(game_id) > 32 or (game_id and not game_id.isdigit()):
            raise SteamZeroError("E-API-SCHEMA", detail="gameId inválido")
        if scope not in _SCOPES or profile not in _PROFILES or fps not in _FPS:
            raise SteamZeroError("E-API-SCHEMA", detail="escopo ou perfil inválido")
        if tdp is not None and (
            not isinstance(tdp, int) or isinstance(tdp, bool) or not 3 <= tdp <= 15
        ):
            raise SteamZeroError("E-API-SCHEMA", detail="TDP fora dos limites 3-15 W")
        if gpu_mode not in _GPU_MODES:
            raise SteamZeroError("E-API-SCHEMA", detail="modo de GPU inválido")
        if gpu_mode == "manual" and (
            not isinstance(gpu_clock, int)
            or isinstance(gpu_clock, bool)
            or not 200 <= gpu_clock <= 1600
        ):
            raise SteamZeroError("E-API-SCHEMA", detail="clock de GPU fora de 200-1600 MHz")
        if gpu_mode == "auto":
            gpu_clock = None
        if mango not in _MANGO or upscaling not in _UPSCALING:
            raise SteamZeroError("E-API-SCHEMA", detail="overlay ou upscaling inválido")
        if frame_generation not in _FRAME_GENERATION:
            raise SteamZeroError("E-API-SCHEMA", detail="modo de geração de quadros inválido")
        if controller_layout not in _CONTROLLER_LAYOUTS:
            raise SteamZeroError("E-API-SCHEMA", detail="layout de controle inválido")
        gamescope = payload.get("gamescope")
        game_mode = payload.get("gameMode")
        if not isinstance(gamescope, bool) or not isinstance(game_mode, bool):
            raise SteamZeroError("E-API-SCHEMA", detail="integrações precisam ser booleanas")
        return {
            "gameId": game_id,
            "scope": scope,
            "profile": profile,
            "fps": fps,
            "tdp": tdp,
            "gpuMode": gpu_mode,
            "gpuClock": gpu_clock,
            "gamescope": gamescope,
            "gameMode": game_mode,
            "mangoHud": mango,
            "upscaling": upscaling,
            "frameGeneration": frame_generation,
            "controllerLayout": controller_layout,
        }

    def _games(self) -> list[dict[str, Any]]:
        roots = self._library_roots()
        games: dict[str, dict[str, Any]] = {}
        for root in roots:
            steamapps = root / "steamapps"
            try:
                manifests = tuple(steamapps.glob("appmanifest_*.acf"))
            except OSError:
                continue
            for manifest in manifests:
                parsed = self._parse_manifest(manifest)
                if parsed is None:
                    continue
                app_id, name = parsed
                if app_id == LSFG_APP_ID:
                    continue
                games[app_id] = {
                    "id": app_id,
                    "name": name,
                    "coverUrl": _file_url(self._cover(root, app_id)),
                    "state": "installed",
                }
        return sorted(games.values(), key=lambda item: str(item["name"]).casefold())[:200]

    def _has_lossless_scaling(self) -> bool:
        for root in self._library_roots():
            manifest = root / "steamapps" / f"appmanifest_{LSFG_APP_ID}.acf"
            try:
                lines = manifest.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in lines[:300]:
                match = _INSTALL_DIR.match(line)
                if match is None:
                    continue
                install_dir = match.group("value").strip()
                if (
                    install_dir
                    and "/" not in install_dir
                    and "\\" not in install_dir
                    and install_dir not in {".", ".."}
                    and (root / "steamapps" / "common" / install_dir / "Lossless.dll").is_file()
                ):
                    return True
        return False

    def _library_roots(self) -> tuple[Path, ...]:
        found: dict[str, Path] = {}
        for root in self._roots:
            if root.is_dir():
                found[str(root.resolve())] = root.resolve()
            file = root / "steamapps/libraryfolders.vdf"
            try:
                lines = file.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in lines:
                match = _LIBRARY_PATH.match(line)
                if match:
                    value = match.group("value").replace("\\\\", "\\")
                    path = Path(value).expanduser()
                    if path.is_dir():
                        found[str(path.resolve())] = path.resolve()
        return tuple(found.values())

    @staticmethod
    def _parse_manifest(path: Path) -> tuple[str, str] | None:
        values: dict[str, str] = {}
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return None
        for line in lines[:300]:
            match = _ACF_FIELD.match(line)
            if match:
                values[match.group("key")] = match.group("value")
        app_id = values.get("appid", "")
        name = values.get("name", "").strip()
        if not app_id.isdigit() or not name:
            return None
        return app_id, name[:160]

    @staticmethod
    def _cover(root: Path, app_id: str) -> Path | None:
        directory = root / "appcache/librarycache" / app_id
        candidates = (
            directory / "library_600x900.jpg",
            directory / "library_600x900_2x.jpg",
            root / "appcache/librarycache" / f"{app_id}_library_600x900.jpg",
        )
        return next((path for path in candidates if path.is_file()), None)

    def _capabilities(self) -> dict[str, bool]:
        steam_available = self._which("steam") is not None or any(
            (root / "steamapps").is_dir() for root in self._roots
        )
        return {
            "steam": steam_available,
            "gamescope": self._which("gamescope") is not None,
            "gamemode": self._which("gamemoderun") is not None,
            "mangohud": self._which("mangohud") is not None,
            "mangoapp": self._which("mangoapp") is not None,
            "vkbasalt": self._which("vkbasalt") is not None,
            "lsfg": any(path.is_file() for path in self._lsfg_manifests),
        }

    @staticmethod
    def _environment(capabilities: dict[str, bool]) -> list[dict[str, Any]]:
        definitions = (
            ("steam", "Steam", "Contexto de jogo e runtime", "Steam", True),
            ("gamescope", "Gamescope", "Composição e limite de quadros", "SteamZero", True),
            ("gamemode", "Feral GameMode", "Prioridade de CPU e processos", "Steam", True),
            ("mangohud", "MangoHud", "Métricas durante o jogo", "SteamZero", False),
            (
                "mangoapp",
                "MangoApp",
                "Overlay compatível com Gamescope",
                "Sistema",
                False,
            ),
            ("vkbasalt", "vkBasalt", "Pós-processamento Vulkan", "Sistema", False),
            (
                "lsfg",
                "LSFG-VK",
                "Geração de quadros configurada por jogo",
                "Sistema",
                False,
            ),
        )
        return [
            {
                "id": key,
                "name": name,
                "detail": detail,
                "owner": owner,
                "required": required,
                "state": "ready" if capabilities[key] else "missing",
                "statusLabel": "pronto"
                if capabilities[key]
                else "ausente, opcional"
                if not required
                else "ausente",
            }
            for key, name, detail, owner, required in definitions
        ]

    def _basis(self, desktop_status: dict[str, Any]) -> str:
        value = {
            "context": desktop_status.get("context", {}),
            "capabilities": self._capabilities(),
            "games": [row["id"] for row in self._games()],
        }
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _changes(current: dict[str, Any], proposed: dict[str, Any]) -> list[str]:
        labels = {
            "profile": "Perfil",
            "fps": "Limite de FPS",
            "tdp": "TDP",
            "gpuMode": "Clock da GPU",
            "gamescope": "Gamescope",
            "gameMode": "Feral GameMode",
            "mangoHud": "MangoHud",
            "upscaling": "Upscaling",
            "frameGeneration": "Geração de quadros",
            "controllerLayout": "Layout de controles",
            "scope": "Escopo",
        }
        changes = [
            f"{label}: {current.get(key)} → {proposed.get(key)}"
            for key, label in labels.items()
            if current.get(key) != proposed.get(key)
        ]
        return changes or ["Nenhuma alteração em relação ao perfil salvo."]

    @staticmethod
    def _resolution(displays: Any) -> str:
        if isinstance(displays, list):
            for display in displays:
                if (
                    isinstance(display, dict)
                    and display.get("internal")
                    and display.get("connected")
                ):
                    width, height = display.get("width"), display.get("height")
                    if isinstance(width, int) and isinstance(height, int):
                        return f"{min(width, height)}x{max(width, height)}"
        return "1280x800"

    @staticmethod
    def _refresh(displays: Any) -> int | None:
        if isinstance(displays, list):
            for display in displays:
                if (
                    isinstance(display, dict)
                    and display.get("internal")
                    and display.get("connected")
                ):
                    value = display.get("refreshHz")
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        return round(value)
        return None

    def _memory_gb(self) -> float | None:
        try:
            for line in self._meminfo.read_text(encoding="utf-8").splitlines():
                if line.startswith("MemAvailable:"):
                    return round(int(line.split()[1]) / 1024 / 1024, 1)
        except (OSError, ValueError, IndexError):
            return None
        return None

    @staticmethod
    def _battery_percent() -> int | None:
        for path in Path("/sys/class/power_supply").glob("BAT*/capacity"):
            try:
                value = int(path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                continue
            if 0 <= value <= 100:
                return value
        return None

    @staticmethod
    def _impact(profile: dict[str, Any], resolution: str) -> dict[str, Any]:
        fps = int(profile.get("fps", 40))
        tdp = profile.get("tdp")
        minutes = 260 - (int(tdp) * 10 if isinstance(tdp, int) else 80)
        return {
            "battery": f"{max(1, minutes // 60)} h {minutes % 60:02d} min",
            "resolution": resolution,
            "fluidity": f"{fps} FPS estáveis",
        }
