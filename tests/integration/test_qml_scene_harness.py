# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""VS-03 — harnesses de imagem e de cena sobre os componentes da fundação.

`CaptureHarness.qml` prova o texto isolado. Estes dois cenários provam o resto
da fundação: ``SceneImage.qml`` (imagem única) e a composição de nós em cena
(vários textos e imagens juntos, como o grid do tema default). Mesmas regras do
harness legado — ambiente canônico, veredito em Python, falha ruidosa, nada de
``skip``.

A resolução de asset é o ponto exercitado aqui com um test-double: o harness
recebe ``mediaFiles`` (chave ``assets/...`` -> arquivo real) porque o papel de
mapear o asset do pacote para o disco é do SHELL, na fronteira do QML. O QML
da cena continua burro — recebe o modelo já apontando para o arquivo, e o
harness recusa um nó cujo asset o runner não mapeou.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from steamzero.domain.qml_render_model import (
    QmlImageRenderModel,
    QmlTextRenderModel,
    to_image_render_model,
    to_render_model,
)
from steamzero.domain.resolved_node import (
    FontAssetHandle,
    FontOrigin,
    ImageFillMode,
    ResolvedGeometry,
    ResolvedImageNode,
    ResolvedTextNode,
)

pytestmark = pytest.mark.visual

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from qml_capture_runner import (  # noqa: E402
    DIAG_CAPTURE,
    CaptureError,
    CaptureResult,
    HarnessKind,
    assert_not_empty,
    capture,
    compare_with_golden,
    write_artifacts,
)

TEST_FONT = "Liberation Sans"
CANVAS = (800, 480)
BACKGROUND = "#101418"

MEDIA_DIR = ROOT / "tests" / "fixtures" / "scene-media"

#: O mapeamento do shell: chave de asset do modelo -> arquivo real.
MEDIA_FILES = {
    "assets/covers/cover-01.png": str(MEDIA_DIR / "cover-01.png"),
    "assets/covers/cover-02.png": str(MEDIA_DIR / "cover-02.png"),
}


def _font() -> FontAssetHandle:
    return FontAssetHandle(
        key=TEST_FONT,
        handle="asset://font/LiberationSans",
        origin=FontOrigin.PACKAGED,
        requested_family=TEST_FONT,
        resolved_family=TEST_FONT,
    )


def _image_model(
    *,
    width: float | None = 320.0,
    height: float | None = 180.0,
    source: str = "assets/covers/cover-01.png",
) -> QmlImageRenderModel:
    return to_image_render_model(
        ResolvedImageNode(
            id="cover",
            source=source,
            geometry=ResolvedGeometry(x=64.0, y=48.0, width=width, height=height),
            fill_mode=ImageFillMode.CROP,
            visible=True,
            opacity=1.0,
        )
    ).require_model()


def _text_model(**overrides: Any) -> QmlTextRenderModel:
    from dataclasses import replace

    base = ResolvedTextNode(
        id="title",
        text="Chrono Trigger",
        geometry=ResolvedGeometry(x=40.0, y=30.0, width=700.0, height=60.0),
        color="#F2F6FB",
        font_family=TEST_FONT,
        font_size=36.0,
        font_asset=_font(),
    )
    return to_render_model(replace(base, **overrides)).require_model()


@pytest.fixture(scope="module")
def rendered_image(tmp_path_factory: pytest.TempPathFactory) -> CaptureResult:
    """Uma captura de imagem por módulo, como no harness de texto."""
    output = tmp_path_factory.mktemp("capture-image")
    model = _image_model(width=640.0, height=180.0)
    result = capture(
        model.to_dict(),
        output=output,
        canvas=CANVAS,
        background=BACKGROUND,
        harness=HarnessKind.IMAGE,
        media_files=MEDIA_FILES,
    )
    write_artifacts(result, output, resolved_node={})
    return result


def _scene_payload() -> dict[str, Any]:
    """Cena composta: um título em cima, uma capa no grid abaixo."""
    return {
        "nodes": [
            {"kind": "text", **dict(_text_model().to_dict())},
            {
                "kind": "image",
                "id": "cover-01",
                "source": "assets/covers/cover-01.png",
                "x": 64.0,
                "y": 120.0,
                "width": 320.0,
                "height": 180.0,
                "visible": True,
                "opacity": 1.0,
                "fillMode": "PreserveAspectCrop",
            },
            {
                "kind": "image",
                "id": "cover-02",
                "source": "assets/covers/cover-02.png",
                "x": 416.0,
                "y": 120.0,
                "width": 320.0,
                "height": 180.0,
                "visible": True,
                "opacity": 1.0,
                "fillMode": "Stretch",
            },
        ]
    }


