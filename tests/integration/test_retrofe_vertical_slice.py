# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""VS-04 — uma declaração real do RetroFE atravessa o pipeline inteiro.

O caminho exercitado, sem atalho em nenhum ponto:

    arquivo RetroFE → declarações com identidade → TranslationLog → Value<T>
    → ElementContract → serialização → desserialização → resolver
    → ResolvedTextNode → adapter → AdaptationResult → require_model()
    → QmlTextRenderModel → harness → SceneText.qml → captura e métricas

O que este módulo NÃO prova: que o renderizador está completo. Não há árvore de
cena, rich text, elide, foco, efeitos nem máscaras. É uma prova vertical
estreita, e a estreiteza é deliberada — uma fatia fina que atravessa tudo diz
mais que uma camada larga que não conecta com nada.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from steamzero.domain.qml_render_model import AdaptationStatus, to_render_model
from steamzero.domain.resolved_node import FontOrigin
from steamzero.domain.retrofe_declarations import (
    OriginKind,
    collect_declarations,
    derived,
)
from steamzero.domain.retrofe_text_slice import SliceResult, TextSliceCompiler
from steamzero.domain.scene_contract import Alignment, DimensionUnit
from steamzero.domain.scene_registry import default_registries
from steamzero.domain.scene_resolver import ResolutionContext, Resolver
from steamzero.domain.scene_typing import SourceReference
from steamzero.domain.scene_value import Verdict
from steamzero.domain.text_node_builder import FontProvider, LayoutBox, build_text_node

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from qml_capture_runner import (  # noqa: E402
    CaptureError,
    assert_not_empty,
    capture,
    write_artifacts,
)

FIXTURES = ROOT / "tests" / "fixtures" / "retrofe"

#: A fonte que o pacote do tema declara. `Gilroy Display` NÃO está aqui de
#: propósito: a fixture positiva pede essa fonte, e o resultado precisa ser um
#: fallback registrado, não um sucesso silencioso.
PACKAGED_FONTS = frozenset({"Liberation Sans"})

PALETTE = {"accent": "#ffd166"}
TRANSLATIONS = frozenset({"menu.play"})

CANVAS = (1920, 1080)
BACKGROUND = "#101418"


def _compile(name: str) -> tuple[Any, SliceResult]:
    path = FIXTURES / f"{name}.xml"
    declarations = collect_declarations(
        path.read_text(encoding="utf-8"), file=f"retrofe/{name}.xml"
    )
    compiler = TextSliceCompiler(
        palette=PALETTE, packaged_fonts=PACKAGED_FONTS, translations=TRANSLATIONS
    )
    return declarations, compiler.compile(declarations)


@pytest.fixture(scope="module")
def positive() -> tuple[Any, SliceResult]:
    return _compile("vs04_positive")


@pytest.fixture(scope="module")
def negative() -> tuple[Any, SliceResult]:
    return _compile("vs04_negative")


def _resolver() -> Resolver:
    return Resolver(
        ResolutionContext(
            registries=default_registries(),
            read_model={"game.title": "Chrono Trigger", "system.time": "21:40"},
            tokens={"color.accent": "#ffd166", "color.text.primary": "#f2f6fb"},
            translations={"menu.play": "Jogar"},
            states=frozenset({"focused"}),
        )
    )


def _by_id(result: SliceResult, suffix: str) -> Any:
    for element in result.elements:
        if element.id == suffix:
            return element
    raise AssertionError(f"elemento {suffix!r} não foi compilado")


