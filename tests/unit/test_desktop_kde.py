# SPDX-License-Identifier: GPL-3.0-or-later
"""Parser e efeitos KDE sem tocar a sessão real."""

from __future__ import annotations

import signal
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from steamzero.adapters import desktop_kde
from steamzero.adapters.desktop_kde import (
    CommandResult,
    KDEDisplayEffect,
    KDEInputMethodEffect,
    KDEPanelEffect,
    LegacyWatcherConflictResolver,
    LinuxDesktopContext,
    VirtualKeyboardController,
    build_desktop_coordinator,
    parse_kscreen_outputs,
    run_command,
    spawn_command,
)
from steamzero.adapters.desktop_kde import (
    _keyboard_geometry as keyboard_geometry,
)
from steamzero.adapters.desktop_kde import (
    _locale_to_xkb_layout as locale_to_xkb_layout,
)
from steamzero.adapters.desktop_kde import (
    _maliit_language_for as maliit_language_for,
)
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain.desktop import PROFILE_HANDHELD, DesktopContext, DisplayState, profile_for

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
    # A sincronização de idioma (gsettings) acontece entre as chamadas qdbus6.
    qdbus_calls = [call[0] for call in calls if call[0] == "qdbus6"]
    assert qdbus_calls == ["qdbus6", "qdbus6", "qdbus6"]
    assert {call[0] for call in calls} <= {"qdbus6", "gsettings"}


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
    non_gsettings = [call[0] for call in calls if call[0] != "gsettings"]
    assert non_gsettings == ["qdbus6", "qdbus6", "qdbus6", "steam"]


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

    def spawner_env(argv: tuple[str, ...], env: dict[str, str]) -> bool:
        spawns.append(argv)
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
    monkeypatch.setattr("steamzero.adapters.desktop_kde.spawner_env", spawner_env)
    controller = VirtualKeyboardController(
        runner=runner, which=lambda command: command, delay=lambda _s: None
    )
    assert controller.activate(context, language="us") == "kwin-maliit"
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
    assert controller.activate(context, language="us") == "wvkbd"
    assert len(spawns) == 1
    spawn = spawns[0]
    assert spawn[0] == "wvkbd-mobintl"
    # Layouts latinos usam a layer padrão; ``-l`` com valor desconhecido
    # encerraria o wvkbd, e ``--hidden`` deixaria a ativação invisível.
    assert "--hidden" not in spawn
    assert "-l" not in spawn
    assert ("-L" in spawn) != ("-H" in spawn)


def test_wvkbd_uses_known_layer_for_cyrillic(monkeypatch: pytest.MonkeyPatch) -> None:
    spawns: list[tuple[str, ...]] = []

    def spawner(argv: Sequence[str]) -> bool:
        spawns.append(tuple(argv))
        return True

    controller = VirtualKeyboardController(
        runner=lambda _a, _t: CommandResult(127, ""),
        which=lambda command: command,
        spawner=spawner,
        delay=lambda _s: None,
    )
    assert controller._spawn_wvkbd("ru", {"width": 1280, "height": 400})
    assert spawns[0][:3] == ("wvkbd-mobintl", "-l", "cyrillic")


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


def test_keyboard_layout_maps_locale_to_language() -> None:
    assert locale_to_xkb_layout("pt_BR.UTF-8") == "br"
    assert locale_to_xkb_layout("en_US.UTF-8") == "us"
    assert locale_to_xkb_layout("es_ES.UTF-8") == "es"
    assert locale_to_xkb_layout("de_DE.UTF-8") == "de"
    assert locale_to_xkb_layout("fr_FR.UTF-8") == "fr"
    assert locale_to_xkb_layout("ja_JP.UTF-8") == "jp"
    assert locale_to_xkb_layout("ko_KR.UTF-8") == "kr"
    assert locale_to_xkb_layout("ru_RU.UTF-8") == "ru"
    assert locale_to_xkb_layout("zh_CN.UTF-8") == "cn"
    assert locale_to_xkb_layout("zh_TW.UTF-8") == "tw"
    assert locale_to_xkb_layout("ar_SA.UTF-8") == "ara"
    assert locale_to_xkb_layout("nl_NL.UTF-8") == "nl"
    assert locale_to_xkb_layout("pl_PL.UTF-8") == "pl"
    assert locale_to_xkb_layout("tr_TR.UTF-8") == "tr"
    assert locale_to_xkb_layout("C") == "us"


