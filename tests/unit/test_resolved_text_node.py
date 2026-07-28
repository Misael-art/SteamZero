# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""VS-01 — ResolvedTextNode e a fronteira do renderizador.

O DTO carrega SOMENTE valores finais e nenhum tipo do Qt. A razão não é purismo:
se o QML pudesse consultar registries, implementaria suas próprias regras de
fallback, e um dia elas divergiriam das do resolver. O mesmo tema renderizaria
diferente conforme o backend, e o diagnóstico apontaria para a regra errada.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from steamzero.domain import scene_value as value
from steamzero.domain.resolved_node import (
    FONT_WEIGHT_SCALE,
    FontAssetHandle,
    FontOrigin,
    FontStyle,
    FontWeight,
    ResolvedGeometry,
    ResolvedTextNode,
    TextAlignment,
    TextVerticalAlignment,
)
from steamzero.domain.scene_contract import (
    Alignment,
    DimensionValue,
    ElementContract,
    LayoutSpec,
    TextLayoutSpec,
    TypographySpec,
)
from steamzero.domain.scene_registry import default_registries
from steamzero.domain.scene_resolver import ResolutionContext, Resolver
from steamzero.domain.scene_typing import SourceReference
from steamzero.domain.text_node_builder import FontProvider, LayoutBox, build_text_node

_MODULE = Path(__file__).resolve().parents[2] / "src" / "steamzero" / "domain" / "resolved_node.py"


def _resolver(**overrides: object) -> Resolver:
    base: dict[str, object] = {
        "registries": default_registries(),
        "tokens": {"color.text.primary": "#f2f6fb"},
        "read_model": {"game.title": "Chrono Trigger", "game.favorite": True},
    }
    base.update(overrides)
    return Resolver(ResolutionContext(**base))  # type: ignore[arg-type]


def _element(**overrides: object) -> ElementContract:
    base: dict[str, object] = {
        "id": "gameTitle",
        "type": "text",
        "source_reference": SourceReference("layouts/arcade.xml", line=183, element="gameTitle"),
        "text_content": value.bind("game.title"),
        "layout": LayoutSpec(x=DimensionValue.percent(50), y=DimensionValue.px(120)),
        "typography": TypographySpec(
            font_family="Gilroy", font_size=48, color=value.token("color.text.primary")
        ),
        "text_layout": TextLayoutSpec(horizontal_alignment=Alignment.CENTER),
    }
    base.update(overrides)
    return ElementContract(**base)  # type: ignore[arg-type]


def _build(**overrides: object) -> ResolvedTextNode:
    return build_text_node(
        _element(**overrides),
        resolver=_resolver(),
        box=LayoutBox(1920, 1080),
        fonts=FontProvider({"Gilroy": "Gilroy"}),
    )


class TestNoQtLeaksIntoTheContract:
    """Se um tipo do Qt entrar aqui, o IR deixa de ser neutro de backend."""

    def test_module_imports_nothing_from_qt(self) -> None:
        tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
        modules: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules.append(node.module or "")
        assert not [name for name in modules if "PySide" in name or name.startswith("Qt")]

    def test_no_qt_identifier_is_used_in_code(self) -> None:
        """Comentários podem citar QColor para explicar; o código não pode usá-lo."""
        tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        suspicious = {
            name
            for name in names | attributes
            if len(name) > 2 and name.startswith("Q") and name[1].isupper()
        }
        assert suspicious == set()

    def test_alignment_enum_is_our_own(self) -> None:
        assert {item.value for item in TextAlignment} == {"start", "center", "end", "justify"}


class TestOnlyFinalValues:
    def test_binding_is_materialized(self) -> None:
        assert _build().text == "Chrono Trigger"

    def test_token_is_materialized(self) -> None:
        assert _build().color == "#f2f6fb"

    def test_conditional_is_materialized(self) -> None:
        node = build_text_node(
            _element(
                typography=TypographySpec(
                    color=value.when(
                        value.compare("equals", value.bind("game.favorite"), True),
                        "#ffd700",
                        "#ffffff",
                    )
                )
            ),
            resolver=_resolver(),
            box=LayoutBox(1920, 1080),
        )
        assert node.color == "#ffd700"

    def test_no_pending_value_survives_serialization(self) -> None:
        """Um dicionário com 'bind' no payload significaria valor não resolvido."""
        payload = json.dumps(_build().to_dict())
        for marker in ('"bind"', '"token"', '"setting"', '"when"'):
            assert marker not in payload

    def test_percentage_is_resolved_against_the_box(self) -> None:
        """O renderizador não conhece a caixa do pai, e não deveria."""
        assert _build().geometry.x == 960.0

    def test_auto_width_becomes_none_not_zero(self) -> None:
        """None significa 'dimensione pelo conteúdo'; zero seria caixa sem tamanho."""
        node = _build(layout=LayoutSpec(width=DimensionValue.auto()))
        assert node.geometry.width is None