class TestSourceIdentity:
    """Cada propriedade declarada tem identidade e lugar no arquivo."""

    def test_every_declaration_carries_its_origin(self, positive: tuple[Any, SliceResult]) -> None:
        declarations, _ = positive
        for item in declarations.declarations:
            assert item.declaration_id
            assert item.source_reference.file.endswith("vs04_positive.xml")
            assert item.source_reference.line and item.source_reference.line > 0

    def test_identifiers_are_unique(self, positive: tuple[Any, SliceResult]) -> None:
        """Ids que colidem fazem um veredito sobrescrever o outro.

        O accounting acusaria duplicata sem conseguir dizer QUAL das duas
        propriedades ficou sem julgamento.
        """
        declarations, _ = positive
        ids = [item.declaration_id for item in declarations.declarations]
        assert len(ids) == len(set(ids))

    def test_the_line_points_at_the_real_declaration(
        self, positive: tuple[Any, SliceResult]
    ) -> None:
        """Diagnóstico sem linha obriga a procurar no arquivo inteiro."""
        declarations, _ = positive
        source = (FIXTURES / "vs04_positive.xml").read_text(encoding="utf-8").splitlines()
        item = next(
            entry for entry in declarations.declarations if entry.raw_value == "Chrono Trigger"
        )
        assert item.source_reference.line is not None
        window = "\n".join(source[item.source_reference.line - 1 : item.source_reference.line + 1])
        assert "Chrono Trigger" in window

    def test_derived_values_do_not_inflate_the_source_count(self) -> None:
        """Default não é declaração.

        Contá-lo faria 100% de cobertura significar "julgamos tudo que
        produzimos" em vez de "traduzimos tudo que o autor escreveu".
        """
        reference = SourceReference(file="retrofe/x.xml", line=1)
        item = derived(
            "retrofe:x.xml:1:text[0].opacity",
            element="text",
            property_name="opacity",
            value="1.0",
            origin_kind=OriginKind.DEFAULT,
            reference=reference,
        )
        assert item.counts_as_source is False

    def test_a_declared_origin_cannot_be_forged_as_derived(self) -> None:
        reference = SourceReference(file="retrofe/x.xml", line=1)
        with pytest.raises(ValueError, match="collect_declarations"):
            derived(
                "x",
                element="text",
                property_name="opacity",
                value="1",
                origin_kind=OriginKind.DECLARED,
                reference=reference,
            )


class TestAccounting:
    """O gate que existe porque 238 `fontColor` sumiram sem ninguém notar."""

    @pytest.mark.parametrize("fixture", ["positive", "negative"])
    def test_every_declaration_gets_exactly_one_verdict(
        self, fixture: str, request: pytest.FixtureRequest
    ) -> None:
        declarations, result = request.getfixturevalue(fixture)
        accounting = result.accounting(declarations)
        assert accounting["unaccounted"] == [], (
            "propriedade declarada sem veredito: some do relatório sem sintoma"
        )
        assert accounting["duplicateVerdicts"] == [], (
            "dois caminhos julgaram a mesma propriedade; o relatório soma mais que o total"
        )
        assert accounting["sourcePropertyCount"] == accounting["translationVerdictCount"]
        assert accounting["accountingCoverage"] == 1.0

    def test_the_count_is_not_trivially_zero(self, positive: tuple[Any, SliceResult]) -> None:
        """Cobertura de 100% sobre zero propriedades aprovaria um arquivo vazio."""
        declarations, result = positive
        assert result.accounting(declarations)["sourcePropertyCount"] > 40


class TestPositiveFixtureProperties:
    def test_a_literal_colour_becomes_a_canonical_colour(
        self, positive: tuple[Any, SliceResult]
    ) -> None:
        element = _by_id(positive[1], "text-1")
        assert element.typography is not None
        assert element.typography.color == "#f2f6fb"

    def test_an_alpha_colour_keeps_its_alpha(self, positive: tuple[Any, SliceResult]) -> None:
        """`F2F6FB80` é meio transparente. Descartar o alfa mudaria a tela."""
        element = _by_id(positive[1], "text-2")
        assert element.typography is not None
        assert element.typography.color == "#f2f6fb80"

    def test_a_palette_reference_becomes_a_token(self, positive: tuple[Any, SliceResult]) -> None:
        """Token, não literal: é o que permite trocar o esquema sem tocar no layout."""
        element = _by_id(positive[1], "text-4")
        assert element.typography is not None
        assert element.typography.color == {"token": "color.accent"}

    def test_the_selected_colour_becomes_a_condition(
        self, positive: tuple[Any, SliceResult]
    ) -> None:
        """Duas cores soltas perderiam o comportamento que o tema descreve."""
        element = _by_id(positive[1], "text-5")
        assert element.typography is not None
        colour = element.typography.color
        assert colour["when"] == {"op": "state", "state": "focused"}
        assert colour["then"] == "#ffd166"
        assert colour["otherwise"] == "#808080"

    def test_a_reloadable_text_becomes_a_binding(self, positive: tuple[Any, SliceResult]) -> None:
        element = _by_id(positive[1], "reloadableText-6")
        assert element.text_content == {"bind": "game.title"}

    def test_a_translation_key_becomes_a_localized_value(
        self, positive: tuple[Any, SliceResult]
    ) -> None:
        element = _by_id(positive[1], "text-7")
        assert element.text_content == {"text": "menu.play", "fallback": "menu.play"}

    @pytest.mark.parametrize(
        ("element_id", "expected"),
        [("text-1", Alignment.START), ("text-2", Alignment.CENTER), ("text-3", Alignment.END)],
    )
    def test_alignment_reaches_the_contract(
        self, positive: tuple[Any, SliceResult], element_id: str, expected: Alignment
    ) -> None:
        element = _by_id(positive[1], element_id)
        assert element.text_layout is not None
        assert element.text_layout.horizontal_alignment is expected

    def test_the_three_dimension_units_survive(self, positive: tuple[Any, SliceResult]) -> None:
        assert _by_id(positive[1], "text-1").layout.x.unit is DimensionUnit.LOGICAL_PX
        assert _by_id(positive[1], "text-2").layout.width.unit is DimensionUnit.PERCENT
        assert _by_id(positive[1], "text-3").layout.width.unit is DimensionUnit.AUTO

    def test_a_font_outside_the_package_is_a_fallback_not_a_success(
        self, positive: tuple[Any, SliceResult]
    ) -> None:
        """O tema pediu `Gilroy Display` e o pacote não tem.

        Marcar como `exact` diria que traduzimos fielmente algo que o usuário
        nunca verá como o autor quis.
        """
        declarations, result = positive
        entry = next(
            item
            for item in result.log.entries
            if item.target == "typography.font_family"
            and declarations.by_id(item.source) is not None
            and declarations.by_id(item.source).raw_value == "Gilroy Display"
        )
        assert entry.verdict is Verdict.FALLBACK
        assert "não está no pacote" in (entry.detail or "")


