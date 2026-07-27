# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Adapter Linux/KDE para a experiência Desktop portátil.

Toda execução usa argv fixo, caminho resolvido e timeout; nunca há shell. A
detecção é read-only e funciona sem KDE. Os dois efeitos mutáveis implementados
aqui (escala de saída e política de maximização) capturam estado para rollback.
"""

from __future__ import annotations

import contextlib
import json
import locale
import os
import re
import shutil
import signal
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from steamzero.core import fs, paths
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
EnvSpawner = Callable[[Sequence[str], dict[str, str]], bool]
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


def _physical_dock_present(usb_root: Path | None = None) -> bool:
    """``usb_root`` injetável: a varredura de USB só encontra dock em host que
    tem um, então sem ele este ramo nunca é exercitado num runner."""
    override = os.environ.get("STEAMZERO_DOCK_PRESENT")
    if override is not None:
        return override == "1"
    root = usb_root if usb_root is not None else Path("/sys/bus/usb/devices")
    for product in sorted(root.glob("*/product")):
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


def _kwin_vk_deactivate(runner: Runner, which: Which) -> bool:
    if which("qdbus6") is None:
        return False
    result = runner(
        (
            "qdbus6",
            "org.kde.KWin",
            "/VirtualKeyboard",
            "org.kde.kwin.VirtualKeyboard.forceDeactivate",
        ),
        3.0,
    )
    return result.returncode == 0


def _host_locale() -> str:
    """Retorna o locale do usuário sem falhar quando ele não está configurado."""
    for key in ("LC_ALL", "LANG"):
        value = os.environ.get(key)
        if value:
            return value.split(".")[0]
    try:
        return locale.getlocale()[0] or "en_US"
    except (AttributeError, ValueError):
        return "en_US"


def _locale_to_xkb_layout(locale_str: str) -> str:
    """Mapeia locale comum para layout XKB usado por teclados virtuais."""
    mapping = {
        "pt_BR": "br",
        "pt_PT": "pt",
        "en_US": "us",
        "en_GB": "gb",
        "es_ES": "es",
        "es_AR": "latam",
        "es_MX": "latam",
        "de_DE": "de",
        "de_AT": "de",
        "fr_FR": "fr",
        "fr_CA": "ca",
        "it_IT": "it",
        "ja_JP": "jp",
        "ko_KR": "kr",
        "ru_RU": "ru",
        "zh_CN": "cn",
        "zh_TW": "tw",
        "ar_SA": "ara",
        "nl_NL": "nl",
        "pl_PL": "pl",
        "tr_TR": "tr",
        "C": "us",
    }
    normalized = locale_str.split(".")[0]
    return mapping.get(normalized, normalized.split("_")[0].lower())


# maliit-keyboard identifica idiomas por código ISO (``pt``, ``zh-hans``), não
# por layout XKB; o mapa cobre os layouts expostos na UI e o resto cai no
# próprio código (vários códigos XKB coincidem com o ISO, ex.: ``de``, ``fr``).
_MALIIT_LANGUAGE_BY_LAYOUT = {
    "br": "pt",
    "us": "en",
    "gb": "en",
    "latam": "es",
    "ca": "fr",
    "jp": "ja",
    "kr": "ko",
    "cn": "zh-hans",
    "tw": "zh-hant",
    "ara": "ar",
}


def _maliit_language_for(layout: str | None) -> str | None:
    if not layout:
        return None
    return _MALIIT_LANGUAGE_BY_LAYOUT.get(layout, layout)


_MALIIT_SCHEMA = "org.maliit.keyboard.maliit"


def _gsettings_get(runner: Runner, key: str) -> str | None:
    result = runner(("gsettings", "get", _MALIIT_SCHEMA, key), 3.0)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _gsettings_set(runner: Runner, key: str, value: str) -> bool:
    return runner(("gsettings", "set", _MALIIT_SCHEMA, key, value), 3.0).returncode == 0


def _apply_maliit_language(runner: Runner, which: Which, layout: str | None) -> bool:
    """Sincroniza o idioma ativo do maliit-keyboard via gsettings.

    O maliit não lê variável de ambiente de layout; o idioma vem de
    ``org.maliit.keyboard.maliit active-language`` e a mudança vale com o
    servidor já em execução — cobre o caso de provider persistente.
    """
    language = _maliit_language_for(layout)
    if language is None or which("gsettings") is None:
        return False
    current = _gsettings_get(runner, "active-language")
    if current is not None and current.strip("'\"") == language:
        return True
    enabled = _gsettings_get(runner, "enabled-languages")
    languages = re.findall(r"'([^']+)'", enabled) if enabled is not None else []
    if language not in languages:
        languages.append(language)
        formatted = "[" + ", ".join(f"'{item}'" for item in languages) + "]"
        _gsettings_set(runner, "enabled-languages", formatted)
    return _gsettings_set(runner, "active-language", language)


# Conforto de digitação: nomes públicos estáveis → chave gsettings do maliit.
_MALIIT_COMFORT_KEYS = {
    "sound": "key-press-feedback",
    "haptic": "key-press-haptic-feedback",
    "theme": "theme",
}


def apply_maliit_comfort(
    settings: dict[str, bool | str],
    *,
    runner: Runner = run_command,
    which: Which = shutil.which,
) -> dict[str, Any]:
    """Aplica som/háptica/tema do maliit-keyboard via gsettings.

    Só grava chaves cujo valor difere do atual, confirma por readback e retorna
    os valores anteriores para o chamador poder desfazer. A mudança vale com o
    teclado em execução — o QML do maliit observa as chaves.
    """
    if which("gsettings") is None:
        raise SteamZeroError(
            "E-COMPONENT-DEGRADED", detail="gsettings indisponível para configurar o teclado"
        )
    unknown = sorted(set(settings) - set(_MALIIT_COMFORT_KEYS))
    if unknown:
        raise ValueError(f"configuração de teclado desconhecida: {', '.join(unknown)}")
    previous: dict[str, str] = {}
    applied: dict[str, str] = {}
    for name, value in settings.items():
        key = _MALIIT_COMFORT_KEYS[name]
        encoded = ("true" if value else "false") if isinstance(value, bool) else str(value)
        current = (_gsettings_get(runner, key) or "").strip("'\"")
        previous[name] = current
        if current == encoded:
            continue
        if not _gsettings_set(runner, key, encoded):
            raise SteamZeroError("E-DESKTOP-VERIFY", detail=f"não foi possível aplicar {key}")
        confirmed = (_gsettings_get(runner, key) or "").strip("'\"")
        if confirmed != encoded:
            # Reverte o que deu para reverter e falha com causa observável.
            _gsettings_set(runner, key, current)
            raise SteamZeroError("E-DESKTOP-VERIFY", detail=f"{key} não aceitou o valor {encoded}")
        applied[name] = encoded
    return {"applied": applied, "previous": previous}


# wvkbd-mobintl aceita apenas layers compiladas; um valor desconhecido em
# ``-l`` encerra o processo, então só enviamos layers garantidas.
_WVKBD_LAYER_BY_LAYOUT = {
    "ru": "cyrillic",
    "ara": "arabic",
    "gr": "greek",
    "ir": "persian",
    "ge": "georgian",
}


def _keyboard_geometry(context: DesktopContext, *, height_ratio: float = 0.35) -> dict[str, int]:
    """Calcula geometria proporcional ao display interno conectado."""
    connected = tuple(display for display in context.displays if display.connected)
    target = next((display for display in connected if display.internal), None) or next(
        iter(connected), None
    )
    if target is None or target.width is None or target.height is None:
        return {"width": 1280, "height": 400, "scale": 100}
    scale = target.scale or 1.0
    width = int(target.width * scale)
    height = max(200, int(target.height * scale * height_ratio))
    return {"width": width, "height": height, "scale": int(scale * 100)}


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


def _signal_process(name: str, sig: int, *, proc: Path = Path("/proc")) -> None:
    """Envia um sinal para todos os processos do usuário com o nome dado."""
    expected_uid = os.getuid()
    try:
        entries = proc.iterdir()
    except OSError:
        return
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
            with contextlib.suppress(OSError):
                os.kill(int(entry.name), sig)


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
    """Ativa/oculta no máximo um provider, avançando apenas após falha confirmada.

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
        env_spawner: EnvSpawner | None = None,
        delay: Delay = time.sleep,
    ) -> None:
        self._runner = runner
        self._which = which
        self._spawner = spawner
        self._env_spawner = env_spawner or spawner_env
        self._delay = delay

    def activate(self, context: DesktopContext, *, language: str | None = None) -> str:
        profile = profile_for(automatic_profile(context), context)
        layout = self._effective_layout(language)
        geometry = _keyboard_geometry(context)
        kwin_attempted = False
        for provider in profile.keyboard_chain:
            if provider in {"plasma-keyboard", "kwin-maliit"}:
                if kwin_attempted or self._which("qdbus6") is None:
                    continue
                kwin_attempted = True
                kwin_available = _kwin_vk_available(self._runner, self._which)
                if kwin_available or self._start_kwin_keyboard_server(layout, geometry):
                    _apply_maliit_language(self._runner, self._which, layout)
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
                if self._process_running("wvkbd-mobintl"):
                    self._signal_provider("wvkbd-mobintl", signal.SIGUSR2)
                    return provider
                if self._spawn_wvkbd(layout, geometry) and self._wait_for_process("wvkbd-mobintl"):
                    return provider
            elif provider == "onboard" and self._which("onboard") is not None:
                if self._spawn_onboard(layout, geometry) and self._wait_for_process("onboard"):
                    return provider
            # KDE Connect é visível como capacidade, mas é iniciado em outro
            # dispositivo (telefone), não por subprocesso neste coordenador.
        raise SteamZeroError("E-DESKTOP-VERIFY", detail="nenhum provider de teclado ficou visível")

    def toggle(self, context: DesktopContext, *, language: str | None = None) -> dict[str, Any]:
        """Alterna visibilidade do teclado virtual, preferindo o DBus do KWin."""
        if self._which("qdbus6") is not None and _kwin_vk_available(self._runner, self._which):
            visible = _kwin_vk_visible(self._runner, self._which)
            if visible:
                _kwin_vk_deactivate(self._runner, self._which)
                return {"action": "hide", "provider": "kwin-maliit"}
            provider = self.activate(context, language=language)
            return {"action": "show", "provider": provider}

        running_provider = self._running_provider()
        if running_provider == "wvkbd" and self._process_running("wvkbd-mobintl"):
            self._signal_provider("wvkbd-mobintl", signal.SIGUSR1)
            return {"action": "hide", "provider": "wvkbd"}
        if running_provider:
            self._stop_provider(running_provider)
            return {"action": "hide", "provider": running_provider}

        provider = self.activate(context, language=language)
        return {"action": "show", "provider": provider}

    def _effective_layout(self, language: str | None) -> str | None:
        if language:
            return language
        host = _host_locale()
        return _locale_to_xkb_layout(host)

    def _start_kwin_keyboard_server(self, layout: str | None, geometry: dict[str, int]) -> bool:
        """Tenta iniciar o servidor Maliit quando o KWin não enxerga teclado."""
        if self._which("maliit-server") is None or any(
            _process_running(name) for name in ("maliit-server", "maliit-keyboard")
        ):
            return False
        _apply_maliit_language(self._runner, self._which, layout)
        env = os.environ.copy()
        scale = geometry.get("scale", 100) / 100.0
        if scale > 0:
            env["QT_SCREEN_SCALE_FACTORS"] = f"{scale}"
        if not self._env_spawner(("maliit-server",), env):
            return False
        for attempt in range(10):
            if _kwin_vk_available(self._runner, self._which):
                return True
            if attempt < 9:
                self._delay(0.25)
        return False

    def _spawn_wvkbd(self, layout: str | None, geometry: dict[str, int]) -> bool:
        argv: list[str] = ["wvkbd-mobintl"]
        layer = _WVKBD_LAYER_BY_LAYOUT.get(layout or "")
        if layer:
            argv.extend(("-l", layer))
        width = geometry.get("width", 0)
        height = geometry.get("height", 0)
        if width and height:
            # A largura do teclado segue a tela; controlamos apenas a altura.
            height_arg = "-L" if width >= height else "-H"
            argv.extend((height_arg, str(height)))
        return self._spawner(tuple(argv))

    def _spawn_onboard(self, layout: str | None, geometry: dict[str, int]) -> bool:
        # Onboard usa o layout XKB do sistema; ``-l`` espera arquivo .onboard
        # (aparência), não idioma — por isso não é usado aqui.
        argv: list[str] = ["onboard", "--foreground"]
        width = geometry.get("width")
        height = geometry.get("height")
        if width and height:
            argv.extend(("--size", f"{width}x{height}"))
        return self._spawner(tuple(argv))

    def _activate_steam_keyboard(self, *, open_keyboard: bool = True) -> bool:
        if self._which("steam") is None:
            return False
        uri = "steam://open/keyboard" if open_keyboard else "steam://close/keyboard"
        # ``steam -ifrunning`` só funciona quando o cliente já está no ar.
        if _process_running("steam"):
            result = self._runner(("steam", "-ifrunning", uri), 5.0)
            return result.returncode == 0
        # Tenta iniciar o Steam silenciosamente e aguarda o processo subir.
        if not self._spawner(("steam", "-silent")):
            return False
        if self._wait_for_process("steam", attempts=10, interval=0.5):
            result = self._runner(("steam", "-ifrunning", uri), 5.0)
            return result.returncode == 0
        return False

    def _running_provider(self) -> str | None:
        names = {
            "kwin-maliit": ("maliit-server", "maliit-keyboard"),
            "wvkbd": ("wvkbd-mobintl",),
            "onboard": ("onboard",),
            "steam": ("steam",),
        }
        for provider, procs in names.items():
            if any(self._process_running(name) for name in procs):
                return provider
        return None

    def _process_running(self, name: str) -> bool:
        return _process_running(name)

    def _signal_provider(self, name: str, sig: int) -> None:
        _signal_process(name, sig)

    def _stop_provider(self, provider: str) -> None:
        signals_by_provider: dict[str, tuple[str, ...]] = {
            "kwin-maliit": ("maliit-server", "maliit-keyboard"),
            "wvkbd": ("wvkbd-mobintl",),
            "onboard": ("onboard",),
        }
        for name in signals_by_provider.get(provider, ()):
            self._signal_provider(name, signal.SIGTERM)
        if provider == "steam":
            self._activate_steam_keyboard(open_keyboard=False)

    def _wait_for_process(self, name: str, *, attempts: int = 5, interval: float = 0.2) -> bool:
        for attempt in range(attempts):
            if _process_running(name):
                return True
            if attempt < attempts - 1:
                self._delay(interval)
        return False


