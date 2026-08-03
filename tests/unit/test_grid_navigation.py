# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""``grid_navigation.move_focus`` — a especificação do movimento de foco.

A função é a decisão de domínio; o QML só a consulta. Estes testes fecham a
semântica de wrap e de linha parcial para que um backend não "melhore" o
comportamento por conta própria.
"""

from __future__ import annotations

import pytest

from steamzero.domain.grid_navigation import Direction, GridSpec, move_focus

FULL = GridSpec(columns=6, rows=4, count=24)


class TestNoSelection:
    def test_any_direction_from_none_focuses_the_first_item(self) -> None:
        for direction in Direction:
            assert move_focus(None, FULL, direction) == 0


class TestHorizontalWrap:
    def test_left_from_the_first_column_wraps_to_row_end(self) -> None:
        assert move_focus(0, FULL, Direction.LEFT) == 5
        assert move_focus(6, FULL, Direction.LEFT) == 11

    def test_right_from_the_last_column_wraps_to_row_start(self) -> None:
        assert move_focus(5, FULL, Direction.RIGHT) == 0
        assert move_focus(11, FULL, Direction.RIGHT) == 6

    def test_moving_in_place_within_a_row(self) -> None:
        assert move_focus(3, FULL, Direction.LEFT) == 2
        assert move_focus(3, FULL, Direction.RIGHT) == 4


class TestVerticalWrap:
    def test_up_from_the_first_row_wraps_to_last_row(self) -> None:
        assert move_focus(2, FULL, Direction.UP) == 20

    def test_down_from_the_last_row_wraps_to_first_row(self) -> None:
        assert move_focus(23, FULL, Direction.DOWN) == 5

    def test_move_in_place_between_rows(self) -> None:
        assert move_focus(8, FULL, Direction.UP) == 2
        assert move_focus(8, FULL, Direction.DOWN) == 14


class TestPartialLastRow:
    """A última linha com menos itens: mover para célula vazia foca a última."""

    PARTIAL = GridSpec(columns=6, rows=4, count=21)

    def test_right_into_the_missing_cell_stays_on_the_last_item(self) -> None:
        last = 20  # linha 3, coluna 2
        assert move_focus(last, self.PARTIAL, Direction.RIGHT) == last

    def test_left_from_the_first_column_of_the_partial_row(self) -> None:
        assert move_focus(18, self.PARTIAL, Direction.LEFT) == 20

    def test_up_is_nowhere_near_the_missing_cells(self) -> None:
        # 20 (linha 3, coluna 2) e 18 (linha 3, coluna 0) sobem para a linha 2,
        # que é completa — coluna preservada.
        assert move_focus(20, self.PARTIAL, Direction.UP) == 14
        assert move_focus(18, self.PARTIAL, Direction.UP) == 12

    def test_down_clamps_to_the_partial_row(self) -> None:
        # 8 (linha 1, coluna 2) desce para a linha 2 completa (14); 2 (linha 0,
        # coluna 2) desce para 8. Nenhum desce para célula vazia.
        assert move_focus(8, self.PARTIAL, Direction.DOWN) == 14
        assert move_focus(2, self.PARTIAL, Direction.DOWN) == 8


class TestSingleItem:
    def test_any_direction_stays_on_the_only_item(self) -> None:
        single = GridSpec(columns=1, rows=1, count=1)
        for direction in Direction:
            assert move_focus(0, single, direction) == 0


class TestValidation:
    def test_an_out_of_range_focus_is_refused(self) -> None:
        with pytest.raises(ValueError, match="fora da grade"):
            move_focus(24, FULL, Direction.RIGHT)

    def test_a_negative_focus_is_refused(self) -> None:
        with pytest.raises(ValueError, match="fora da grade"):
            move_focus(-1, FULL, Direction.DOWN)

    @pytest.mark.parametrize(
        ("columns", "rows", "count"),
        [(0, 2, 4), (2, 0, 4), (2, 2, 0), (2, 2, 5)],
    )
    def test_an_impossible_grid_is_refused(self, columns: int, rows: int, count: int) -> None:
        with pytest.raises(ValueError):
            GridSpec(columns=columns, rows=rows, count=count)

    def test_the_direction_set_is_closed(self) -> None:
        """Direção desconhecida não chega a ``move_focus``: o enum recusa."""
        with pytest.raises(ValueError):
            Direction("diagonal")
