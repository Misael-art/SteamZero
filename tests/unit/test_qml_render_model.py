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
    DIAG_APPROXIMATED,
    DIAG_FONT_FALLBACK,
    DIAG_FONT_UNAVAILABLE,
    DIAG_INVALID_COLOR,
    DIAG_INVALID_HANDLE,
    DIAG_OUT_OF_RANGE,
    DIAG_PENDING_VALUE,
    DIAG_UNKNOWN_ENUM,
    AdaptationError,
    AdaptationResult,
    AdaptationStatus,
    AdapterDiagnostic,
    QmlTextRenderModel,
    Severity,
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


def _codes(result: AdaptationResult[QmlTextRenderModel]) -> list[str]:
    return [item.code for item in result.diagnostics]


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
        result = to_render_model(_node(horizontal_alignment=canonical))
        assert result.require_model().horizontal_alignment == expected
        assert result.status is AdaptationStatus.SUCCESS

    @pytest.mark.parametrize(
        ("canonical", "expected"),
        [
            (TextVerticalAlignment.TOP, "AlignTop"),
            (TextVerticalAlignment.MIDDLE, "AlignVCenter"),
            (TextVerticalAlignment.BOTTOM, "AlignBottom"),
        ],
    )
    def test_vertical(self, canonical: TextVerticalAlignment, expected: str) -> None:
        result = to_render_model(_node(vertical_alignment=canonical))
        assert result.require_model().vertical_alignment == expected
        assert result.status is AdaptationStatus.SUCCESS


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
        result = to_render_model(_node(font_weight=canonical))
        assert result.require_model().font_weight == expected
        assert result.status is AdaptationStatus.SUCCESS

    @pytest.mark.parametrize(
        ("canonical", "expected"),
        [(FontStyle.NORMAL, False), (FontStyle.ITALIC, True)],
    )
    def test_style(self, canonical: FontStyle, expected: bool) -> None:
        result = to_render_model(_node(font_style=canonical))
        assert result.require_model().font_italic is expected
        assert result.status is AdaptationStatus.SUCCESS

    def test_oblique_is_degraded_not_silently_italic(self) -> None:
        """`font.italic` é booleano no QML e não distingue os dois.

        Itálico sintético é mais próximo do pedido do que texto reto, então o
        modelo sai — mas como `degraded`, porque o tema não recebeu o que pediu.
        """
        result = to_render_model(_node(font_style=FontStyle.OBLIQUE))
        assert result.status is AdaptationStatus.DEGRADED
        assert result.require_model().font_italic is True
        assert DIAG_APPROXIMATED in _codes(result)