class TestFontHandleIsSafe:
    def test_packaged_font_is_marked(self) -> None:
        handle = _build().font_asset
        assert handle is not None
        assert handle.origin is FontOrigin.PACKAGED
        assert handle.fallback_applied is False

    def test_missing_font_falls_back_with_a_reason(self) -> None:
        node = build_text_node(
            _element(typography=TypographySpec(font_family="FonteInexistente")),
            resolver=_resolver(),
            box=LayoutBox(1920, 1080),
            fonts=FontProvider({"Gilroy": "Gilroy"}),
        )
        handle = node.font_asset
        assert handle is not None
        assert handle.origin is FontOrigin.FALLBACK_SYSTEM
        assert handle.requested_family == "FonteInexistente"
        assert handle.resolved_family != "FonteInexistente"
        assert handle.fallback_reason

    def test_declared_fallback_wins_over_the_system(self) -> None:
        """É o que o autor escreveu que quer quando a primeira falha."""
        node = build_text_node(
            _element(typography=TypographySpec(font_family="Ausente", font_fallback=("Gilroy",))),
            resolver=_resolver(),
            box=LayoutBox(1920, 1080),
            fonts=FontProvider({"Gilroy": "Gilroy"}),
        )
        handle = node.font_asset
        assert handle is not None
        assert handle.origin is FontOrigin.FALLBACK_DECLARED
        assert handle.resolved_family == "Gilroy"

    def test_handle_never_contains_a_host_path(self) -> None:
        payload = json.dumps(_build().to_dict())
        for marker in ("/home/", "C:\\", "..", ".ttf", ".otf"):
            assert marker not in payload

    def test_resolved_family_is_assertable(self) -> None:
        """O teste precisa afirmar a família RENDERIZADA, não aceitar a do sistema."""
        node = build_text_node(
            _element(typography=TypographySpec(font_family="Ausente")),
            resolver=_resolver(),
            box=LayoutBox(1920, 1080),
            fonts=FontProvider({}, system_family="TestSans"),
        )
        assert node.font_asset is not None
        assert node.font_asset.resolved_family == "TestSans"


class TestDeterministicSerialization:
    def test_same_input_produces_identical_payload(self) -> None:
        assert json.dumps(_build().to_dict()) == json.dumps(_build().to_dict())

    def test_round_trip_preserves_every_field(self) -> None:
        original = _build()
        restored = ResolvedTextNode.from_dict(original.to_dict())
        assert restored == original

    def test_round_trip_survives_diagnostics(self) -> None:
        node = ResolvedTextNode(
            id="a",
            resolution_diagnostics=({"code": "X-1", "message": "m", "property": "a.color"},),
        )
        assert ResolvedTextNode.from_dict(node.to_dict()) == node

    def test_nodes_compare_by_value(self) -> None:
        assert _build() == _build()

    def test_font_weight_scale_covers_every_name(self) -> None:
        assert set(FONT_WEIGHT_SCALE) == set(FontWeight)


class TestProvenanceTravelsWithoutLiveReferences:
    def test_source_reference_survives(self) -> None:
        assert _build().source_reference is not None
        assert _build().to_dict()["sourceReference"]["line"] == 183

    def test_diagnostics_are_plain_data(self) -> None:
        """Sem referência viva a registry: o DTO precisa sobreviver à serialização."""
        node = ResolvedTextNode(id="a", resolution_diagnostics=({"code": "X-1", "message": "m"},))
        assert all(isinstance(entry, dict) for entry in node.resolution_diagnostics)
        json.dumps(node.to_dict())

    def test_incompatible_condition_diagnostic_reaches_the_node(self) -> None:
        node = build_text_node(
            _element(
                typography=TypographySpec(
                    color=value.when(
                        value.compare("greaterThan", value.bind("game.title"), 1990),
                        "#ff0000",
                        "#00ff00",
                    )
                )
            ),
            resolver=_resolver(),
            box=LayoutBox(1920, 1080),
        )
        assert node.resolution_diagnostics
        assert node.color != "#00ff00"


class TestDefaults:
    def test_defaults_are_explicit(self) -> None:
        node = ResolvedTextNode(id="a")
        assert node.visible is True
        assert node.opacity == 1.0
        assert node.font_weight is FontWeight.NORMAL
        assert node.font_style is FontStyle.NORMAL
        assert node.horizontal_alignment is TextAlignment.START
        assert node.vertical_alignment is TextVerticalAlignment.TOP

    @pytest.mark.parametrize(
        ("alignment", "expected"),
        [
            (Alignment.START, TextAlignment.START),
            (Alignment.CENTER, TextAlignment.CENTER),
            (Alignment.END, TextAlignment.END),
        ],
    )
    def test_alignment_is_mapped(self, alignment: Alignment, expected: TextAlignment) -> None:
        node = _build(text_layout=TextLayoutSpec(horizontal_alignment=alignment))
        assert node.horizontal_alignment is expected

    def test_geometry_defaults_to_origin(self) -> None:
        assert ResolvedGeometry().to_dict() == {"x": 0.0, "y": 0.0}

    def test_unavailable_font_reports_unavailable(self) -> None:
        assert FontAssetHandle(key="x").available is False
