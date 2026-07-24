# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import pytest

from steamzero.api import contracts
from steamzero.core.errors import SteamZeroError
from steamzero.domain.launch_environment import (
    EnvironmentLayer,
    compose_launch_environment,
)


def test_environment_composition_is_pure_closed_and_public_values_are_redacted() -> None:
    base = {"PATH": "/usr/bin", "SECRET": "inherited"}
    layer = EnvironmentLayer(
        "steamzero",
        {"STEAMZERO_GAME_ID": "10", "STEAMZERO_PROFILE_DIGEST": "a" * 64},
    )

    result = compose_launch_environment(base, [layer])

    assert base == {"PATH": "/usr/bin", "SECRET": "inherited"}
    assert result.values["PATH"] == "/usr/bin"
    assert result.values["STEAMZERO_GAME_ID"] == "10"
    public = result.public()
    contracts.validate(public, "gtool-launch-environment-v1.schema.json")
    assert public["managedKeys"] == [
        "STEAMZERO_GAME_ID",
        "STEAMZERO_PROFILE_DIGEST",
    ]
    assert "10" not in str(public)
    assert "SECRET" not in str(public)


@pytest.mark.parametrize(
    "layers,detail",
    [
        (
            [
                EnvironmentLayer("one", {"MANGOHUD_CONFIG": "fps"}),
                EnvironmentLayer("two", {"MANGOHUD_CONFIG": "frametime"}),
            ],
            "colisão",
        ),
        ([EnvironmentLayer("bad", {"LD_PRELOAD": "/opt/inject.so"})], "inválida"),
        ([EnvironmentLayer("Bad Layer", {"MANGOHUD_CONFIG": "fps"})], "camada"),
        ([EnvironmentLayer("one", {"MANGOHUD_CONFIG": "bad\x00value"})], "inválida"),
    ],
)
def test_environment_composition_fails_closed(layers: list[EnvironmentLayer], detail: str) -> None:
    with pytest.raises(SteamZeroError, match=detail):
        compose_launch_environment({}, layers)


def test_environment_composition_rejects_inherited_managed_key() -> None:
    with pytest.raises(SteamZeroError, match="ownership"):
        compose_launch_environment(
            {"STEAMZERO_GAME_ID": "foreign"},
            [EnvironmentLayer("steamzero", {"STEAMZERO_GAME_ID": "10"})],
        )
