# SPDX-License-Identifier: GPL-3.0-or-later
"""Sessão Game Mode independente com fallback seguro para o Desktop.

O launcher é selecionável no SDDM. A integração privilegiada de boot vive no
módulo ``steam_boot`` e apenas aponta o SDDM para esta sessão. Uma falha de
Steam/Gamescope sempre entrega a sessão ao Plasma disponível, evitando loop.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Never

from steamzero.core import fs, paths
from steamzero.core.errors import SteamZeroError

Which = Callable[[str], str | None]
Runner = Callable[..., subprocess.CompletedProcess[str]]
BootMarker = Callable[[], dict[str, Any]]
BootStatus = Callable[[], dict[str, Any]]
_TARGETS = frozenset({"desktop", "plasma", "steam", "gamepadui", "reboot", "shutdown"})


def _mark_boot_started() -> dict[str, Any]:
    from steamzero.adapters.steam_boot import mark_started

    return mark_started()


def _direct_boot_status() -> dict[str, Any]:
    from steamzero.adapters.steam_boot import status

    return status()


def _desktop_command(which: Which = shutil.which) -> tuple[str, ...] | None:
    biglinux = which("startkde-biglinux")
    if biglinux:
        return (biglinux, "wayland")
    plasma = which("startplasma-wayland")
    if plasma:
        return (plasma,)
    x11 = which("startplasma-x11")
    return (x11,) if x11 else None


def readiness(
    *, which: Which = shutil.which, boot_status: BootStatus = _direct_boot_status
) -> dict[str, Any]:
    steam = which("steam")
    gamescope = which("gamescope")
    session_wrapper = which("gamescope-session-plus")
    desktop = _desktop_command(which)
    ready = bool(steam and gamescope and session_wrapper and desktop)
    return {
        "state": "ready" if ready else "degraded",
        "statusLabel": "Game Mode disponível" if ready else "Dependências incompletas",
        "steam": steam is not None,
        "gamescope": gamescope is not None,
        "gamescopeSession": session_wrapper is not None,
        "desktopFallback": desktop is not None,
        "independentRuntime": True,
        "sessionId": "steamzero-gamemode",
        "directBoot": boot_status(),
    }


def _target_path() -> Path:
    return paths.runtime_dir() / "gamemode-target"


def request_target(
    target: str, *, which: Which = shutil.which, runner: Runner = subprocess.run
) -> dict[str, Any]:
    if target not in _TARGETS:
        raise SteamZeroError("E-API-SCHEMA", detail="destino de sessão inválido")
    fs.write_atomic_text(_target_path(), target)
    steam = which("steam")
    if steam is not None and target in {"desktop", "plasma", "reboot", "shutdown"}:
        with contextlib.suppress(subprocess.TimeoutExpired):
            runner(
                [steam, "-shutdown"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=15,
                text=True,
            )
    return {"status": "requested", "target": target}


def run_session(
    *,
    which: Which = shutil.which,
    runner: Runner = subprocess.run,
    environ: dict[str, str] | None = None,
    boot_started: BootMarker = _mark_boot_started,
    boot_status: BootStatus = _direct_boot_status,
) -> int:
    status = readiness(which=which, boot_status=boot_status)
    desktop = _desktop_command(which)
    if desktop is None:
        raise SteamZeroError("E-SESSION-LAUNCH-FAILED", detail="fallback Plasma indisponível")
    environment = dict(os.environ if environ is None else environ)
    if (environment.get("WAYLAND_DISPLAY") or environment.get("DISPLAY")) and environment.get(
        "STEAMZERO_ALLOW_NESTED_SESSION"
    ) != "1":
        raise SteamZeroError(
            "E-SESSION-LAUNCH-FAILED",
            detail="recusando iniciar Game Mode dentro de uma sessão gráfica existente",
        )
    steam = which("steam")
    gamescope = which("gamescope")
    session_wrapper = which("gamescope-session-plus")
    if (
        not status["steam"]
        or not status["gamescope"]
        or not status["gamescopeSession"]
        or steam is None
        or gamescope is None
        or session_wrapper is None
    ):
        return _exec_desktop(desktop)
    fs.ensure_dir(paths.runtime_dir(), mode=0o700)
    target_path = _target_path()
    executable_dir = str(Path(sys.executable).resolve().parent)
    environment["PATH"] = executable_dir + os.pathsep + environment.get("PATH", "")
    environment["STEAMZERO_GAMEMODE_SESSION"] = "1"
    try:
        boot_started()
    except Exception as exc:
        # A telemetria de boot não pode transformar uma sessão funcional em tela preta.
        print(f"SteamZero: falha ao registrar início da sessão: {exc}", file=sys.stderr)
    failures = 0
    while failures < 3:
        fs.remove_file(target_path)
        completed = runner(
            [session_wrapper, "steam"],
            stdin=subprocess.DEVNULL,
            check=False,
            env=environment,
            text=True,
        )
        target = _read_target(target_path)
        fs.remove_file(target_path)
        if target in {"steam", "gamepadui"}:
            failures = 0 if completed.returncode == 0 else failures + 1
            continue
        if target == "reboot":
            _power("reboot", which=which, runner=runner)
        elif target == "shutdown":
            _power("poweroff", which=which, runner=runner)
        return _exec_desktop(desktop)
    return _exec_desktop(desktop)


def _read_target(path: Path) -> str:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return "desktop"
    return value if value in _TARGETS else "desktop"


def _power(action: str, *, which: Which, runner: Runner) -> None:
    systemctl = which("systemctl")
    if systemctl is None:
        return
    runner(
        [systemctl, action],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=30,
        text=True,
    )


def _exec_desktop(command: Sequence[str]) -> Never:
    os.execv(command[0], list(command))  # noqa: S606 - argv allowlisted e absoluto


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sessão Game Mode resiliente do SteamZero")
    parser.add_argument("--check", action="store_true", help="somente verifica dependências")
    args = parser.parse_args(argv)
    if args.check:
        status = readiness()
        print(json.dumps(status, ensure_ascii=False, sort_keys=True))
        return 0 if status["state"] == "ready" else 4
    return run_session()


def select_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Solicita transição da sessão Game Mode")
    parser.add_argument("target", choices=sorted(_TARGETS), nargs="?", default="desktop")
    args = parser.parse_args(argv)
    result = request_target(args.target)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