def activate_virtual_keyboard(language: str | None = None) -> str:
    context = LinuxDesktopContext().snapshot()
    return VirtualKeyboardController().activate(context, language=language)


class KDEPanelEffect:
    """Auto-oculta painéis do Plasma para maximizar área útil, com rollback."""

    name = "kde-panel"
    # A leitura não pode atribuir ``hiding`` — capturar estado deve ser
    # observação pura, senão todo apply corrompe a configuração dos painéis.
    _READ_SCRIPT = """
var result = {};
var panels = panelIds;
for (var i = 0; i < panels.length; i++) {
    result[panels[i]] = panelById(panels[i]).hiding;
}
print(JSON.stringify(result));
"""
    _WRITE_SCRIPT_TEMPLATE = """
var panels = panelIds;
for (var i = 0; i < panels.length; i++) {
    panelById(panels[i]).hiding = '%s';
}
"""

    def __init__(self, *, runner: Runner = run_command, which: Which = shutil.which) -> None:
        self._runner = runner
        self._which = which

    def available(self, context: DesktopContext) -> bool:
        return (
            "kde-plasma" in context.capabilities
            and self._which("qdbus6") is not None
            and self._which("plasmashell") is not None
        )

    def capture(self, context: DesktopContext) -> dict[str, Any]:
        return {"panelHidingStates": self._read_hiding_states()}

    def apply(self, profile: ExperienceProfile, context: DesktopContext) -> None:
        hiding = "autohide" if profile.panel_auto_hide else "none"
        self._set_hiding(hiding)

    def verify(self, profile: ExperienceProfile, context: DesktopContext) -> bool:
        expected = "autohide" if profile.panel_auto_hide else "none"
        states = self._read_hiding_states()
        if not states:
            return False
        return all(state == expected for state in states.values())

    def restore(self, snapshot: dict[str, Any]) -> None:
        value = snapshot.get("panelHidingStates")
        if not isinstance(value, dict):
            raise RuntimeError("snapshot de painel inválido")
        for panel_id, hiding in value.items():
            self._set_panel_hiding(panel_id, str(hiding))

    def _read_hiding_states(self) -> dict[str, str]:
        result = self._evaluate_script(self._READ_SCRIPT)
        if result is None:
            return {}
        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            return {}
        return {str(key): str(value) for key, value in parsed.items() if isinstance(value, str)}

    def _set_hiding(self, hiding: str) -> None:
        script = self._WRITE_SCRIPT_TEMPLATE % hiding
        self._evaluate_script(script)

    def _set_panel_hiding(self, panel_id: str, hiding: str) -> None:
        script = f"var p = panelById({panel_id}); if (p) p.hiding = '{hiding}';"
        self._evaluate_script(script)

    def _evaluate_script(self, script: str) -> str | None:
        if self._which("qdbus6") is None:
            return None
        result = self._runner(
            (
                "qdbus6",
                "org.kde.plasmashell",
                "/PlasmaShell",
                "org.kde.PlasmaShell.evaluateScript",
                script,
            ),
            5.0,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None


_SHORTCUT_MARKER = "X-SteamZero-Managed=true"
_SHORTCUT_DESKTOP_TEMPLATE = """[Desktop Entry]
Type=Application
Name=Alternar teclado virtual SteamZero
Exec=steamzero desktop keyboard --toggle
Icon=input-keyboard-virtual
NoDisplay=true
Terminal=false
X-KDE-GlobalAccel-CommandShortcut=true
X-SteamZero-Managed=true
"""


class KDEShortcutEffect:
    """Registra atalho global (Meta+K) para alternar o teclado, com rollback.

    Publica um desktop file próprio (marcado) em escopo de usuário e o binding
    em ``kglobalshortcutsrc``. O kglobalaccel só carrega o atalho na próxima
    sessão; a configuração é verificável por readback imediatamente.
    """

    name = "kde-shortcut"
    _SERVICE = "steamzero-keyboard-toggle.desktop"
    _DEFAULT_ENTRY = "Meta+K,Meta+K,Alternar teclado virtual SteamZero"

    def __init__(
        self,
        *,
        runner: Runner = run_command,
        which: Which = shutil.which,
        applications_dir: Path | None = None,
    ) -> None:
        self._runner = runner
        self._which = which
        self._apps_dir = applications_dir or Path.home() / ".local" / "share" / "applications"

    def available(self, context: DesktopContext) -> bool:
        return (
            "kde-config" in context.capabilities
            and self._which("kreadconfig6") is not None
            and self._which("kwriteconfig6") is not None
        )

    def capture(self, context: DesktopContext) -> dict[str, Any]:
        return {
            "shortcutEntry": self._read_entry(),
            "desktopFilePresent": (self._apps_dir / self._SERVICE).is_file(),
        }

    def apply(self, profile: ExperienceProfile, context: DesktopContext) -> None:
        self._write_desktop_file()
        self._write_entry(self._DEFAULT_ENTRY)

    def verify(self, profile: ExperienceProfile, context: DesktopContext) -> bool:
        target = self._apps_dir / self._SERVICE
        return target.is_file() and self._read_entry() == self._DEFAULT_ENTRY

    def restore(self, snapshot: dict[str, Any]) -> None:
        entry = snapshot.get("shortcutEntry")
        if not snapshot.get("desktopFilePresent"):
            self._remove_desktop_file()
        if isinstance(entry, str) and entry:
            self._write_entry(entry)
        else:
            self._delete_entry()

    def _write_desktop_file(self) -> None:
        target = self._apps_dir / self._SERVICE
        if target.exists():
            content = _read_text(target)
            if _SHORTCUT_MARKER not in content:
                raise RuntimeError(f"recusando sobrescrever artefato sem marcador: {target}")
        fs.ensure_dir(target.parent)
        fs.write_atomic_text(target, _SHORTCUT_DESKTOP_TEMPLATE)

    def _remove_desktop_file(self) -> None:
        target = self._apps_dir / self._SERVICE
        if not target.exists():
            return
        if _SHORTCUT_MARKER not in _read_text(target):
            raise RuntimeError(f"recusando remover artefato sem marcador: {target}")
        fs.remove_file(target)

    def _config_argv(self, *suffix: str) -> tuple[str, ...]:
        return (
            "--file",
            "kglobalshortcutsrc",
            "--group",
            "services",
            "--group",
            self._SERVICE,
            "--key",
            "_launch",
            *suffix,
        )

    def _read_entry(self) -> str | None:
        result = self._runner(("kreadconfig6", *self._config_argv()), 3.0)
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def _write_entry(self, value: str) -> None:
        self._runner(("kwriteconfig6", *self._config_argv(value)), 3.0)

    def _delete_entry(self) -> None:
        self._runner(("kwriteconfig6", *self._config_argv("--delete")), 3.0)


_EDGE_SCRIPT_ID = "steamzero-edge-keyboard"
_EDGE_METADATA = """{
  "KPlugin": {
    "Id": "steamzero-edge-keyboard",
    "Name": "SteamZero Edge Keyboard",
    "Description": "Desliza da borda inferior alterna o teclado virtual",
    "ServiceTypes": ["KWin/Script"],
    "Version": "1.0"
  },
  "X-Plasma-API": "javascript",
  "X-Plasma-MainScript": "code/main.js",
  "X-SteamZero-Managed": true
}
"""
_EDGE_MAIN_JS = """// X-SteamZero-Managed: true
function steamzeroToggleKeyboard() {
    callDBus(
        "org.kde.KWin",
        "/VirtualKeyboard",
        "org.freedesktop.DBus.Properties",
        "Get",
        "org.kde.kwin.VirtualKeyboard",
        "visible",
        function (visible) {
            var method = visible ? "forceDeactivate" : "forceActivate";
            callDBus("org.kde.KWin", "/VirtualKeyboard", "org.kde.kwin.VirtualKeyboard", method);
        }
    );
}
registerTouchScreenEdge(KWin.ElectricBottom, steamzeroToggleKeyboard);
"""


class KDEEdgeGestureEffect:
    """Gesto de toque na borda inferior alterna o teclado (spike, com rollback).

    Publica um KWin script marcado em escopo de usuário e o habilita em
    ``kwinrc [Plugins]``. O KWin recarrega scripts no ``reconfigure``; se o
    gesto se mostrar instável no host, o restore remove tudo.
    """

    name = "kde-edge-gesture"

    def __init__(
        self,
        *,
        runner: Runner = run_command,
        which: Which = shutil.which,
        scripts_dir: Path | None = None,
    ) -> None:
        self._runner = runner
        self._which = which
        self._scripts_dir = scripts_dir or Path.home() / ".local" / "share" / "kwin" / "scripts"

    def available(self, context: DesktopContext) -> bool:
        return (
            "kde-config" in context.capabilities
            and self._which("kreadconfig6") is not None
            and self._which("kwriteconfig6") is not None
        )

    def capture(self, context: DesktopContext) -> dict[str, Any]:
        return {
            "pluginEnabled": self._read_enabled(),
            "scriptPresent": self._metadata_path().is_file(),
        }

    def apply(self, profile: ExperienceProfile, context: DesktopContext) -> None:
        self._write_script()
        self._write_enabled("true")
        self._reconfigure()

    def verify(self, profile: ExperienceProfile, context: DesktopContext) -> bool:
        return self._metadata_path().is_file() and self._read_enabled() == "true"

    def restore(self, snapshot: dict[str, Any]) -> None:
        if not snapshot.get("scriptPresent"):
            self._remove_script()
        enabled = snapshot.get("pluginEnabled")
        if isinstance(enabled, str) and enabled:
            self._write_enabled(enabled)
        else:
            self._delete_enabled()
        self._reconfigure()

    def _script_root(self) -> Path:
        return self._scripts_dir / _EDGE_SCRIPT_ID

    def _metadata_path(self) -> Path:
        return self._script_root() / "metadata.json"

    def _write_script(self) -> None:
        metadata = self._metadata_path()
        if metadata.exists() and "X-SteamZero-Managed" not in _read_text(metadata):
            raise RuntimeError(f"recusando sobrescrever artefato sem marcador: {metadata}")
        code_dir = self._script_root() / "contents" / "code"
        fs.ensure_dir(code_dir)
        fs.write_atomic_text(metadata, _EDGE_METADATA)
        fs.write_atomic_text(code_dir / "main.js", _EDGE_MAIN_JS)

    def _remove_script(self) -> None:
        metadata = self._metadata_path()
        if not metadata.exists():
            return
        if "X-SteamZero-Managed" not in _read_text(metadata):
            raise RuntimeError(f"recusando remover artefato sem marcador: {metadata}")
        fs.remove_tree(self._script_root())

    def _plugins_argv(self, *suffix: str) -> tuple[str, ...]:
        return (
            "--file",
            "kwinrc",
            "--group",
            "Plugins",
            "--key",
            f"{_EDGE_SCRIPT_ID}Enabled",
            *suffix,
        )

    def _read_enabled(self) -> str | None:
        result = self._runner(("kreadconfig6", *self._plugins_argv()), 3.0)
        if result.returncode != 0:
            return None
        return result.stdout.strip() or None

    def _write_enabled(self, value: str) -> None:
        self._runner(("kwriteconfig6", *self._plugins_argv(value)), 3.0)

    def _delete_enabled(self) -> None:
        self._runner(("kwriteconfig6", *self._plugins_argv("--delete")), 3.0)

    def _reconfigure(self) -> None:
        if self._which("qdbus6") is None:
            return
        self._runner(("qdbus6", "org.kde.KWin", "/KWin", "org.kde.KWin.reconfigure"), 5.0)


def logout_desktop_session(*, runner: Runner = run_command, which: Which = shutil.which) -> bool:
    """Encerra a sessão Plasma atual via DBus (sem prompt).

    Usado após registrar o alvo de sessão Game Mode: o logout devolve o
    controle à cadeia de boot, que lê o alvo e sobe a sessão pedida.
    """
    if which("qdbus6") is None:
        return False
    result = runner(
        ("qdbus6", "org.kde.Shutdown", "/Shutdown", "org.kde.Shutdown.logout"),
        5.0,
    )
    return result.returncode == 0


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
        "hostLocale": _host_locale(),
        "keyboardLayout": _locale_to_xkb_layout(_host_locale()),
    }


