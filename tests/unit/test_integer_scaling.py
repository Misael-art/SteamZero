# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from steamzero.api import contracts
from steamzero.core.errors import SteamZeroError
from steamzero.domain.integer_scaling import normative_table, scaling_plan


def test_normative_handheld_table_is_versioned_and_has_known_rows() -> None:
    table = normative_table()
    contracts.validate(table, "retro-integer-scaling-v1.schema.json")

    rows = {row["systemId"]: row for row in table["rows"]}
    assert rows["gb-gbc"]["selected"] == {
        "mode": "integer",
        "filter": "nearest",
        "integerScale": 5,
        "outputWidth": 800,
        "outputHeight": 720,
        "marginX": 480,
        "marginY": 80,
        "coveragePermille": 562,
        "reason": "largest-integer-fit",
    }
    assert rows["gba"]["selected"]["integerScale"] == 5
    assert rows["snes"]["selected"]["integerScale"] == 3
    assert all(row["fallback"]["filter"] == "sharp-bilinear" for row in table["rows"])


def test_integer_plan_uses_largest_scale_that_fits_without_crop_or_stretch() -> None:
    plan = scaling_plan(320, 240, 1280, 800)
    assert plan["selected"]["integerScale"] == 3
    assert plan["selected"]["outputWidth"] == 960
    assert plan["selected"]["outputHeight"] == 720
    assert plan["selected"]["marginX"] == 320
    assert plan["selected"]["marginY"] == 80


def test_oversized_source_falls_back_to_sharp_bilinear() -> None:
    plan = scaling_plan(1920, 1080, 1280, 800)
    assert plan["selected"] == {
        "mode": "sharp-bilinear",
        "filter": "sharp-bilinear",
        "integerScale": None,
        "outputWidth": 1280,
        "outputHeight": 720,
        "marginX": 0,
        "marginY": 80,
        "coveragePermille": 900,
        "reason": "source-exceeds-viewport",
    }


@pytest.mark.parametrize(
    "dimensions",
    [
        (0, 240, 1280, 800),
        (320, -1, 1280, 800),
        (320, 240, True, 800),
        (320, 240, 1280, 9000),
    ],
)
def test_scaling_rejects_invalid_dimensions(dimensions: tuple[int, int, int, int]) -> None:
    with pytest.raises(SteamZeroError) as error:
        scaling_plan(*dimensions)
    assert error.value.code == "E-API-SCHEMA"
