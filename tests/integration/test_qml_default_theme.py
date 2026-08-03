# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""VS-03 — o tema default RENDERIZA: fatia 3x2 do grid na captura de cena.

O teste unitário prova a geometria e a resolução em números. Este prova que a
cena composta — cabeçalho + grid de capas + títulos — renderiza no runtime
QML real, com o mesmo contrato do harness de cena: ambiente canônico, veredito
em Python, falha ruidosa.

A fatia usa o MESMO ``default_theme`` do produto com um canvas menor
(800x480): o tema é parametrizado por métricas, e é exatamente essa
parametrização que permite pré-visualizar o tema default num canvas de teste.
As capas são os assets do pacote do tema mapeados pelo test-double do shell.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from steamzero.domain.default_theme import (
    FONT_FAMILY,
    DefaultGridMetrics,
    build_default_scene,
    default_tokens,
)
from steamzero.domain.qml_render_model import to_image_render_model, to_render_model
from steamzero.domain.scene_registry import default_registries
from steamzero.domain.scene_resolver import ResolutionContext, Resolver
from steamzero.domain.scene_tree import walk_tree
from steamzero.domain.text_node_builder import (
    FontProvider,
    LayoutBox,
    build_image_node,
    build_text_node,
)

pytestmark = pytest.mark.visual

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from qml_capture_runner import (  # noqa: E402
    CaptureResult,
    HarnessKind,
    assert_not_empty,
    capture,
    compare_with_golden,
    write_artifacts,
)

CANVAS = (800, 480)
BACKGROUND = "#0b1020"
MEDIA_DIR = ROOT / "tests" / "fixtures" / "scene-media"

SMALL = DefaultGridMetrics(columns=3, rows=2, canvas_width=800.0, canvas_height=480.0)


def _media_files() -> dict[str, str]:
    return {
        f"assets/covers/cover-{i:02d}.png": str(MEDIA_DIR / f"cover-{i:02d}.png")
        for i in range(1, 7)
    } | {"assets/covers/cover-fallback.png": str(MEDIA_DIR / "cover-fallback.png")}


def _scene_payload() -> dict[str, Any]:
    """Resolve a fatia 3x2 do tema e entrega o payload de cena do harness."""
    resolver = Resolver(
        ResolutionContext(
            registries=default_registries(),
            tokens=default_tokens(),
            read_model={},
            assets=frozenset(_media_files()),
            theme_id="org.steamzero.default",
        )
    )
    fonts = FontProvider(packaged={"default": FONT_FAMILY})
    box = LayoutBox(SMALL.canvas_width, SMALL.canvas_height)
    nodes: list[dict[str, Any]] = []
    for _depth, element in walk_tree(build_default_scene(SMALL)):
        if element.type == "container":
            continue
        if element.type == "image":
            nodes.append(
                {
                    "kind": "image",
                    **dict(
                        to_image_render_model(build_image_node(element, resolver=resolver, box=box))
                        .require_model()
                        .to_dict()
                    ),
                }
            )
        else:
            nodes.append(
                {
                    "kind": "text",
                    **dict(
                        to_render_model(
                            build_text_node(element, resolver=resolver, box=box, fonts=fonts)
                        )
                        .require_model()
                        .to_dict()
                    ),
                }
            )
    return {"nodes": nodes}


@pytest.fixture(scope="module")
def rendered_theme(tmp_path_factory: pytest.TempPathFactory) -> CaptureResult:
    output = tmp_path_factory.mktemp("capture-theme")
    result = capture(
        _scene_payload(),
        output=output,
        canvas=CANVAS,
        background=BACKGROUND,
        harness=HarnessKind.SCENE,
        media_files=_media_files(),
    )
    write_artifacts(result, output, resolved_node={})
    return result


class TestDefaultThemeRenders:
    def test_the_theme_paints_over_the_background(self, rendered_theme: CaptureResult) -> None:
        assert assert_not_empty(rendered_theme.image, background=BACKGROUND) > 1

    def test_no_forbidden_warning_was_emitted(self, rendered_theme: CaptureResult) -> None:
        assert not rendered_theme.forbidden_messages, [
            item.text for item in rendered_theme.forbidden_messages
        ]

    def test_every_node_of_the_slice_is_reported(self, rendered_theme: CaptureResult) -> None:
        # 2 (cabeçalho) + 6 células x 2 (capa + título) = 14 nós.
        assert rendered_theme.geometry["count"] == 14

    def test_the_header_keeps_its_place_and_text(self, rendered_theme: CaptureResult) -> None:
        nodes = {item["id"]: item for item in rendered_theme.geometry["nodes"]}
        title = nodes["header-title"]
        assert title["text"] == "Biblioteca"
        assert title["x"] == 64
        assert title["y"] == 48
        assert 0 < title["contentWidth"] <= title["width"]

    def test_the_first_cover_sits_where_the_theme_says(self, rendered_theme: CaptureResult) -> None:
        nodes = {item["id"]: item for item in rendered_theme.geometry["nodes"]}
        cover = nodes["cell-01-cover"]
        expected = SMALL.cover_geometry(0)
        assert cover["x"] == pytest.approx(expected.x)
        assert cover["y"] == pytest.approx(expected.y)
        assert cover["width"] == pytest.approx(expected.width)
        assert cover["height"] == pytest.approx(expected.height)
        assert cover["fillMode"] == "PreserveAspectCrop"

    def test_the_grid_is_laid_out_row_by_row(self, rendered_theme: CaptureResult) -> None:
        nodes = {item["id"]: item for item in rendered_theme.geometry["nodes"]}
        first = nodes["cell-01-cover"]
        second = nodes["cell-02-cover"]
        assert second["x"] == pytest.approx(first["x"] + first["width"] + SMALL.gap)
        assert second["y"] == first["y"]
        first_title = nodes["cell-01-title"]
        assert first_title["y"] == pytest.approx(first["y"] + first["height"] + SMALL.title_gap)

    def test_titles_fall_back_to_rendered_text(self, rendered_theme: CaptureResult) -> None:
        nodes = {item["id"]: item for item in rendered_theme.geometry["nodes"]}
        title = nodes["cell-01-title"]
        assert title["text"] == "Jogo sem título"
        assert 0 < title["contentWidth"] <= title["width"]

    def test_the_slice_is_deterministic(self, tmp_path: Path) -> None:
        first = capture(
            _scene_payload(),
            output=tmp_path / "first",
            canvas=CANVAS,
            background=BACKGROUND,
            harness=HarnessKind.SCENE,
            media_files=_media_files(),
        )
        second = capture(
            _scene_payload(),
            output=tmp_path / "second",
            canvas=CANVAS,
            background=BACKGROUND,
            harness=HarnessKind.SCENE,
            media_files=_media_files(),
        )
        metrics = compare_with_golden(second.image, first.image, tmp_path / "compare")
        assert metrics.changed_pixel_count == 0, f"tema não determinístico: {metrics.to_dict()}"