def test_input_method_status_publishes_real_pt_br_layout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(desktop_kde, "_host_locale", lambda: "pt_BR")
    monkeypatch.setattr(desktop_kde, "_maliit_desktop_file", lambda: None)
    monkeypatch.setattr(desktop_kde, "_kwin_vk_available", lambda _runner, _which: False)
    monkeypatch.setattr(desktop_kde.shutil, "which", lambda _command: None)

    status = desktop_kde.input_method_status()

    assert status["hostLocale"] == "pt_BR"
    assert status["keyboardLayout"] == "br"


def test_reduced_motion_reads_real_plasma_duration_factor() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        return CommandResult(0, "0\n", "")

    assert (
        desktop_kde.reduced_motion_enabled(
            runner=runner, which=lambda command: f"/usr/bin/{command}"
        )
        is True
    )
    assert calls == [
        (
            "kreadconfig6",
            "--file",
            "kdeglobals",
            "--group",
            "KDE",
            "--key",
            "AnimationDurationFactor",
        )
    ]


def test_high_contrast_reads_real_plasma_color_scheme() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        return CommandResult(0, "HighContrastDark\n", "")

    assert (
        desktop_kde.high_contrast_enabled(
            runner=runner, which=lambda command: f"/usr/bin/{command}"
        )
        is True
    )
    assert calls == [
        (
            "kreadconfig6",
            "--file",
            "kdeglobals",
            "--group",
            "General",
            "--key",
            "ColorScheme",
        )
    ]


def test_high_contrast_is_false_for_ordinary_scheme_and_degrades_without_plasma() -> None:
    """Esquema comum é falso; ausência de kreadconfig6 degrada sem executar nada."""

    def runner(_argv: Sequence[str], _timeout: float) -> CommandResult:
        return CommandResult(0, "BreezeDark\n", "")

    assert (
        desktop_kde.high_contrast_enabled(
            runner=runner, which=lambda command: f"/usr/bin/{command}"
        )
        is False
    )

    def exploding(_argv: Sequence[str], _timeout: float) -> CommandResult:
        raise AssertionError("não deve consultar o host sem kreadconfig6")

    assert desktop_kde.high_contrast_enabled(runner=exploding, which=lambda _c: None) is False


def test_high_contrast_ignores_separators_and_failed_read() -> None:
    """ "High-Contrast" e "high contrast" contam; returncode != 0 degrada para falso."""

    def spaced(_argv: Sequence[str], _timeout: float) -> CommandResult:
        return CommandResult(0, "High-Contrast Light\n", "")

    assert (
        desktop_kde.high_contrast_enabled(
            runner=spaced, which=lambda command: f"/usr/bin/{command}"
        )
        is True
    )

    def failing(_argv: Sequence[str], _timeout: float) -> CommandResult:
        return CommandResult(1, "", "erro")

    assert (
        desktop_kde.high_contrast_enabled(
            runner=failing, which=lambda command: f"/usr/bin/{command}"
        )
        is False
    )


def _minimal_context(
    capabilities: frozenset[str] = frozenset({"kde-plasma"}),
    displays: tuple[DisplayState, ...] = (),
) -> DesktopContext:
    return DesktopContext(
        device_kind="deck-lcd",
        session_type="wayland",
        displays=displays,
        physical_dock=False,
        external_keyboard=False,
        external_mouse=False,
        capabilities=capabilities,
        conflicts=(),
    )


def test_keyboard_geometry_computes_scale_from_internal_display() -> None:
    displays = (
        DisplayState(
            name="eDP-1",
            connected=True,
            internal=True,
            width=1280,
            height=800,
            scale=1.5,
            refresh_hz=60.0,
        ),
        DisplayState(
            name="HDMI-1",
            connected=True,
            internal=False,
            width=1920,
            height=1080,
            scale=1.0,
            refresh_hz=60.0,
        ),
    )
    geometry = keyboard_geometry(_minimal_context(displays=displays))
    assert geometry["scale"] == 150
    assert geometry["width"] == int(1280 * 1.5)
    assert geometry["height"] == int(800 * 1.5 * 0.35)


