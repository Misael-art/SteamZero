# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Tema default: cena renderizável mínima consumindo a fundação de cena.

Este é o PRIMEIRO consumidor real de ``build_text_node``/``build_image_node``.
O que ele prova é a composição: um grid de jogos não é uma lista de elementos
soltos, é uma GEOMETRIA derivada de parâmetros — colunas, linhas, entrelinha —
e cada célula é um par (capa, título) com foco navegável.

A paleta é a Aura de referência declarada na spec do PR 2: fundo profundo,
superfície elevada, texto de dois níveis e um anel de foco ciano. Os valores
vivem em ``DEFAULT_TOKENS`` e entram no resolver como a tabela de tokens do
``ResolutionContext`` — o tema não "escreve cores na mão" em cada elemento.

Limites honestos desta entrega:

- ``game.title`` é o único binding usado, com fallback. O read model da
  biblioteca ainda não existe; o fallback é o que mantém a cena renderizável
  de pé e é o caminho de degradação real do produto (falha degrada, nunca
  trava — AGENTS.md §8).
- As capas são assets do pacote (``assets/covers/cover-0N.png``) declarados
  por ``asset()``. O shell mapeia o asset para o arquivo na fronteira do QML;
  aqui, o test-double do harness faz esse papel.
- O foco é ``grid_navigation.move_focus``: a cena ainda não recebe eventos de
  controle — a navegação por controle chega com o shell —, mas o destino do
  foco já é função pura da célula atual, e é isso que o teste prova.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from steamzero.domain.grid_navigation import Direction, GridSpec, move_focus
from steamzero.domain.resolved_node import ResolvedGeometry
from steamzero.domain.scene_contract import (
    Alignment,
    DimensionValue,
    ElementContract,
    LayoutSpec,
    TextLayoutSpec,
    TypographySpec,
)
from steamzero.domain.scene_tree import validate_tree
from steamzero.domain.scene_value import asset, bind, token

#: Grid canônico do tema: 6 colunas por 4 linhas = 24 jogos visíveis.
GRID_COLUMNS = 6
GRID_ROWS = 4

#: A fonte empacotada da fundação (VIS-01). O fontconfig do harness é isolado
#: nela; o tema declara a família e o shell decide o arquivo.
FONT_FAMILY = "Liberation Sans"

#: Paleta Aura da spec do PR 2, no vocabulário de tokens do registro
#: (``default_registries``). Valores finais; o resolver apenas os entrega.
DEFAULT_TOKENS: dict[str, str] = {
    "color.background.primary": "#0b1020",
    "color.surface": "#141a2e",
    "color.surface.focused": "#1c2440",
    "color.text.primary": "#e8ecf7",
    "color.text.secondary": "#8b93a8",
    "color.accent": "#22d3ee",
    "color.focusRing": "#22d3ee",
    "color.border": "#262f4d",
    "color.overlay": "#0b1020",
}

#: Dimensões do grid em pixels lógicos. Centralizadas aqui para que a prova
#: geométrica do teste seja contra os MESMOS números que o tema usa.
PAGE_PADDING = 64.0
GRID_GAP = 24.0
HEADER_HEIGHT = 96.0
GRID_TOP = 140.0
TITLE_SLOT_HEIGHT = 44.0
TITLE_GAP = 8.0
GRID_BOTTOM_PAD = 48.0


@dataclass(frozen=True)
class DefaultGridMetrics:
    """Geometria derivada do grid: células e caixas, em pixels lógicos.

    Tudo aqui é função pura dos parâmetros — o teste de layout verifica as
    fórmulas exatamente como o tema as usa, e um golden futuro congela os
    pixels que elas produzem.
    """

    columns: int = GRID_COLUMNS
    rows: int = GRID_ROWS
    canvas_width: float = 1920.0
    canvas_height: float = 1080.0
    padding: float = PAGE_PADDING
    gap: float = GRID_GAP
    header_height: float = HEADER_HEIGHT
    grid_top: float = GRID_TOP
    title_slot_height: float = TITLE_SLOT_HEIGHT
    title_gap: float = TITLE_GAP
    grid_bottom_pad: float = GRID_BOTTOM_PAD

    @property
    def cell_count(self) -> int:
        return self.columns * self.rows

    @property
    def cell_width(self) -> float:
        """Largura da célula: o que sobra do canvas depois de margens e gaps."""
        usable = self.canvas_width - 2 * self.padding - (self.columns - 1) * self.gap
        return usable / self.columns

    @property
    def cover_height(self) -> float:
        """Capa 16:9 dentro da largura da célula."""
        return self.cell_width * 9.0 / 16.0

    @property
    def cell_height(self) -> float:
        return self.cover_height + self.title_gap + self.title_slot_height

    def _column(self, index: int) -> int:
        return index % self.columns

    def _row(self, index: int) -> int:
        return index // self.columns

    def cover_geometry(self, index: int) -> ResolvedGeometry:
        column = self._column(index)
        row = self._row(index)
        return ResolvedGeometry(
            x=round(self.padding + column * (self.cell_width + self.gap), 4),
            y=round(self.grid_top + row * (self.cell_height + self.gap), 4),
            width=round(self.cell_width, 4),
            height=round(self.cover_height, 4),
        )

    def title_geometry(self, index: int) -> ResolvedGeometry:
        cover = self.cover_geometry(index)
        return ResolvedGeometry(
            x=cover.x,
            y=round(cover.y + self.cover_height + self.title_gap, 4),
            width=round(self.cell_width, 4),
            height=self.title_slot_height,
        )


