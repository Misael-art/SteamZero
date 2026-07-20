# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Adapter Linux/KDE para a experiência Desktop portátil.

Toda execução usa argv fixo, caminho resolvido e timeout; nunca há shell. A
detecção é read-only e funciona sem KDE. Os dois efeitos mutáveis implementados
aqui (escala de saída e política de maximização) capturam estado para rollback.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steamzero.core import paths
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain.desktop import (
    PROFILE_DOCKED,
    DesktopConflictAction,
    DesktopContext,
    DesktopEffectPort,
    DisplayState,
    ExperienceCoordinator,
    ExperienceProfile,
    automatic_profile,
    profile_for,
)
from steamzero.domain.device import classify

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_OUTPUT_RE = re.compile(r"^Output:\s+\d+\s+(\S+)", re.MULTILINE)
_MODE_RE = re.compile(r"(\d+)x(\d+)@([0-9.]+)\*")
_SCALE_RE = re.compile(r"^\s*Scale:\s*([0-9.]+)", re.MULTILINE)
_INTERNAL_PREFIXES = ("edp", "lvds", "dsi")
_LEGACY_WATCHER_UNIT = "phasezero-steamdeck-mode-watcher.service"
_LEGACY_WATCHER_ACTION = "disable-legacy-steamdeck-mode-watcher"


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str = ""


Runner = Callable[[Sequence[str], float], CommandResult]
Which = Callable[[str], str | None]
Spawner = Callable[[Sequence[str]], bool]
Delay = Callable[[float], None]