def test_keyboard_geometry_falls_back_to_defaults() -> None:
    geometry = keyboard_geometry(_minimal_context())
    assert geometry == {"width": 1280, "height": 400, "scale": 100}


def _panel_which(commands: set[str]) -> Callable[[str], str | None]:
    return lambda cmd: cmd if cmd in commands else None


def test_panel_effect_available_on_kde() -> None:
    effect = KDEPanelEffect(which=_panel_which({"qdbus6", "plasmashell"}))
    assert effect.available(_minimal_context())


def test_panel_effect_not_available_without_qdbus6() -> None:
    effect = KDEPanelEffect(which=lambda _cmd: None)
    assert not effect.available(_minimal_context())


def _eval_script_for_states(script: str, states: dict[str, str]) -> str | None:
    if "hiding" in script.lower():
        # Leitura imprime JSON; escrita apenas atribui e não imprime nada.
        if "JSON.stringify" in script:
            import json

            return json.dumps(states)
        return ""
    return None


def test_panel_effect_capture_reads_hiding_states() -> None:
    states = {"panel1": "autohide", "panel2": "windowsgocanhide"}

    effect = KDEPanelEffect(which=_panel_which({"qdbus6", "plasmashell"}))
    effect._evaluate_script = lambda script: _eval_script_for_states(script, states)  # type: ignore[method-assign]
    captured = effect.capture(_minimal_context())
    assert captured == {"panelHidingStates": states}


def test_panel_effect_apply_sets_expected_hiding_state() -> None:
    evaluated: list[str] = []

    def eval_script(script: str) -> str | None:
        if "hiding" in script.lower() and "JSON.stringify" not in script:
            evaluated.append(script.split("'")[1])
            return ""
        return None

    effect = KDEPanelEffect(which=_panel_which({"qdbus6", "plasmashell"}))
    effect._evaluate_script = eval_script  # type: ignore[method-assign]
    profile = profile_for(PROFILE_HANDHELD, _minimal_context())
    effect.apply(profile, _minimal_context())
    assert evaluated == ["autohide"]


def test_panel_effect_verify_checks_hiding_state() -> None:
    states = {"panel1": "autohide", "panel2": "autohide"}

    effect = KDEPanelEffect(which=_panel_which({"qdbus6", "plasmashell"}))
    effect._evaluate_script = lambda script: _eval_script_for_states(script, states)  # type: ignore[method-assign]
    profile = profile_for(PROFILE_HANDHELD, _minimal_context())
    assert effect.verify(profile, _minimal_context())

    states["panel2"] = "windowsgocanhide"
    assert not effect.verify(profile, _minimal_context())


def test_build_desktop_coordinator_includes_kde_panel_effect(
    tmp_path: Path,
) -> None:
    coordinator = build_desktop_coordinator(StateStore(tmp_path / "state.db"))
    assert any(isinstance(effect, KDEPanelEffect) for effect in coordinator._effects)


def _is_qdbus_property(argv: Sequence[str], name: str) -> bool:
    return argv[0] == "qdbus6" and "org.freedesktop.DBus.Properties.Get" in argv and name in argv


def test_toggle_virtual_keyboard_launches_deactivate_when_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Sequence[str]] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(argv)
        if _is_qdbus_property(argv, "available"):
            return CommandResult(0, "true")
        if _is_qdbus_property(argv, "visible"):
            return CommandResult(0, "true")
        return CommandResult(0, "")

    monkeypatch.setattr("steamzero.adapters.desktop_kde._process_running", lambda _name: False)
    context = _minimal_context(frozenset({"kwin-virtual-keyboard"}))
    controller = VirtualKeyboardController(
        runner=runner,
        which=lambda command: command if command == "qdbus6" else None,
        spawner=lambda _argv: False,
        delay=lambda _s: None,
    )
    result = controller.toggle(context)
    assert result["action"] == "hide"
    assert result["provider"] == "kwin-maliit"
    assert any(
        argv[0] == "qdbus6" and "org.kde.kwin.VirtualKeyboard.forceDeactivate" in argv
        for argv in calls
    )