class TestFontOriginIsCarriedThrough:
    def test_packaged_produces_the_authorized_reference(self) -> None:
        result = to_render_model(_node())
        assert result.status is AdaptationStatus.SUCCESS
        model = result.require_model()
        assert model.font_source == "asset://font/Gilroy"
        assert model.font_family == "Gilroy"

    def test_fallback_declared_renders_the_family_that_was_resolved(self) -> None:
        """A família RENDERIZADA é a resolvida, não a solicitada.

        Emitir "Gilroy" aqui faria o Qt procurar uma fonte que o pacote não tem e
        escolher sozinho um substituto — decisão que pertence ao shell.
        """
        result = to_render_model(
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
        assert result.status is AdaptationStatus.DEGRADED, (
            "substituição de fonte é fallback explícito, não sucesso"
        )
        model = result.require_model()
        assert model.font_family == "Inter"
        assert model.font_source == "asset://font/Inter"
        assert DIAG_FONT_FALLBACK in _codes(result)

    def test_fallback_system_is_degraded_not_failed(self) -> None:
        """O shell resolveu — só não com o que o tema pediu.

        Reprovar aqui derrubaria a tela por um fallback legítimo; aprovar como
        sucesso esconderia que o pacote do tema está incompleto.
        """
        result = to_render_model(
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
        assert result.status is AdaptationStatus.DEGRADED
        assert result.require_model().font_family == "sans-serif"
        assert DIAG_FONT_FALLBACK in _codes(result)

    def test_unavailable_produces_no_model(self) -> None:
        """Fonte indisponível não rende tela.

        Renderizar com a fonte do sistema em silêncio esconderia que o pacote do
        tema está quebrado, e o texto sairia com métrica errada sem explicação.
        """
        result = to_render_model(
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
        assert result.status is AdaptationStatus.FAILED
        assert result.model is None
        assert DIAG_FONT_UNAVAILABLE in _codes(result)

    def test_absent_handle_is_not_a_defect(self) -> None:
        """Texto sem fonte declarada usa a do sistema. Isso é legítimo."""
        result = to_render_model(_node(font_asset=None))
        assert result.status is AdaptationStatus.SUCCESS
        assert result.require_model().font_source == ""


class TestFailureCarriesNoModel:
    """O ponto do VS-02 revisado: não há payload parcial para entregar ao QML."""

    def test_unknown_enum_produces_no_model(self) -> None:
        """Simula o adapter mais velho que o DTO.

        `AlignLeft` em silêncio produziria uma tela plausível e errada, e
        ninguém investiga o que parece certo.
        """
        node = _node()
        object.__setattr__(node, "horizontal_alignment", "diagonal")
        result = to_render_model(node)
        assert result.status is AdaptationStatus.FAILED
        assert result.model is None
        assert DIAG_UNKNOWN_ENUM in _codes(result)

    def test_unknown_font_style_produces_no_model(self) -> None:
        node = _node()
        object.__setattr__(node, "font_style", "cursive")
        result = to_render_model(node)
        assert result.model is None
        assert DIAG_UNKNOWN_ENUM in _codes(result)

    def test_invalid_asset_handle_produces_no_model(self) -> None:
        """Um nó vindo de disco pode trazer handle que a gramática recusa.

        A validação é REFEITA aqui em vez de assumida do DTO — o adapter não
        sabe por qual caminho o nó chegou até ele.
        """
        handle = FontAssetHandle(
            key="Gilroy", handle="asset://font/Gilroy", origin=FontOrigin.PACKAGED
        )
        object.__setattr__(handle, "handle", "/home/misael/.fonts/Gilroy.ttf")
        result = to_render_model(_node(font_asset=handle))
        assert result.model is None, "caminho do host nunca chega perto do QML"
        assert DIAG_INVALID_HANDLE in _codes(result)

    def test_handle_in_the_wrong_namespace_produces_no_model(self) -> None:
        handle = FontAssetHandle(
            key="Gilroy", handle="asset://video/Gilroy", origin=FontOrigin.PACKAGED
        )
        result = to_render_model(_node(font_asset=handle))
        assert result.model is None
        assert DIAG_INVALID_HANDLE in _codes(result)

    @pytest.mark.parametrize("bad", ["red", "rgba(212,84,84,0.08)", "#fff", "", "#12345"])
    def test_invalid_color_produces_no_model(self, bad: str) -> None:
        """Cor inválida não vira transparente.

        Transparente é um valor que um tema pode ter pedido de propósito. Usá-lo
        como marca de erro tornaria os dois casos indistinguíveis no resultado.
        `rgba()` está na lista porque o QML já o recusou de verdade, com
        "Invalid property assignment".
        """
        result = to_render_model(_node(color=bad))
        assert result.status is AdaptationStatus.FAILED
        assert result.model is None
        assert DIAG_INVALID_COLOR in _codes(result)

    def test_pending_value_never_reaches_the_qml(self) -> None:
        """Última barreira contra um construtor que esqueceu de resolver.

        O QML receberia um dicionário onde espera um escalar e renderizaria
        vazio sem reclamar.
        """
        node = _node()
        object.__setattr__(node, "text", {"bind": "game.title"})
        result = to_render_model(node)
        assert result.status is AdaptationStatus.FAILED
        assert DIAG_PENDING_VALUE in _codes(result)

    def test_require_model_refuses_a_failed_result(self) -> None:
        """Um consumidor não consegue mandar modelo inválido ao QML sem querer."""
        result = to_render_model(_node(color="vermelho"))
        with pytest.raises(AdaptationError, match=DIAG_INVALID_COLOR):
            result.require_model()

    def test_require_model_allows_a_degraded_result(self) -> None:
        """Degradado passa — o consumidor já desempacotou explicitamente.

        A política de apresentação é do shell (VS-04); o adapter só garante que
        ninguém renderize sem ter olhado.
        """
        result = to_render_model(_node(font_style=FontStyle.OBLIQUE))
        assert result.require_model().font_italic is True


class TestResultStatesAreUnmistakable:
    """Estado e conteúdo não podem discordar.

    Um `failed` com modelo, ou um `success` com diagnóstico, seria um convite a
    ler o status errado — e quem lê errado renderiza errado.
    """

    def _diagnostic(self) -> AdapterDiagnostic:
        return AdapterDiagnostic(code="X-1", target="t.color", detail="teste")

    def test_failed_cannot_carry_a_model(self) -> None:
        with pytest.raises(ValueError, match="failed não carrega modelo"):
            AdaptationResult(
                status=AdaptationStatus.FAILED,
                model=to_render_model(_node()).require_model(),
                diagnostics=(self._diagnostic(),),
            )

    def test_failed_requires_a_diagnostic(self) -> None:
        with pytest.raises(ValueError, match="failed exige diagnóstico"):
            AdaptationResult(status=AdaptationStatus.FAILED, model=None)

    def test_success_cannot_carry_a_diagnostic(self) -> None:
        with pytest.raises(ValueError, match="success não carrega diagnóstico"):
            AdaptationResult(
                status=AdaptationStatus.SUCCESS,
                model=to_render_model(_node()).require_model(),
                diagnostics=(self._diagnostic(),),
            )

    def test_degraded_requires_a_diagnostic(self) -> None:
        with pytest.raises(ValueError, match="degraded exige diagnóstico"):
            AdaptationResult(
                status=AdaptationStatus.DEGRADED,
                model=to_render_model(_node()).require_model(),
            )

    def test_a_present_model_is_required_outside_failed(self) -> None:
        with pytest.raises(ValueError, match="exige modelo"):
            AdaptationResult(status=AdaptationStatus.SUCCESS, model=None)

    def test_severity_separates_fatal_from_degraded(self) -> None:
        degraded = to_render_model(_node(font_style=FontStyle.OBLIQUE))
        assert all(item.severity is Severity.DEGRADED for item in degraded.diagnostics)
        failed = to_render_model(_node(color="vermelho"))
        assert any(item.severity is Severity.FATAL for item in failed.diagnostics)


class TestNumericLimits:
    @pytest.mark.parametrize("limit", [0.0, 1.0])
    def test_opacity_at_the_limits_is_valid(self, limit: float) -> None:
        result = to_render_model(_node(opacity=limit))
        assert result.require_model().opacity == limit
        assert result.status is AdaptationStatus.SUCCESS

    @pytest.mark.parametrize(("raw", "expected"), [(-0.5, 0.0), (1.5, 1.0)])
    def test_opacity_outside_the_range_is_degraded_not_failed(
        self, raw: float, expected: float
    ) -> None:
        """Fora da faixa a intenção é inequívoca: 1.5 é opaco, -0.5 é invisível.

        Limitar é substituição declarada, não adivinhação — diferente de cor
        inválida, onde não há como saber o que o autor queria.
        """
        result = to_render_model(_node(opacity=raw))
        assert result.status is AdaptationStatus.DEGRADED
        assert result.require_model().opacity == expected
        assert DIAG_OUT_OF_RANGE in _codes(result)

    def test_automatic_dimension_stays_none(self) -> None:
        """`None` é dimensão implícita. Virar 0.0 apagaria o elemento."""
        result = to_render_model(_node(geometry=ResolvedGeometry(x=10.0, y=20.0)))
        assert result.require_model().width is None
        assert result.require_model().height is None
        assert result.status is AdaptationStatus.SUCCESS
        assert "width" not in result.require_model().to_dict(), "ausente no payload, não zero"

    def test_explicit_zero_is_not_automatic(self) -> None:
        result = to_render_model(
            _node(geometry=ResolvedGeometry(x=0.0, y=0.0, width=0.0, height=0.0))
        )
        assert result.require_model().width == 0.0
        assert result.require_model().to_dict()["width"] == 0.0

    def test_negative_dimension_produces_no_model(self) -> None:
        """Zerar produziria um elemento invisível que parece intencional.

        Largura negativa é defeito de quem produziu o nó, e é lá que precisa
        aparecer — não como uma caixa vazia na tela.
        """
        result = to_render_model(_node(geometry=ResolvedGeometry(width=-10.0)))
        assert result.status is AdaptationStatus.FAILED
        assert result.model is None
        assert DIAG_OUT_OF_RANGE in _codes(result)


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
            result = to_render_model(_node(**{field_name: member}))
            assert DIAG_UNKNOWN_ENUM not in _codes(result), (
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