def default_tokens() -> dict[str, Any]:
    """Cópia da paleta, para o contexto do resolver nunca reutilizar a mesma."""
    return dict(DEFAULT_TOKENS)


def default_grid_metrics() -> DefaultGridMetrics:
    return DefaultGridMetrics()


def _dim(value: float | None) -> DimensionValue:
    """Pixel lógico de uma dimensão da geometria. Célula/capa sempre tem valor."""
    if value is None:
        raise ValueError("dimensão ausente na geometria do tema default")
    return DimensionValue.logical_px(value)


def build_cell_contracts(
    metrics: DefaultGridMetrics, index: int
) -> tuple[ElementContract, ElementContract]:
    """Capa + título de uma célula do grid.

    A capa é ``asset()`` do pacote (nunca caminho do host). O título liga em
    ``game.title`` com fallback — o binding real da biblioteca, ainda sem read
    model. A ordem do par importa para o teste: capa primeiro, título abaixo.
    """
    number = index + 1
    cover_id = f"cell-{number:02d}-cover"
    title_id = f"cell-{number:02d}-title"

    cover = ElementContract(
        id=cover_id,
        type="image",
        image_content=asset(
            f"assets/covers/cover-{(index % 6) + 1:02d}.png",
            fallback=asset("assets/covers/cover-fallback.png"),
        ),
        layout=LayoutSpec(
            x=_dim(metrics.cover_geometry(index).x),
            y=_dim(metrics.cover_geometry(index).y),
            width=_dim(metrics.cover_geometry(index).width),
            height=_dim(metrics.cover_geometry(index).height),
        ),
    )

    title = ElementContract(
        id=title_id,
        type="text",
        text_content=bind("game.title", fallback="Jogo sem título"),
        layout=LayoutSpec(
            x=_dim(metrics.title_geometry(index).x),
            y=_dim(metrics.title_geometry(index).y),
            width=_dim(metrics.title_geometry(index).width),
            height=_dim(metrics.title_geometry(index).height),
        ),
        typography=TypographySpec(
            color=token("color.text.secondary"),
            font_family=FONT_FAMILY,
            font_size=18.0,
            font_weight=400,
        ),
        text_layout=TextLayoutSpec(
            horizontal_alignment=Alignment.START,
            vertical_alignment=Alignment.CENTER,
        ),
    )
    return cover, title


def build_default_scene(
    metrics: DefaultGridMetrics | None = None,
) -> ElementContract:
    """A cena inteira do tema default: cabeçalho + grid 6x4 de capas.

    Um único nó raiz com todos os filhos — é a forma que ``validate_tree``
    conhece, e o que o shell futuro vai entregar ao renderizador de uma vez.
    """
    metrics = metrics or default_grid_metrics()

    header_title = ElementContract(
        id="header-title",
        type="text",
        text_content="Biblioteca",
        layout=LayoutSpec(
            x=_dim(metrics.padding),
            y=_dim(48.0),
            width=_dim(600.0),
            height=_dim(56.0),
        ),
        typography=TypographySpec(
            color=token("color.text.primary"),
            font_family=FONT_FAMILY,
            font_size=34.0,
            font_weight=700,
        ),
        text_layout=TextLayoutSpec(
            horizontal_alignment=Alignment.START,
            vertical_alignment=Alignment.CENTER,
        ),
    )

    header_subtitle = ElementContract(
        id="header-subtitle",
        type="text",
        text_content=bind("system.time", fallback="—"),
        layout=LayoutSpec(
            x=_dim(metrics.padding),
            y=_dim(112.0),
            width=_dim(400.0),
            height=_dim(28.0),
        ),
        typography=TypographySpec(
            color=token("color.text.secondary"),
            font_family=FONT_FAMILY,
            font_size=16.0,
            font_weight=400,
        ),
        text_layout=TextLayoutSpec(
            horizontal_alignment=Alignment.START,
            vertical_alignment=Alignment.CENTER,
        ),
    )

    cells: list[ElementContract] = []
    for index in range(metrics.cell_count):
        cover, title = build_cell_contracts(metrics, index)
        cells.append(cover)
        cells.append(title)

    root = ElementContract(
        id="default-scene",
        type="container",
        visible=True,
        children=tuple([header_title, header_subtitle, *cells]),
    )
    validate_tree(root)
    return root


def focus_target(
    current: int, direction: Direction, metrics: DefaultGridMetrics | None = None
) -> int:
    """Destino do foco a partir da célula atual.

    Delega a ``grid_navigation.move_focus`` — a semântica de wrap/clamp é a
    mesma, e a cena não precisa reimplementá-la.
    """
    metrics = metrics or default_grid_metrics()
    if not 0 <= current < metrics.cell_count:
        raise ValueError(f"célula fora do grid: {current}")
    spec = GridSpec(columns=metrics.columns, rows=metrics.rows, count=metrics.cell_count)
    target = move_focus(current, spec, direction)
    if target is None:  # impossível: GridSpec recusa grade vazia
        raise ValueError("move_focus devolveu None fora de grade vazia")
    return target