def test_toggle_virtual_keyboard_launches_activate_when_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Sequence[str]] = []
    visible_after_activate = {"value": False}

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(argv)
        if _is_qdbus_property(argv, "available"):
            return CommandResult(0, "true")
        if _is_qdbus_property(argv, "visible"):
            return CommandResult(0, "true" if visible_after_activate["value"] else "false")
        if argv[0] == "qdbus6" and "org.kde.kwin.VirtualKeyboard.forceActivate" in argv:
            visible_after_activate["value"] = True
            return CommandResult(0, "")
        return CommandResult(0, "")

    monkeypatch.setattr("steamzero.adapters.desktop_kde._process_running", lambda _name: False)
    context = _minimal_context(frozenset({"kwin-virtual-keyboard"}))
    controller = VirtualKeyboardController(
        runner=runner,
        which=lambda command: command if command == "qdbus6" else None,
        spawner=lambda _argv: False,
        delay=lambda _s: None,
    )
    result = controller.toggle(context)
    assert result["action"] == "show"
    assert result["provider"] == "kwin-maliit"
    assert any(
        argv[0] == "qdbus6" and "org.kde.kwin.VirtualKeyboard.forceActivate" in argv
        for argv in calls
    )


def test_toggle_virtual_keyboard_hides_wvkbd_with_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signals: list[tuple[str, int]] = []

    def signal_process(name: str, sig: int) -> None:
        signals.append((name, sig))

    monkeypatch.setattr(
        "steamzero.adapters.desktop_kde._process_running",
        lambda name: name == "wvkbd-mobintl",
    )
    monkeypatch.setattr("steamzero.adapters.desktop_kde._signal_process", signal_process)

    context = _minimal_context(frozenset({"wvkbd"}))
    controller = VirtualKeyboardController(
        runner=lambda _a, _t: CommandResult(127, ""),
        which=lambda command: command,
        spawner=lambda _argv: False,
        delay=lambda _s: None,
    )
    result = controller.toggle(context)
    assert result == {"action": "hide", "provider": "wvkbd"}
    assert ("wvkbd-mobintl", signal.SIGUSR1) in signals


def test_activate_reuses_wvkbd_and_shows_with_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signals: list[tuple[str, int]] = []
    spawns: list[tuple[str, ...]] = []

    def signal_process(name: str, sig: int) -> None:
        signals.append((name, sig))

    monkeypatch.setattr(
        "steamzero.adapters.desktop_kde._process_running",
        lambda name: name == "wvkbd-mobintl",
    )
    monkeypatch.setattr("steamzero.adapters.desktop_kde._signal_process", signal_process)

    context = _minimal_context(frozenset({"wvkbd"}))
    controller = VirtualKeyboardController(
        runner=lambda _a, _t: CommandResult(127, ""),
        which=lambda command: command,
        spawner=lambda argv: spawns.append(tuple(argv)) or True,
        delay=lambda _s: None,
    )
    result = controller.activate(context, language="us")
    assert result == "wvkbd"
    assert ("wvkbd-mobintl", signal.SIGUSR2) in signals
    assert not spawns


def test_maliit_language_mapping_uses_iso_codes() -> None:
    assert maliit_language_for("br") == "pt"
    assert maliit_language_for("us") == "en"
    assert maliit_language_for("gb") == "en"
    assert maliit_language_for("cn") == "zh-hans"
    assert maliit_language_for("tw") == "zh-hant"
    assert maliit_language_for("jp") == "ja"
    assert maliit_language_for("ara") == "ar"
    assert maliit_language_for("de") == "de"
    assert maliit_language_for(None) is None


def test_activate_kwin_maliit_syncs_language_via_gsettings() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        if _is_qdbus_property(argv, "available"):
            return CommandResult(0, "true")
        if _is_qdbus_property(argv, "visible"):
            return CommandResult(0, "true")
        if argv[0] == "gsettings" and argv[1] == "get" and argv[-1] == "active-language":
            return CommandResult(0, "'en'")
        if argv[0] == "gsettings" and argv[1] == "get" and argv[-1] == "enabled-languages":
            return CommandResult(0, "['en']")
        return CommandResult(0, "")

    context = _minimal_context(frozenset({"kwin-virtual-keyboard"}))
    controller = VirtualKeyboardController(
        runner=runner,
        which=lambda command: command,
        spawner=lambda _argv: False,
        delay=lambda _s: None,
    )
    assert controller.activate(context, language="br") == "kwin-maliit"
    schema = "org.maliit.keyboard.maliit"
    assert ("gsettings", "set", schema, "enabled-languages", "['en', 'pt']") in calls
    assert ("gsettings", "set", schema, "active-language", "pt") in calls


