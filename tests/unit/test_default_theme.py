# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Tema default: geometria do grid, cena, resolução e foco.

Este é o teste do PRIMEIRO consumidor da fundação. Ele prova três coisas
separadas: a geometria derivada (números), a cena declarada (árvore válida,
ids únicos) e a resolução ponta a ponta (contrato → nó → modelo QML) com a
cena inteira — não um elemento de cada vez.

O grid canônico é 6x4 em 1920x1080; os testes usam o mesmo canvas, e o teste
visual da fatia renderiza uma versão menor para caber no harness.
"""

from __future__ import annotations

from typing import Any

import pytest

from steamzero.domain.default_theme import (
    DEFAULT_TOKENS,
    FONT_FAMILY,
    DefaultGridMetrics,
    build_cell_contracts,
    build_default_scene,
    default_grid_metrics,
    default_tokens,
    focus_target,
)
from steamzero.domain.grid_navigation import Direction
from steamzero.domain.qml_render_model import (
    to_image_render_model,
    to_render_model,
)
from steamzero.domain.scene_registry import default_registries
from steamzero.domain.scene_resolver import ResolutionContext, Resolver
from steamzero.domain.scene_tree import tree_stats, walk_tree
from steamzero.domain.text_node_builder import (
    FontProvider,
    LayoutBox,
    build_image_node,
    build_text_node,
)

METRICS = default_grid_metrics()

COVER_ASSETS = frozenset(
    {f"assets/covers/cover-{i:02d}.png" for i in range(1, 7)} | {"assets/covers/cover-fallback.png"}
)


def _resolver(read_model: dict[str, Any] | None = None) -> Resolver:
    return Resolver(
        ResolutionContext(
            registries=default_registries(),
            tokens=default_tokens(),
            read_model=read_model or {},
            assets=COVER_ASSETS,
            theme_id="org.steamzero.default",
        )
    )


def _resolve_scene(root: Any) -> list[Any]:
    """Resolve a cena inteira com UM resolver e UMA caixa de referência."""
    resolver = _resolver()
    fonts = FontProvider(packaged={"default": FONT_FAMILY})
    box = LayoutBox(METRICS.canvas_width, METRICS.canvas_height)
    nodes: list[Any] = []
    for _depth, element in walk_tree(root):
        if element.type == "container":
            continue
        if element.type == "image":
            nodes.append(build_image_node(element, resolver=resolver, box=box))
        else:
            nodes.append(build_text_node(element, resolver=resolver, box=box, fonts=fonts))
    return nodes


class TestGridGeometry:
    def test_the_canonical_grid_is_6x4(self) -> None:
        assert METRICS.columns == 6
        assert METRICS.rows == 4
        assert METRICS.cell_count == 24

    def test_cell_width_is_derived_from_the_canvas(self) -> None:
        usable = 1920 - 2 * 64 - 5 * 24
        assert METRICS.cell_width == pytest.approx(usable / 6)

    def test_covers_keep_the_16x9_ratio(self) -> None:
        assert METRICS.cover_height == pytest.approx(METRICS.cell_width * 9 / 16)

    def test_every_cell_fits_inside_the_canvas(self) -> None:
        last = METRICS.cell_count - 1
        cover = METRICS.cover_geometry(last)
        bottom = METRICS.title_geometry(last).y + METRICS.title_slot_height
        assert cover.x + cover.width <= METRICS.canvas_width
        assert cover.y >= METRICS.grid_top
        assert bottom <= METRICS.canvas_height

    def test_neighbouring_cells_are_gap_apart(self) -> None:
        first = METRICS.cover_geometry(0)
        second = METRICS.cover_geometry(1)
        assert second.x - (first.x + first.width) == pytest.approx(METRICS.gap)

    def test_title_sits_under_its_cover(self) -> None:
        for index in (0, 7, 23):
            cover = METRICS.cover_geometry(index)
            title = METRICS.title_geometry(index)
            assert title.x == cover.x
            assert title.width == cover.width
            assert title.y == pytest.approx(cover.y + METRICS.cover_height + METRICS.title_gap)


class TestScene:
    def test_the_scene_builds_and_validates(self) -> None:
        root = build_default_scene()
        stats = tree_stats(root)
        assert stats.nodes == 1 + 2 + METRICS.cell_count * 2
        assert stats.max_depth == 2
        assert root.id == "default-scene"

    def test_every_cell_declares_cover_and_title(self) -> None:
        root = build_default_scene()
        cells = [element for _depth, element in walk_tree(root) if element.id.startswith("cell-")]
        assert len(cells) == METRICS.cell_count * 2
        for index in range(METRICS.cell_count):
            number = index + 1
            marker = f"-{number:02d}-"
            ids = {element.id for element in cells if marker in element.id}
            assert ids == {f"cell-{number:02d}-cover", f"cell-{number:02d}-title"}

    def test_the_tokens_are_the_aura_palette(self) -> None:
        tokens = default_tokens()
        assert tokens["color.background.primary"] == "#0b1020"
        assert tokens["color.accent"] == tokens["color.focusRing"]
        assert tokens["color.focusRing"] == "#22d3ee"

    def test_the_scene_uses_tokens_not_literals(self) -> None:
        root = build_default_scene()
        for _depth, element in walk_tree(root):
            if element.typography is not None and element.typography.color is not None:
                assert "color." in str(element.typography.color), element.id


class TestResolution:
    def test_the_scene_resolves_to_49_nodes(self) -> None:
        nodes = _resolve_scene(build_default_scene())
        assert len(nodes) == 2 + METRICS.cell_count * 2
        assert all(node.visible for node in nodes)

    def test_covers_resolve_to_package_assets(self) -> None:
        nodes = _resolve_scene(build_default_scene())
        covers = [node for node in nodes if hasattr(node, "source")]
        assert len(covers) == METRICS.cell_count
        assert all(node.source.startswith("assets/covers/") for node in covers)

    def test_titles_fall_back_without_a_read_model(self) -> None:
        nodes = _resolve_scene(build_default_scene())
        titles = [node for node in nodes if node.id.startswith("cell-") and hasattr(node, "text")]
        assert len(titles) == METRICS.cell_count
        assert all(node.text == "Jogo sem título" for node in titles)

    def test_the_read_model_feeds_the_titles(self) -> None:
        resolver = _resolver(read_model={"game.title": "Chrono Trigger"})
        fonts = FontProvider(packaged={"default": FONT_FAMILY})
        box = LayoutBox(METRICS.canvas_width, METRICS.canvas_height)
        root = build_default_scene()
        title = next(
            build_text_node(element, resolver=resolver, box=box, fonts=fonts)
            for _depth, element in walk_tree(root)
            if element.id == "cell-01-title"
        )
        assert title.text == "Chrono Trigger"

    def test_a_missing_cover_degrades_to_the_fallback_asset(self) -> None:
        element = build_cell_contracts(METRICS, 0)[0]
        resolver = Resolver(
            ResolutionContext(
                registries=default_registries(),
                tokens=default_tokens(),
                read_model={},
                assets=frozenset({"assets/covers/cover-fallback.png"}),
            )
        )
        node = build_image_node(element, resolver=resolver, box=LayoutBox(1920.0, 1080.0))
        assert node.source == "assets/covers/cover-fallback.png"
        assert node.resolution_diagnostics, "a degradação precisa estar registrada"

    def test_colors_come_from_the_tokens(self) -> None:
        nodes = _resolve_scene(build_default_scene())
        header = next(node for node in nodes if node.id == "header-title")
        assert header.color == DEFAULT_TOKENS["color.text.primary"]

    def test_the_adapters_accept_every_resolved_node(self) -> None:
        nodes = _resolve_scene(build_default_scene())
        for node in nodes:
            if hasattr(node, "source"):
                result = to_image_render_model(node)
            else:
                result = to_render_model(node)
            assert result.require_model() is not None, node.id


class TestFocus:
    def test_right_advances_within_the_row(self) -> None:
        assert focus_target(0, Direction.RIGHT) == 1
        assert focus_target(4, Direction.RIGHT) == 5

    def test_right_from_the_row_end_wraps(self) -> None:
        assert focus_target(5, Direction.RIGHT) == 0

    def test_down_moves_a_full_row(self) -> None:
        assert focus_target(2, Direction.DOWN) == 8

    def test_up_wraps_from_the_first_row(self) -> None:
        assert focus_target(2, Direction.UP) == 20

    def test_a_cell_outside_the_grid_is_refused(self) -> None:
        with pytest.raises(ValueError):
            focus_target(24, Direction.RIGHT)

    def test_the_small_grid_keeps_the_same_rules(self) -> None:
        small = DefaultGridMetrics(columns=3, rows=2, canvas_width=800.0, canvas_height=480.0)
        assert focus_target(0, Direction.RIGHT, small) == 1
        assert focus_target(2, Direction.RIGHT, small) == 0
        assert focus_target(0, Direction.DOWN, small) == 3
        assert focus_target(3, Direction.UP, small) == 0
