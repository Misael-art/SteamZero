# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Ponte shell→tema→QML: a cena do tema + estado de foco = payload do shell.

O shell de entrada consome o tema default como o harness de cena consome nós
avulsos, com uma diferença: além dos nós de texto/imagem, o payload carrega o
ANEL de foco — a célula atualmente focada, desenhada sobre a cena. Quem produz
o payload é o shell; quem desenha é o QML; quem decidiu onde o foco está é o
domínio (``theme_shell.apply_control``).

O anel entra como um nó ``kind: "focus"``, com a geometria já resolvida pelo
tema (``DefaultGridMetrics.focus_ring_geometry``) e a cor do token
``color.focusRing``. O QML não re-deriva nada: recebe a caixa pronta e desenha
a borda.

O destino do anel é o índice da célula focada; se nenhum índice for passado,
o shell começa com a célula 0 (a mesma semântica de ``move_focus`` com
``current=None``).
"""

from __future__ import annotations

from typing import Any

from steamzero.domain.default_theme import (
    DEFAULT_TOKENS,
    FOCUS_RING_WIDTH,
    DefaultGridMetrics,
    default_grid_metrics,
)
from steamzero.domain.qml_render_model import (
    to_image_render_model,
    to_render_model,
)
from steamzero.domain.scene_tree import walk_tree
from steamzero.domain.text_node_builder import (
    FontProvider,
    LayoutBox,
    build_image_node,
    build_text_node,
)


def focus_ring_payload(
    index: int,
    metrics: DefaultGridMetrics | None = None,
) -> dict[str, Any]:
    """Payload do anel de foco: caixa resolvida pelo tema + cor do token."""
    metrics = metrics or default_grid_metrics()
    if not 0 <= index < metrics.cell_count:
        raise ValueError(f"célula focada fora do grid: {index}")
    ring = metrics.focus_ring_geometry(index)
    return {
        "kind": "focus",
        "id": f"focus-ring-{index:02d}",
        "x": ring.x,
        "y": ring.y,
        "width": ring.width,
        "height": ring.height,
        "visible": True,
        "color": DEFAULT_TOKENS["color.focusRing"],
        "borderWidth": FOCUS_RING_WIDTH,
    }


def assemble_shell_payload(
    scene: Any,
    *,
    focused: int,
    resolver: Any,
    fonts: FontProvider,
    box: LayoutBox,
    metrics: DefaultGridMetrics | None = None,
) -> dict[str, Any]:
    """Resolve a cena do tema e acopia o anel de foco da célula indicada.

    A entrada é a cena contratual (``build_default_scene``), o resolver já
    montado com registries/tokens/read_model e a caixa de referência. A saída
    é o payload do shell: uma lista de nós (texto/imagem/foco) no mesmo
    formato que ``CaptureShellHarness.qml`` consome.
    """
    metrics = metrics or default_grid_metrics()
    nodes: list[dict[str, Any]] = []
    for depth, element in walk_tree(scene):
        del depth
        if element.type == "container":
            continue
        if element.type == "image":
            image_node = build_image_node(element, resolver=resolver, box=box)
            payload = to_image_render_model(image_node).require_model().to_dict()
        else:
            text_node = build_text_node(element, resolver=resolver, box=box, fonts=fonts)
            payload = to_render_model(text_node).require_model().to_dict()
        nodes.append({"kind": element.type, **payload})

    nodes.append(focus_ring_payload(focused, metrics=metrics))
    return {"nodes": nodes}