def test_maliit_language_sync_skips_when_already_active() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        if _is_qdbus_property(argv, "available"):
            return CommandResult(0, "true")
        if _is_qdbus_property(argv, "visible"):
            return CommandResult(0, "true")
        if argv[0] == "gsettings" and argv[1] == "get" and argv[-1] == "active-language":
            return CommandResult(0, "'pt'")
        return CommandResult(0, "")

    context = _minimal_context(frozenset({"kwin-virtual-keyboard"}))
    controller = VirtualKeyboardController(
        runner=runner,
        which=lambda command: command,
        spawner=lambda _argv: False,
        delay=lambda _s: None,
    )
    assert controller.activate(context, language="br") == "kwin-maliit"
    assert not any(argv[:2] == ("gsettings", "set") for argv in calls)


def test_panel_effect_read_script_does_not_mutate_state() -> None:
    assert ".hiding = '" not in KDEPanelEffect._READ_SCRIPT
    assert "JSON.stringify" in KDEPanelEffect._READ_SCRIPT


def test_host_locale_prefers_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LC_ALL", "pt_BR.UTF-8")
    assert desktop_kde._host_locale() == "pt_BR"
    monkeypatch.delenv("LC_ALL")
    monkeypatch.setenv("LANG", "de_DE.UTF-8")
    assert desktop_kde._host_locale() == "de_DE"


def test_signal_process_targets_only_current_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import os

    uid = os.getuid()
    mine = tmp_path / "321"
    mine.mkdir()
    (mine / "comm").write_text("wvkbd-mobintl\n", encoding="utf-8")
    (mine / "status").write_text(
        f"Name:\twvkbd\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n", encoding="utf-8"
    )
    other = tmp_path / "322"
    other.mkdir()
    (other / "comm").write_text("wvkbd-mobintl\n", encoding="utf-8")
    (other / "status").write_text("Name:\twvkbd\nUid:\t0\t0\t0\t0\n", encoding="utf-8")

    killed: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "steamzero.adapters.desktop_kde.os.kill",
        lambda pid, sig: killed.append((pid, sig)),
    )
    desktop_kde._signal_process("wvkbd-mobintl", signal.SIGUSR2, proc=tmp_path)
    assert killed == [(321, signal.SIGUSR2)]


def test_toggle_stops_onboard_when_running(monkeypatch: pytest.MonkeyPatch) -> None:
    signals: list[tuple[str, int]] = []
    monkeypatch.setattr(
        "steamzero.adapters.desktop_kde._process_running", lambda name: name == "onboard"
    )
    monkeypatch.setattr(
        "steamzero.adapters.desktop_kde._signal_process",
        lambda name, sig: signals.append((name, sig)),
    )
    controller = VirtualKeyboardController(
        runner=lambda _a, _t: CommandResult(127, ""),
        which=lambda command: command,
        spawner=lambda _argv: False,
        delay=lambda _s: None,
    )
    result = controller.toggle(_minimal_context(frozenset({"onboard"})))
    assert result == {"action": "hide", "provider": "onboard"}
    assert ("onboard", signal.SIGTERM) in signals


def test_spawner_env_passes_custom_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def popen(argv: list[str], **kwargs: object) -> object:
        captured["argv"] = argv
        captured.update(kwargs)
        return object()

    monkeypatch.setattr("steamzero.adapters.desktop_kde.shutil.which", lambda _n: "/tool")
    monkeypatch.setattr("steamzero.adapters.desktop_kde.subprocess.Popen", popen)
    assert desktop_kde.spawner_env(("provider",), {"A": "1"}) is True
    assert captured["env"] == {"A": "1"}
    assert captured["start_new_session"] is True
    assert desktop_kde.spawner_env((), {}) is False


def test_launch_ashyterm_uses_wayland_input_env() -> None:
    captured: dict[str, object] = {}

    def spawn(argv: Sequence[str], env: dict[str, str]) -> bool:
        captured["argv"] = tuple(argv)
        captured["env"] = env
        return True

    result = desktop_kde.launch_ashyterm(
        which=lambda cmd: "/usr/sbin/ashyterm" if cmd == "ashyterm" else None, spawn=spawn
    )
    assert result["status"] == "started"
    assert captured["argv"] == ("/usr/sbin/ashyterm",)
    env = captured["env"]
    assert isinstance(env, dict)
    assert "GTK_IM_MODULE" in env
    assert "GDK_BACKEND" in env


