# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Shell de entrada: eventos de controle viram movimento de foco no grid.

Este é o teste da PONTE: um evento de controle (tecla de direção, D-pad) é o
que o usuário produz; ``move_focus`` é o que o tema decide; ``theme_shell`` é
o elo entre os dois. Nenhum runtime QML é necessário aqui — a decisão mora no
domínio, e o QML só desenha o que o modelo manda.

O anel de foco também é testado aqui: a geometria é do tema (capa expandida
pela margem do anel), e o QML recebe essa caixa pronta.
"""

from __future__ import annotations

import pytest

from steamzero.domain.default_theme import (
    FOCUS_RING_INSET,
    FOCUS_RING_WIDTH,
    DefaultGridMetrics,
    default_grid_metrics,
)
from steamzero.domain.grid_navigation import Direction
from steamzero.domain.theme_shell import ControlEvent, apply_control, map_control

METRICS = default_grid_metrics()

SMALL = DefaultGridMetrics(columns=3, rows=2, canvas_width=800.0, canvas_height=480.0)


class TestMapControl:
    def test_every_event_maps_to_the_same_direction(self) -> None:
        assert map_control(ControlEvent.LEFT) is Direction.LEFT
        assert map_control(ControlEvent.RIGHT) is Direction.RIGHT
        assert map_control(ControlEvent.UP) is Direction.UP
        assert map_control(ControlEvent.DOWN) is Direction.DOWN

    def test_an_unknown_event_is_refused(self) -> None:
        with pytest.raises(ValueError):
            map_control("confirm")  # type: ignore[arg-type]


class TestApplyControl:
    def test_nothing_focused_focuses_the_first_cell(self) -> None:
        assert apply_control(None, ControlEvent.RIGHT) == 0
        assert apply_control(None, ControlEvent.UP) == 0

    def test_right_advances_within_the_row(self) -> None:
        assert apply_control(0, ControlEvent.RIGHT) == 1
        assert apply_control(4, ControlEvent.RIGHT) == 5

    def test_right_from_the_row_end_wraps(self) -> None:
        assert apply_control(5, ControlEvent.RIGHT) == 0

    def test_down_moves_a_full_row(self) -> None:
        assert apply_control(2, ControlEvent.DOWN) == 8

    def test_up_wraps_from_the_first_row(self) -> None:
        assert apply_control(2, ControlEvent.UP) == 20

    def test_the_small_grid_keeps_the_same_rules(self) -> None:
        assert apply_control(0, ControlEvent.RIGHT, SMALL) == 1
        assert apply_control(2, ControlEvent.RIGHT, SMALL) == 0
        assert apply_control(0, ControlEvent.DOWN, SMALL) == 3
        assert apply_control(3, ControlEvent.UP, SMALL) == 0

    def test_a_cell_outside_the_grid_is_refused(self) -> None:
        with pytest.raises(ValueError):
            apply_control(24, ControlEvent.RIGHT)


class TestFocusRingGeometry:
    def test_the_ring_wraps_the_cover(self) -> None:
        for index in (0, 7, 23):
            cover = METRICS.cover_geometry(index)
            ring = METRICS.focus_ring_geometry(index)
            assert ring.x == pytest.approx(cover.x - FOCUS_RING_INSET)
            assert ring.y == pytest.approx(cover.y - FOCUS_RING_INSET)
            assert ring.width == pytest.approx(cover.width + 2 * FOCUS_RING_INSET)
            assert ring.height == pytest.approx(cover.height + 2 * FOCUS_RING_INSET)

    def test_the_ring_encloses_the_cover(self) -> None:
        cover = METRICS.cover_geometry(0)
        ring = METRICS.focus_ring_geometry(0)
        assert ring.x < cover.x
        assert ring.y < cover.y
        assert ring.x + ring.width > cover.x + cover.width
        assert ring.y + ring.height > cover.y + cover.height

    def test_the_stroke_fits_inside_the_inset(self) -> None:
        assert FOCUS_RING_WIDTH <= FOCUS_RING_INSET

    def test_the_ring_moves_with_the_focus(self) -> None:
        first = METRICS.focus_ring_geometry(0)
        second = METRICS.focus_ring_geometry(1)
        assert second.x > first.x
        assert second.y == first.y
