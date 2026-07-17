# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Launcher Steam user-scoped com política aplicada e observação de lifecycle.

O Steam chama este executável nas Launch Options, passando ``%command%`` depois
de ``--``. Não há shell: a linha original permanece uma lista de argumentos.
Gamescope/GameMode/MangoHud e LSFG são compostos por prefixos/ambiente
allowlisted; efeitos ainda sem adapter real ficam explicitamente adiados.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
from collections.abc import Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from steamzero.adapters.lsfg import LSFG_APP_ID
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore

StoreFactory = Callable[[], StateStore]
Which = Callable[[str], str | None]
AliveProbe = Callable[[int], bool]
ObservationProbe = Callable[[int, str, str], bool]
ContextProbe = Callable[[], str | None]

_RUNTIME_KIND = "performance-runtime"
_RUNTIME_OWNER = "steamzero-launcher"
_FRAME_MULTIPLIERS = {"lsfg-2x": "2", "lsfg-3x": "3", "lsfg-4x": "4"}
_MANGO_CONFIG = {
    "basic": "fps,frametime,frame_timing=0,cpu_stats=0,gpu_stats=0",
    "detailed": "fps,frametime,cpu_stats,gpu_stats,ram,vram,battery,battery_watt",
}
_INSTALL_DIR = re.compile(r'^\s*"installdir"\s+"(?P<value>[^"\x00\r\n]+)"\s*$')


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _default_roots() -> tuple[Path, ...]:
    home = Path.home()
    return (
        home / ".local/share/Steam",
        home / ".steam/steam",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
    )


def _is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


def _is_observed_process(pid: int, app_id: str, profile_digest: str) -> bool:
    """Confirma PID e marcadores do ambiente; PID vivo isoladamente não basta."""
    try:
        values = (Path("/proc") / str(pid) / "environ").read_bytes().split(b"\0")
    except OSError:
        return False
    return (
        f"STEAMZERO_GAME_ID={app_id}".encode() in values
        and f"STEAMZERO_PROFILE_DIGEST={profile_digest}".encode() in values
    )


def _display_context() -> str | None:
    """Classifica dock de forma read-only; desconhecido não inventa contexto."""
    try:
        statuses = tuple(Path("/sys/class/drm").glob("card*-*/status"))
    except OSError:
        return None
    observed = False
    for status in statuses:
        try:
            connected = status.read_text(encoding="utf-8").strip() == "connected"
        except OSError:
            continue
        if not connected:
            continue
        observed = True
        connector = status.parent.name.casefold()
        if not any(internal in connector for internal in ("edp", "dsi", "lvds")):
            return "dock"
    return "portable" if observed else None


class ChildProcess(Protocol):
    pid: int

    def wait(self) -> int: ...

    def send_signal(self, sig: int) -> None: ...


class ProcessPort(Protocol):
    def start(self, argv: Sequence[str], env: dict[str, str]) -> ChildProcess: ...


class SubprocessPort:
    """Efetor real sem shell; o filho permanece no grupo criado pela Steam."""

    def start(self, argv: Sequence[str], env: dict[str, str]) -> ChildProcess:
        return subprocess.Popen(list(argv), env=env)  # noqa: S603


@dataclass(frozen=True)
class LaunchSpec:
    app_id: str
    profile: dict[str, Any]
    argv: tuple[str, ...]
    environment: dict[str, str]
    applied_effects: tuple[str, ...]
    deferred_effects: tuple[str, ...]
    profile_digest: str

    def public(self) -> dict[str, Any]:
        return {
            "gameId": self.app_id,
            "appliedEffects": list(self.applied_effects),
            "deferredEffects": list(self.deferred_effects),
            "profileDigest": self.profile_digest,
        }