def test_launch_ashyterm_error_when_spawn_fails() -> None:
    with pytest.raises(SteamZeroError):
        desktop_kde.launch_ashyterm(which=lambda _cmd: "/x", spawn=lambda _a, _e: False)


def test_launch_ashyterm_falls_back_to_desktop_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "is_file", lambda _self: True)
    captured: dict[str, object] = {}

    def spawn(argv: Sequence[str], env: dict[str, str]) -> bool:
        captured["argv"] = tuple(argv)
        return True

    result = desktop_kde.launch_ashyterm(which=lambda _cmd: None, spawn=spawn)
    argv = captured["argv"]
    assert isinstance(argv, tuple)
    assert argv[0] == "xdg-open"
    assert result["command"] == "xdg-open"


def test_panel_effect_restore_reapplies_snapshot() -> None:
    evaluated: list[str] = []
    effect = KDEPanelEffect(which=_panel_which({"qdbus6", "plasmashell"}))
    effect._evaluate_script = lambda script: (evaluated.append(script), "")[1]  # type: ignore[method-assign]
    effect.restore({"panelHidingStates": {"3": "none", "4": "autohide"}})
    assert any("panelById(3)" in script and "'none'" in script for script in evaluated)
    assert any("panelById(4)" in script and "'autohide'" in script for script in evaluated)


def test_panel_effect_restore_rejects_invalid_snapshot() -> None:
    effect = KDEPanelEffect()
    with pytest.raises(RuntimeError):
        effect.restore({"panelHidingStates": "autohide"})


def test_panel_effect_evaluate_script_degrades_without_qdbus() -> None:
    effect = KDEPanelEffect(which=lambda _c: None)
    assert effect._evaluate_script("print('x')") is None
    failing = KDEPanelEffect(runner=lambda _a, _t: CommandResult(1, "boom"), which=lambda c: c)
    assert failing._evaluate_script("print('x')") is None
    ok = KDEPanelEffect(runner=lambda _a, _t: CommandResult(0, " out \n"), which=lambda c: c)
    assert ok._evaluate_script("print('x')") == "out"


def _comfort_runner(
    store: dict[str, str], calls: list[tuple[str, ...]]
) -> Callable[..., CommandResult]:
    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        if argv[0] == "gsettings" and argv[1] == "get":
            return CommandResult(0, store.get(argv[3], ""))
        if argv[0] == "gsettings" and argv[1] == "set":
            store[argv[3]] = argv[4]
            return CommandResult(0, "")
        return CommandResult(127, "")

    return runner


def test_maliit_comfort_applies_only_changed_keys() -> None:
    store = {
        "key-press-feedback": "false",
        "key-press-haptic-feedback": "true",
        "theme": "'Ambiance'",
    }
    calls: list[tuple[str, ...]] = []
    result = desktop_kde.apply_maliit_comfort(
        {"sound": True, "haptic": True, "theme": "SuruDark"},
        runner=_comfort_runner(store, calls),
        which=lambda command: command,
    )
    assert result["applied"] == {"sound": "true", "theme": "SuruDark"}
    assert result["previous"]["sound"] == "false"
    assert result["previous"]["theme"] == "Ambiance"
    # háptica já estava correta: nenhum set para a chave dela
    assert not any(argv[1] == "set" and argv[3] == "key-press-haptic-feedback" for argv in calls)
    assert store["key-press-feedback"] == "true"
    assert store["theme"] == "SuruDark"


def test_maliit_comfort_rejects_unknown_setting() -> None:
    with pytest.raises(ValueError, match="desconhecida"):
        desktop_kde.apply_maliit_comfort(
            {"volume": True},  # type: ignore[dict-item]
            runner=lambda _a, _t: CommandResult(0, ""),
            which=lambda command: command,
        )


def test_maliit_comfort_degrades_without_gsettings() -> None:
    with pytest.raises(SteamZeroError):
        desktop_kde.apply_maliit_comfort(
            {"sound": True},
            runner=lambda _a, _t: CommandResult(0, ""),
            which=lambda _command: None,
        )