def reduced_motion_enabled(*, runner: Runner = run_command, which: Which = shutil.which) -> bool:
    """Lê a preferência real de animações do Plasma sem alterar o host."""
    if which("kreadconfig6") is None:
        return False
    result = runner(
        (
            "kreadconfig6",
            "--file",
            "kdeglobals",
            "--group",
            "KDE",
            "--key",
            "AnimationDurationFactor",
        ),
        3.0,
    )
    if result.returncode != 0:
        return False
    try:
        return float(result.stdout.strip()) <= 0
    except ValueError:
        return False


def high_contrast_enabled(*, runner: Runner = run_command, which: Which = shutil.which) -> bool:
    """Lê o esquema de cores do Plasma sem alterar o host.

    O Plasma não expõe um booleano de alto contraste: a preferência é o esquema
    de cores escolhido. Tratamos como ativo quando o nome do esquema declara
    contraste alto, que é o que os esquemas de acessibilidade do KDE usam.
    """
    if which("kreadconfig6") is None:
        return False
    result = runner(
        ("kreadconfig6", "--file", "kdeglobals", "--group", "General", "--key", "ColorScheme"),
        3.0,
    )
    if result.returncode != 0:
        return False
    return "highcontrast" in result.stdout.strip().replace(" ", "").replace("-", "").lower()


