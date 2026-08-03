# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Ponte shell→tema→QML: o payload do shell carrega cena + anel de foco.

O teste da integração prova o que o QML desenha. Este prova o que a ponte
produz sem runtime nenhum: a cena do tema resolvida e traduzida, o anel de
foco acoplado na célula pedida, e a recusa de foco fora do grid.
"""

from __future__ import annotations

import pytest

from steamzero.domain.default_theme import (
    FONT_FAMILY,
    DefaultGridMetrics,
    build_default_scene,
    default_tokens,
)
from steamzero.domain.scene_registry import default_registries
from steamzero.domain.scene_resolver import ResolutionContext, Resolver
from steamzero.domain.shell_bridge import assemble_shell_payload, focus_ring_payload
from steamzero.domain.text_node_builder import FontProvider, LayoutBox

SMALL = DefaultGridMetrics(columns=3, rows=3, canvas_width=800.0, canvas_height=480.0)

COVER_ASSETS = frozenset(
    {f"assets/covers/cover-{i:02d}.png" for i in range(1, 7)} | {"assets/covers/cover-fallback.png"}
)


def _payload(focused: int = 0) -> dict[str, object]:
    resolver = Resolver(
        ResolutionContext(
            registries=default_registries(),
            tokens=default_tokens(),
            read_model={},
            assets=COVER_ASSETS,
            theme_id="org.steamzero.default",
        )
    )
    fonts = FontProvider(packaged={"default": FONT_FAMILY})
    box = LayoutBox(SMALL.canvas_width, SMALL.canvas_height)
    return assemble_shell_payload(
        build_default_scene(SMALL),
        focused=focused,
        resolver=resolver,
        fonts=fonts,
        box=box,
        metrics=SMALL,
    )


class TestFocusRingPayload:
    def test_the_ring_is_a_focus_node_with_the_token_color(self) -> None:
        ring = focus_ring_payload(0, SMALL)
        assert ring["kind"] == "focus"
        assert ring["id"] == "focus-ring-00"
        assert ring["color"] == "#22d3ee"
        assert ring["visible"] is True

    def test_the_ring_geometry_is_the_expanded_cover(self) -> None:
        ring = focus_ring_payload(5, SMALL)
        expected = SMALL.focus_ring_geometry(5)
        assert ring["x"] == expected.x
        assert ring["y"] == expected.y
        assert ring["width"] == expected.width
        assert ring["height"] == expected.height

    def test_a_focused_cell_outside_the_grid_is_refused(self) -> None:
        with pytest.raises(ValueError):
            focus_ring_payload(9, SMALL)


class TestAssembleShellPayload:
    def test_the_payload_has_the_scene_plus_the_ring(self) -> None:
        payload = _payload(0)
        nodes = payload["nodes"]
        assert isinstance(nodes, list)
        assert len(nodes) == 2 + SMALL.cell_count * 2 + 1
        kinds = [node["kind"] for node in nodes]
        assert kinds.count("focus") == 1
        assert kinds.count("image") == SMALL.cell_count
        assert kinds.count("text") == 2 + SMALL.cell_count

    def test_the_ring_comes_last_and_is_the_focused_cell(self) -> None:
        payload = _payload(5)
        nodes = payload["nodes"]
        assert nodes[-1]["kind"] == "focus"
        assert nodes[-1]["id"] == "focus-ring-05"

    def test_every_node_carries_the_adapter_payload(self) -> None:
        payload = _payload(0)
        for node in payload["nodes"]:
            if node["kind"] == "focus":
                assert "borderWidth" in node
            elif node["kind"] == "image":
                assert node["source"].startswith("assets/covers/")
                assert "fillMode" in node
            else:
                assert "text" in node
                assert "fontFamily" in node

    def test_a_focused_cell_outside_the_grid_is_refused(self) -> None:
        with pytest.raises(ValueError):
            _payload(9)