def run_command(argv: Sequence[str], timeout: float = 3.0) -> CommandResult:
    if not argv:
        return CommandResult(127, "", "comando vazio")
    executable = shutil.which(argv[0])
    if executable is None:
        return CommandResult(127, "", f"comando ausente: {argv[0]}")
    try:
        completed = subprocess.run(  # noqa: S603
            [executable, *argv[1:]],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = _command_output(exc.stdout)
        stderr = _command_output(exc.stderr)
        detail = f"{stderr}\ncomando excedeu {timeout:g}s".strip()
        return CommandResult(124, stdout, detail)
    except OSError as exc:
        return CommandResult(126, "", f"falha ao executar {argv[0]}: {exc}")
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


def spawn_command(argv: Sequence[str]) -> bool:
    """Inicia um provider persistente sem matá-lo quando o chamador termina."""
    if not argv:
        return False
    executable = shutil.which(argv[0])
    if executable is None:
        return False
    try:
        subprocess.Popen(  # noqa: S603
            [executable, *argv[1:]],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    except OSError:
        return False
    return True


def _command_output(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def parse_kscreen_outputs(text: str) -> tuple[DisplayState, ...]:
    """Converte a saída humana do kscreen-doctor em estado estável."""
    clean = _ANSI_RE.sub("", text)
    starts = list(_OUTPUT_RE.finditer(clean))
    displays: list[DisplayState] = []
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(clean)
        block = clean[match.start() : end]
        name = match.group(1)
        mode = _MODE_RE.search(block)
        scale = _SCALE_RE.search(block)
        displays.append(
            DisplayState(
                name=name,
                connected="connected" in block,
                internal=name.lower().startswith(_INTERNAL_PREFIXES),
                width=int(mode.group(1)) if mode else None,
                height=int(mode.group(2)) if mode else None,
                refresh_hz=float(mode.group(3)) if mode else None,
                scale=float(scale.group(1)) if scale else None,
            )
        )
    return tuple(displays)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _read_dmi() -> dict[str, str]:
    base = Path("/sys/class/dmi/id")
    return {
        key: _read_text(base / filename).lower()
        for key, filename in {
            "product_name": "product_name",
            "sys_vendor": "sys_vendor",
            "board_name": "board_name",
        }.items()
    }


def _external_input_state() -> tuple[bool, bool]:
    text = _read_text(Path("/proc/bus/input/devices"))
    keyboard = False
    mouse = False
    ignored = ("steam deck", "power button", "video bus", "lid switch", "gpio")
    for block in text.split("\n\n"):
        lowered = block.lower()
        if any(marker in lowered for marker in ignored):
            continue
        handlers = next((line.lower() for line in block.splitlines() if "handlers=" in line), "")
        keyboard = keyboard or "kbd" in handlers
        mouse = mouse or "mouse" in handlers
    return keyboard, mouse


def _physical_dock_present() -> bool:
    override = os.environ.get("STEAMZERO_DOCK_PRESENT")
    if override is not None:
        return override == "1"
    for product in Path("/sys/bus/usb/devices").glob("*/product"):
        name = _read_text(product).lower()
        if any(marker in name for marker in ("dock", "docking", "usb-c hub", "type-c hub")):
            return True
    return False


def _external_controller_conflicts(runner: Runner, which: Which) -> tuple[str, ...]:
    if which("systemctl") is None:
        return ()
    result = runner(
        (
            "systemctl",
            "--user",
            "list-units",
            "--type=service",
            "--state=running",
            "--no-legend",
            "--plain",
        ),
        3.0,
    )
    if result.returncode != 0:
        return ()
    patterns = ("mode-watcher", "display-watcher", "input-remapper")
    units = []
    for line in result.stdout.splitlines():
        unit = line.split(maxsplit=1)[0] if line.strip() else ""
        lowered = unit.lower()
        if unit and "steamzero" not in lowered and any(pattern in lowered for pattern in patterns):
            units.append(f"controlador externo ativo: {unit}")
    return tuple(sorted(set(units)))


class LegacyWatcherConflictResolver:
    """Remove somente o watcher legado conhecido, no escopo user onde foi detectado."""

    def __init__(self, *, runner: Runner = run_command, which: Which = shutil.which) -> None:
        self._runner = runner
        self._which = which

    def actions(self, context: DesktopContext) -> tuple[DesktopConflictAction, ...]:
        expected = f"controlador externo ativo: {_LEGACY_WATCHER_UNIT}"
        if expected not in context.conflicts or self._which("systemctl") is None:
            return ()
        return (self._allowed_action(),)

    def release(self, action: DesktopConflictAction) -> dict[str, Any]:
        if action != self._allowed_action():
            raise SteamZeroError(
                "E-DESKTOP-CONFLICT-RELEASE", detail="ação de remediação fora da allowlist"
            )

        was_active = self._is_active()
        was_enabled = self._is_enabled()
        stopped = self._runner(action.commands[0], 15.0)
        if stopped.returncode != 0:
            raise SteamZeroError(
                "E-DESKTOP-CONFLICT-RELEASE",
                detail=self._failure_detail("não foi possível parar o watcher", stopped),
            )
        disabled = self._runner(action.commands[1], 15.0)
        if disabled.returncode != 0:
            rollback = self._restore(was_active=was_active, was_enabled=was_enabled)
            detail = self._failure_detail("não foi possível desabilitar o watcher", disabled)
            if rollback:
                detail += f"; restauração incompleta: {'; '.join(rollback)}"
            raise SteamZeroError("E-DESKTOP-CONFLICT-RELEASE", detail=detail)

        if self._is_active() or self._is_enabled():
            rollback = self._restore(was_active=was_active, was_enabled=was_enabled)
            detail = "o serviço continuou ativo ou habilitado após a operação"
            if rollback:
                detail += f"; restauração incompleta: {'; '.join(rollback)}"
            raise SteamZeroError("E-DESKTOP-CONFLICT-RELEASE", detail=detail)
        return {
            "unit": action.unit,
            "scope": action.scope,
            "stopped": True,
            "disabled": True,
            "rollbackPerformed": False,
        }

    def _allowed_action(self) -> DesktopConflictAction:
        return DesktopConflictAction(
            action_id=_LEGACY_WATCHER_ACTION,
            unit=_LEGACY_WATCHER_UNIT,
            scope="user",
            summary="Desativar o watcher legado que disputa o controle de display e entrada",
            requires_privilege=False,
            commands=(
                ("systemctl", "--user", "stop", _LEGACY_WATCHER_UNIT),
                ("systemctl", "--user", "disable", _LEGACY_WATCHER_UNIT),
            ),
        )

    def _is_active(self) -> bool:
        result = self._runner(("systemctl", "--user", "is-active", _LEGACY_WATCHER_UNIT), 3.0)
        return result.returncode == 0

    def _is_enabled(self) -> bool:
        result = self._runner(("systemctl", "--user", "is-enabled", _LEGACY_WATCHER_UNIT), 3.0)
        return result.returncode == 0

    def _restore(self, *, was_active: bool, was_enabled: bool) -> list[str]:
        failures: list[str] = []
        if was_enabled:
            enabled = self._runner(("systemctl", "--user", "enable", _LEGACY_WATCHER_UNIT), 15.0)
            if enabled.returncode != 0:
                failures.append(self._failure_detail("enable", enabled))
        if was_active:
            started = self._runner(("systemctl", "--user", "start", _LEGACY_WATCHER_UNIT), 15.0)
            if started.returncode != 0:
                failures.append(self._failure_detail("start", started))
        return failures

    def _failure_detail(self, prefix: str, result: CommandResult) -> str:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
        return f"{prefix}: {detail}"


class LinuxDesktopContext:
    """Detector Linux genérico, com enriquecimento KDE quando disponível."""

    def __init__(self, *, runner: Runner = run_command, which: Which = shutil.which) -> None:
        self._runner = runner
        self._which = which

    def snapshot(self) -> DesktopContext:
        displays: tuple[DisplayState, ...] = ()
        if self._which("kscreen-doctor"):
            result = self._runner(("kscreen-doctor", "-o"), 3.0)
            if result.returncode == 0:
                displays = parse_kscreen_outputs(result.stdout)

        capabilities = self._capabilities()
        external_keyboard, external_mouse = _external_input_state()
        declared_conflict = os.environ.get("STEAMZERO_DESKTOP_CONFLICT", "").strip()
        conflicts = _external_controller_conflicts(self._runner, self._which)
        if declared_conflict:
            conflicts = tuple(dict.fromkeys((*conflicts, declared_conflict)))
        return DesktopContext(
            device_kind=classify(_read_dmi()),
            session_type=os.environ.get("XDG_SESSION_TYPE", "unknown").lower(),
            displays=displays,
            physical_dock=_physical_dock_present(),
            external_keyboard=external_keyboard,
            external_mouse=external_mouse,
            capabilities=capabilities,
            conflicts=conflicts,
        )

    def _capabilities(self) -> frozenset[str]:
        available: set[str] = set()
        commands = {
            "kscreen-doctor": "kde-display",
            "kwriteconfig6": "kde-config",
            "maliit-keyboard": "kwin-virtual-keyboard",
            "plasma-keyboard": "plasma-keyboard",
            "steam": "steam-keyboard",
            "wvkbd-mobintl": "wvkbd",
            "onboard": "onboard",
            "kdeconnect-cli": "kde-connect",
            "inputplumber": "inputplumber",
            "tts-text": "tts-biglinux",
        }
        for command, capability in commands.items():
            if self._which(command):
                available.add(capability)
        marker = paths.config_home() / "capabilities" / "inputplumber.validated"
        if "inputplumber" in available and marker.is_file():
            available.add("inputplumber-validated")
        if os.environ.get("KDE_FULL_SESSION") == "true":
            available.add("kde-plasma")
        return frozenset(available)


class KDEDisplayEffect:
    name = "kde-display"

    def __init__(self, *, runner: Runner = run_command, which: Which = shutil.which) -> None:
        self._runner = runner
        self._which = which

    def available(self, context: DesktopContext) -> bool:
        return "kde-display" in context.capabilities and self._which("kscreen-doctor") is not None

    def capture(self, context: DesktopContext) -> dict[str, Any]:
        return {
            "outputs": [
                {"name": display.name, "connected": display.connected, "scale": display.scale}
                for display in context.displays
            ]
        }

    def apply(self, profile: ExperienceProfile, context: DesktopContext) -> None:
        display = self._target_display(profile, context)
        if display is None:
            raise RuntimeError("nenhuma saída conectada")
        scale = self._target_scale(profile, display)
        self._require_ok(("kscreen-doctor", f"output.{display.name}.enable"))
        self._require_ok(("kscreen-doctor", f"output.{display.name}.scale.{scale:g}"))

    def verify(self, profile: ExperienceProfile, context: DesktopContext) -> bool:
        result = self._runner(("kscreen-doctor", "-o"), 3.0)
        if result.returncode != 0:
            return False
        displays = parse_kscreen_outputs(result.stdout)
        target = self._target_display(
            profile,
            DesktopContext(
                device_kind=context.device_kind,
                session_type=context.session_type,
                displays=displays,
                physical_dock=context.physical_dock,
                external_keyboard=context.external_keyboard,
                external_mouse=context.external_mouse,
                capabilities=context.capabilities,
                conflicts=context.conflicts,
            ),
        )
        if target is None or target.scale is None:
            return False
        return abs(target.scale - self._target_scale(profile, target)) <= 0.02

    def restore(self, snapshot: dict[str, Any]) -> None:
        outputs = snapshot.get("outputs", [])
        if not isinstance(outputs, list):
            raise RuntimeError("snapshot de display inválido")
        for output in outputs:
            if not isinstance(output, dict) or not output.get("connected"):
                continue
            name = str(output.get("name", ""))
            scale = output.get("scale")
            if not name or not isinstance(scale, int | float):
                continue
            self._require_ok(("kscreen-doctor", f"output.{name}.enable"))
            self._require_ok(("kscreen-doctor", f"output.{name}.scale.{float(scale):g}"))

    def _target_display(
        self, profile: ExperienceProfile, context: DesktopContext
    ) -> DisplayState | None:
        connected = tuple(display for display in context.displays if display.connected)
        if profile.profile_id == PROFILE_DOCKED:
            external = next((display for display in connected if not display.internal), None)
            if external is not None:
                return external
        return next((display for display in connected if display.internal), None) or next(
            iter(connected), None
        )

    def _target_scale(self, profile: ExperienceProfile, display: DisplayState) -> float:
        if display.internal and profile.profile_id == PROFILE_DOCKED:
            return 1.35
        return profile.scale

    def _require_ok(self, argv: Sequence[str]) -> None:
        result = self._runner(argv, 5.0)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "falha sem detalhe"
            raise RuntimeError(f"{' '.join(argv)}: {detail}")


class KDEWindowEffect:
    name = "kde-window-policy"
    _MISSING = "__steamzero_missing__"

    def __init__(self, *, runner: Runner = run_command, which: Which = shutil.which) -> None:
        self._runner = runner
        self._which = which

    def available(self, context: DesktopContext) -> bool:
        return "kde-config" in context.capabilities and all(
            self._which(command) is not None for command in ("kreadconfig6", "kwriteconfig6")
        )

    def capture(self, context: DesktopContext) -> dict[str, Any]:
        result = self._read()
        return {"borderlessMaximizedWindows": result if result else self._MISSING}

    def apply(self, profile: ExperienceProfile, context: DesktopContext) -> None:
        value = "true" if profile.maximize_windows else "false"
        self._write(value)

    def verify(self, profile: ExperienceProfile, context: DesktopContext) -> bool:
        expected = "true" if profile.maximize_windows else "false"
        return self._read().lower() == expected

    def restore(self, snapshot: dict[str, Any]) -> None:
        value = snapshot.get("borderlessMaximizedWindows")
        if not isinstance(value, str):
            raise RuntimeError("snapshot de política de janela inválido")
        args = [
            "kwriteconfig6",
            "--file",
            "kwinrc",
            "--group",
            "Windows",
            "--key",
            "BorderlessMaximizedWindows",
        ]
        if value == self._MISSING:
            args.append("--delete")
        else:
            args.append(value)
        self._require_ok(tuple(args))
        self._reconfigure()

    def _read(self) -> str:
        result = self._runner(
            (
                "kreadconfig6",
                "--file",
                "kwinrc",
                "--group",
                "Windows",
                "--key",
                "BorderlessMaximizedWindows",
            ),
            3.0,
        )
        return result.stdout.strip() if result.returncode == 0 else ""

    def _write(self, value: str) -> None:
        self._require_ok(
            (
                "kwriteconfig6",
                "--file",
                "kwinrc",
                "--group",
                "Windows",
                "--key",
                "BorderlessMaximizedWindows",
                value,
            )
        )
        self._reconfigure()

    def _reconfigure(self) -> None:
        if self._which("qdbus6"):
            self._runner(("qdbus6", "org.kde.KWin", "/KWin", "reconfigure"), 3.0)

    def _require_ok(self, argv: Sequence[str]) -> None:
        result = self._runner(argv, 5.0)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "falha sem detalhe"
            raise RuntimeError(f"{' '.join(argv)}: {detail}")


def _kwin_vk_property(runner: Runner, which: Which, name: str) -> str:
    if which("qdbus6") is None:
        return ""
    result = runner(
        (
            "qdbus6",
            "org.kde.KWin",
            "/VirtualKeyboard",
            "org.freedesktop.DBus.Properties.Get",
            "org.kde.kwin.VirtualKeyboard",
            name,
        ),
        3.0,
    )
    return result.stdout.strip().lower() if result.returncode == 0 else ""


def _kwin_vk_available(runner: Runner, which: Which) -> bool:
    return _kwin_vk_property(runner, which, "available") == "true"


def _kwin_vk_visible(runner: Runner, which: Which) -> bool:
    return _kwin_vk_property(runner, which, "visible") == "true"


def _maliit_desktop_file() -> Path | None:
    candidates = (
        Path("/usr/share/applications/com.github.maliit.keyboard.desktop"),
        Path("/usr/local/share/applications/com.github.maliit.keyboard.desktop"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _process_running(name: str, *, proc: Path = Path("/proc"), uid: int | None = None) -> bool:
    """Verifica um processo do usuário atual, sem aceitar providers de outra sessão."""
    expected_uid = os.getuid() if uid is None else uid
    try:
        entries = proc.iterdir()
    except OSError:
        return False
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            comm = (entry / "comm").read_text(encoding="utf-8").strip()
            status = (entry / "status").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        uid_line = next((line for line in status.splitlines() if line.startswith("Uid:")), "")
        fields = uid_line.split()
        owner = int(fields[1]) if len(fields) > 1 and fields[1].isdigit() else None
        if comm == name and owner == expected_uid:
            return True
    return False


class KDEInputMethodEffect:
    """Configura o input method do KWin quando nenhum está ativo.

    O teclado virtual do KWin só fica disponível quando um input method
    compatível (Maliit) é publicado no Wayland. Este efeito garante que o
    Maliit seja o input method padrão quando ele estiver presente no sistema,
    restaurando o valor anterior no rollback.
    """

    name = "kde-input-method"
    _MISSING = "__steamzero_missing__"

    def __init__(self, *, runner: Runner = run_command, which: Which = shutil.which) -> None:
        self._runner = runner
        self._which = which

    def available(self, context: DesktopContext) -> bool:
        return (
            "kde-config" in context.capabilities
            and _maliit_desktop_file() is not None
            and all(
                self._which(command) is not None
                for command in ("kreadconfig6", "kwriteconfig6", "qdbus6")
            )
        )

    def capture(self, context: DesktopContext) -> dict[str, Any]:
        current = self._read_input_method()
        return {"inputMethod": current if current else self._MISSING}

    def apply(self, profile: ExperienceProfile, context: DesktopContext) -> None:
        if _kwin_vk_available(self._runner, self._which):
            return
        if _maliit_desktop_file() is None:
            raise RuntimeError("Maliit não está instalado como input method do KWin")
        self._write_input_method(str(_maliit_desktop_file()))
        self._reconfigure_kwin()

    def verify(self, profile: ExperienceProfile, context: DesktopContext) -> bool:
        if _kwin_vk_available(self._runner, self._which):
            return True
        desktop_file = _maliit_desktop_file()
        configured = self._read_input_method()
        return desktop_file is not None and desktop_file.name in configured

    def restore(self, snapshot: dict[str, Any]) -> None:
        value = snapshot.get("inputMethod")
        if not isinstance(value, str):
            raise RuntimeError("snapshot de input method inválido")
        args = [
            "kwriteconfig6",
            "--file",
            "kwinrc",
            "--group",
            "Wayland",
            "--key",
            "InputMethod",
        ]
        if value == self._MISSING:
            args.append("--delete")
        else:
            args.append(value)
        self._require_ok(tuple(args))
        self._reconfigure_kwin()

    def _read_input_method(self) -> str:
        result = self._runner(
            (
                "kreadconfig6",
                "--file",
                "kwinrc",
                "--group",
                "Wayland",
                "--key",
                "InputMethod",
            ),
            3.0,
        )
        return result.stdout.strip() if result.returncode == 0 else ""

    def _write_input_method(self, path: str) -> None:
        self._require_ok(
            (
                "kwriteconfig6",
                "--file",
                "kwinrc",
                "--group",
                "Wayland",
                "--key",
                "InputMethod",
                path,
            )
        )

    def _reconfigure_kwin(self) -> None:
        if self._which("qdbus6"):
            self._runner(("qdbus6", "org.kde.KWin", "/KWin", "reconfigure"), 3.0)

    def _require_ok(self, argv: Sequence[str]) -> None:
        result = self._runner(argv, 5.0)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "falha sem detalhe"
            raise RuntimeError(f"{' '.join(argv)}: {detail}")


class VirtualKeyboardController:
    """Ativa no máximo um provider, avançando apenas após falha confirmada.

    O KWin pode reportar sucesso no ``forceActivate`` sem tornar o teclado
    realmente visível (p. ex., input method não configurado ou servidor parado).
    Por isso verificamos ``available`` antes e ``visible`` depois, e avançamos na
    cadeia quando a ativação não produz efeito observável.
    """

    def __init__(
        self,
        *,
        runner: Runner = run_command,
        which: Which = shutil.which,
        spawner: Spawner = spawn_command,
        delay: Delay = time.sleep,
    ) -> None:
        self._runner = runner
        self._which = which
        self._spawner = spawner
        self._delay = delay

    def activate(self, context: DesktopContext) -> str:
        profile = profile_for(automatic_profile(context), context)
        kwin_attempted = False
        for provider in profile.keyboard_chain:
            if provider in {"plasma-keyboard", "kwin-maliit"}:
                if kwin_attempted or self._which("qdbus6") is None:
                    continue
                kwin_attempted = True
                kwin_available = _kwin_vk_available(self._runner, self._which)
                if kwin_available or self._start_kwin_keyboard_server():
                    result = self._runner(
                        (
                            "qdbus6",
                            "org.kde.KWin",
                            "/VirtualKeyboard",
                            "org.kde.kwin.VirtualKeyboard.forceActivate",
                        ),
                        3.0,
                    )
                    if result.returncode == 0 and _kwin_vk_visible(self._runner, self._which):
                        return provider
            elif provider == "steam" and self._which("steam") is not None:
                if self._activate_steam_keyboard():
                    return provider
            elif provider == "wvkbd" and self._which("wvkbd-mobintl") is not None:
                if self._spawner(("wvkbd-mobintl",)) and self._wait_for_process("wvkbd-mobintl"):
                    return provider
            elif provider == "onboard" and self._which("onboard") is not None:
                if self._spawner(("onboard", "--foreground")) and self._wait_for_process("onboard"):
                    return provider
            # KDE Connect é visível como capacidade, mas é iniciado em outro
            # dispositivo (telefone), não por subprocesso neste coordenador.
        raise SteamZeroError("E-DESKTOP-VERIFY", detail="nenhum provider de teclado ficou visível")

    def _start_kwin_keyboard_server(self) -> bool:
        """Tenta iniciar o servidor Maliit quando o KWin não enxerga teclado."""
        if self._which("maliit-server") is None or any(
            _process_running(name) for name in ("maliit-server", "maliit-keyboard")
        ):
            return False
        if not self._spawner(("maliit-server",)):
            return False
        for attempt in range(10):
            if _kwin_vk_available(self._runner, self._which):
                return True
            if attempt < 9:
                self._delay(0.25)
        return False

    def _activate_steam_keyboard(self) -> bool:
        if self._which("steam") is None:
            return False
        # ``steam -ifrunning`` só funciona quando o cliente já está no ar.
        if _process_running("steam"):
            result = self._runner(("steam", "-ifrunning", "steam://open/keyboard"), 5.0)
            return result.returncode == 0
        # Tenta iniciar o Steam silenciosamente e aguarda o processo subir.
        if not self._spawner(("steam", "-silent")):
            return False
        if self._wait_for_process("steam", attempts=10, interval=0.5):
            result = self._runner(("steam", "-ifrunning", "steam://open/keyboard"), 5.0)
            return result.returncode == 0
        return False

    def _wait_for_process(self, name: str, *, attempts: int = 5, interval: float = 0.2) -> bool:
        for attempt in range(attempts):
            if _process_running(name):
                return True
            if attempt < attempts - 1:
                self._delay(interval)
        return False


def activate_virtual_keyboard() -> str:
    context = LinuxDesktopContext().snapshot()
    return VirtualKeyboardController().activate(context)


def input_method_status() -> dict[str, Any]:
    """Estado observável do input method do KWin para a UI."""
    runner = run_command
    which = shutil.which
    desktop_file = _maliit_desktop_file()
    available = _kwin_vk_available(runner, which)
    configured: str | None = None
    if which("kreadconfig6"):
        result = runner(
            ("kreadconfig6", "--file", "kwinrc", "--group", "Wayland", "--key", "InputMethod"),
            3.0,
        )
        if result.returncode == 0:
            configured = result.stdout.strip() or None

    if available:
        state = "available"
        detail = "Teclado virtual do KWin está ativo."
    elif desktop_file is None:
        state = "missing"
        detail = "Nenhum input method compatível está instalado (Maliit, wvkbd ou onboard)."
    elif configured and desktop_file.name in configured:
        state = "configured-restart-needed"
        detail = "Input method configurado; reinicie a sessão Plasma para ativar."
    else:
        state = "unconfigured"
        detail = "Input method do KWin não está configurado; aplique um perfil Desktop."

    return {
        "state": state,
        "detail": detail,
        "configuredInputMethod": configured,
        "preferredInputMethod": str(desktop_file) if desktop_file else None,
        "serverRunning": _process_running("maliit-server") or _process_running("maliit-keyboard"),
    }


def build_desktop_coordinator(store: StateStore) -> ExperienceCoordinator:
    effects: tuple[DesktopEffectPort, ...] = (
        KDEInputMethodEffect(),
        KDEDisplayEffect(),
        KDEWindowEffect(),
    )
    return ExperienceCoordinator(
        LinuxDesktopContext(), effects, store, LegacyWatcherConflictResolver()
    )