class SteamGameLauncher:
    """Compila, executa e observa uma política persistida por jogo."""

    def __init__(
        self,
        *,
        roots: Sequence[Path] | None = None,
        which: Which = shutil.which,
        store_factory: StoreFactory = StateStore,
        processes: ProcessPort | None = None,
        alive_probe: AliveProbe = _is_alive,
        observation_probe: ObservationProbe = _is_observed_process,
        context_probe: ContextProbe = _display_context,
        environ: Callable[[], dict[str, str]] = lambda: dict(os.environ),
        lsfg_manifests: Sequence[Path] | None = None,
    ) -> None:
        self._roots = tuple(roots) if roots is not None else _default_roots()
        self._which = which
        self._store_factory = store_factory
        self._processes = processes or SubprocessPort()
        self._alive_probe = alive_probe
        self._observation_probe = observation_probe
        self._context_probe = context_probe
        self._environ = environ
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

    @staticmethod
    def launch_option(app_id: str) -> str:
        SteamGameLauncher._validate_app_id(app_id)
        return f"steamzero-launch --appid {app_id} -- %command%"

    def status(self, app_id: str) -> dict[str, Any]:
        if not app_id:
            return {
                "state": "unconfigured",
                "statusLabel": "Selecione um jogo",
                "launchOption": "",
                "recoveryRequired": False,
            }
        self._validate_app_id(app_id)
        desired = self._load_profile(app_id)
        runtime = self._load_runtime(app_id)
        state = "desired" if desired is not None else "recommended"
        recovery = False
        observed = False
        if runtime is not None:
            runtime_state = str(runtime.get("state", "unknown"))
            pid = runtime.get("pid")
            runtime_digest = str(runtime.get("profileDigest", ""))
            desired_digest = self._profile_digest(desired) if desired is not None else ""
            pid_value = pid if isinstance(pid, int) else -1
            alive = pid_value > 0 and self._alive_probe(pid_value)
            observed = (
                alive
                and bool(runtime_digest)
                and self._observation_probe(pid_value, app_id, runtime_digest)
            )
            if runtime_state == "active" and observed and runtime_digest == desired_digest:
                state = "observed"
            elif runtime_state == "active" and observed:
                state = "stale"
            elif runtime_state in {"launching", "active"}:
                state = "stale"
                recovery = not alive
            elif runtime_state == "failed":
                state = "degraded"
        labels = {
            "recommended": "Perfil recomendado",
            "desired": "Aguardando lançamento gerenciado",
            "observed": "Perfil observado em execução",
            "stale": ("Perfil alterado durante execução" if observed else "Sessão interrompida"),
            "degraded": "Falha no último lançamento",
        }
        return {
            "state": state,
            "statusLabel": labels[state],
            "launchOption": self.launch_option(app_id),
            "recoveryRequired": recovery,
            "runtime": runtime,
        }

    def desired_profile(self, app_id: str) -> dict[str, Any] | None:
        self._validate_app_id(app_id)
        profile = self._load_profile(app_id)
        return dict(profile) if profile is not None else None

    def recover(self, app_id: str) -> dict[str, Any]:
        current = self.status(app_id)
        if not current["recoveryRequired"]:
            return {"status": "clean", "gameId": app_id}
        runtime = dict(current.get("runtime") or {})
        runtime.update({"state": "interrupted", "finishedAt": _now(), "pid": None})
        self._save_runtime(app_id, runtime)
        return {"status": "recovered", "gameId": app_id}

    def compile(self, app_id: str, command: Sequence[str]) -> LaunchSpec:
        self._validate_app_id(app_id)
        original = self._validate_command(command)
        profile = self._load_profile(app_id)
        if profile is None:
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED",
                detail=f"nenhum perfil por jogo foi salvo para App {app_id}",
            )
        profile = self._validated_profile(profile, app_id)
        profile_digest = self._profile_digest(profile)
        argv = list(original)
        environment = self._environ()
        environment.update(
            {
                "STEAMZERO_GAME_ID": app_id,
                "STEAMZERO_PROFILE_DIGEST": profile_digest,
            }
        )
        applied: list[str] = []
        deferred: list[str] = []

        if profile["gameMode"]:
            argv = [self._required_tool("gamemoderun"), *argv]
            applied.append("Feral GameMode")

        mango = str(profile["mangoHud"])
        gamescope = bool(profile["gamescope"])
        if mango != "off":
            environment["MANGOHUD_CONFIG"] = _MANGO_CONFIG[mango]
            if gamescope:
                self._required_tool("mangoapp")
            else:
                argv = [self._required_tool("mangohud"), *argv]
            applied.append(f"MangoHud {mango}")

        if gamescope:
            gamescope_args = [self._required_tool("gamescope"), "-r", str(profile["fps"])]
            if profile["upscaling"] == "gamescope-fsr":
                gamescope_args.extend(("-F", "fsr"))
                applied.append("Gamescope FSR")
            if mango != "off":
                gamescope_args.append("--mangoapp")
            argv = [*gamescope_args, "--", *argv]
            applied.append(f"Gamescope {profile['fps']} FPS")

        frame_generation = str(profile["frameGeneration"])
        if frame_generation != "off":
            if not any(path.is_file() and not path.is_symlink() for path in self._lsfg_manifests):
                raise SteamZeroError("E-COMPONENT-DEGRADED", detail="camada LSFG-VK ausente")
            dll = self._lossless_dll()
            if dll is None:
                raise SteamZeroError(
                    "E-COMPONENT-DEGRADED", detail="Lossless.dll não foi observado na Steam"
                )
            environment.update(
                {
                    "LSFG_LEGACY": "1",
                    "LSFG_DLL_PATH": str(dll),
                    "LSFG_MULTIPLIER": _FRAME_MULTIPLIERS[frame_generation],
                    "LSFG_FLOW_SCALE": "1.0",
                    "LSFG_PERFORMANCE_MODE": ("1" if profile["profile"] == "economy" else "0"),
                }
            )
            applied.append(f"LSFG {_FRAME_MULTIPLIERS[frame_generation]}x")

        if profile["upscaling"] in {"fsr2-quality", "fsr2-balanced"}:
            deferred.append("FSR 2 precisa ser confirmado nas opções internas do jogo")
        if profile["tdp"] is not None:
            deferred.append("TDP aguarda transporte privilegiado validado em hardware")
        if profile["gpuMode"] == "manual":
            deferred.append("Clock da GPU aguarda transporte privilegiado validado em hardware")

        return LaunchSpec(
            app_id=app_id,
            profile=profile,
            argv=tuple(argv),
            environment=environment,
            applied_effects=tuple(applied),
            deferred_effects=tuple(deferred),
            profile_digest=profile_digest,
        )

    def run(self, app_id: str, command: Sequence[str]) -> int:
        spec = self.compile(app_id, command)
        base = {
            "state": "launching",
            "gameId": app_id,
            "profileDigest": spec.profile_digest,
            "appliedEffects": list(spec.applied_effects),
            "deferredEffects": list(spec.deferred_effects),
            "startedAt": _now(),
            "pid": None,
        }
        self._save_runtime(app_id, base)
        child: ChildProcess | None = None
        previous_handlers: dict[int, Any] = {}
        try:
            child = self._processes.start(spec.argv, spec.environment)
            active = {**base, "state": "active", "pid": child.pid}
            self._save_runtime(app_id, active)

            def forward(signum: int, _frame: object) -> None:
                if child is not None:
                    with suppress(OSError):
                        child.send_signal(signum)

            if threading.current_thread() is threading.main_thread():
                for signum in (signal.SIGTERM, signal.SIGINT):
                    try:
                        previous_handlers[signum] = signal.signal(signum, forward)
                    except ValueError:
                        previous_handlers.clear()
                        break
            exit_code = child.wait()
            self._save_runtime(
                app_id,
                {**active, "state": "exited", "finishedAt": _now(), "exitCode": exit_code},
            )
            return exit_code
        except Exception as exc:
            self._save_runtime(
                app_id,
                {
                    **base,
                    "state": "failed",
                    "finishedAt": _now(),
                    "error": type(exc).__name__,
                },
            )
            raise
        finally:
            for restore_signum, handler in previous_handlers.items():
                signal.signal(restore_signum, handler)

    def _load_profile(self, app_id: str) -> dict[str, Any] | None:
        context = self._context_probe()
        profile_ids = [f"steam-gameplay:game:{app_id}"]
        if context in {"portable", "dock"}:
            profile_ids.append(f"steam-gameplay:{context}:default")
        profile_ids.append("steam-gameplay:global:default")
        with self._store_factory() as store:
            store.migrate()
            rows = [store.get_profile(profile_id) for profile_id in profile_ids]
        for row in rows:
            if row is None or row.get("kind") != "performance":
                continue
            try:
                value = json.loads(str(row["payload_json"]))
            except (KeyError, TypeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                value["gameId"] = app_id
                return value
        return None

    def _load_runtime(self, app_id: str) -> dict[str, Any] | None:
        with self._store_factory() as store:
            store.migrate()
            row = store.get_profile(f"steam-runtime:game:{app_id}")
        if row is None or row.get("kind") != _RUNTIME_KIND:
            return None
        try:
            value = json.loads(str(row["payload_json"]))
        except (KeyError, TypeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _save_runtime(self, app_id: str, payload: dict[str, Any]) -> None:
        with self._store_factory() as store:
            store.migrate()
            store.save_profile(
                {
                    "id": f"steam-runtime:game:{app_id}",
                    "scope": "game",
                    "kind": _RUNTIME_KIND,
                    "payload_json": json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    "priority": 100,
                    "profile_owner": _RUNTIME_OWNER,
                }
            )

    def _required_tool(self, name: str) -> str:
        path = self._which(name)
        if path is None:
            raise SteamZeroError("E-COMPONENT-DEGRADED", detail=f"{name} não está disponível")
        return path

    @staticmethod
    def _profile_digest(profile: dict[str, Any]) -> str:
        canonical = json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(canonical).hexdigest()

    def _lossless_dll(self) -> Path | None:
        for root in self._roots:
            manifest = root / "steamapps" / f"appmanifest_{LSFG_APP_ID}.acf"
            try:
                lines = manifest.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in lines[:300]:
                match = _INSTALL_DIR.match(line)
                if match is None:
                    continue
                directory = match.group("value").strip()
                if not directory or "/" in directory or "\\" in directory:
                    continue
                candidate = root / "steamapps/common" / directory / "Lossless.dll"
                if candidate.is_file() and not candidate.is_symlink():
                    return candidate.resolve()
        return None

    @staticmethod
    def _validate_app_id(app_id: str) -> None:
        if not app_id.isdigit() or len(app_id) > 32:
            raise SteamZeroError("E-API-SCHEMA", detail="gameId inválido")

    @staticmethod
    def _validate_command(command: Sequence[str]) -> tuple[str, ...]:
        if not command or len(command) > 512:
            raise SteamZeroError("E-API-SCHEMA", detail="comando Steam ausente ou excessivo")
        normalized: list[str] = []
        for value in command:
            if not isinstance(value, str) or not value or "\x00" in value or len(value) > 8192:
                raise SteamZeroError("E-API-SCHEMA", detail="argumento Steam inválido")
            normalized.append(value)
        return tuple(normalized)

    @staticmethod
    def _validated_profile(profile: dict[str, Any], app_id: str) -> dict[str, Any]:
        required = {
            "gameId",
            "scope",
            "profile",
            "fps",
            "tdp",
            "gpuMode",
            "gpuClock",
            "gamescope",
            "gameMode",
            "mangoHud",
            "upscaling",
            "frameGeneration",
        }
        if not required.issubset(profile) or profile.get("gameId") != app_id:
            raise SteamZeroError(
                "E-STATE-INTEGRITY", detail="perfil Steam incompleto ou divergente"
            )
        if profile["scope"] not in {"game", "global", "portable", "dock"} or profile[
            "profile"
        ] not in {
            "economy",
            "balanced",
            "performance",
        }:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="perfil Steam fora da allowlist")
        if profile["fps"] not in {30, 40, 60}:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="FPS Steam fora da allowlist")
        tdp = profile["tdp"]
        if tdp is not None and (
            not isinstance(tdp, int) or isinstance(tdp, bool) or not 3 <= tdp <= 15
        ):
            raise SteamZeroError("E-STATE-INTEGRITY", detail="TDP Steam fora da allowlist")
        if profile["gpuMode"] not in {"auto", "manual"}:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="modo de GPU fora da allowlist")
        gpu_clock = profile["gpuClock"]
        if profile["gpuMode"] == "manual" and (
            not isinstance(gpu_clock, int)
            or isinstance(gpu_clock, bool)
            or not 200 <= gpu_clock <= 1600
        ):
            raise SteamZeroError("E-STATE-INTEGRITY", detail="clock de GPU fora da allowlist")
        if profile["mangoHud"] not in {"off", "basic", "detailed"}:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="MangoHud fora da allowlist")
        if profile["upscaling"] not in {
            "native",
            "fsr2-quality",
            "fsr2-balanced",
            "gamescope-fsr",
        } or profile["frameGeneration"] not in {"off", *_FRAME_MULTIPLIERS}:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="renderização fora da allowlist")
        if not isinstance(profile["gamescope"], bool) or not isinstance(profile["gameMode"], bool):
            raise SteamZeroError("E-STATE-INTEGRITY", detail="integrações Steam inválidas")
        return dict(profile)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        separator = args.index("--")
    except ValueError:
        print("uso: steamzero-launch --appid APPID -- %command%", file=sys.stderr)
        return 2
    header, command = args[:separator], args[separator + 1 :]
    if len(header) != 2 or header[0] != "--appid":
        print("uso: steamzero-launch --appid APPID -- %command%", file=sys.stderr)
        return 2
    try:
        return SteamGameLauncher().run(header[1], command)
    except SteamZeroError as exc:
        print(f"SteamZero: {exc}", file=sys.stderr)
        return 70
    except OSError as exc:
        print(f"SteamZero: falha ao iniciar o jogo ({type(exc).__name__})", file=sys.stderr)
        return 71


if __name__ == "__main__":
    raise SystemExit(main())
