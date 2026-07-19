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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steamzero.core import fs, paths
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain.desktop import (
    PROFILE_DOCKED,
    PROFILE_SAFE,
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


def detect_deck_input_keys() -> bool:
    """True se o gamepad do Steam Deck expõe handlers de teclado no kernel.

    Quando Steam Input está ativo em background, os botões físicos do Deck
    chegam ao Plasma como eventos de tecla (kbd) além de joystick/gamepad.
    Se só houver js0/event*, os botões não acionarão atalhos KDE globais e
    o caminho futuro é InputPlumber.
    """
    text = _read_text(Path("/proc/bus/input/devices"))
    for block in text.split("\n\n"):
        lowered = block.lower()
        if "vendor=28de" not in lowered or "valve" not in lowered:
            continue
        handlers = next(
            (line.lower() for line in block.splitlines() if "handlers=" in line.lower()), ""
        )
        if "kbd" in handlers:
            return True
    return False


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
            deck_input_keys=detect_deck_input_keys(),
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
        if detect_deck_input_keys():
            available.add("deck-keys-available")
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


class KDEShortcutsEffect:
    """Atalhos KDE globais com snapshot/rollback via kglobalshortcutsrc."""

    name = "kde-shortcuts"
    _MISSING = "__steamzero_missing__"
    _DESKTOP_FILE_NAME = "steamzero-desktop-keyboard.desktop"

    _SHORTCUTS: tuple[tuple[tuple[str, ...], str, str], ...] = (
        (("kwin",), "ExposeAll", "Meta+Ctrl+D,Meta+Ctrl+D,Exposição de todas as áreas de trabalho"),
        (("kwin",), "Lock Session", "Meta+Ctrl+L,Meta+Ctrl+L,Bloquear sessão"),
        (("kwin",), "ShowDesktop", "Meta+D,Meta+D,Mostrar área de trabalho"),
        (
            ("services", "steamzero-desktop-keyboard"),
            "_launch",
            "Meta+Ctrl+K,Meta+Ctrl+K,Abrir teclado virtual SteamZero",
        ),
    )

    def __init__(
        self,
        *,
        runner: Runner = run_command,
        which: Which = shutil.which,
        applications_dir: Path | None = None,
    ) -> None:
        self._runner = runner
        self._which = which
        self._applications_dir = applications_dir or (
            Path.home() / ".local" / "share" / "applications"
        )

    def available(self, context: DesktopContext) -> bool:
        return "kde-config" in context.capabilities and all(
            self._which(command) is not None for command in ("kreadconfig6", "kwriteconfig6")
        )

    def capture(self, context: DesktopContext) -> dict[str, Any]:
        snapshot: dict[str, Any] = {"shortcuts": {}}
        for groups, key, _default in self._SHORTCUTS:
            value = self._read(groups, key)
            node = snapshot["shortcuts"]
            for group in groups:
                node = node.setdefault(group, {})
            node[key] = value if value else self._MISSING
        desktop_path = self._desktop_file_path()
        snapshot["desktopFileCreated"] = not desktop_path.is_file()
        return snapshot

    def apply(self, profile: ExperienceProfile, context: DesktopContext) -> None:
        if profile.profile_id == PROFILE_SAFE:
            return
        for groups, key, value in self._SHORTCUTS:
            self._write(groups, key, value)
        self._ensure_desktop_file()
        self._reconfigure()

    def verify(self, profile: ExperienceProfile, context: DesktopContext) -> bool:
        if profile.profile_id == PROFILE_SAFE:
            return True
        for groups, key, value in self._SHORTCUTS:
            if self._read(groups, key) != value:
                return False
        return self._desktop_file_path().is_file()

    def restore(self, snapshot: dict[str, Any]) -> None:
        shortcuts = snapshot.get("shortcuts")
        if not isinstance(shortcuts, dict):
            raise RuntimeError("snapshot de atalhos inválido")
        for groups, key, _default in self._SHORTCUTS:
            node = shortcuts
            for group in groups:
                node = node.get(group, {}) if isinstance(node, dict) else {}
            value = node.get(key, self._MISSING) if isinstance(node, dict) else self._MISSING
            if not isinstance(value, str):
                value = self._MISSING
            args = [
                "kwriteconfig6",
                "--file",
                "kglobalshortcutsrc",
                *self._group_args(groups),
                "--key",
                key,
            ]
            if value == self._MISSING:
                args.append("--delete")
            else:
                args.append(value)
            self._require_ok(tuple(args))
        created = snapshot.get("desktopFileCreated")
        if created is True:
            fs.remove_file(self._desktop_file_path())
        self._reconfigure()

    def _read(self, groups: tuple[str, ...], key: str) -> str:
        result = self._runner(
            ("kreadconfig6", "--file", "kglobalshortcutsrc", *self._group_args(groups), "--key", key),
            3.0,
        )
        return result.stdout.strip() if result.returncode == 0 else ""

    def _write(self, groups: tuple[str, ...], key: str, value: str) -> None:
        self._require_ok(
            (
                "kwriteconfig6",
                "--file",
                "kglobalshortcutsrc",
                *self._group_args(groups),
                "--key",
                key,
                value,
            )
        )

    def _group_args(self, groups: tuple[str, ...]) -> tuple[str, ...]:
        args: list[str] = []
        for group in groups:
            args.extend(("--group", group))
        return tuple(args)

    def _ensure_desktop_file(self) -> None:
        path = self._desktop_file_path()
        if path.is_file():
            return
        content = (
            "[Desktop Entry]\n"
            "Name=SteamZero Virtual Keyboard\n"
            "Exec=steamzero desktop keyboard\n"
            "Type=Application\n"
            "Terminal=false\n"
            "Icon=input-keyboard-virtual\n"
        )
        fs.write_atomic_text(path, content)

    def _desktop_file_path(self) -> Path:
        return self._applications_dir / self._DESKTOP_FILE_NAME

    def _reconfigure(self) -> None:
        if self._which("qdbus6"):
            self._runner(("qdbus6", "org.kde.kglobalaccel", "/kglobalaccel", "reconfigure"), 3.0)

    def _require_ok(self, argv: Sequence[str]) -> None:
        result = self._runner(argv, 5.0)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "falha sem detalhe"
            raise RuntimeError(f"{' '.join(argv)}: {detail}")


class VirtualKeyboardController:
    """Ativa no máximo um provider, avançando apenas após falha confirmada."""

    def __init__(self, *, runner: Runner = run_command, which: Which = shutil.which) -> None:
        self._runner = runner
        self._which = which

    def activate(self, context: DesktopContext) -> str:
        profile = profile_for(automatic_profile(context), context)
        kwin_attempted = False
        for provider in profile.keyboard_chain:
            if provider in {"plasma-keyboard", "kwin-maliit"}:
                if kwin_attempted or self._which("qdbus6") is None:
                    continue
                kwin_attempted = True
                result = self._runner(
                    (
                        "qdbus6",
                        "org.kde.KWin",
                        "/VirtualKeyboard",
                        "org.kde.kwin.VirtualKeyboard.forceActivate",
                    ),
                    3.0,
                )
                if result.returncode == 0:
                    return provider
            elif provider == "steam" and self._which("steam") is not None:
                result = self._runner(("steam", "-ifrunning", "steam://open/keyboard"), 5.0)
                if result.returncode == 0:
                    return provider
            elif provider == "wvkbd" and self._which("wvkbd-mobintl") is not None:
                result = self._runner(("wvkbd-mobintl", "--daemon"), 3.0)
                if result.returncode == 0:
                    return provider
            elif provider == "onboard" and self._which("onboard") is not None:
                result = self._runner(("onboard", "--foreground"), 3.0)
                if result.returncode == 0:
                    return provider
            # KDE Connect é visível como capacidade, mas é iniciado em outro
            # dispositivo (telefone), não por subprocesso neste coordenador.
        raise SteamZeroError(
            "E-DESKTOP-VERIFY", detail="nenhum provider de teclado aceitou a ativação"
        )


def activate_virtual_keyboard() -> str:
    context = LinuxDesktopContext().snapshot()
    return VirtualKeyboardController().activate(context)


def build_desktop_coordinator(store: StateStore) -> ExperienceCoordinator:
    effects: tuple[DesktopEffectPort, ...] = (
        KDEDisplayEffect(),
        KDEWindowEffect(),
        KDEShortcutsEffect(),
    )
    return ExperienceCoordinator(
        LinuxDesktopContext(), effects, store, LegacyWatcherConflictResolver()
    )