def toggle_virtual_keyboard(
    language: str | None = None,
    *,
    runner: Runner = run_command,
    which: Which = shutil.which,
    spawner: Spawner = spawn_command,
    delay: Delay = time.sleep,
) -> dict[str, Any]:
    context = LinuxDesktopContext(runner=runner, which=which).snapshot()
    return VirtualKeyboardController(
        runner=runner, which=which, spawner=spawner, delay=delay
    ).toggle(context, language=language)


def launch_ashyterm(
    *,
    which: Which = shutil.which,
    spawn: Callable[[Sequence[str], dict[str, str]], bool] | None = None,
) -> dict[str, Any]:
    """Inicia o Terminal Ashy com ambiente favorável ao teclado virtual."""
    spawn = spawn or spawner_env
    executable = which("ashyterm") or which("org.communitybig.ashyterm")
    desktop_file = Path("/usr/share/applications/org.communitybig.ashyterm.desktop")
    if executable is None:
        # Fallback para a desktop entry quando não há binário no PATH
        if not desktop_file.is_file():
            raise SteamZeroError(
                "E-COMPONENT-DEGRADED", detail="Terminal Ashy não encontrado no sistema"
            )
        executable = "xdg-open"
        argv: tuple[str, ...] = (executable, str(desktop_file))
    else:
        argv = (executable,)

    env = os.environ.copy()
    # GTK4/Wayland: usar o input method nativo do compositor quando disponível.
    env["GTK_IM_MODULE"] = env.get("GTK_IM_MODULE", "wayland")
    # Garante que o foco em widgets de texto dispare o text-input do Wayland.
    env["GDK_BACKEND"] = env.get("GDK_BACKEND", "wayland")

    if not spawn(argv, env):
        raise SteamZeroError("E-DESKTOP-VERIFY", detail="não foi possível iniciar o Terminal Ashy")
    return {"status": "started", "application": "ashyterm", "command": argv[0]}


def spawner_env(argv: Sequence[str], env: dict[str, str]) -> bool:
    """Inicia provider persistente com ambiente customizado."""
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
            env=env,
        )
    except OSError:
        return False
    return True


def build_desktop_coordinator(store: StateStore) -> ExperienceCoordinator:
    effects: tuple[DesktopEffectPort, ...] = (
        KDEInputMethodEffect(),
        KDEDisplayEffect(),
        KDEWindowEffect(),
        KDEPanelEffect(),
        KDEShortcutEffect(),
        KDEEdgeGestureEffect(),
    )
    return ExperienceCoordinator(
        LinuxDesktopContext(), effects, store, LegacyWatcherConflictResolver()
    )
