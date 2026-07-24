# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Tabela normativa e cálculo puro de integer scale."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from steamzero.api import contracts
from steamzero.core.errors import SteamZeroError

_MAX_DIMENSION = 8192


@dataclass(frozen=True)
class SourceMode:
    system_id: str
    mode_id: str
    width: int
    height: int


NORMATIVE_SOURCE_MODES = (
    SourceMode("gb-gbc", "lcd-160x144", 160, 144),
    SourceMode("gba", "lcd-240x160", 240, 160),
    SourceMode("nes-famicom", "240p-256x240", 256, 240),
    SourceMode("snes", "224p-256x224", 256, 224),
    SourceMode("mega-drive", "224p-320x224", 320, 224),
    SourceMode("arcade", "240p-320x240", 320, 240),
    SourceMode("playstation", "240p-320x240", 320, 240),
)


def _dimension(value: int, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= _MAX_DIMENSION:
        raise SteamZeroError("E-API-SCHEMA", detail=f"{label} fora de 1-{_MAX_DIMENSION}")
    return value


def scaling_plan(
    source_width: int,
    source_height: int,
    viewport_width: int,
    viewport_height: int,
) -> dict[str, Any]:
    """Seleciona integer-fit; downscale cai explicitamente em sharp-bilinear."""

    source_width = _dimension(source_width, "largura da fonte")
    source_height = _dimension(source_height, "altura da fonte")
    viewport_width = _dimension(viewport_width, "largura do viewport")
    viewport_height = _dimension(viewport_height, "altura do viewport")
    integer_scale = min(viewport_width // source_width, viewport_height // source_height)
    if integer_scale >= 1:
        output_width = source_width * integer_scale
        output_height = source_height * integer_scale
        mode = "integer"
        filter_id = "nearest"
        scale_value: int | None = integer_scale
        reason = "largest-integer-fit"
    else:
        output_width, output_height = _sharp_fit(
            source_width, source_height, viewport_width, viewport_height
        )
        mode = "sharp-bilinear"
        filter_id = "sharp-bilinear"
        scale_value = None
        reason = "source-exceeds-viewport"

    fallback_width, fallback_height = _sharp_fit(
        source_width, source_height, viewport_width, viewport_height
    )
    return {
        "source": {"width": source_width, "height": source_height},
        "viewport": {"width": viewport_width, "height": viewport_height},
        "selected": {
            "mode": mode,
            "filter": filter_id,
            "integerScale": scale_value,
            "outputWidth": output_width,
            "outputHeight": output_height,
            "marginX": viewport_width - output_width,
            "marginY": viewport_height - output_height,
            "coveragePermille": (
                output_width * output_height * 1000 // (viewport_width * viewport_height)
            ),
            "reason": reason,
        },
        "fallback": {
            "mode": "sharp-bilinear",
            "filter": "sharp-bilinear",
            "outputWidth": fallback_width,
            "outputHeight": fallback_height,
            "reason": "fill-or-downscale-only",
        },
    }


def normative_table(
    viewport_width: int = 1280,
    viewport_height: int = 800,
) -> dict[str, Any]:
    rows = []
    for source in NORMATIVE_SOURCE_MODES:
        row = {
            "systemId": source.system_id,
            "modeId": source.mode_id,
            **scaling_plan(
                source.width,
                source.height,
                viewport_width,
                viewport_height,
            ),
        }
        rows.append(row)
    payload = {
        "schemaVersion": 1,
        "tableId": "retro-integer-scaling-v1",
        "policy": {
            "primary": "largest-integer-fit",
            "fallback": "sharp-bilinear",
            "stretch": False,
            "crop": False,
        },
        "viewport": {
            "width": _dimension(viewport_width, "largura do viewport"),
            "height": _dimension(viewport_height, "altura do viewport"),
        },
        "rows": rows,
    }
    contracts.validate(payload, "retro-integer-scaling-v1.schema.json")
    return payload


def _sharp_fit(
    source_width: int,
    source_height: int,
    viewport_width: int,
    viewport_height: int,
) -> tuple[int, int]:
    if viewport_width * source_height <= viewport_height * source_width:
        return viewport_width, max(1, source_height * viewport_width // source_width)
    return max(1, source_width * viewport_height // source_height), viewport_height
