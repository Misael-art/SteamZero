# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Fatia de imagem: ``ElementContract`` → ``ResolvedImageNode`` → modelo QML.

A contraparte de imagem da fatia de texto: mesmo formato de fronteira, mesma
disciplina. O que muda é o conteúdo — um asset do pacote em vez de texto — e é
precisamente essa mudança que este módulo testa.

Caminho exercitado:

    ElementContract(image) → serialização → build_image_node → resolver
    → ResolvedImageNode → to_image_render_model → QmlImageRenderModel
"""

from __future__ import annotations

import json

import pytest

from steamzero.domain.qml_render_model import (
    DIAG_INVALID_MEDIA,
    DIAG_PENDING_VALUE,
    AdaptationStatus,
    to_image_render_model,
)
from steamzero.domain.resolved_node import ImageFillMode, ResolvedImageNode
from steamzero.domain.scene_contract import (
    CONTRACT_PROPERTY_TYPES,
    DimensionValue,
    ElementContract,
    LayoutSpec,
)
from steamzero.domain.scene_registry import default_registries
from steamzero.domain.scene_resolver import (
    DIAG_MISSING_ASSET,
    ResolutionContext,
    ResolutionError,
    Resolver,
)
from steamzero.domain.scene_typing import ValueType
from steamzero.domain.scene_value import asset
from steamzero.domain.text_node_builder import LayoutBox, build_image_node

CANVAS = (1920, 1080)
PACKAGE_ASSETS = frozenset({"assets/cover.png", "assets/cover-fallback.png"})


def _resolver(
    *,
    assets: frozenset[str] = PACKAGE_ASSETS,
    tokens: dict[str, str] | None = None,
) -> Resolver:
    return Resolver(
        ResolutionContext(
            registries=default_registries(),
            assets=assets,
            tokens=tokens or {},
            read_model={},
        )
    )


def _image_element(**overrides: object) -> ElementContract:
    base: dict[str, object] = {
        "id": "cover",
        "type": "image",
        "image_content": asset("assets/cover.png"),
        "layout": LayoutSpec(
            x=DimensionValue.logical_px(64.0),
            y=DimensionValue.logical_px(48.0),
            width=DimensionValue.logical_px(320.0),
            height=DimensionValue.logical_px(180.0),
        ),
    }
    base.update(overrides)
    return ElementContract(**base)  # type: ignore[arg-type]


class TestContract:
    def test_image_content_is_a_closed_value_slot(self) -> None:
        assert CONTRACT_PROPERTY_TYPES["imageContent"] is ValueType.MEDIA

    def test_the_registry_derives_the_declaration(self) -> None:
        properties = default_registries().properties
        assert properties.type_of("imageContent") is ValueType.MEDIA

    def test_image_content_survives_serialization(self) -> None:
        element = _image_element()
        payload = json.loads(json.dumps(element.to_dict(), ensure_ascii=False))
        assert payload["imageContent"] == {"asset": "assets/cover.png"}


class TestBuildImageNode:
    def test_an_asset_becomes_the_source(self) -> None:
        node = build_image_node(_image_element(), resolver=_resolver(), box=LayoutBox(*CANVAS))
        assert node.source == "assets/cover.png"

    def test_a_missing_asset_with_declared_fallback_degrades(self) -> None:
        element = _image_element(
            image_content=asset("assets/ausente.png", fallback=asset("assets/cover-fallback.png"))
        )
        node = build_image_node(element, resolver=_resolver(), box=LayoutBox(*CANVAS))
        assert node.source == "assets/cover-fallback.png"
        assert node.resolution_diagnostics, "a degradação precisa estar registrada"

    def test_a_missing_asset_without_fallback_fails_at_build(self) -> None:
        element = _image_element(image_content=asset("assets/ausente.png"))
        with pytest.raises(ResolutionError) as caught:
            build_image_node(element, resolver=_resolver(), box=LayoutBox(*CANVAS))
        assert caught.value.code == DIAG_MISSING_ASSET

    def test_an_image_element_without_source_is_a_defect(self) -> None:
        element = _image_element(image_content=None)
        with pytest.raises(ValueError, match="sem imageContent"):
            build_image_node(element, resolver=_resolver(), box=LayoutBox(*CANVAS))

    def test_percent_dimensions_become_logical_pixels(self) -> None:
        element = _image_element(
            layout=LayoutSpec(
                x=DimensionValue.percent(25.0),
                y=DimensionValue.percent(10.0),
                width=DimensionValue.percent(50.0),
                height=DimensionValue.percent(25.0),
            )
        )
        node = build_image_node(element, resolver=_resolver(), box=LayoutBox(*CANVAS))
        assert node.geometry.x == round(CANVAS[0] * 0.25, 4)
        assert node.geometry.y == round(CANVAS[1] * 0.10, 4)
        assert node.geometry.width == round(CANVAS[0] * 0.50, 4)
        assert node.geometry.height == round(CANVAS[1] * 0.25, 4)

    def test_auto_dimensions_stay_implicit(self) -> None:
        element = _image_element(
            layout=LayoutSpec(
                width=DimensionValue.auto(),
                height=DimensionValue.auto(),
            )
        )
        node = build_image_node(element, resolver=_resolver(), box=LayoutBox(*CANVAS))
        assert node.geometry.width is None
        assert node.geometry.height is None

    def test_visibility_and_opacity_are_resolved(self) -> None:
        node = build_image_node(
            _image_element(visible=False, opacity=0.5),
            resolver=_resolver(),
            box=LayoutBox(*CANVAS),
        )
        assert node.visible is False
        assert node.opacity == 0.5


class TestAdapter:
    def test_a_valid_source_reaches_the_qml_model(self) -> None:
        node = build_image_node(_image_element(), resolver=_resolver(), box=LayoutBox(*CANVAS))
        result = to_image_render_model(node)
        assert result.status is AdaptationStatus.SUCCESS
        model = result.require_model()
        assert model.source == "assets/cover.png"
        assert model.x == 64.0
        assert model.y == 48.0
        assert model.width == 320.0
        assert model.height == 180.0
        assert model.fill_mode == "PreserveAspectCrop"

    @pytest.mark.parametrize(
        ("mode", "expected"),
        [
            (ImageFillMode.CROP, "PreserveAspectCrop"),
            (ImageFillMode.STRETCH, "Stretch"),
            (ImageFillMode.FIT, "PreserveAspectFit"),
            (ImageFillMode.ORIGINAL, "Original"),
        ],
    )
    def test_fill_modes_are_translated(self, mode: ImageFillMode, expected: str) -> None:
        from dataclasses import replace

        node = replace(
            build_image_node(_image_element(), resolver=_resolver(), box=LayoutBox(*CANVAS)),
            fill_mode=mode,
        )
        result = to_image_render_model(node)
        assert result.require_model().fill_mode == expected

    @pytest.mark.parametrize(
        "bad",
        [
            "/etc/passwd",
            "/home/user/capa.png",
            "assets/../escapes.png",
            "http://host/capa.png",
            "",
        ],
    )
    def test_a_host_path_is_refused(self, bad: str) -> None:
        from dataclasses import replace

        node = replace(
            build_image_node(_image_element(), resolver=_resolver(), box=LayoutBox(*CANVAS)),
            source=bad,
        )
        result = to_image_render_model(node)
        assert result.status is AdaptationStatus.FAILED
        assert result.model is None
        assert any(item.code == DIAG_INVALID_MEDIA for item in result.diagnostics)

    def test_a_pending_value_cannot_cross_the_adapter(self) -> None:
        node = ResolvedImageNode(id="cover", source={"asset": "assets/cover.png"})  # type: ignore[arg-type]
        result = to_image_render_model(node)
        assert result.status is AdaptationStatus.FAILED
        assert any(item.code == DIAG_PENDING_VALUE for item in result.diagnostics)

    def test_a_negative_dimension_fails(self) -> None:
        from dataclasses import replace

        from steamzero.domain.resolved_node import ResolvedGeometry

        node = replace(
            build_image_node(_image_element(), resolver=_resolver(), box=LayoutBox(*CANVAS)),
            geometry=ResolvedGeometry(x=0.0, y=0.0, width=-1.0, height=180.0),
        )
        result = to_image_render_model(node)
        assert result.status is AdaptationStatus.FAILED
        assert result.model is None

    def test_opacity_out_of_range_is_a_declared_clamp(self) -> None:
        from dataclasses import replace

        node = replace(
            build_image_node(_image_element(), resolver=_resolver(), box=LayoutBox(*CANVAS)),
            opacity=1.5,
        )
        result = to_image_render_model(node)
        assert result.status is AdaptationStatus.DEGRADED
        assert result.require_model().opacity == 1.0


class TestRoundTrip:
    def test_the_node_round_trips_through_serialization(self) -> None:
        node = build_image_node(_image_element(), resolver=_resolver(), box=LayoutBox(*CANVAS))
        payload = json.loads(json.dumps(node.to_dict(), ensure_ascii=False))
        restored = ResolvedImageNode.from_dict(payload)
        assert restored == node
        assert restored.fill_mode is ImageFillMode.CROP

    def test_the_qml_model_round_trips_to_a_plain_dict(self) -> None:
        node = build_image_node(_image_element(), resolver=_resolver(), box=LayoutBox(*CANVAS))
        payload = to_image_render_model(node).require_model().to_dict()
        assert payload["source"] == "assets/cover.png"
        assert payload["fillMode"] == "PreserveAspectCrop"
        assert payload["width"] == 320.0
