# SPDX-License-Identifier: GPL-3.0-or-later
import math

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.switch_runtime import (
    evaluate_lsfg_30_to_60,
    resolve_switch_runtime_profile,
)


def test_handheld_uses_720p_internal_mode_and_builtin_controller() -> None:
    profile = resolve_switch_runtime_profile(
        "handheld", connected_controllers=1, built_in_controller=True
    )

    assert profile.system_mode == "handheld"
    assert (profile.resolution_width, profile.resolution_height) == (1280, 720)
    assert profile.active_players == 2


def test_dock_uses_safe_resolution_and_caps_four_players() -> None:
    profile = resolve_switch_runtime_profile(
        "dock",
        connected_controllers=6,
        external_width=3840,
        external_height=2160,
    )

    assert profile.system_mode == "docked"
    assert (profile.resolution_width, profile.resolution_height) == (1920, 1080)
    assert profile.active_players == 4
    assert profile.warnings


def test_requested_players_degrades_to_available_controllers() -> None:
    profile = resolve_switch_runtime_profile(
        "dock", connected_controllers=2, requested_players=4
    )

    assert profile.active_players == 2
    assert "Solicitados 4" in profile.warnings[0]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"environment": "unknown", "connected_controllers": 1},
        {"environment": "dock", "connected_controllers": -1},
        {"environment": "dock", "connected_controllers": 1, "requested_players": 5},
    ],
)
def test_runtime_profile_rejects_invalid_inputs(kwargs: dict[str, object]) -> None:
    with pytest.raises(SteamZeroError):
        resolve_switch_runtime_profile(**kwargs)  # type: ignore[arg-type]


def test_lsfg_recommends_only_stable_opted_in_30_to_60() -> None:
    decision = evaluate_lsfg_30_to_60(
        [29.5, 30.0, 30.5, 29.8, 30.2],
        enabled_for_game=True,
        runtime_ready=True,
        vulkan_ready=True,
        display_refresh_hz=60.0,
    )

    assert decision.state == "ready"
    assert decision.multiplier == 2 and decision.target_fps == 60
    assert decision.should_apply


def test_lsfg_never_auto_applies_without_opt_in_or_prerequisite() -> None:
    disabled = evaluate_lsfg_30_to_60(
        [30.0] * 5,
        enabled_for_game=False,
        runtime_ready=True,
        vulkan_ready=True,
        display_refresh_hz=60.0,
    )
    blocked = evaluate_lsfg_30_to_60(
        [30.0] * 5,
        enabled_for_game=True,
        runtime_ready=False,
        vulkan_ready=True,
        display_refresh_hz=60.0,
    )

    assert not disabled.should_apply
    assert blocked.state == "blocked" and not blocked.should_apply


@pytest.mark.parametrize(
    "samples",
    [[20.0, 30.0, 40.0, 30.0, 20.0], [30.0] * 4, [30.0, 30.0, math.nan, 30.0, 30.0]],
)
def test_lsfg_rejects_unstable_or_invalid_samples(samples: list[float]) -> None:
    decision = evaluate_lsfg_30_to_60(
        samples,
        enabled_for_game=True,
        runtime_ready=True,
        vulkan_ready=True,
        display_refresh_hz=60.0,
    )

    assert not decision.should_apply
