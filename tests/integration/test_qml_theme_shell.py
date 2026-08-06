# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""VS-03 — o shell de entrada RENDERIZA: cena do tema + anel de foco móvel.

A unidade prova o mapeamento controle→foco em números. Este teste prova que a
PONTE funciona no runtime real: o shell resolve a cena do tema, acopia o anel
na célula focada, e o QML desenha o anel no lugar certo.

A prova não é um golden — é a GEOMETRIA do anel mudando entre foco 0 e foco 5
(fatias de 3x3), mais a verificação de que o pixel da cor do anel (#22d3ee) é
desenhado na linha do anel. Um anel que declara a posição mas não pinta nada
reprovaria na checagem de pixels — geometria verde com tela sem anel é um
verde falso.

Foco nunca é "fora": o shell sempre tem uma célula focada (a 0 no começo). A
checagem de sem-anel renderiza a cena SEM o nó do anel e confirma que a cor do
anel não aparece — provando que a cor que o teste procura é desenhada SÓ pelo
anel, não por outra parte da cena.
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
from steamzero.domain.scene_registry import default_registries
from steamzero.domain.scene_resolver import ResolutionContext, Resolver
from steamzero.domain.shell_bridge import assemble_shell_payload
from steamzero.domain.text_node_builder import FontProvider, LayoutBox

pytestmark = pytest.mark.visual

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from qml_capture_runner import (  # noqa: E402
    CaptureResult,
    HarnessKind,
    assert_not_empty,
    capture,
    write_artifacts,
)

CANVAS = (800, 480)
BACKGROUND = "#0b1020"
MEDIA_DIR = ROOT / "tests" / "fixtures" / "scene-media"
RING_COLOR = "22d3ee"
RING_RGB = (0x22, 0xD3, 0xEE)

#: Fatia 3x3 em 800x480. Célula 0 (linha 0, coluna 0) e célula 5 (linha 1,
#: coluna 2) personalidad o anel longe o suficiente para provar o movimento.
SMALL = DefaultGridMetrics(columns=3, rows=3, canvas_width=800.0, canvas_height=480.0)


def _media_files() -> dict[str, str]:
    return {
        f"assets/covers/cover-{i:02d}.png": str(MEDIA_DIR / f"cover-{i:02d}.png")
        for i in range(1, 7)
    } | {"assets/covers/cover-fallback.png": str(MEDIA_DIR / "cover-fallback.png")}


def _resolver() -> Resolver:
    return Resolver(
        ResolutionContext(
            registries=default_registries(),
            tokens=default_tokens(),
            read_model={},
            assets=frozenset(_media_files()),
            theme_id="org.steamzero.default",
        )
    )


def _payload(focused: int | None) -> dict[str, Any]:
    resolver = _resolver()
    fonts = FontProvider(packaged={"default": FONT_FAMILY})
    box = LayoutBox(SMALL.canvas_width, SMALL.canvas_height)
    full = assemble_shell_payload(
        build_default_scene(SMALL),
        focused=0,
        resolver=resolver,
        fonts=fonts,
        box=box,
        metrics=SMALL,
    )
    if focused is None:
        # Sem anel: a cena do tema sem o nó "focus". Nenhum foco desenhado.
        return {"nodes": full["nodes"][:-1]}
    resolve = _resolver()
    fonts = FontProvider(packaged={"default": FONT_FAMILY})
    box = LayoutBox(SMALL.canvas_width, SMALL.canvas_height)
    return assemble_shell_payload(
        build_default_scene(SMALL),
        focused=focused,
        resolver=resolve,
        fonts=fonts,
        box=box,
        metrics=SMALL,
    )


def _render(focused: int | None, output: Path) -> CaptureResult:
    output.mkdir(parents=True, exist_ok=True)
    result = capture(
        _payload(focused),
        output=output,
        canvas=CANVAS,
        background=BACKGROUND,
        harness=HarnessKind.SHELL,
        media_files=_media_files(),
    )
    write_artifacts(result, output, resolved_node={})
    return result


def _ring_of(result: CaptureResult) -> dict[str, Any]:
    rings = [node for node in result.geometry["nodes"] if node["kind"] == "focus"]
    assert len(rings) == 1, f"esperava 1 anel, achei {len(rings)}"
    return rings[0]


def _pixels(image: Path) -> Any:
    from PIL import Image

    return Image.open(image).convert("RGB")


def _count_pixels(path: Path, color: tuple[int, int, int]) -> int:
    picture = _pixels(path)
    counts = picture.getcolors(maxcolors=picture.width * picture.height)
    if counts is None:
        return 0
    return sum(count for count, entry in counts if entry == color)


class TestShellRenders:
    def test_the_theme_paints_over_the_background(self, tmp_path: Path) -> None:
        result = _render(0, tmp_path / "theme")
        assert assert_not_empty(result.image, background=BACKGROUND) > 1

    def test_no_forbidden_warning_was_emitted(self, tmp_path: Path) -> None:
        result = _render(0, tmp_path / "nowarning")
        assert not result.forbidden_messages, [item.text for item in result.forbidden_messages]

    def test_every_node_of_the_slice_is_reported(self, tmp_path: Path) -> None:
        # 2 (cabeçalho) + 9 células x 2 (capa + título) + 1 anel = 21 nós.
        result = _render(0, tmp_path / "count")
        assert result.geometry["count"] == 2 + SMALL.cell_count * 2 + 1


class TestFocusRing:
    def test_the_ring_sits_on_the_focused_cell(self, tmp_path: Path) -> None:
        for index in (0, 5):
            result = _render(index, tmp_path / f"f{index}")
            ring = _ring_of(result)
            expected = SMALL.focus_ring_geometry(index)
            assert ring["id"] == f"focus-ring-{index:02d}"
            assert ring["x"] == pytest.approx(expected.x)
            assert ring["y"] == pytest.approx(expected.y)
            assert ring["width"] == pytest.approx(expected.width)
            assert ring["height"] == pytest.approx(expected.height)
            assert ring["color"] == "#" + RING_COLOR

    def test_focus_0_and_focus_5_draw_the_ring_in_different_places(self, tmp_path: Path) -> None:
        first = _render(0, tmp_path / "f0")
        second = _render(5, tmp_path / "f5")
        ring0 = _ring_of(first)
        ring5 = _ring_of(second)
        assert ring5["x"] > ring0["x"]
        assert ring5["y"] > ring0["y"]

    def test_the_ring_color_is_painted_on_the_screen(self, tmp_path: Path) -> None:
        result = _render(0, tmp_path / "paint")
        assert _count_pixels(result.image, RING_RGB) > 0

    def test_the_ring_is_the_only_source_of_the_color(self, tmp_path: Path) -> None:
        # Sem o nó "focus", o cyan do anel não aparece em lugar nenhum da cena
        # — senão a checagem de pixel seria um falso positivo.
        without = _render(None, tmp_path / "noring")
        with_ring = _render(0, tmp_path / "ring")
        assert _count_pixels(without.image, RING_RGB) == 0
        assert _count_pixels(with_ring.image, RING_RGB) > 0

    def test_the_ring_moves_with_control_events(self, tmp_path: Path) -> None:
        # O que o domínio decide (move_focus/apply_control) é o que o shell
        # desenha: de foco 0, um RIGHT leva a 1 e o anel anda uma célula.
        from steamzero.domain.theme_shell import ControlEvent, apply_control

        step = apply_control(0, ControlEvent.RIGHT, SMALL)
        assert step == 1
        result = _render(step, tmp_path / "moved")
        ring = _ring_of(result)
        assert ring["id"] == "focus-ring-01"
        assert ring["x"] == pytest.approx(SMALL.focus_ring_geometry(1).x)


class TestDeterminism:
    def test_two_captures_of_the_same_focus_are_identical(self, tmp_path: Path) -> None:
        first = _render(3, tmp_path / "a")
        second = _render(3, tmp_path / "b")
        assert first.image.read_bytes() == second.image.read_bytes()
