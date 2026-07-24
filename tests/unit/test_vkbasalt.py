# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path

import pytest

from steamzero.api import contracts
from steamzero.core.errors import SteamZeroError
from steamzero.domain.vkbasalt import catalog, config_path, render_config


def test_catalog_is_versioned_and_costs_are_explicit() -> None:
    payload = catalog(available=True)
    contracts.validate(payload, "gtool-vkbasalt-v1.schema.json")
    assert payload["scope"] == "game"
    assert [row["gpuCost"] for row in payload["presets"]] == [
        "none",
        "low",
        "medium",
        "high",
    ]
    assert payload["presets"][0]["completeOff"] is True


@pytest.mark.parametrize("mode,effect", [("cas", "cas"), ("fxaa", "fxaa"), ("smaa", "smaa")])
def test_rendered_presets_are_closed(mode: str, effect: str) -> None:
    rendered = render_config(mode).decode()
    assert f"effects = {effect}" in rendered
    assert "enableOnLaunch = True" in rendered
    assert "/" not in rendered


@pytest.mark.parametrize("mode", ["off", "custom", "../../shader"])
def test_render_config_rejects_off_and_unknown_values(mode: str) -> None:
    with pytest.raises(SteamZeroError):
        render_config(mode)


def test_config_path_is_fixed_to_numeric_game_id(tmp_path: Path) -> None:
    root = tmp_path / "config"
    assert config_path(root, "10") == root / "10.conf"
    with pytest.raises(SteamZeroError):
        config_path(root, "../../etc")