class TestNegativeFixtureDegradesWithoutCollapsing:
    """Uma cena que morre inteira por uma cor errada é tão ruim quanto uma que
    renderiza a cor errada em silêncio."""

    def test_the_healthy_element_survives_every_defect(
        self, negative: tuple[Any, SliceResult]
    ) -> None:
        element = next(item for item in negative[1].elements if item.text_content == "sobrevivente")
        assert element.typography is not None
        assert element.typography.color == "#f2f6fb"
        assert element.text_layout is not None

    @pytest.mark.parametrize(
        ("raw_value", "prop", "expected"),
        [
            ("vermelho", "fontColor", Verdict.INVALID),
            ("diagonal", "alignment", Verdict.INVALID),
            ("12em", "x", Verdict.INVALID),
            ("nan", "x", Verdict.INVALID),
            ("inf", "x", Verdict.INVALID),
            ("true", "x", Verdict.INVALID),
            ("-12", "fontSize", Verdict.INVALID),
            ("creditosDoJogador", "type", Verdict.UNSUPPORTED),
            ("hostSerial", "type", Verdict.IGNORED_BY_POLICY),
            ("3", "layer", Verdict.UNSUPPORTED),
            # O literal "nan" como TEXTO é válido. O mesmo texto como dimensão
            # não é — e a diferença precisa aparecer no veredito.
            ("nan", "value", Verdict.EXACT),
        ],
    )
    def test_each_defect_gets_the_right_verdict(
        self, negative: tuple[Any, SliceResult], raw_value: str, prop: str, expected: Verdict
    ) -> None:
        declarations, result = negative
        # Filtra por propriedade também: `value="nan"` e `x="nan"` coexistem na
        # fixture, e o texto literal "nan" é EXATO enquanto a dimensão é
        # inválida. Selecionar só pelo valor cru testaria a declaração errada.
        item = next(
            entry
            for entry in declarations.declarations
            if entry.raw_value == raw_value and entry.property_name == prop
        )
        assert result.verdicts[item.declaration_id] is expected

    def test_policy_refusal_is_distinct_from_our_limitation(
        self, negative: tuple[Any, SliceResult]
    ) -> None:
        """`unsupported` vira trabalho futuro; `ignoredByPolicy` não entra na fila.

        Confundir os dois faria alguém tentar implementar acesso ao número de
        série do host.
        """
        counts = negative[1].log.counts()
        assert counts.get("ignoredByPolicy", 0) >= 1
        assert counts.get("unsupported", 0) >= 1

    def test_every_defect_names_its_origin(self, negative: tuple[Any, SliceResult]) -> None:
        """Erro sem arquivo, linha, elemento e valor original não é acionável."""
        declarations, result = negative
        for entry in result.log.entries:
            if entry.verdict not in {Verdict.INVALID, Verdict.IGNORED_BY_POLICY}:
                continue
            declaration = declarations.by_id(entry.source)
            assert declaration is not None, entry.source
            assert declaration.source_reference.file
            assert declaration.source_reference.line
            assert declaration.element
            assert declaration.raw_value
            assert entry.detail

    def test_an_invalid_property_does_not_silently_become_a_default(
        self, negative: tuple[Any, SliceResult]
    ) -> None:
        """A cor inválida precisa ficar AUSENTE, não virar preto.

        Um default aqui produziria uma tela plausível, e ninguém investiga o que
        parece certo.
        """
        element = next(item for item in negative[1].elements if item.text_content == "cor inválida")
        assert element.typography is None or element.typography.color is None


