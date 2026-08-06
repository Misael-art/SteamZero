# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""``move_focus`` — a especificação do movimento de foco numa grade.

A decisão mora no domínio, e não no QML, pela mesma razão do resto do IR: se
cada renderizador implementasse a própria regra de wrap, um dia elas
divergiriam, e o mesmo controle navegaria diferente conforme o backend. O QML
recebe o índice focado por esta função e só desenha.

Semântica da função:

- ``current=None`` foca o primeiro item — é o estado da grade que acabou de
  carregar, sem seleção.
- As quatro direções dão a volta na grade: na borda, esquerda/direita
  continuam na MESMA linha e cima/baixo na MESMA coluna.
- Linha parcial (última linha com menos itens que ``columns``) é resolvida por
  clamp: mover para um item que não existe foca o último existente. É a única
  aproximação da função, e está documentada aqui porque o ``current`` de
  retorno nunca aponta para uma célula vazia.
- ``count`` é o número de itens; ``rows`` existem para o wrap vertical, e
  ``count`` pode ser menor que ``columns * rows``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Direction(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    UP = "up"
    DOWN = "down"


@dataclass(frozen=True)
class GridSpec:
    """A forma da grade. ``count`` pode ser menor que ``columns * rows``."""

    columns: int
    rows: int
    count: int

    def __post_init__(self) -> None:
        if self.columns < 1 or self.rows < 1:
            raise ValueError(
                f"grade com colunas/linhas zeradas ou negativas: {self.columns}x{self.rows}"
            )
        if self.count < 1:
            raise ValueError(f"grade sem itens: {self.count}")
        if self.count > self.columns * self.rows:
            raise ValueError(f"{self.count} itens não cabem na grade {self.columns}x{self.rows}")


def move_focus(current: int | None, spec: GridSpec, direction: Direction) -> int | None:
    """Devolve o índice que deve receber foco após o movimento.

    ``None`` de volta só é possível quando a grade está vazia — e ``GridSpec``
    recusa grade vazia, então o retorno ``None`` não existe neste caminho; o
    tipo permanece opcional apenas para honrar o contrato da entrada.
    """
    if current is None:
        return 0
    if not 0 <= current < spec.count:
        raise ValueError(f"índice focado fora da grade: {current} (0..{spec.count - 1})")

    columns = spec.columns
    rows = spec.rows
    last = spec.count - 1

    if spec.count == 1:
        return 0

    row, col = divmod(current, columns)

    if direction is Direction.LEFT:
        if col > 0:
            return col - 1
        return min(row * columns + columns - 1, last)
    if direction is Direction.RIGHT:
        if col < columns - 1:
            return min(row * columns + col + 1, last)
        return min(row * columns, last)
    if direction is Direction.UP:
        target = ((row - 1) % rows) * columns + col
        return min(target, last)
    if direction is Direction.DOWN:
        target = ((row + 1) % rows) * columns + col
        return min(target, last)
    raise ValueError(f"direção desconhecida: {direction!r}")
