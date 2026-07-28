# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Etapa A do P0-03 — tipos canônicos e registros de tipo.

Dois pontos que estes testes protegem:

O registro de tipos torna possível recusar `fontSize = binding("game.title")`
MESMO SEM FALLBACK, porque o registro publica que `game.title` produz texto. O
fallback sozinho não pegava esse caso — que é justamente o erro mais provável.

Dimensão é tipo fechado. Sem `calc()`, sem fórmula: dimensão calculada seria uma
linguagem de expressão entrando pela porta dos fundos.
"""

from __future__ import annotations

import pytest

from steamzero.domain import scene_value as value
from steamzero.domain.scene_contract import (
    RESERVED_NAMESPACES,
    Alignment,
    AppearanceSpec,
    ColorValue,
    DimensionUnit,
    DimensionValue,
    ElementContract,
    ElideMode,
    GradientKind,
    GradientStop,
    GradientValue,
    LayoutSpec,
    TextLayoutSpec,
    TypographySpec,
    WrapMode,
)
from steamzero.domain.scene_registry import (
    DeferredValue,
    ResolutionPhase,
    UnknownPathPolicy,
    default_registries,
)
from steamzero.domain.scene_typing import SourceReference, ValueType


class TestRegistryCatchesWhatFallbackCannot:
    """O ponto central da correção do roteiro."""

    def test_binding_of_wrong_type_is_refused_without_fallback(self) -> None:
        """Caso literal da especificação: fontSize = binding(game.title)."""
        registries = default_registries()
        deferred = DeferredValue("bind", "game.title", ValueType.NUMBER, ResolutionPhase.RUNTIME)
        result = registries.check_deferred(deferred)
        assert result.ok is False
        assert "produz string" in (result.reason or "")

    def test_matching_binding_is_accepted(self) -> None:
        registries = default_registries()
        deferred = DeferredValue("bind", "game.year", ValueType.NUMBER, ResolutionPhase.RUNTIME)
        assert registries.check_deferred(deferred).ok is True

    def test_token_of_wrong_type_is_refused(self) -> None:
        registries = default_registries()
        deferred = DeferredValue(
            "token", "color.accent", ValueType.NUMBER, ResolutionPhase.LOAD_TIME
        )
        assert registries.check_deferred(deferred).ok is False

    def test_wrong_fallback_is_still_caught(self) -> None:
        registries = default_registries()
        deferred = DeferredValue(
            "bind",
            "game.title",
            ValueType.STRING,
            ResolutionPhase.RUNTIME,
            fallback=42,
        )
        assert registries.check_deferred(deferred).ok is False


class TestUnknownPathPolicy:
    """Caminho desconhecido nunca é aceito em silêncio."""

    def _deferred(self, path: str, fallback: object = None) -> DeferredValue:
        return DeferredValue(
            "bind", path, ValueType.STRING, ResolutionPhase.RUNTIME, fallback=fallback
        )

    def test_required_unknown_binding_is_invalid(self) -> None:
        result = default_registries().check_deferred(self._deferred("game.inventado"))
        assert result.policy is UnknownPathPolicy.INVALID

    def test_optional_unknown_binding_with_fallback_uses_it(self) -> None:
        result = default_registries().check_deferred(
            self._deferred("game.inventado", fallback="—"), required=False
        )
        assert result.policy is UnknownPathPolicy.USE_FALLBACK

    def test_unknown_extension_negotiates_capability(self) -> None:
        result = default_registries().check_deferred(self._deferred("extension.acme.foo"))
        assert result.policy is UnknownPathPolicy.NEGOTIATE_CAPABILITY

    def test_malformed_path_is_refused_before_lookup(self) -> None:
        """Procurar no registro sugeriria que poderia existir."""
        result = default_registries().check_deferred(self._deferred("../etc/passwd"))
        assert result.ok is False
        assert result.policy is None


class TestDeferredValueCarriesItsContract:
    def test_all_four_required_fields_are_present(self) -> None:
        deferred = DeferredValue(
            "bind",
            "game.title",
            ValueType.STRING,
            ResolutionPhase.RUNTIME,
            fallback="—",
            source_reference=SourceReference("a.xml", line=10),
        )
        payload = deferred.to_dict()
        for key in ("expectedType", "resolutionPhase", "fallback", "sourceReference"):
            assert key in payload

    @pytest.mark.parametrize(
        "phase", [ResolutionPhase.COMPILE_TIME, ResolutionPhase.LOAD_TIME, ResolutionPhase.RUNTIME]
    )
    def test_every_phase_is_expressible(self, phase: ResolutionPhase) -> None:
        deferred = DeferredValue("token", "color.accent", ValueType.COLOR, phase)
        assert deferred.to_dict()["resolutionPhase"] == phase.value


class TestDimensionIsClosed:
    @pytest.mark.parametrize(
        "dimension",
        [DimensionValue.logical_px(64), DimensionValue.percent(50), DimensionValue.auto()],
    )
    def test_supported_units(self, dimension: DimensionValue) -> None:
        assert dimension.to_dict()["kind"] in {"logicalPx", "percent", "auto"}

    @pytest.mark.parametrize("bad", ["em", "rem", "vw", 50, None, "logicalpx"])
    def test_unit_outside_the_contract_is_refused(self, bad: object) -> None:
        """Fechado quer dizer fechado.

        Sem esta checagem, `unit="em"` de um tema importado não casa com nenhuma
        comparação `is` da validação, sobrevive à construção e só falha na
        conversão para float — longe da causa e sem dizer qual tema errou.
        """
        with pytest.raises(ValueError, match="unidade fora do contrato"):
            DimensionValue(unit=bad, value=10)  # type: ignore[arg-type]

    @pytest.mark.parametrize("bad", ["em", "rem", None, "logicalpx"])
    def test_unit_outside_the_contract_is_refused_when_parsing(self, bad: object) -> None:
        """A desserialização é a outra porta de entrada.

        Sem `from_dict` validando, um payload com `"kind": "em"` entraria pelo
        round-trip sem nunca passar pela validação da construção.
        """
        with pytest.raises(ValueError, match="unidade fora do contrato"):
            DimensionValue.from_dict({"kind": bad, "value": 10})

    @pytest.mark.parametrize(
        "dimension",
        [DimensionValue.logical_px(64), DimensionValue.percent(50), DimensionValue.auto()],
    )
    def test_round_trip_through_the_payload(self, dimension: DimensionValue) -> None:
        assert DimensionValue.from_dict(dimension.to_dict()) == dimension

    def test_positional_construction_is_refused(self) -> None:
        """Os campos são `unit, value`, mas a leitura natural é a ordem inversa.

        `DimensionValue(50, PERCENT)` passava pela validação inteira e só
        explodia na conversão para float, longe da causa.
        """
        with pytest.raises(TypeError, match="positional"):
            DimensionValue(DimensionUnit.PERCENT, 50)  # type: ignore[misc]

    @pytest.mark.parametrize("factory", [DimensionValue.logical_px, DimensionValue.percent])
    @pytest.mark.parametrize("bad", [True, False, "50", None, float("nan"), float("inf")])
    def test_measured_units_require_a_finite_number(self, factory: object, bad: object) -> None:
        """`bool` é subclasse de `int`.

        Sem a checagem explícita, `percent(True)` viraria 1.0 e ninguém saberia
        que o tema declarou um booleano.
        """
        with pytest.raises(ValueError, match=r"exige (número|valor)"):
            factory(bad)  # type: ignore[operator]

    def test_auto_carries_no_value(self) -> None:
        with pytest.raises(ValueError, match="auto não aceita valor"):
            DimensionValue(unit=DimensionUnit.AUTO, value=10)

    def test_px_requires_a_value(self) -> None:
        with pytest.raises(ValueError, match="exige valor"):
            DimensionValue(unit=DimensionUnit.LOGICAL_PX)

    def test_out_of_range_percent_is_refused(self) -> None:
        with pytest.raises(ValueError, match="percentual fora da faixa"):
            DimensionValue.percent(5000)

    def test_no_formula_unit_exists(self) -> None:
        """calc(), expr e script não têm representação no tipo."""
        assert {unit.value for unit in DimensionUnit} == {"logicalPx", "percent", "auto"}


class TestColor:
    def test_hex_round_trip(self) -> None:
        assert ColorValue.from_hex("#ff8000").to_hex() == "#ff8000"

    def test_alpha_is_preserved(self) -> None:
        color = ColorValue.from_hex("#ff800080")
        assert 0.49 < color.alpha < 0.51
        assert color.to_hex().endswith("80")

    def test_color_space_is_explicit(self) -> None:
        """Acrescentar HDR depois vira campo novo, não migração de temas."""
        assert ColorValue.from_hex("#000000").to_dict()["space"] == "sRGB"

    @pytest.mark.parametrize("bad", ["#ff", "#gggggg", "vermelho"])
    def test_invalid_hex_is_refused(self, bad: str) -> None:
        with pytest.raises(ValueError):
            ColorValue.from_hex(bad)

    def test_channel_out_of_range_is_refused(self) -> None:
        with pytest.raises(ValueError, match=r"fora de 0\.\.255"):
            ColorValue(300, 0, 0)


class TestGradient:
    def _stops(self) -> tuple[GradientStop, ...]:
        return (
            GradientStop(0.0, ColorValue.from_hex("#000000")),
            GradientStop(1.0, ColorValue.from_hex("#ffffff")),
        )

    def test_linear_gradient(self) -> None:
        gradient = GradientValue(GradientKind.LINEAR, self._stops(), angle=90)
        assert gradient.to_dict()["kind"] == "linear"
        assert len(gradient.to_dict()["stops"]) == 2

    def test_single_stop_is_not_a_gradient(self) -> None:
        """Seria cor sólida disfarçada, e o render não bateria com o escrito."""
        with pytest.raises(ValueError, match="ao menos dois stops"):
            GradientValue(GradientKind.RADIAL, (GradientStop(0.0, ColorValue(0, 0, 0)),))

    def test_stop_outside_range_is_refused(self) -> None:
        with pytest.raises(ValueError, match=r"fora de 0\.\.1"):
            GradientStop(1.5, ColorValue(0, 0, 0))

    def test_unordered_stops_are_refused(self) -> None:
        stops = (
            GradientStop(0.8, ColorValue(0, 0, 0)),
            GradientStop(0.2, ColorValue(255, 255, 255)),
        )
        with pytest.raises(ValueError, match="ordem crescente"):
            GradientValue(GradientKind.LINEAR, stops)


class TestLayoutValidation:
    def test_min_greater_than_max_is_refused(self) -> None:
        """Contradição que renderizaria silenciosamente errado."""
        layout = LayoutSpec(
            min_width=DimensionValue.logical_px(500), max_width=DimensionValue.logical_px(100)
        )
        with pytest.raises(ValueError, match="mínima maior que a máxima"):
            layout.validate()

    def test_consistent_bounds_pass(self) -> None:
        LayoutSpec(
            min_width=DimensionValue.logical_px(100), max_width=DimensionValue.logical_px(500)
        ).validate()

    def test_different_units_are_not_compared(self) -> None:
        """px contra percent não é comparável sem a caixa do pai."""
        LayoutSpec(
            min_width=DimensionValue.logical_px(500), max_width=DimensionValue.percent(10)
        ).validate()


class TestElementContract:
    def _element(self) -> ElementContract:
        return ElementContract(
            id="gameTitle",
            type="text",
            source_reference=SourceReference("layouts/arcade.xml", line=183),
            visible=True,
            layout=LayoutSpec(x=DimensionValue.percent(50), horizontal_alignment=Alignment.CENTER),
            typography=TypographySpec(
                font_family="Gilroy",
                font_size=48,
                color=value.when(value.in_state("focused"), "#ffffff", "#dedede"),
                font_fallback=("Open Sans",),
            ),
            text_layout=TextLayoutSpec(wrap=WrapMode.WORD, elide=ElideMode.END, max_lines=2),
            appearance=AppearanceSpec(background=ColorValue.from_hex("#101820")),
        )

    def test_serializes_without_empty_sections(self) -> None:
        payload = self._element().to_dict()
        assert set(payload) >= {"id", "type", "layout", "typography", "textLayout"}
        assert all(section for section in payload.values() if isinstance(section, dict))

    def test_source_reference_survives_serialization(self) -> None:
        """Sem origem, um veredito é inauditável."""
        assert self._element().to_dict()["sourceReference"]["line"] == 183

    def test_conditional_color_is_kept_structured(self) -> None:
        """O que boundText/boundImage impedia."""
        color = self._element().to_dict()["typography"]["color"]
        assert color["when"]["state"] == "focused"

    def test_reserved_namespaces_are_declared_not_implemented(self) -> None:
        """Declarar agora evita redesenhar o elemento depois."""
        assert set(RESERVED_NAMESPACES) == {
            "effects",
            "stateVariants",
            "interaction",
            "accessibility",
            "performance",
        }
        assert not set(RESERVED_NAMESPACES) & set(self._element().to_dict())

    def test_dimensions_serialize_as_typed_objects(self) -> None:
        assert self._element().to_dict()["layout"]["x"] == {"kind": "percent", "value": 50}