@pytest.fixture(scope="module")
def rendered_scene(tmp_path_factory: pytest.TempPathFactory) -> CaptureResult:
    output = tmp_path_factory.mktemp("capture-scene")
    result = capture(
        _scene_payload(),
        output=output,
        canvas=CANVAS,
        background=BACKGROUND,
        harness=HarnessKind.SCENE,
        media_files=MEDIA_FILES,
    )
    write_artifacts(result, output, resolved_node={})
    return result


class TestImageHarness:
    def test_the_image_exists_and_is_not_uniform(self, rendered_image: CaptureResult) -> None:
        assert rendered_image.image.exists()
        assert assert_not_empty(rendered_image.image, background=BACKGROUND) > 1

    def test_the_canvas_has_the_configured_size(self, rendered_image: CaptureResult) -> None:
        from PIL import Image

        with Image.open(rendered_image.image) as picture:
            assert picture.size == CANVAS

    def test_no_forbidden_warning_was_emitted(self, rendered_image: CaptureResult) -> None:
        assert not rendered_image.forbidden_messages, [
            item.text for item in rendered_image.forbidden_messages
        ]

    def test_the_source_is_resolved_to_the_real_file(self, rendered_image: CaptureResult) -> None:
        """O harness fez o papel do shell: asset -> arquivo, antes do QML."""
        assert rendered_image.geometry["source"] == MEDIA_FILES["assets/covers/cover-01.png"]

    def test_position_and_size_survive(self, rendered_image: CaptureResult) -> None:
        geometry = rendered_image.geometry
        assert geometry["x"] == 64
        assert geometry["y"] == 48
        assert geometry["width"] == 640
        assert geometry["height"] == 180

    def test_crop_is_visible_in_the_painted_size(self, rendered_image: CaptureResult) -> None:
        """Capa 320x180 numa caixa 640x180 com crop: escala para 640x360 (cobre)
        e a caixa clipe a sobra — `paintedHeight` prova a escala, `height` prova
        o corte, ambos em números."""
        geometry = rendered_image.geometry
        assert geometry["sourceSizeWidth"] == 320
        assert geometry["sourceSizeHeight"] == 180
        assert geometry["paintedWidth"] == 640
        assert geometry["paintedHeight"] == 360
        assert geometry["width"] == 640
        assert geometry["height"] == 180

    def test_the_environment_record_identifies_the_run(self, rendered_image: CaptureResult) -> None:
        record = rendered_image.environment
        assert record["harness"] == "image"
        assert record["backend"] == "software"
        assert record["qtVersion"].startswith("6.")

    def test_every_artifact_is_published(self, rendered_image: CaptureResult) -> None:
        for name in ("actual.png", "qml-render-model.json", "qml-warnings.txt", "environment.json"):
            assert name in rendered_image.artifacts, name
            assert rendered_image.artifacts[name].exists()