class TestPipelineReachesTheRenderer:
    """Da declaração até o modelo que o QML consome, passando pela serialização."""

    def _pipeline(self, element: Any) -> Any:
        # Serializa e desserializa no meio do caminho: se o contrato não
        # sobrevivesse a isso, o cache e o round-trip do VS-05 estariam
        # construídos sobre areia.
        payload = json.loads(json.dumps(element.to_dict(), ensure_ascii=False))
        assert payload["id"] == element.id

        node = build_text_node(
            element,
            resolver=_resolver(),
            box=LayoutBox(*CANVAS),
            fonts=FontProvider({name: name for name in PACKAGED_FONTS}),
        )
        return node, to_render_model(node)

    def test_a_literal_colour_reaches_the_qml_model(
        self, positive: tuple[Any, SliceResult]
    ) -> None:
        node, result = self._pipeline(_by_id(positive[1], "text-1"))
        assert result.status is AdaptationStatus.SUCCESS
        assert result.require_model().color == "#f2f6fb"
        assert node.color == "#f2f6fb"

    def test_a_token_colour_is_resolved_before_the_boundary(
        self, positive: tuple[Any, SliceResult]
    ) -> None:
        """O QML nunca vê `{"token": ...}` — se visse, resolveria por conta."""
        _node, result = self._pipeline(_by_id(positive[1], "text-4"))
        assert result.require_model().color == "#ffd166"

    def test_a_binding_is_resolved_before_the_boundary(
        self, positive: tuple[Any, SliceResult]
    ) -> None:
        _node, result = self._pipeline(_by_id(positive[1], "reloadableText-6"))
        assert result.require_model().text == "Chrono Trigger"

    def test_a_translation_is_resolved_before_the_boundary(
        self, positive: tuple[Any, SliceResult]
    ) -> None:
        _node, result = self._pipeline(_by_id(positive[1], "text-7"))
        assert result.require_model().text == "Jogar"

    def test_a_condition_selects_the_focused_branch(
        self, positive: tuple[Any, SliceResult]
    ) -> None:
        _node, result = self._pipeline(_by_id(positive[1], "text-5"))
        assert result.require_model().color == "#ffd166", "estado 'focused' está ativo"

    def test_a_percent_dimension_becomes_logical_pixels(
        self, positive: tuple[Any, SliceResult]
    ) -> None:
        node, _result = self._pipeline(_by_id(positive[1], "text-2"))
        assert node.geometry.width == float(CANVAS[0]), "100% do canvas"

    def test_an_auto_dimension_stays_implicit(self, positive: tuple[Any, SliceResult]) -> None:
        """`auto` vira None, não zero. Zero seria caixa sem tamanho."""
        node, result = self._pipeline(_by_id(positive[1], "text-3"))
        assert node.geometry.width is None
        assert result.require_model().width is None

    def test_the_missing_font_arrives_as_a_declared_fallback(
        self, positive: tuple[Any, SliceResult]
    ) -> None:
        node, result = self._pipeline(_by_id(positive[1], "text-8"))
        assert node.font_asset is not None
        assert node.font_asset.origin is not FontOrigin.PACKAGED
        assert result.status is AdaptationStatus.DEGRADED
        payload = result.diagnostics[0].to_dict()
        assert payload["originalValue"] == "Gilroy Display"
        assert payload["resolvedValue"] != "Gilroy Display"


