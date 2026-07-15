# SPDX-License-Identifier: GPL-3.0-or-later
"""Parser e efeitos KDE sem tocar a sessão real."""

from __future__ import annotations

from collections.abc import Sequence

from steamzero.adapters.desktop_kde import (
    CommandResult,
    KDEDisplayEffect,
    LinuxDesktopContext,
    VirtualKeyboardController,
    parse_kscreen_outputs,
)
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


def test_parse_kscreen_outputs() -> None:
    outputs = parse_kscreen_outputs(KSCREEN)
    assert [(output.name, output.internal, output.scale) for output in outputs] == [
        ("eDP-1", True, 1.35),
        ("DP-1", False, 1.0),
    ]
    assert outputs[1].refresh_hz == 75.0


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
