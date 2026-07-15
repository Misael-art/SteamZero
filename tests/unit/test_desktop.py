# SPDX-License-Identifier: GPL-3.0-or-later
"""Regras puras do perfil Desktop portátil."""

from __future__ import annotations

from steamzero.domain.desktop import (
    PROFILE_DOCKED,
    PROFILE_HANDHELD,
    PROFILE_SAFE,
    DesktopContext,
    DisplayState,
    automatic_profile,
    profile_for,
)


def context(
    *,
    external_display: bool = False,
    dock: bool = False,
    keyboard: bool = False,
    capabilities: frozenset[str] = frozenset(),
) -> DesktopContext:
    displays = [DisplayState("eDP-1", True, True, 800, 1280, 60.0, 1.35)]
    if external_display:
        displays.append(DisplayState("DP-1", True, False, 2560, 1080, 75.0, 1.0))
    return DesktopContext(
        device_kind="deck-lcd",
        session_type="wayland",
        displays=tuple(displays),
        physical_dock=dock,
        external_keyboard=keyboard,
        external_mouse=False,
        capabilities=capabilities,
    )


def test_auto_handheld_ignores_keyboard_alone() -> None:
    assert automatic_profile(context(keyboard=True)) == PROFILE_HANDHELD


def test_auto_dock_uses_external_display_or_physical_dock() -> None:
    assert automatic_profile(context(external_display=True)) == PROFILE_DOCKED
    assert automatic_profile(context(dock=True)) == PROFILE_DOCKED


def test_keyboard_chain_is_capability_driven() -> None:
    profile = profile_for(
        PROFILE_HANDHELD,
        context(
            capabilities=frozenset(
                {
                    "plasma-keyboard",
                    "kwin-virtual-keyboard",
                    "steam-keyboard",
                    "kde-connect",
                }
            )
        ),
    )
    assert profile.keyboard_chain == (
        "plasma-keyboard",
        "kwin-maliit",
        "steam",
        "kde-connect",
    )


def test_inputplumber_requires_validation_marker() -> None:
    installed = profile_for(PROFILE_HANDHELD, context(capabilities=frozenset({"inputplumber"})))
    validated = profile_for(
        PROFILE_HANDHELD,
        context(capabilities=frozenset({"inputplumber", "inputplumber-validated"})),
    )
    assert installed.preferred_input_owner == "kde-shortcuts"
    assert validated.preferred_input_owner == "inputplumber"


def test_safe_profile_has_no_input_owner() -> None:
    profile = profile_for(PROFILE_SAFE, context())
    assert profile.preferred_input_owner == "none"
    assert profile.scale == 1.35
    assert not profile.maximize_windows
