# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Gates de fechamento do modelo de valor.

O modelo permite qualquer origem em qualquer propriedade. Sozinho isso seria
permissivo demais — nada impediria `fontSize = asset("bg.png")`. Estes testes
protegem os seis gates que tornam a permissividade segura.

O princípio de fundo: uma propriedade que some sem veredito é PIOR que uma
recusada, porque a recusada aparece no relatório.
"""

from __future__ import annotations

import pytest

from steamzero.domain import scene_value as value
from steamzero.domain.scene_typing import (
    Accounting,
    Category,
    SourceReference,
    TypeError_,
    ValueType,
    check_type,
    normalize_legacy_kind,
    resolve_chain,
    validate_path,
)


class TestTypedValues:
    """Gate 2.4: o valor precisa ser compatível com o tipo da propriedade."""

    def test_color_accepts_hex(self) -> None:
        check_type("#ff0000", ValueType.COLOR)
        check_type("#ff0000aa", ValueType.COLOR)

    @pytest.mark.parametrize("bad", ["vermelho", "ff0000", "#ff", 42, True])
    def test_color_refuses_non_color(self, bad: object) -> None:
        with pytest.raises(TypeError_, match="cor precisa ser"):
            check_type(bad, ValueType.COLOR)

    def test_fontsize_refuses_asset(self) -> None:
        """Caso literal da especificação."""
        with pytest.raises(TypeError_, match="asset não é compatível"):
            check_type(value.asset("assets/background.png"), ValueType.NUMBER)

    def test_visible_refuses_translation(self) -> None:
        """Caso literal da especificação."""
        with pytest.raises(TypeError_, match="tradução só produz texto"):
            check_type(value.localized("game.title"), ValueType.BOOLEAN)

    def test_image_source_refuses_number(self) -> None:
        """Caso literal da especificação."""
        with pytest.raises(TypeError_, match="exige asset ou binding"):
            check_type(42, ValueType.MEDIA)

    def test_volume_refuses_color(self) -> None:
        """Caso literal da especificação."""
        with pytest.raises(TypeError_, match="esperado número"):
            check_type("#FFFFFF", ValueType.NUMBER)

    def test_boolean_is_not_a_number(self) -> None:
        """True == 1 em Python; o contrato não pode herdar essa confusão."""
        with pytest.raises(TypeError_, match="esperado número"):
            check_type(True, ValueType.NUMBER)

    @pytest.mark.parametrize("good", [64, 12.5, "50%", "auto", "center"])
    def test_dimension_accepts_its_forms(self, good: object) -> None:
        check_type(good, ValueType.DIMENSION)

    @pytest.mark.parametrize("bad", ["50vw", "calc(100% - 4)", True])
    def test_dimension_refuses_formulas(self, bad: object) -> None:
        """Dimensão calculada viraria linguagem executável."""
        with pytest.raises(TypeError_):
            check_type(bad, ValueType.DIMENSION)


class TestConditionalBranchesMustAgree:
    """Gate 2.4: ramos de um condicional precisam ser do mesmo tipo."""

    def test_matching_branches_are_accepted(self) -> None:
        candidate = value.when(
            value.compare("equals", value.bind("game.favorite"), True),
            "#ffd700",
            "#ffffff",
        )
        check_type(candidate, ValueType.COLOR)

    def test_mismatched_branches_are_refused(self) -> None:
        """Caso literal da especificação: cor no then, asset no else."""
        candidate = value.when(
            value.compare("equals", value.bind("game.favorite"), True),
            "#ffd700",
            value.asset("assets/background.png"),
        )
        with pytest.raises(TypeError_, match="otherwise"):
            check_type(candidate, ValueType.COLOR)

    def test_nested_conditional_is_checked_through(self) -> None:
        inner = value.when(value.in_state("focused"), "#111111", "naoEhCor")
        outer = value.when(value.in_state("selected"), "#000000", inner)
        with pytest.raises(TypeError_):
            check_type(outer, ValueType.COLOR)


class TestDeferredOriginsAreCheckedByFallback:
    """Token e binding resolvem no shell; o fallback revela a intenção do autor."""

    def test_binding_alone_is_accepted(self) -> None:
        check_type(value.bind("game.year"), ValueType.NUMBER)

    def test_binding_with_wrong_fallback_is_refused(self) -> None:
        candidate = value.bind("game.title", fallback="grande")
        with pytest.raises(TypeError_, match="fallback"):
            check_type(candidate, ValueType.NUMBER)

    def test_token_with_correct_fallback_passes(self) -> None:
        check_type(value.token("color.accent", fallback="#00ff00"), ValueType.COLOR)


class TestAccounting:
    """Gate 2.1: toda propriedade encontrada recebe exatamente um veredito."""

    def test_complete_accounting(self) -> None:
        accounting = Accounting()
        for name in ("fontColor", "font", "alignment"):
            accounting.observe(name)
            accounting.judge(name)
        assert accounting.unaccounted == 0
        assert accounting.coverage == 1.0
        assert accounting.complete is True

    def test_missing_verdict_is_detected(self) -> None:
        """Foi assim que 238 fontColor sumiram sem ninguém notar."""
        accounting = Accounting()
        accounting.observe("fontColor")
        accounting.observe("font")
        accounting.judge("fontColor")
        assert accounting.unaccounted == 1
        assert accounting.complete is False
        assert accounting.coverage == 0.5

    def test_duplicate_verdict_is_detected(self) -> None:
        """Julgar duas vezes faz o relatório somar mais que o total."""
        accounting = Accounting()
        accounting.observe("fontColor")
        accounting.judge("fontColor")
        accounting.judge("fontColor")
        assert accounting.duplicates == ["fontColor"]
        assert accounting.complete is False

    def test_empty_source_is_complete(self) -> None:
        assert Accounting().complete is True

    def test_report_exposes_the_gate_fields(self) -> None:
        accounting = Accounting()
        accounting.observe("x")
        accounting.judge("x")
        report = accounting.to_dict()
        assert report["sourcePropertyCount"] == report["translationVerdictCount"]
        assert report["unaccounted"] == 0
        assert report["accountingCoverage"] == 1.0


class TestFallbackChain:
    """Gate 2.5: ordem determinística e detecção de ciclo."""

    def test_chain_is_walked_in_order(self) -> None:
        candidate = value.token("color.accent", fallback=value.setting("accent", fallback="#fff"))
        assert resolve_chain(candidate) == ["token", "setting", "literal"]

    def test_self_referencing_token_is_a_cycle(self) -> None:
        """Travaria a resolução em runtime; aqui vira erro de contrato."""
        candidate = {"token": "color.accent", "fallback": {"token": "color.accent"}}
        with pytest.raises(ValueError, match="ciclo de fallback"):
            resolve_chain(candidate)

    def test_excessive_depth_is_refused(self) -> None:
        candidate: dict = {"token": "a.b"}
        current = candidate
        for index in range(12):
            current["fallback"] = {"token": f"t{index}.x"}
            current = current["fallback"]
        with pytest.raises(ValueError, match="excede"):
            resolve_chain(candidate)

    def test_literal_terminates_the_chain(self) -> None:
        assert resolve_chain("#fff") == ["literal"]


class TestPathNamespaces:
    """Gate 2.6: caminho é chave lógica, nunca caminho físico."""

    @pytest.mark.parametrize(
        "path",
        [
            "media.image.packaging.box.front",
            "media.video.preview.gameplay",
            "extension.orgArcade.controls.layout",
            "theme.neonGrid.image.customFrame",
        ],
    )
    def test_authorized_namespaces_are_accepted(self, path: str) -> None:
        validate_path(path, theme_id="neonGrid")

    @pytest.mark.parametrize(
        "path", ["../etc/passwd", "media/image/box", "media.image\\box", "Media.Image"]
    )
    def test_physical_paths_are_refused(self, path: str) -> None:
        with pytest.raises(ValueError):
            validate_path(path)

    def test_theme_cannot_read_another_themes_namespace(self) -> None:
        with pytest.raises(ValueError, match="não pode acessar recurso"):
            validate_path("theme.outroTema.image.x", theme_id="neonGrid")

    def test_extension_requires_a_vendor(self) -> None:
        with pytest.raises(ValueError):
            validate_path("extension")


class TestLegacyNormalization:
    """Gate 2.7: os tipos legados não chegam ao runtime."""

    def test_bound_text_becomes_text_with_binding(self) -> None:
        assert normalize_legacy_kind("boundText") == ("text", True)

    def test_bound_image_becomes_image_with_binding(self) -> None:
        assert normalize_legacy_kind("boundImage") == ("image", True)

    def test_modern_kind_is_untouched(self) -> None:
        assert normalize_legacy_kind("menu") == ("menu", False)


class TestDiagnosticOrigin:
    """Gate 2.8: sem origem, um veredito é inauditável."""

    def test_reference_renders_a_location(self) -> None:
        reference = SourceReference("layouts/arcade.xml", line=183, element="gameTitle")
        assert str(reference) == "layouts/arcade.xml:183"
        assert reference.to_dict()["element"] == "gameTitle"

    def test_column_is_included_when_known(self) -> None:
        assert str(SourceReference("a.xml", line=10, column=4)) == "a.xml:10:4"

    def test_file_alone_is_valid(self) -> None:
        assert str(SourceReference("a.xml")) == "a.xml"


class TestCategories:
    def test_every_category_of_the_specification_exists(self) -> None:
        """Fidelidade agregada esconde que a tipografia está em zero."""
        expected = {
            "layout",
            "typography",
            "color",
            "media",
            "animation",
            "audio",
            "navigation",
            "accessibility",
            "effects",
            "interaction",
            "unknown",
        }
        assert {item.value for item in Category} == expected