class TestGeometryIsProvenByRendering:
    """Alinhamento validado geometricamente, não pelo enum.

    O enum prova que o adapter escolheu o nome certo. Só a renderização prova
    que o conteúdo foi de fato posicionado — e foi um enum "correto" que não
    resolvia (`Text[nome]` devolvendo undefined) que motivou este gate.
    """

    @pytest.fixture(scope="module")
    @staticmethod
    def rendered(
        positive: tuple[Any, SliceResult], tmp_path_factory: pytest.TempPathFactory
    ) -> dict[str, Any]:
        captured: dict[str, Any] = {}
        for element_id in ("text-1", "text-2", "text-3"):
            element = _by_id(positive[1], element_id)
            node = build_text_node(
                element,
                resolver=_resolver(),
                box=LayoutBox(*CANVAS),
                fonts=FontProvider({name: name for name in PACKAGED_FONTS}),
            )
            model = to_render_model(node).require_model()
            output = tmp_path_factory.mktemp(element_id)
            result = capture(model.to_dict(), output=output, canvas=CANVAS, background=BACKGROUND)
            assert_not_empty(result.image, background=BACKGROUND)
            write_artifacts(
                result,
                output,
                resolved_node=node.to_dict(),
                adaptation=to_render_model(node).to_dict(),
            )
            captured[element_id] = result
        return captured

    def test_no_forbidden_warning_in_any_scene(self, rendered: dict[str, Any]) -> None:
        for element_id, result in rendered.items():
            assert not result.forbidden_messages, (element_id, result.forbidden_messages)

    def test_left_aligned_content_starts_at_the_box(self, rendered: dict[str, Any]) -> None:
        geometry = rendered["text-1"].geometry
        assert geometry["horizontalAlignment"] == 1
        assert geometry["x"] == 40
        assert geometry["contentWidth"] < geometry["width"], (
            "o teste de centralização não teria sentido se o conteúdo enchesse a caixa"
        )

    def test_centered_content_is_narrower_than_its_box(self, rendered: dict[str, Any]) -> None:
        """Centralizar só é observável quando sobra espaço nos dois lados."""
        geometry = rendered["text-2"].geometry
        assert geometry["horizontalAlignment"] == 4
        assert geometry["width"] == CANVAS[0]
        assert 0 < geometry["contentWidth"] < geometry["width"]

    def test_right_aligned_content_uses_the_implicit_width(self, rendered: dict[str, Any]) -> None:
        geometry = rendered["text-3"].geometry
        assert geometry["horizontalAlignment"] == 2
        assert geometry["width"] == geometry["implicitWidth"]

    def test_the_colour_survives_to_the_scene(self, rendered: dict[str, Any]) -> None:
        assert "f2f6fb" in rendered["text-1"].geometry["color"].lower()

    def test_the_font_hash_is_recorded_for_each_scene(self, rendered: dict[str, Any]) -> None:
        """Sem o hash, divergência por atualização de pacote pareceria regressão."""
        for element_id, result in rendered.items():
            fingerprint = result.environment["fontFile"]
            assert fingerprint.get("sha256"), (element_id, fingerprint)


class TestFailedResultsNeverReachTheHarness:
    def test_a_failed_adaptation_has_no_model_to_send(self) -> None:
        """`require_model()` é a única porta, e ela recusa `failed`."""
        from dataclasses import replace

        from steamzero.domain.resolved_node import ResolvedTextNode

        node = replace(ResolvedTextNode(id="x", text="oi"), color="vermelho")
        result = to_render_model(node)
        assert result.status is AdaptationStatus.FAILED
        assert result.model is None

    def test_the_harness_cannot_be_fed_without_unwrapping(self, tmp_path: Path) -> None:
        """Não existe caminho que mande um resultado `failed` para o QML.

        A prova é de tipo, não de disciplina: `capture` recebe o payload de um
        modelo, e em `failed` não há modelo para gerar payload.
        """
        from dataclasses import replace

        from steamzero.domain.resolved_node import ResolvedTextNode

        node = replace(ResolvedTextNode(id="x", text="oi"), color="vermelho")
        result = to_render_model(node)
        with pytest.raises(Exception, match="tradução falhou"):
            capture(
                result.require_model().to_dict(),
                output=tmp_path,
                canvas=CANVAS,
                background=BACKGROUND,
            )

    def test_a_pending_value_cannot_be_captured(self, tmp_path: Path) -> None:
        """Defesa em profundidade: nada impede montar o dicionário à mão.

        Antes desta barreira, `{"text": {"bind": ...}}` passado direto ao
        harness renderizava "[object Object]" sem erro nenhum — o QML aceita
        objeto onde espera string.
        """
        with pytest.raises(CaptureError, match="não resolvido"):
            capture(
                {"id": "x", "text": {"bind": "game.title"}},
                output=tmp_path,
                canvas=CANVAS,
                background=BACKGROUND,
            )


class TestScopeLimitsAreHonest:
    """O que o VS-04 NÃO entrega, afirmado por teste em vez de por promessa."""

    def test_the_full_corpus_is_not_migrated(self, positive: tuple[Any, SliceResult]) -> None:
        declarations, _ = positive
        assert declarations.source_property_count < 388, (
            "a fatia é estreita de propósito; o corpus de 388 é do P0-03"
        )

    def test_only_text_elements_are_compiled(self, negative: tuple[Any, SliceResult]) -> None:
        declarations, result = negative
        image = next(item for item in declarations.declarations if item.raw_value == "logo.png")
        assert result.verdicts[image.declaration_id] is Verdict.UNSUPPORTED
        assert all(element.type == "text" for element in result.elements)
