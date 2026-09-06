# SPDX-License-Identifier: GPL-3.0-or-later
"""The pixel contrast inventory must measure text, not control chrome."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from ui_contrast_inventory import measure  # noqa: E402


def test_measure_uses_declared_text_color_inside_a_control_box() -> None:
    """A border color must not masquerade as the label foreground."""
    image = Image.new("RGB", (32, 20), "white")
    ImageDraw.Draw(image).rectangle((0, 0, 31, 19), outline="black", width=2)

    result = measure(image, (0, 0, 32, 20), (22, 33, 42))

    assert result is not None
    assert result["background"] == "#ffffff"
    assert result["foreground"] == "#16212a"


def test_measure_rejects_a_declared_color_equal_to_the_background() -> None:
    image = Image.new("RGB", (16, 16), "white")

    assert measure(image, (0, 0, 16, 16), (255, 255, 255)) is None
