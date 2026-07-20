# SPDX-License-Identifier: GPL-3.0-or-later
"""Parser e efeitos KDE sem tocar a sessão real."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from steamzero.adapters import desktop_kde
from steamzero.adapters.desktop_kde import (
    CommandResult,
    KDEDisplayEffect,
    KDEInputMethodEffect,
    LegacyWatcherConflictResolver,
    LinuxDesktopContext,
    VirtualKeyboardController,
    parse_kscreen_outputs,
    run_command,
    spawn_command,
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


def test_spawn_command_detaches_persistent_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def popen(argv: list[str], **kwargs: object) -> object:
        captured["argv"] = argv
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("steamzero.adapters.desktop_kde.shutil.which", lambda _name: "/tool")
    monkeypatch.setattr("steamzero.adapters.desktop_kde.subprocess.Popen", popen)

    assert spawn_command(("provider", "--foreground")) is True
    assert captured["argv"] == ["/tool", "--foreground"]
    assert captured["start_new_session"] is True
    assert captured["close_fds"] is True


def test_process_detection_is_scoped_to_current_user(tmp_path: Path) -> None:
    other = tmp_path / "101"
    other.mkdir()
    (other / "comm").write_text("steam\n", encoding="utf-8")
    (other / "status").write_text("Name:\tsteam\nUid:\t1001\t1001\t1001\t1001\n", encoding="utf-8")

    assert desktop_kde._process_running("steam", proc=tmp_path, uid=1000) is False

    owned = tmp_path / "102"
    owned.mkdir()
    (owned / "comm").write_text("steam\n", encoding="utf-8")
    (owned / "status").write_text("Name:\tsteam\nUid:\t1000\t1000\t1000\t1000\n", encoding="utf-8")

    assert desktop_kde._process_running("steam", proc=tmp_path, uid=1000) is True


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


def test_input_method_effect_requires_maliit_desktop_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("steamzero.adapters.desktop_kde._maliit_desktop_file", lambda: None)

    def which(command: str) -> str | None:
        return command if command in {"kreadconfig6", "kwriteconfig6", "qdbus6"} else None

    context = DesktopContext(
        "deck-lcd",
        "wayland",
        parse_kscreen_outputs(KSCREEN),
        False,
        False,
        False,
        frozenset({"kde-config"}),
    )
    effect = KDEInputMethodEffect(runner=lambda _a, _t: CommandResult(127, ""), which=which)
    assert effect.available(context) is False


def test_input_method_effect_configures_maliit_when_keyboard_not_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "steamzero.adapters.desktop_kde._maliit_desktop_file",
        lambda: Path("/usr/share/applications/com.github.maliit.keyboard.desktop"),
    )
    calls: list[tuple[str, ...]] = []
    configured = {"value": ""}

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        if argv[0] == "qdbus6" and "Properties.Get" in argv and "available" in argv:
            return CommandResult(0, "false")
        if argv[0] == "kreadconfig6":
            return CommandResult(0, configured["value"])
        if argv[0] == "kwriteconfig6":
            configured["value"] = str(argv[-1])
            return CommandResult(0, "")
        return CommandResult(0, "")

    def which(command: str) -> str | None:
        return command if command in {"kreadconfig6", "kwriteconfig6", "qdbus6"} else None

    context = DesktopContext(
        "deck-lcd",
        "wayland",
        parse_kscreen_outputs(KSCREEN),
        False,
        False,
        False,
        frozenset({"kde-config"}),
    )
    effect = KDEInputMethodEffect(runner=runner, which=which)
    assert effect.available(context) is True

    effect.capture(context)
    effect.apply(profile_for(PROFILE_HANDHELD, context), context)

    assert any(call[0] == "kwriteconfig6" for call in calls)
    assert effect.verify(profile_for(PROFILE_HANDHELD, context), context) is True
    assert configured["value"].endswith("com.github.maliit.keyboard.desktop")


def test_input_method_effect_restores_previous_value() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        return CommandResult(0, "")

    def which(command: str) -> str | None:
        return command if command in {"kreadconfig6", "kwriteconfig6", "qdbus6"} else None

    effect = KDEInputMethodEffect(runner=runner, which=which)
    effect.restore({"inputMethod": "/usr/share/old.desktop"})

    write = next((call for call in calls if call[0] == "kwriteconfig6"), None)
    assert write is not None
    assert "/usr/share/old.desktop" in write


def test_virtual_keyboard_uses_kwin_when_it_becomes_visible() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        if argv[0] == "qdbus6":
            # available -> visible -> forceActivate
            if "org.freedesktop.DBus.Properties.Get" in argv and "available" in argv:
                return CommandResult(0, "true")
            if "org.freedesktop.DBus.Properties.Get" in argv and "visible" in argv:
                return CommandResult(0, "true")
            return CommandResult(0, "")
        return CommandResult(127, "")

    context = DesktopContext(
        "deck-lcd",
        "wayland",
        parse_kscreen_outputs(KSCREEN),
        False,
        False,
        False,
        frozenset({"kwin-virtual-keyboard"}),
    )
    controller = VirtualKeyboardController(runner=runner, which=lambda command: command)
    assert controller.activate(context) == "kwin-maliit"
    assert [call[0] for call in calls] == ["qdbus6", "qdbus6", "qdbus6"]


def test_virtual_keyboard_falls_back_to_steam_when_kwin_does_not_show(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        if argv[0] == "qdbus6":
            if "org.freedesktop.DBus.Properties.Get" in argv and "available" in argv:
                return CommandResult(0, "true")
            if "org.freedesktop.DBus.Properties.Get" in argv and "visible" in argv:
                return CommandResult(0, "false")
            return CommandResult(0, "")
        if argv[0] == "steam":
            return CommandResult(0, "")
        return CommandResult(127, "")

    context = DesktopContext(
        "deck-lcd",
        "wayland",
        parse_kscreen_outputs(KSCREEN),
        False,
        False,
        False,
        frozenset({"kwin-virtual-keyboard", "steam-keyboard"}),
    )
    monkeypatch.setattr(
        "steamzero.adapters.desktop_kde._process_running", lambda name: name == "steam"
    )
    controller = VirtualKeyboardController(runner=runner, which=lambda command: command)
    assert controller.activate(context) == "steam"
    assert [call[0] for call in calls] == ["qdbus6", "qdbus6", "qdbus6", "steam"]


def test_virtual_keyboard_starts_steam_when_not_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    spawns: list[tuple[str, ...]] = []
    running = {"steam": False}

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        if argv[0] == "qdbus6":
            return CommandResult(0, "false")
        if argv[0] == "steam":
            return CommandResult(0, "")
        return CommandResult(127, "")

    def spawner(argv: Sequence[str]) -> bool:
        spawns.append(tuple(argv))
        if argv[0] == "steam":
            running["steam"] = True
        return True

    context = DesktopContext(
        "deck-lcd",
        "wayland",
        parse_kscreen_outputs(KSCREEN),
        False,
        False,
        False,
        frozenset({"kwin-virtual-keyboard", "steam-keyboard"}),
    )

    def process_running(name: str) -> bool:
        if name == "steam":
            return running["steam"]
        return False

    monkeypatch.setattr("steamzero.adapters.desktop_kde._process_running", process_running)
    controller = VirtualKeyboardController(
        runner=runner,
        which=lambda command: None if command == "maliit-server" else command,
        spawner=spawner,
        delay=lambda _s: None,
    )
    assert controller.activate(context) == "steam"
    assert spawns == [("steam", "-silent")]
    assert ("steam", "-ifrunning", "steam://open/keyboard") in calls


def test_virtual_keyboard_tries_to_start_maliit_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    spawns: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        if argv[0] == "qdbus6":
            if "org.freedesktop.DBus.Properties.Get" in argv and "available" in argv:
                return CommandResult(0, "true" if spawns else "false")
            if "org.freedesktop.DBus.Properties.Get" in argv and "visible" in argv:
                return CommandResult(0, "true")
            return CommandResult(0, "")
        return CommandResult(127, "")

    def spawner(argv: Sequence[str]) -> bool:
        spawns.append(tuple(argv))
        return True

    context = DesktopContext(
        "deck-lcd",
        "wayland",
        parse_kscreen_outputs(KSCREEN),
        False,
        False,
        False,
        frozenset({"kwin-virtual-keyboard"}),
    )
    monkeypatch.setattr("steamzero.adapters.desktop_kde._process_running", lambda _name: False)
    controller = VirtualKeyboardController(
        runner=runner, which=lambda command: command, spawner=spawner, delay=lambda _s: None
    )
    assert controller.activate(context) == "kwin-maliit"
    assert spawns == [("maliit-server",)]


def test_virtual_keyboard_falls_back_to_wvkbd(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []
    spawns: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        if argv[0] == "qdbus6":
            return CommandResult(0, "false")
        return CommandResult(127, "")

    def spawner(argv: Sequence[str]) -> bool:
        spawns.append(tuple(argv))
        return True

    context = DesktopContext(
        "deck-lcd",
        "wayland",
        parse_kscreen_outputs(KSCREEN),
        False,
        False,
        False,
        frozenset({"kwin-virtual-keyboard", "wvkbd"}),
    )
    monkeypatch.setattr(
        "steamzero.adapters.desktop_kde._process_running",
        lambda name: name == "wvkbd-mobintl" and bool(spawns),
    )
    controller = VirtualKeyboardController(
        runner=runner, which=lambda command: command, spawner=spawner, delay=lambda _s: None
    )
    assert controller.activate(context) == "wvkbd"
    assert spawns == [("maliit-server",), ("wvkbd-mobintl",)]


def test_virtual_keyboard_skips_maliit_server_when_already_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        if argv[0] == "qdbus6":
            if "org.freedesktop.DBus.Properties.Get" in argv and "available" in argv:
                return CommandResult(0, "false")
            return CommandResult(0, "")
        if argv[0] == "steam":
            return CommandResult(0, "")
        return CommandResult(127, "")

    context = DesktopContext(
        "deck-lcd",
        "wayland",
        parse_kscreen_outputs(KSCREEN),
        False,
        False,
        False,
        frozenset({"kwin-virtual-keyboard", "steam-keyboard"}),
    )
    controller = VirtualKeyboardController(
        runner=runner, which=lambda command: command, spawner=lambda _argv: False
    )
    # Simula maliit-server já rodando: não deve tentar iniciá-lo.
    monkeypatch.setattr("steamzero.adapters.desktop_kde._process_running", lambda _name: True)
    assert controller.activate(context) == "steam"
    assert ("maliit-server",) not in calls


def test_virtual_keyboard_reports_failure_when_no_provider_works() -> None:
    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        if argv[0] == "qdbus6":
            if "org.freedesktop.DBus.Properties.Get" in argv and "available" in argv:
                return CommandResult(0, "false")
            return CommandResult(0, "")
        return CommandResult(127, "")

    context = DesktopContext(
        "deck-lcd",
        "wayland",
        parse_kscreen_outputs(KSCREEN),
        False,
        False,
        False,
        frozenset({"kwin-virtual-keyboard"}),
    )
    controller = VirtualKeyboardController(
        runner=runner, which=lambda command: command, spawner=lambda _argv: False
    )
    with pytest.raises(SteamZeroError, match="nenhum provider de teclado ficou visível"):
        controller.activate(context)


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
