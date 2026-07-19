# SPDX-License-Identifier: GPL-3.0-or-later
"""Parser e efeitos KDE sem tocar a sessão real."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from steamzero.adapters.desktop_kde import (
    CommandResult,
    KDEDisplayEffect,
    KDEShortcutsEffect,
    LegacyWatcherConflictResolver,
    LinuxDesktopContext,
    VirtualKeyboardController,
    detect_deck_input_keys,
    parse_kscreen_outputs,
    run_command,
)
from steamzero.core.errors import SteamZeroError
from steamzero.domain.desktop import PROFILE_HANDHELD, DesktopContext, profile_for

KSCREEN = """Output: 1 eDP-1 uuid-a
\tenabled
\tconnected
\tPanel
\tModes:  1:800x1280@60.00*!  2:800x600@60.00
\tScale: 1.35
Output: 2 DP-1 uuid-b
\tenabled
\tconnected
\tModes:  1:2560x1080@75.00*!
\tScale: 1
"""

LEGACY_WATCHER = "phasezero-steamdeck-mode-watcher.service"


def _conflicted_context() -> DesktopContext:
    return DesktopContext(
        "deck-lcd",
        "wayland",
        parse_kscreen_outputs(KSCREEN),
        False,
        False,
        False,
        frozenset(),
        (f"controlador externo ativo: {LEGACY_WATCHER}",),
    )


def test_parse_kscreen_outputs() -> None:
    outputs = parse_kscreen_outputs(KSCREEN)
    assert [(output.name, output.internal, output.scale) for output in outputs] == [
        ("eDP-1", True, 1.35),
        ("DP-1", False, 1.0),
    ]
    assert outputs[1].refresh_hz == 75.0


def test_run_command_converts_timeout_to_degraded_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(
            ("/usr/bin/kscreen-doctor", "-o"),
            3.0,
            output="saída parcial",
            stderr="display ocupado",
        )

    monkeypatch.setattr("steamzero.adapters.desktop_kde.shutil.which", lambda _name: "/tool")
    monkeypatch.setattr("steamzero.adapters.desktop_kde.subprocess.run", timeout)

    result = run_command(("kscreen-doctor", "-o"), 3.0)

    assert result.returncode == 124
    assert result.stdout == "saída parcial"
    assert "display ocupado" in result.stderr
    assert "excedeu 3s" in result.stderr


def test_display_effect_targets_internal_handheld() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        return CommandResult(0, KSCREEN)

    outputs = parse_kscreen_outputs(KSCREEN)
    context = DesktopContext(
        "deck-lcd",
        "wayland",
        outputs,
        False,
        False,
        False,
        frozenset({"kde-display"}),
    )
    effect = KDEDisplayEffect(runner=runner, which=lambda _command: "/usr/bin/tool")
    effect.apply(profile_for(PROFILE_HANDHELD, context), context)
    assert ("kscreen-doctor", "output.eDP-1.enable") in calls
    assert ("kscreen-doctor", "output.eDP-1.scale.1.35") in calls


def test_virtual_keyboard_falls_back_to_steam_after_kwin_failure() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        return CommandResult(1 if argv[0] == "qdbus6" else 0, "")

    context = DesktopContext(
        "deck-lcd",
        "wayland",
        parse_kscreen_outputs(KSCREEN),
        False,
        False,
        False,
        frozenset({"kwin-virtual-keyboard", "steam-keyboard"}),
    )
    controller = VirtualKeyboardController(runner=runner, which=lambda command: command)
    assert controller.activate(context) == "steam"
    assert [call[0] for call in calls] == ["qdbus6", "steam"]


def test_virtual_keyboard_uses_wvkbd_when_steam_and_kwin_absent() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        return CommandResult(0, "")

    context = DesktopContext(
        "deck-lcd",
        "wayland",
        parse_kscreen_outputs(KSCREEN),
        False,
        False,
        False,
        frozenset({"wvkbd"}),
    )
    controller = VirtualKeyboardController(runner=runner, which=lambda command: command)
    assert controller.activate(context) == "wvkbd"
    assert ("wvkbd-mobintl", "--daemon") in calls


def test_virtual_keyboard_falls_back_to_wvkbd_after_kwin_and_steam_fail() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        failing = {"qdbus6", "steam"}
        return CommandResult(0 if argv[0] not in failing else 1, "")

    context = DesktopContext(
        "deck-lcd",
        "wayland",
        parse_kscreen_outputs(KSCREEN),
        False,
        False,
        False,
        frozenset({"kwin-virtual-keyboard", "steam-keyboard", "wvkbd"}),
    )
    controller = VirtualKeyboardController(runner=runner, which=lambda command: command)
    assert controller.activate(context) == "wvkbd"
    assert [call[0] for call in calls] == ["qdbus6", "steam", "wvkbd-mobintl"]


def test_virtual_keyboard_raises_when_no_provider_accepts() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        return CommandResult(1, "")

    context = DesktopContext(
        "deck-lcd",
        "wayland",
        parse_kscreen_outputs(KSCREEN),
        False,
        False,
        False,
        frozenset({"wvkbd"}),
    )
    controller = VirtualKeyboardController(runner=runner, which=lambda command: command)
    with pytest.raises(SteamZeroError, match="E-DESKTOP-VERIFY"):
        controller.activate(context)
    assert ("wvkbd-mobintl", "--daemon") in calls


def test_context_reports_generic_external_mode_watcher() -> None:
    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        if argv[0] == "kscreen-doctor":
            return CommandResult(0, KSCREEN)
        if argv[0] == "systemctl":
            return CommandResult(
                0,
                "vendor-steamdeck-mode-watcher.service loaded active running watcher\n",
            )
        return CommandResult(127, "")

    present = {"kscreen-doctor", "systemctl"}
    context = LinuxDesktopContext(
        runner=runner, which=lambda command: command if command in present else None
    ).snapshot()
    assert context.conflicts == (
        "controlador externo ativo: vendor-steamdeck-mode-watcher.service",
    )


def test_legacy_watcher_release_uses_exact_user_scope_commands() -> None:
    active = True
    enabled = True
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        nonlocal active, enabled
        call = tuple(argv)
        calls.append(call)
        operation = call[2]
        if operation == "is-active":
            return CommandResult(0 if active else 3, "active\n" if active else "inactive\n")
        if operation == "is-enabled":
            return CommandResult(0 if enabled else 1, "enabled\n" if enabled else "disabled\n")
        if operation == "stop":
            active = False
            return CommandResult(0, "")
        if operation == "disable":
            enabled = False
            return CommandResult(0, "")
        return CommandResult(1, "", "ação inesperada")

    resolver = LegacyWatcherConflictResolver(runner=runner, which=lambda command: command)
    clean = DesktopContext(**{**_conflicted_context().__dict__, "conflicts": ()})
    assert resolver.actions(clean) == ()
    action = resolver.actions(_conflicted_context())[0]
    result = resolver.release(action)

    assert result["stopped"] is True
    assert result["disabled"] is True
    assert active is False and enabled is False
    assert action.commands == (
        ("systemctl", "--user", "stop", LEGACY_WATCHER),
        ("systemctl", "--user", "disable", LEGACY_WATCHER),
    )
    assert all(call[:2] == ("systemctl", "--user") for call in calls)


def test_legacy_watcher_disable_failure_restores_previous_state() -> None:
    active = True
    enabled = True
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        nonlocal active, enabled
        call = tuple(argv)
        calls.append(call)
        operation = call[2]
        if operation == "is-active":
            return CommandResult(0 if active else 3, "active\n" if active else "inactive\n")
        if operation == "is-enabled":
            return CommandResult(0 if enabled else 1, "enabled\n" if enabled else "disabled\n")
        if operation == "stop":
            active = False
            return CommandResult(0, "")
        if operation == "disable":
            return CommandResult(1, "", "falha simulada")
        if operation == "enable":
            enabled = True
            return CommandResult(0, "")
        if operation == "start":
            active = True
            return CommandResult(0, "")
        return CommandResult(1, "", "ação inesperada")

    resolver = LegacyWatcherConflictResolver(runner=runner, which=lambda command: command)
    action = resolver.actions(_conflicted_context())[0]

    with pytest.raises(SteamZeroError, match="não foi possível desabilitar"):
        resolver.release(action)

    assert active is True and enabled is True
    assert ("systemctl", "--user", "enable", LEGACY_WATCHER) in calls
    assert ("systemctl", "--user", "start", LEGACY_WATCHER) in calls


DECK_INPUT_DEVICES_WITH_KEYS = """I: Bus=0018 Vendor=28de Product=1205 Version=0100
N: Name="Valve Software Steam Deck Controller"
P: Phys=usb-0000:03:00.3-1/input0
U: Uniq=
H: Handlers=event0 js0 kbd
B: PROP=0
B: EV=10001b
B: KEY=7fff800000000000 e0ffdfdbe7ffffff 1ffffffffffffe78
"""

DECK_INPUT_DEVICES_PURE_GAMEPAD = """I: Bus=0003 Vendor=28de Product=1205 Version=0100
N: Name="Valve Software Steam Deck Controller"
H: Handlers=event0 js0
B: PROP=0
"""


def test_detect_deck_input_keys_finds_valve_keyboard_handler() -> None:
    def read_text(_path: Path) -> str:
        return DECK_INPUT_DEVICES_WITH_KEYS

    import steamzero.adapters.desktop_kde as desktop_kde

    original = desktop_kde._read_text
    desktop_kde._read_text = read_text
    try:
        assert detect_deck_input_keys() is True
    finally:
        desktop_kde._read_text = original


def test_detect_deck_input_keys_reports_false_for_pure_gamepad() -> None:
    def read_text(_path: Path) -> str:
        return DECK_INPUT_DEVICES_PURE_GAMEPAD

    import steamzero.adapters.desktop_kde as desktop_kde

    original = desktop_kde._read_text
    desktop_kde._read_text = read_text
    try:
        assert detect_deck_input_keys() is False
    finally:
        desktop_kde._read_text = original


def test_status_reports_deck_input_keys_state(monkeypatch: pytest.MonkeyPatch) -> None:
    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        if argv[0] == "kscreen-doctor":
            return CommandResult(0, KSCREEN)
        if argv[0] == "systemctl":
            return CommandResult(0, "")
        return CommandResult(127, "")

    monkeypatch.setattr("steamzero.adapters.desktop_kde.detect_deck_input_keys", lambda: True)
    present = {"kscreen-doctor", "systemctl"}
    context = LinuxDesktopContext(
        runner=runner,
        which=lambda command: command if command in present else None,
    ).snapshot()
    assert context.deck_input_keys is True
    assert "deck-keys-available" in context.capabilities
    assert context.to_dict()["deckInputKeys"] is True


def test_kde_shortcuts_effect_applies_meta_ctrl_k_for_osk(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []
    apps_dir = tmp_path / "applications"

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        return CommandResult(0, "")

    context = DesktopContext(
        "deck-lcd",
        "wayland",
        parse_kscreen_outputs(KSCREEN),
        False,
        False,
        False,
        frozenset({"kde-config"}),
    )
    effect = KDEShortcutsEffect(
        runner=runner,
        which=lambda command: command,
        applications_dir=apps_dir,
    )
    effect.apply(profile_for(PROFILE_HANDHELD, context), context)

    assert (
        "kwriteconfig6",
        "--file",
        "kglobalshortcutsrc",
        "--group",
        "kwin",
        "--key",
        "ExposeAll",
        "Meta+Ctrl+D,Meta+Ctrl+D,Exposição de todas as áreas de trabalho",
    ) in calls
    assert (
        "kwriteconfig6",
        "--file",
        "kglobalshortcutsrc",
        "--group",
        "services",
        "--group",
        "steamzero-desktop-keyboard",
        "--key",
        "_launch",
        "Meta+Ctrl+K,Meta+Ctrl+K,Abrir teclado virtual SteamZero",
    ) in calls
    assert (apps_dir / "steamzero-desktop-keyboard.desktop").is_file()


def test_kde_shortcuts_effect_restores_missing_binding_with_delete(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []
    apps_dir = tmp_path / "applications"

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        return CommandResult(0, "")

    effect = KDEShortcutsEffect(
        runner=runner,
        which=lambda command: command,
        applications_dir=apps_dir,
    )
    snapshot = {
        "shortcuts": {
            "kwin": {"ExposeAll": "__steamzero_missing__"},
            "services": {"steamzero-desktop-keyboard": {"_launch": "__steamzero_missing__"}},
        },
        "desktopFileCreated": True,
    }
    desktop_file = apps_dir / "steamzero-desktop-keyboard.desktop"
    desktop_file.parent.mkdir(parents=True)
    desktop_file.write_text("dummy", encoding="utf-8")

    effect.restore(snapshot)

    assert (
        "kwriteconfig6",
        "--file",
        "kglobalshortcutsrc",
        "--group",
        "kwin",
        "--key",
        "ExposeAll",
        "--delete",
    ) in calls
    assert (
        "kwriteconfig6",
        "--file",
        "kglobalshortcutsrc",
        "--group",
        "services",
        "--group",
        "steamzero-desktop-keyboard",
        "--key",
        "_launch",
        "--delete",
    ) in calls
    assert not desktop_file.exists()


def test_kde_shortcuts_effect_unavailable_without_kde_config() -> None:
    effect = KDEShortcutsEffect(
        runner=lambda _argv, _timeout: CommandResult(0, ""),
        which=lambda command: command,
    )
    context = DesktopContext(
        "deck-lcd",
        "wayland",
        parse_kscreen_outputs(KSCREEN),
        False,
        False,
        False,
        frozenset(),
    )
    assert effect.available(context) is False