def test_maliit_comfort_reverts_when_readback_diverges() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        if argv[0] == "gsettings" and argv[1] == "get":
            # Sempre devolve o valor antigo: o set "não pegou".
            return CommandResult(0, "'Ambiance'")
        return CommandResult(0, "")

    with pytest.raises(SteamZeroError):
        desktop_kde.apply_maliit_comfort(
            {"theme": "Inexistente"}, runner=runner, which=lambda command: command
        )
    # Reverteu para o valor anterior após o readback divergente.
    assert ("gsettings", "set", "org.maliit.keyboard.maliit", "theme", "Ambiance") in calls


def _shortcut_runner(
    store: dict[str, str], calls: list[tuple[str, ...]]
) -> Callable[..., CommandResult]:
    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        if argv[0] == "kreadconfig6":
            return CommandResult(0, store.get("_launch", ""))
        if argv[0] == "kwriteconfig6":
            if argv[-1] == "--delete":
                store.pop("_launch", None)
            else:
                store["_launch"] = argv[-1]
            return CommandResult(0, "")
        return CommandResult(127, "")

    return runner


def _shortcut_effect(
    tmp_path: Path, store: dict[str, str], calls: list[tuple[str, ...]]
) -> desktop_kde.KDEShortcutEffect:
    return desktop_kde.KDEShortcutEffect(
        runner=_shortcut_runner(store, calls),
        which=lambda command: command if command in {"kreadconfig6", "kwriteconfig6"} else None,
        applications_dir=tmp_path,
    )


def test_shortcut_effect_available_requires_kde_config(tmp_path: Path) -> None:
    effect = _shortcut_effect(tmp_path, {}, [])
    assert effect.available(_minimal_context(frozenset({"kde-config"})))
    assert not effect.available(_minimal_context(frozenset()))


def test_shortcut_effect_apply_writes_marked_artifact_and_binding(tmp_path: Path) -> None:
    store: dict[str, str] = {}
    calls: list[tuple[str, ...]] = []
    effect = _shortcut_effect(tmp_path, store, calls)
    context = _minimal_context(frozenset({"kde-config"}))
    profile = profile_for(PROFILE_HANDHELD, context)

    captured = effect.capture(context)
    assert captured == {"shortcutEntry": None, "desktopFilePresent": False}

    effect.apply(profile, context)
    desktop_file = tmp_path / "steamzero-keyboard-toggle.desktop"
    content = desktop_file.read_text(encoding="utf-8")
    assert "X-SteamZero-Managed=true" in content
    assert "Exec=steamzero desktop keyboard --toggle" in content
    assert "X-KDE-GlobalAccel-CommandShortcut=true" in content
    assert store["_launch"].startswith("Meta+K,")
    assert effect.verify(profile, context)


def test_shortcut_effect_restore_removes_artifact_and_binding(tmp_path: Path) -> None:
    store: dict[str, str] = {}
    effect = _shortcut_effect(tmp_path, store, [])
    context = _minimal_context(frozenset({"kde-config"}))
    snapshot = effect.capture(context)
    effect.apply(profile_for(PROFILE_HANDHELD, context), context)

    effect.restore(snapshot)
    assert not (tmp_path / "steamzero-keyboard-toggle.desktop").exists()
    assert "_launch" not in store


def test_shortcut_effect_restore_preserves_previous_binding(tmp_path: Path) -> None:
    store: dict[str, str] = {"_launch": "Meta+F1,Meta+F1,Antigo"}
    effect = _shortcut_effect(tmp_path, store, [])
    (tmp_path / "steamzero-keyboard-toggle.desktop").write_text(
        "[Desktop Entry]\nX-SteamZero-Managed=true\n", encoding="utf-8"
    )
    context = _minimal_context(frozenset({"kde-config"}))
    snapshot = effect.capture(context)
    effect.apply(profile_for(PROFILE_HANDHELD, context), context)
    assert store["_launch"].startswith("Meta+K,")

    effect.restore(snapshot)
    assert store["_launch"] == "Meta+F1,Meta+F1,Antigo"
    assert (tmp_path / "steamzero-keyboard-toggle.desktop").exists()


