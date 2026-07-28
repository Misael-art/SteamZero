# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""VS-02 — o adapter traduz, e recusa o que não sabe traduzir.

O teste mais importante aqui não é nenhum mapeamento individual: é
``test_every_enum_member_has_a_mapping``. Um membro novo em ``FontStyle`` sem
entrada na tabela do adapter só apareceria em produção, como texto sem itálico,
e ninguém ligaria o sintoma à causa. O teste transforma isso em falha de build.
"""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from steamzero.domain.qml_render_model import (
    DIAG_FONT_UNAVAILABLE,
    DIAG_INVALID_COLOR,
    DIAG_INVALID_HANDLE,
    DIAG_OUT_OF_RANGE,
    DIAG_UNKNOWN_ENUM,
    QmlTextRenderModel,
    to_render_model,
)
from steamzero.domain.resolved_node import (
    FontAssetHandle,
    FontOrigin,
    FontStyle,
    FontWeight,
    ResolvedGeometry,
    ResolvedTextNode,
    TextAlignment,
    TextVerticalAlignment,
)

_ADAPTER = (
    Path(__file__).resolve().parents[2] / "src" / "steamzero" / "domain" / "qml_render_model.py"
)
_COMPONENT = (
    Path(__file__).resolve().parents[2] / "src" / "steamzero" / "ui" / "qml" / "SceneText.qml"
)


def _node(**overrides: object) -> ResolvedTextNode:
    base = ResolvedTextNode(
        id="gameTitle",
        text="Chrono Trigger",
        geometry=ResolvedGeometry(x=960.0, y=120.0, width=1536.0, height=64.0),
        color="#F2F6FB",
        font_family="Gilroy",
        font_asset=FontAssetHandle(
            key="Gilroy",
            handle="asset://font/Gilroy",
            origin=FontOrigin.PACKAGED,
            requested_family="Gilroy",
            resolved_family="Gilroy",
        ),
        font_size=48.0,
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


def _codes(model: QmlTextRenderModel) -> list[str]:
    return [item.code for item in model.diagnostics]


class TestAlignmentMapping:
    @pytest.mark.parametrize(
        ("canonical", "expected"),
        [
            (TextAlignment.START, "AlignLeft"),
            (TextAlignment.CENTER, "AlignHCenter"),
            (TextAlignment.END, "AlignRight"),
            (TextAlignment.JUSTIFY, "AlignJustify"),
        ],
    )
    def test_horizontal(self, canonical: TextAlignment, expected: str) -> None:
        model = to_render_model(_node(horizontal_alignment=canonical))
        assert model.horizontal_alignment == expected
        assert model.ok

    @pytest.mark.parametrize(
        ("canonical", "expected"),
        [
            (TextVerticalAlignment.TOP, "AlignTop"),
            (TextVerticalAlignment.MIDDLE, "AlignVCenter"),
            (TextVerticalAlignment.BOTTOM, "AlignBottom"),
        ],
    )
    def test_vertical(self, canonical: TextVerticalAlignment, expected: str) -> None:
        model = to_render_model(_node(vertical_alignment=canonical))
        assert model.vertical_alignment == expected
        assert model.ok


class TestFontMapping:
    @pytest.mark.parametrize(
        ("canonical", "expected"),
        [
            (FontWeight.NORMAL, 400),
            (FontWeight.MEDIUM, 500),
            (FontWeight.SEMI_BOLD, 600),
            (FontWeight.BOLD, 700),
        ],
    )
    def test_weight(self, canonical: FontWeight, expected: int) -> None:
        model = to_render_model(_node(font_weight=canonical))
        assert model.font_weight == expected
        assert model.ok

    @pytest.mark.parametrize(
        ("canonical", "expected"),
        [(FontStyle.NORMAL, False), (FontStyle.ITALIC, True)],
    )
    def test_style(self, canonical: FontStyle, expected: bool) -> None:
        model = to_render_model(_node(font_style=canonical))
        assert model.font_italic is expected
        assert model.ok

    def test_oblique_is_approximated_to_italic(self) -> None:
        """`font.italic` é booleano no QML e não distingue os dois.

        A aproximação é aceita porque itálico sintético é mais próximo do pedido
        do que texto reto — mas está registrada no módulo, não escondida.
        """
        assert to_render_model(_node(font_style=FontStyle.OBLIQUE)).font_italic is True


class TestFontOriginIsCarriedThrough:
    def test_packaged_produces_the_authorized_reference(self) -> None:
        model = to_render_model(_node())
        assert model.font_source == "asset://font/Gilroy"
        assert model.font_family == "Gilroy"
        assert model.ok

    def test_fallback_declared_renders_the_family_that_was_resolved(self) -> None:
        """A família RENDERIZADA é a resolvida, não a solicitada.

        Emitir "Gilroy" aqui faria o Qt procurar uma fonte que o pacote não tem e
        escolher sozinho um substituto — decisão que pertence ao shell.
        """
        model = to_render_model(
            _node(
                font_family="Inter",
                font_asset=FontAssetHandle(
                    key="Gilroy",
                    handle="asset://font/Inter",
                    origin=FontOrigin.FALLBACK_DECLARED,
                    requested_family="Gilroy",
                    resolved_family="Inter",
                    fallback_reason="fonte 'Gilroy' não está no pacote",
                ),
            )
        )
        assert model.font_family == "Inter"
        assert model.font_source == "asset://font/Inter"
        assert model.ok

    def test_fallback_system_is_not_an_adapter_defect(self) -> None:
        model = to_render_model(
            _node(
                font_family="sans-serif",
                font_asset=FontAssetHandle(
                    key="Gilroy",
                    handle="asset://font/sans-serif",
                    origin=FontOrigin.FALLBACK_SYSTEM,
                    requested_family="Gilroy",
                    resolved_family="sans-serif",
                ),
            )
        )
        assert model.font_family == "sans-serif"
        assert model.ok, "fallback do sistema é decisão do shell, já registrada lá"

    def test_unavailable_produces_no_reference_and_a_diagnostic(self) -> None:
        model = to_render_model(
            _node(
                font_family=None,
                font_asset=FontAssetHandle(
                    key="Gilroy",
                    handle="asset://font/Gilroy",
                    origin=FontOrigin.UNAVAILABLE,
                    fallback_reason="pacote não declara a fonte",
                ),
            )
        )
        assert model.font_source == ""
        assert DIAG_FONT_UNAVAILABLE in _codes(model)

    def test_absent_handle_is_not_a_defect(self) -> None:
        """Texto sem fonte declarada usa a do sistema. Isso é legítimo."""
        model = to_render_model(_node(font_asset=None))
        assert model.font_source == ""
        assert model.ok


class TestRefusalInsteadOfSilentDefault:
    def test_unknown_enum_is_refused(self) -> None:
        """Simula o adapter mais velho que o DTO.

        O construtor tipado não deixa isto acontecer por engano, mas um nó
        desserializado por um caminho futuro deixaria — e é justamente aí que
        escolher `AlignLeft` em silêncio produziria uma tela plausível e errada.
        """
        node = _node()
        object.__setattr__(node, "horizontal_alignment", "diagonal")
        model = to_render_model(node)
        assert DIAG_UNKNOWN_ENUM in _codes(model)
        assert not model.ok
        assert model.horizontal_alignment == "AlignLeft", (
            "o default mantém a tradução seguindo, mas não vale sem o diagnóstico"
        )

    def test_unknown_font_style_is_refused(self) -> None:
        node = _node()
        object.__setattr__(node, "font_style", "cursive")
        assert DIAG_UNKNOWN_ENUM in _codes(to_render_model(node))

    def test_invalid_asset_handle_is_refused(self) -> None:
        """Um nó vindo de disco pode trazer handle que a gramática recusa.

        A validação é REFEITA aqui em vez de assumida do DTO — o adapter não
        sabe por qual caminho o nó chegou até ele.
        """
        handle = FontAssetHandle(key="Gilroy", handle="asset://font/Gilroy")
        object.__setattr__(handle, "handle", "/home/misael/.fonts/Gilroy.ttf")
        model = to_render_model(_node(font_asset=handle))
        assert DIAG_INVALID_HANDLE in _codes(model)
        assert model.font_source == "", "caminho do host nunca vira referência"

    def test_handle_in_the_wrong_namespace_is_refused(self) -> None:
        handle = FontAssetHandle(
            key="Gilroy", handle="asset://video/Gilroy", origin=FontOrigin.PACKAGED
        )
        model = to_render_model(_node(font_asset=handle))
        assert DIAG_INVALID_HANDLE in _codes(model)
        assert model.font_source == ""

    @pytest.mark.parametrize("bad", ["red", "rgba(212,84,84,0.08)", "#fff", "", "#12345"])
    def test_invalid_color_becomes_transparent_not_black(self, bad: str) -> None:
        """Preto é uma cor plausível; preto transparente some.

        Substituir por preto faria a tela parecer correta enquanto estivesse
        errada. `rgba()` está na lista porque o QML já o recusou de verdade, com
        "Invalid property assignment".
        """
        model = to_render_model(_node(color=bad))
        assert model.color == "#00000000"
        assert DIAG_INVALID_COLOR in _codes(model)

    @pytest.mark.parametrize("good", ["#F2F6FB", "#80112233"])
    def test_valid_color_is_normalized(self, good: str) -> None:
        model = to_render_model(_node(color=good))
        assert model.color == good.lower()
        assert model.ok


class TestNumericLimits:
    @pytest.mark.parametrize("limit", [0.0, 1.0])
    def test_opacity_at_the_limits_is_valid(self, limit: float) -> None:
        model = to_render_model(_node(opacity=limit))
        assert model.opacity == limit
        assert model.ok

    @pytest.mark.parametrize(("raw", "expected"), [(-0.5, 0.0), (1.5, 1.0)])
    def test_opacity_outside_the_range_is_clamped_with_a_diagnostic(
        self, raw: float, expected: float
    ) -> None:
        model = to_render_model(_node(opacity=raw))
        assert model.opacity == expected
        assert DIAG_OUT_OF_RANGE in _codes(model)

    def test_automatic_dimension_stays_none(self) -> None:
        """`None` é dimensão implícita. Virar 0.0 apagaria o elemento."""
        model = to_render_model(_node(geometry=ResolvedGeometry(x=10.0, y=20.0)))
        assert model.width is None
        assert model.height is None
        assert model.ok
        assert "width" not in model.to_dict(), "ausente no payload, não zero"

    def test_explicit_zero_is_not_automatic(self) -> None:
        model = to_render_model(
            _node(geometry=ResolvedGeometry(x=0.0, y=0.0, width=0.0, height=0.0))
        )
        assert model.width == 0.0
        assert model.to_dict()["width"] == 0.0

    def test_negative_dimension_is_refused(self) -> None:
        model = to_render_model(_node(geometry=ResolvedGeometry(width=-10.0)))
        assert model.width == 0.0
        assert DIAG_OUT_OF_RANGE in _codes(model)


class TestTablesStayComplete:
    """O teste que impede o adapter de envelhecer em silêncio."""

    @pytest.mark.parametrize(
        ("enum_type", "field_name"),
        [
            (TextAlignment, "horizontal_alignment"),
            (TextVerticalAlignment, "vertical_alignment"),
            (FontWeight, "font_weight"),
            (FontStyle, "font_style"),
        ],
    )
    def test_every_enum_member_has_a_mapping(self, enum_type: type, field_name: str) -> None:
        for member in enum_type:
            model = to_render_model(_node(**{field_name: member}))
            assert DIAG_UNKNOWN_ENUM not in _codes(model), (
                f"{enum_type.__name__}.{member.name} não tem tradução no adapter"
            )


class TestAdapterIsATranslator:
    def test_it_is_deterministic(self) -> None:
        node = _node()
        assert to_render_model(node).to_dict() == to_render_model(node).to_dict()

    def test_it_does_not_modify_the_node(self) -> None:
        node = _node()
        before = node.to_dict()
        to_render_model(node)
        assert node.to_dict() == before

    def test_it_imports_nothing_from_qt(self) -> None:
        """Independente da escolha futura entre PySide6 e Qt nativo."""
        tree = ast.parse(_ADAPTER.read_text(encoding="utf-8"))
        imported = {
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        } | {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        forbidden = {
            name for name in imported if name.split(".")[0] in {"PySide6", "PyQt5", "PyQt6"}
        }
        assert not forbidden, f"o adapter importou Qt: {sorted(forbidden)}"

    def test_it_does_not_reach_for_registries_or_the_resolver(self) -> None:
        """Traduzir é uma função do argumento. Consultar estado não é traduzir."""
        source = _ADAPTER.read_text(encoding="utf-8")
        for forbidden in ("scene_registry", "scene_resolver", "Registries", "Resolver"):
            assert forbidden not in source, f"o adapter alcançou {forbidden}"


class TestComponentIsDeliberatelySimple:
    """O QML só atribui. Regra que não sobrevive sem alguém verificando."""

    #: Exatamente o que o usuário autorizou o componente a tocar.
    ALLOWED = frozenset(
        {
            "objectName",
            "text",
            "x",
            "y",
            "width",
            "height",
            "visible",
            "opacity",
            "color",
            "font.family",
            "font.pixelSize",
            "font.weight",
            "font.italic",
            "horizontalAlignment",
            "verticalAlignment",
            "id",
        }
    )

    def _assignments(self) -> set[str]:
        found: set[str] = set()
        for line in _COMPONENT.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("//") or ":" not in stripped:
                continue
            name = stripped.split(":", 1)[0].strip()
            if name.startswith("required property") or name.startswith("property"):
                continue
            if all(part.isidentifier() for part in name.split(".")):
                found.add(name)
        return found

    def test_it_assigns_only_authorized_properties(self) -> None:
        extra = self._assignments() - self.ALLOWED
        assert not extra, f"propriedade não autorizada em SceneText.qml: {sorted(extra)}"

    def test_it_holds_no_logic(self) -> None:
        """Sem função, sem fallback de fonte, sem acesso ao read model.

        Cada um destes existiria como uma segunda implementação das regras do
        resolver — e o dia em que divergisse, o diagnóstico apontaria para o
        lugar errado.
        """
        source = _COMPONENT.read_text(encoding="utf-8")
        code = "\n".join(line for line in source.splitlines() if not line.strip().startswith("//"))
        for forbidden in ("function ", "Component.onCompleted", "readModel", "Qt.font", "console."):
            assert forbidden not in code, f"lógica em SceneText.qml: {forbidden!r}"

    def test_it_imports_only_qtquick(self) -> None:
        imports = [
            line.strip()
            for line in _COMPONENT.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("import ")
        ]
        assert imports == ["import QtQuick"], imports