class TestSceneHarness:
    def test_the_image_is_not_uniform(self, rendered_scene: CaptureResult) -> None:
        assert assert_not_empty(rendered_scene.image, background=BACKGROUND) > 1

    def test_no_forbidden_warning_was_emitted(self, rendered_scene: CaptureResult) -> None:
        assert not rendered_scene.forbidden_messages, [
            item.text for item in rendered_scene.forbidden_messages
        ]

    def test_all_nodes_are_reported(self, rendered_scene: CaptureResult) -> None:
        assert rendered_scene.geometry["count"] == 3
        assert {item["id"] for item in rendered_scene.geometry["nodes"]} == {
            "title",
            "cover-01",
            "cover-02",
        }

    def test_the_text_node_keeps_its_content(self, rendered_scene: CaptureResult) -> None:
        nodes = {item["id"]: item for item in rendered_scene.geometry["nodes"]}
        title = nodes["title"]
        assert title["kind"] == "text"
        assert title["text"] == "Chrono Trigger"
        assert 0 < title["contentWidth"] <= title["width"]
        assert 0 < title["contentHeight"] <= title["height"]
        assert "f2f6fb" in title["color"].lower()

    def test_the_image_nodes_keep_their_geometry(self, rendered_scene: CaptureResult) -> None:
        nodes = {item["id"]: item for item in rendered_scene.geometry["nodes"]}
        first = nodes["cover-01"]
        assert first["kind"] == "image"
        assert first["x"] == 64
        assert first["y"] == 120
        assert first["width"] == 320
        assert first["height"] == 180
        assert first["source"] == MEDIA_FILES["assets/covers/cover-01.png"]
        assert first["fillMode"] == "PreserveAspectCrop"

    def test_fill_modes_differ_visibly_in_numbers(self, rendered_scene: CaptureResult) -> None:
        """Stretch 320x180 numa caixa 320x180 não corta; crop da mesma caixa
        também não — mas os dois precisam ter chegado ao QML com seus modos."""
        nodes = {item["id"]: item for item in rendered_scene.geometry["nodes"]}
        assert nodes["cover-01"]["fillMode"] == "PreserveAspectCrop"
        assert nodes["cover-02"]["fillMode"] == "Stretch"
        assert nodes["cover-02"]["paintedWidth"] == 320
        assert nodes["cover-02"]["paintedHeight"] == 180

    def test_the_environment_record_identifies_the_scene(
        self, rendered_scene: CaptureResult
    ) -> None:
        assert rendered_scene.environment["harness"] == "scene"

    def test_the_scene_renders_deterministically(self, tmp_path: Path) -> None:
        """Duas capturas idênticas do mesmo cenário — pré-requisito de golden."""
        first = capture(
            _scene_payload(),
            output=tmp_path / "first",
            canvas=CANVAS,
            background=BACKGROUND,
            harness=HarnessKind.SCENE,
            media_files=MEDIA_FILES,
        )
        second = capture(
            _scene_payload(),
            output=tmp_path / "second",
            canvas=CANVAS,
            background=BACKGROUND,
            harness=HarnessKind.SCENE,
            media_files=MEDIA_FILES,
        )
        metrics = compare_with_golden(second.image, first.image, tmp_path / "compare")
        assert metrics.changed_pixel_count == 0, f"cena não determinística: {metrics.to_dict()}"


class TestDeclaredFailureModesActuallyFire:
    def test_an_unmapped_asset_is_refused(self, tmp_path: Path) -> None:
        """O harness recusa nó cujo asset o runner não mapeou — o mesmo
        sintoma de um shell que esqueceu de resolver a capa."""
        with pytest.raises(CaptureError) as raised:
            capture(
                _scene_payload(),
                output=tmp_path,
                canvas=CANVAS,
                background=BACKGROUND,
                harness=HarnessKind.SCENE,
                media_files={},
            )
        assert raised.value.code == DIAG_CAPTURE
        assert "não mapeou" in raised.value.detail

    def test_a_missing_media_file_is_refused(self, tmp_path: Path) -> None:
        """Asset mapeado para um arquivo que não existe: a imagem não carrega,
        e a captura reprova em vez de congelar um retângulo vazio."""
        mapping = {"assets/covers/cover-01.png": str(tmp_path / "ausente.png")}
        with pytest.raises(CaptureError) as raised:
            capture(
                _scene_payload(),
                output=tmp_path,
                canvas=CANVAS,
                background=BACKGROUND,
                harness=HarnessKind.SCENE,
                media_files=mapping,
            )
        assert raised.value.code == DIAG_CAPTURE

    def test_a_pending_value_in_a_scene_node_is_refused(self, tmp_path: Path) -> None:
        payload = {
            "nodes": [
                {
                    "kind": "text",
                    "id": "bad",
                    "text": {"bind": "game.title"},
                    "x": 0,
                    "y": 0,
                    "width": 100,
                    "height": 20,
                    "visible": True,
                    "opacity": 1.0,
                    "color": "#FFFFFF",
                    "fontFamily": TEST_FONT,
                    "fontPixelSize": 12,
                }
            ]
        }
        with pytest.raises(CaptureError) as raised:
            capture(
                payload,
                output=tmp_path,
                canvas=CANVAS,
                background=BACKGROUND,
                harness=HarnessKind.SCENE,
                media_files=MEDIA_FILES,
            )
        assert raised.value.code == DIAG_CAPTURE
        assert "não resolvido" in raised.value.detail

    def test_the_image_harness_also_rejects_unmapped_assets(self, tmp_path: Path) -> None:
        with pytest.raises(CaptureError) as raised:
            capture(
                _image_model().to_dict(),
                output=tmp_path,
                canvas=CANVAS,
                background=BACKGROUND,
                harness=HarnessKind.IMAGE,
                media_files={},
            )
        assert raised.value.code == DIAG_CAPTURE
        assert "não mapeou" in raised.value.detail