def test_shortcut_effect_refuses_unmarked_artifact(tmp_path: Path) -> None:
    target = tmp_path / "steamzero-keyboard-toggle.desktop"
    target.write_text("[Desktop Entry]\nExec=outro\n", encoding="utf-8")
    effect = _shortcut_effect(tmp_path, {}, [])
    context = _minimal_context(frozenset({"kde-config"}))
    with pytest.raises(RuntimeError, match="sem marcador"):
        effect.apply(profile_for(PROFILE_HANDHELD, context), context)
    with pytest.raises(RuntimeError, match="sem marcador"):
        effect._remove_desktop_file()
    assert target.read_text(encoding="utf-8") == "[Desktop Entry]\nExec=outro\n"


def test_build_desktop_coordinator_includes_shortcut_effect(tmp_path: Path) -> None:
    coordinator = build_desktop_coordinator(StateStore(tmp_path / "state.db"))
    assert any(isinstance(effect, desktop_kde.KDEShortcutEffect) for effect in coordinator._effects)


def _edge_runner(
    store: dict[str, str], calls: list[tuple[str, ...]]
) -> Callable[..., CommandResult]:
    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        if argv[0] == "kreadconfig6":
            return CommandResult(0, store.get("enabled", ""))
        if argv[0] == "kwriteconfig6":
            if argv[-1] == "--delete":
                store.pop("enabled", None)
            else:
                store["enabled"] = argv[-1]
            return CommandResult(0, "")
        if argv[0] == "qdbus6":
            return CommandResult(0, "")
        return CommandResult(127, "")

    return runner


def _edge_effect(
    tmp_path: Path, store: dict[str, str], calls: list[tuple[str, ...]]
) -> desktop_kde.KDEEdgeGestureEffect:
    return desktop_kde.KDEEdgeGestureEffect(
        runner=_edge_runner(store, calls),
        which=lambda command: command,
        scripts_dir=tmp_path,
    )


def test_edge_gesture_apply_installs_script_and_enables_plugin(tmp_path: Path) -> None:
    store: dict[str, str] = {}
    calls: list[tuple[str, ...]] = []
    effect = _edge_effect(tmp_path, store, calls)
    context = _minimal_context(frozenset({"kde-config"}))
    profile = profile_for(PROFILE_HANDHELD, context)

    snapshot = effect.capture(context)
    assert snapshot == {"pluginEnabled": None, "scriptPresent": False}

    effect.apply(profile, context)
    metadata = tmp_path / "steamzero-edge-keyboard" / "metadata.json"
    main_js = tmp_path / "steamzero-edge-keyboard" / "contents" / "code" / "main.js"
    assert "X-SteamZero-Managed" in metadata.read_text(encoding="utf-8")
    assert "registerTouchScreenEdge" in main_js.read_text(encoding="utf-8")
    assert store["enabled"] == "true"
    assert effect.verify(profile, context)
    assert any(argv[0] == "qdbus6" and "org.kde.KWin.reconfigure" in argv for argv in calls)


def test_edge_gesture_restore_removes_script_and_key(tmp_path: Path) -> None:
    store: dict[str, str] = {}
    effect = _edge_effect(tmp_path, store, [])
    context = _minimal_context(frozenset({"kde-config"}))
    snapshot = effect.capture(context)
    effect.apply(profile_for(PROFILE_HANDHELD, context), context)

    effect.restore(snapshot)
    assert not (tmp_path / "steamzero-edge-keyboard").exists()
    assert "enabled" not in store


def test_edge_gesture_refuses_unmarked_script(tmp_path: Path) -> None:
    root = tmp_path / "steamzero-edge-keyboard"
    root.mkdir(parents=True)
    (root / "metadata.json").write_text("{}", encoding="utf-8")
    effect = _edge_effect(tmp_path, {}, [])
    context = _minimal_context(frozenset({"kde-config"}))
    with pytest.raises(RuntimeError, match="sem marcador"):
        effect.apply(profile_for(PROFILE_HANDHELD, context), context)
    with pytest.raises(RuntimeError, match="sem marcador"):
        effect._remove_script()
    assert (root / "metadata.json").read_text(encoding="utf-8") == "{}"


def test_build_desktop_coordinator_includes_edge_gesture_effect(tmp_path: Path) -> None:
    coordinator = build_desktop_coordinator(StateStore(tmp_path / "state.db"))
    assert any(
        isinstance(effect, desktop_kde.KDEEdgeGestureEffect) for effect in coordinator._effects
    )
