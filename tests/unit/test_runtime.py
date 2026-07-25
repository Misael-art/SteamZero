# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from unittest.mock import patch

from steamzero.runtime import observe_session_environment


def test_observe_with_device_dict_adds_kind() -> None:
    with patch(
        "steamzero.runtime.LinuxSessionEnvironment",
    ) as mock_env:
        mock_env.return_value.snapshot.return_value = {
            "device": {
                "dmi": {"product_name": "ROG Ally"},
                "signals": {"lid": 0},
            },
        }
        result = observe_session_environment()
    assert isinstance(result["device"], dict)
    assert "kind" in result["device"]


def test_observe_without_device_returns_raw() -> None:
    with patch(
        "steamzero.runtime.LinuxSessionEnvironment",
    ) as mock_env:
        mock_env.return_value.snapshot.return_value = {}
        result = observe_session_environment()
    assert result == {}


def test_observe_with_non_dict_device_returns_raw() -> None:
    with patch(
        "steamzero.runtime.LinuxSessionEnvironment",
    ) as mock_env:
        mock_env.return_value.snapshot.return_value = {"device": "not-a-dict"}
        result = observe_session_environment()
    assert "kind" not in result.get("device", {})
