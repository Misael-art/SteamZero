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

from pathlib import Path
from typing import Any, ClassVar

import pytest

from steamzero.domain import scene_value as value
from steamzero.domain.scene_contract import (
    CONTRACT_PROPERTY_TYPES,
    CONTRACT_VALUE_FIELDS,
    RESERVED_MASK_CAPABILITIES,
    RESERVED_MASK_TYPES,
    RESERVED_NAMESPACES,
    RESERVED_VALUE_FIELDS,
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
    TransformSpec,
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


class TestMaskReservationSurvivesTheFreeze:
    """A reserva só serve se ninguém puder congelar o contrato sem ela.

    `AppearanceSpec.clip` é booleano, herdado do QML: recorta ou não, sempre
    retangular. Canto arredondado, avatar circular e cover em degradê não cabem
    nele — e descobrir isso depois de congelar o schema obrigaria a migrar todo
    tema já importado.
    """

    @pytest.mark.parametrize("name", ["clip_spec", "mask_stack", "hit_test_shape"])
    def test_the_reserved_field_exists(self, name: str) -> None:
        assert hasattr(AppearanceSpec(), name)

    def test_the_reserved_fields_default_to_absent(self) -> None:
        """Reservado significa vazio, não implementado pela metade.

        Uma implementação parcial seria pior que a ausência: temas passariam a
        depender dela, e a forma final teria de acomodar o improviso.
        """
        appearance = AppearanceSpec()
        assert appearance.clip_spec is None
        assert appearance.mask_stack is None
        assert appearance.hit_test_shape is None
        assert "clipSpec" not in appearance.to_dict()
        assert "maskStack" not in appearance.to_dict()

    def test_a_declared_reservation_survives_serialization(self) -> None:
        """Quando o P0-08 preencher, o payload já tem onde colocar."""
        payload = AppearanceSpec(clip_spec={"shape": "roundedRect"}).to_dict()
        assert payload["clipSpec"] == {"shape": "roundedRect"}

    def test_hit_test_is_separate_from_the_visual_mask(self) -> None:
        """Uma cover circular não pode encolher o alvo de toque.

        A máscara é aparência; o hit test é acessibilidade. Confundir os dois
        produz uma interface bonita e inoperável, e o defeito só aparece para
        quem usa controle ou toque — não para quem revisa a captura.
        """
        appearance = AppearanceSpec(
            mask_stack=[{"shape": "circle"}], hit_test_shape={"shape": "rect"}
        )
        payload = appearance.to_dict()
        assert payload["maskStack"] != payload["hitTestShape"]

    def test_the_p0_08_types_are_registered(self) -> None:
        assert set(RESERVED_MASK_TYPES) == {
            "ClipSpec",
            "MaskSpec",
            "MaskStack",
            "HitTestShape",
            "ViewTransitionMaskSpec",
        }

    def test_the_capability_vocabulary_is_registered(self) -> None:
        """Sem o vocabulário, um tema que peça o indisponível falha sem nome.

        Com ele, a negociação devolve `fallback`/`approximated` — que é a regra
        do projeto para tudo que não é exato.
        """
        assert "graphics.clip.roundedRect" in RESERVED_MASK_CAPABILITIES
        assert "transition.masked.circle" in RESERVED_MASK_CAPABILITIES
        assert "renderer.rhi" in RESERVED_MASK_CAPABILITIES

    def test_the_contract_document_exists(self) -> None:
        """Campo reservado sem contrato escrito é campo que alguém preenche errado."""
        document = (
            Path(__file__).resolve().parents[2]
            / "docs"
            / "03-architecture"
            / "clip-and-mask-contract.md"
        )
        assert document.exists()
        text = document.read_text(encoding="utf-8")
        for required in ("ClipSpec", "MaskSpec", "MaskStack", "HitTestShape", "visual-rhi"):
            assert required in text, required


class TestContractClosure:
    """O contrato é fechado: nenhum campo ``Any`` sem tipo, nenhum tipo sem campo.

    A tabela ``CONTRACT_PROPERTY_TYPES`` é a fonte única da qual o registro de
    tipos deriva. Dois defeitos precisam de trava: um campo novo acrescentado a
    um spec sem ganhar tipo (propriedade que aceita qualquer coisa em silêncio)
    e uma entrada de tabela que não corresponde a campo nenhum (tipo morto que
    ninguém consulta).
    """

    _DATACLASSES: ClassVar[dict[str, type]] = {
        "element": ElementContract,
        "layout": LayoutSpec,
        "transform": TransformSpec,
        "appearance": AppearanceSpec,
        "typography": TypographySpec,
        "textLayout": TextLayoutSpec,
    }

    @staticmethod
    def _camel(snake: str) -> str:
        head, *rest = snake.split("_")
        return head + "".join(part.capitalize() for part in rest)

    @staticmethod
    def _snake(camel: str) -> str:
        import re

        return re.sub(r"(?<!^)(?=[A-Z])", "_", camel).lower()

    def _any_fields(self) -> dict[str, str]:
        """campo camelCase -> onde mora, para cada campo tipado ``Any``."""
        found: dict[str, str] = {}
        for where, cls in self._DATACLASSES.items():
            for name, field in cls.__dataclass_fields__.items():
                # Com `from __future__ import annotations` o tipo chega como a
                # STRING "Any", não como o objeto. Comparar com `is` seria um
                # falso negativo silencioso: todo campo pareceria tipado.
                if str(field.type) == "Any":
                    found[self._camel(name)] = where
        return found

    def test_every_value_field_has_an_entry(self) -> None:
        any_fields = self._any_fields()
        missing = sorted(set(any_fields) - set(CONTRACT_VALUE_FIELDS))
        assert missing == [], f"campo Any sem tipo no contrato: {missing}"

    def test_the_reserved_trio_is_the_only_untyped_slot(self) -> None:
        typed = set(CONTRACT_PROPERTY_TYPES)
        assert set(RESERVED_VALUE_FIELDS) == {"clipSpec", "maskStack", "hitTestShape"}
        assert typed.isdisjoint(RESERVED_VALUE_FIELDS)

    def test_every_entry_maps_to_a_real_field(self) -> None:
        any_fields = self._any_fields()
        snakes = {self._snake(name) for name in any_fields}
        ghost = sorted(name for name in CONTRACT_VALUE_FIELDS if self._snake(name) not in snakes)
        assert ghost == [], f"entradas sem campo correspondente: {ghost}"

    def test_every_entry_names_an_any_field(self) -> None:
        for name in CONTRACT_PROPERTY_TYPES:
            cls = self._DATACLASSES[self._any_fields()[name]]
            field = cls.__dataclass_fields__[self._snake(name)]
            assert str(field.type) == "Any", (
                f"{name} é campo tipado ({field.type}), não slot de valor"
            )

    def test_the_registry_derives_from_the_table(self) -> None:
        """Uma segunda lista escrita à mão divergiria do contrato."""
        properties = default_registries().properties
        assert set(properties.types) == set(CONTRACT_PROPERTY_TYPES)
        for name, value_type in CONTRACT_PROPERTY_TYPES.items():
            assert properties.type_of(name) is value_type, name

    def test_the_legacy_names_are_gone_from_the_registry(self) -> None:
        """`content` e `source` eram nomes que o contrato nunca teve."""
        properties = default_registries().properties.types
        assert "content" not in properties
        assert "source" not in properties

    def test_enums_are_not_value_slots(self) -> None:
        """`horizontalAlignment` é enum fechado (campo tipado), não ``Value<T>``.

        A distinção é o ponto do fechamento: valor que aceita literal, token,
        binding e condicional precisa de tipo na tabela; enum fechado já é o
        próprio tipo, e declará-lo como slot abriria a porta para
        ``horizontalAlignment = token(...)`` sem contrato.
        """
        for name in ("horizontal_alignment", "vertical_alignment", "wrap", "elide"):
            cls = (
                LayoutSpec
                if name.startswith("horizontal") or name.startswith("vertical")
                else TextLayoutSpec
            )
            field = cls.__dataclass_fields__[name]
            assert field.type is not Any
        assert "horizontalAlignment" not in CONTRACT_PROPERTY_TYPES
        assert "verticalAlignment" not in CONTRACT_PROPERTY_TYPES
