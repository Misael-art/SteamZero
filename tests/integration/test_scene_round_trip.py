# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""VS-05 — round-trip, contabilidade e diagnósticos sobre as fixtures reais.

O corpus é o mesmo do VS-04, e isso é deliberado: um round-trip provado sobre um
documento sintético prova que o serializador lê o que o serializador escreveu.
Sobre um layout RetroFE de verdade, com token, binding, tradução, condicional e
fonte ausente, ele prova algo.

O gate principal é SEMÂNTICO. Igualdade de bytes como critério transformaria
qualquer mudança de formatação em falso positivo, e um teste que dá falso
positivo é um teste que o time aprende a ignorar. O determinismo textual entra
como gate secundário, por outro motivo: diffs irrelevantes no versionamento.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from steamzero.domain.qml_render_model import AdaptationStatus, to_render_model
from steamzero.domain.resolved_node import ASSET_HANDLE, FontAssetHandle, ResolvedTextNode
from steamzero.domain.retrofe_declarations import (
    DeclarationSet,
    OriginKind,
    collect_declarations,
    derived,
)
from steamzero.domain.retrofe_text_slice import SliceResult, TextSliceCompiler
from steamzero.domain.scene_registry import (
    FORBIDDEN_NAMESPACES,
    DeferredValue,
    ResolutionPhase,
    UnknownPathPolicy,
    default_registries,
    forbidden_namespace,
)
from steamzero.domain.scene_resolver import ResolutionContext, Resolver
from steamzero.domain.scene_serialization import (
    SCHEMA_VERSION,
    SerializationError,
    assert_no_frozen_dynamics,
    canonical_json,
    document,
    parse_document,
    semantic_diff,
    semantic_equal,
)
from steamzero.domain.scene_typing import SourceReference, ValueType, validate_path
from steamzero.domain.scene_value import Verdict, is_pending_value
from steamzero.domain.text_node_builder import FontProvider, LayoutBox, build_text_node

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "retrofe"

PACKAGED_FONTS = frozenset({"Liberation Sans"})
PALETTE = {"accent": "#ffd166"}
TRANSLATIONS = frozenset({"menu.play"})

#: Contagens do VS-04. Ficam explícitas para que uma mudança na fixture apareça
#: como falha aqui em vez de passar despercebida como "o número agora é outro".
EXPECTED_PROPERTIES = {"vs04_positive": 65, "vs04_negative": 73}


def _compile(name: str) -> tuple[Any, SliceResult]:
    path = FIXTURES / f"{name}.xml"
    declarations = collect_declarations(
        path.read_text(encoding="utf-8"), file=f"retrofe/{name}.xml"
    )
    compiler = TextSliceCompiler(
        palette=PALETTE, packaged_fonts=PACKAGED_FONTS, translations=TRANSLATIONS
    )
    return declarations, compiler.compile(declarations)


@pytest.fixture(scope="module", params=sorted(EXPECTED_PROPERTIES))
def corpus(request: pytest.FixtureRequest) -> tuple[str, Any, SliceResult]:
    name = request.param
    declarations, result = _compile(name)
    return name, declarations, result


def _resolver() -> Resolver:
    return Resolver(
        ResolutionContext(
            registries=default_registries(),
            read_model={"game.title": "Chrono Trigger"},
            tokens={"color.accent": "#ffd166"},
            translations={"menu.play": "Jogar"},
            states=frozenset({"focused"}),
        )
    )


def _round_trip(elements: list[Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """normalize(parse(serialize(normalize(parse(source)))))."""
    first = document(elements)
    text = canonical_json(first)
    reparsed = parse_document(json.loads(text))
    return first, document(reparsed)


class TestSemanticRoundTrip:
    def test_the_document_survives_unchanged(self, corpus: tuple[str, Any, SliceResult]) -> None:
        name, _declarations, result = corpus
        before, after = _round_trip(result.elements)
        differences = semantic_diff(before, after)
        assert not differences, f"{name} perdeu significado no round-trip:\n" + "\n".join(
            differences[:20]
        )
        assert semantic_equal(before, after)

    @pytest.mark.parametrize(
        ("label", "key"),
        [
            ("cor alterada", "typography"),
            ("alinhamento removido", "textLayout"),
            ("origem removida", "sourceReference"),
            ("layout removido", "layout"),
        ],
    )
    def test_the_comparison_detects_a_real_loss(
        self, label: str, key: str, corpus: tuple[str, Any, SliceResult]
    ) -> None:
        """Comparação que nunca acusa perda aprova qualquer serializador.

        A mutação se LOCALIZA em vez de assumir posição: na fixture negativa o
        primeiro elemento não declara alinhamento, e uma mutação por índice fixo
        quebrava por estrutura em vez de reprovar por perda.
        """
        _name, _declarations, result = corpus
        before = document(result.elements)
        mutated = copy.deepcopy(before)
        target = next(
            (item for item in mutated["elements"] if key in item),
            None,
        )
        assert target is not None, f"nenhum elemento da fixture tem {key!r}"
        target.pop(key)
        differences = semantic_diff(before, mutated)
        assert differences, f"{label} passou despercebido"

    def test_removing_an_element_is_detected(self, corpus: tuple[str, Any, SliceResult]) -> None:
        _name, _declarations, result = corpus
        before = document(result.elements)
        mutated = copy.deepcopy(before)
        mutated["elements"].pop()
        assert semantic_diff(before, mutated)

    def test_changing_a_colour_is_detected(self, corpus: tuple[str, Any, SliceResult]) -> None:
        _name, _declarations, result = corpus
        before = document(result.elements)
        mutated = copy.deepcopy(before)
        target = next(item for item in mutated["elements"] if "typography" in item)
        target["typography"]["color"] = "#000000"
        assert semantic_diff(before, mutated)

    def test_key_order_is_not_a_difference(self, corpus: tuple[str, Any, SliceResult]) -> None:
        """Dicionário reordenado não é um tema diferente."""
        _name, _declarations, result = corpus
        before = document(result.elements)
        shuffled = json.loads(json.dumps(before))
        shuffled["elements"] = [dict(reversed(list(item.items()))) for item in shuffled["elements"]]
        assert semantic_equal(before, shuffled)

    def test_integer_and_float_are_the_same_dimension(self) -> None:
        """JSON não distingue `1` de `1.0` de forma confiável."""
        assert semantic_equal({"x": 1}, {"x": 1.0})

    def test_colour_case_is_not_a_difference(self) -> None:
        assert semantic_equal({"color": "#F2F6FB"}, {"color": "#f2f6fb"})


class TestDeterministicSerialization:
    def test_the_same_input_produces_the_same_text(
        self, corpus: tuple[str, Any, SliceResult]
    ) -> None:
        """Sem isto, o versionamento enche de diffs que não significam nada."""
        _name, _declarations, result = corpus
        first = document(result.elements)
        assert canonical_json(first) == canonical_json(first)
        assert canonical_json(first) == canonical_json(document(parse_document(first)))

    def test_recompiling_the_fixture_produces_the_same_text(
        self, corpus: tuple[str, Any, SliceResult]
    ) -> None:
        """Compilar duas vezes o mesmo arquivo não pode divergir."""
        name, _declarations, _result = corpus
        _d1, r1 = _compile(name)
        _d2, r2 = _compile(name)
        assert canonical_json(document(r1.elements)) == canonical_json(document(r2.elements))

    def test_the_schema_version_is_recorded(self, corpus: tuple[str, Any, SliceResult]) -> None:
        _name, _declarations, result = corpus
        assert document(result.elements)["schemaVersion"] == SCHEMA_VERSION


class TestDeclarationsSurviveTheDisk:
    """As declarações também vão a disco: sem elas o accounting não reabre."""

    def test_the_set_round_trips_without_losing_identity(
        self, corpus: tuple[str, Any, SliceResult]
    ) -> None:
        _name, declarations, _result = corpus
        restored = DeclarationSet.from_dict(
            json.loads(json.dumps(declarations.to_dict(), ensure_ascii=False))
        )
        assert restored.ids() == declarations.ids()
        assert restored.source_property_count == declarations.source_property_count
        for original in declarations.declarations:
            copy_of = restored.by_id(original.declaration_id)
            assert copy_of is not None
            assert copy_of.origin_kind is original.origin_kind
            assert copy_of.raw_value == original.raw_value
            assert copy_of.source_reference == original.source_reference

    def test_the_origin_kind_survives(self) -> None:
        """`default` voltando como `declared` inflaria a contagem da origem."""
        reference = SourceReference(file="retrofe/x.xml", line=1)
        item = derived(
            "retrofe:x.xml:1:text[0].opacity",
            element="text",
            property_name="opacity",
            value="1.0",
            origin_kind=OriginKind.DEFAULT,
            reference=reference,
        )
        restored = DeclarationSet.from_dict(
            {"file": "retrofe/x.xml", "declarations": [item.to_dict()]}
        )
        assert restored.declarations[0].origin_kind is OriginKind.DEFAULT
        assert restored.source_property_count == 0


class TestIdentityStability:
    def test_the_declaration_ids_are_identical_before_and_after(
        self, corpus: tuple[str, Any, SliceResult]
    ) -> None:
        """O round-trip não pode inventar id para declaração que já existia."""
        name, declarations, _result = corpus
        path = FIXTURES / f"{name}.xml"
        again = collect_declarations(path.read_text(encoding="utf-8"), file=f"retrofe/{name}.xml")
        assert declarations.ids() == again.ids()

    def test_the_source_reference_survives_the_document(
        self, corpus: tuple[str, Any, SliceResult]
    ) -> None:
        """Sem a origem, o diagnóstico deixa de ser acionável depois de salvar."""
        _name, _declarations, result = corpus
        _before, after = _round_trip(result.elements)
        for element in after["elements"]:
            reference = element.get("sourceReference")
            assert reference is not None, element["id"]
            assert reference["file"].endswith(".xml")
            assert reference["line"] > 0

    def test_element_ids_are_preserved(self, corpus: tuple[str, Any, SliceResult]) -> None:
        _name, _declarations, result = corpus
        before, after = _round_trip(result.elements)
        assert [item["id"] for item in before["elements"]] == [
            item["id"] for item in after["elements"]
        ]

    def test_the_deferred_contract_keeps_its_fields(self) -> None:
        """`expectedType` e `resolutionPhase` são o que permite validar sem resolver."""
        deferred = DeferredValue(
            source_kind="bind",
            source_path="game.title",
            expected_type=ValueType.STRING,
            resolution_phase=ResolutionPhase.RUNTIME,
        )
        payload = deferred.to_dict()
        assert payload["sourceKind"] == "bind"
        assert payload["sourcePath"] == "game.title"
        assert payload["expectedType"] == "string"
        assert payload["resolutionPhase"] == "runtime"


class TestIdempotentAccounting:
    def test_the_counts_match_the_fixture(self, corpus: tuple[str, Any, SliceResult]) -> None:
        name, declarations, result = corpus
        accounting = result.accounting(declarations)
        assert accounting["sourcePropertyCount"] == EXPECTED_PROPERTIES[name]

    def test_recompiling_does_not_add_a_second_verdict(
        self, corpus: tuple[str, Any, SliceResult]
    ) -> None:
        """Reexecutar não pode julgar de novo o que já foi julgado.

        Um segundo veredito para a mesma declaração faria a cobertura passar de
        100% sem significar nada, e esconderia qual dos dois valeu.
        """
        name, _declarations, _result = corpus
        first_declarations, first = _compile(name)
        second_declarations, second = _compile(name)
        assert first.accounting(first_declarations) == second.accounting(second_declarations)
        assert second.duplicates == []

    def test_coverage_is_total_with_nothing_unaccounted(
        self, corpus: tuple[str, Any, SliceResult]
    ) -> None:
        _name, declarations, result = corpus
        accounting = result.accounting(declarations)
        assert accounting["accountingCoverage"] == 1.0
        assert accounting["unaccounted"] == []
        assert accounting["duplicateVerdicts"] == []
        assert accounting["sourcePropertyCount"] == accounting["translationVerdictCount"]

    def test_a_repeated_judgement_is_reported_not_swallowed(
        self, corpus: tuple[str, Any, SliceResult]
    ) -> None:
        """Sobrescrever esconderia que dois caminhos julgaram a mesma coisa."""
        _name, declarations, result = corpus
        first = declarations.declarations[0]
        result.record(first, Verdict.INVALID, detail="segundo julgamento forçado")
        assert first.declaration_id in result.duplicates
        assert result.accounting(declarations)["duplicateVerdicts"] != []
        # Devolve o estado para não contaminar os demais testes do módulo.
        result.duplicates.clear()


class TestVerdictsAreNotRewritten:
    def test_every_verdict_kind_survives_recompilation(
        self, corpus: tuple[str, Any, SliceResult]
    ) -> None:
        """`fallback` virando `exact` mentiria sobre a fidelidade da importação."""
        name, declarations, result = corpus
        again_declarations, again = _compile(name)
        for key, verdict in result.verdicts.items():
            assert again.verdicts[key] is verdict, key
        assert result.log.counts() == again.log.counts()
        assert declarations.ids() == again_declarations.ids()

    def test_the_negative_fixture_keeps_its_policy_refusal(self) -> None:
        """`ignoredByPolicy` não pode degradar para `unsupported`.

        Um vira recusa deliberada; o outro vira fila de trabalho. Confundir os
        dois faria alguém implementar acesso ao número de série do host.
        """
        _declarations, result = _compile("vs04_negative")
        assert result.log.counts().get("ignoredByPolicy", 0) == 1

    def test_the_positive_fixture_keeps_its_font_fallback(self) -> None:
        _declarations, result = _compile("vs04_positive")
        assert result.log.counts().get("fallback", 0) >= 1


class TestDegradationsSurvive:
    def _degraded(self, element_id: str) -> Any:
        _declarations, result = _compile("vs04_positive")
        element = next(item for item in result.elements if item.id == element_id)
        before, after = _round_trip([element])
        assert semantic_equal(before, after)
        reparsed = parse_document(after)[0]
        node = build_text_node(
            reparsed,
            resolver=_resolver(),
            box=LayoutBox(1920, 1080),
            fonts=FontProvider({name: name for name in PACKAGED_FONTS}),
        )
        return to_render_model(node)

    def test_a_font_substitution_keeps_its_full_record(self) -> None:
        """O registro precisa sobreviver ao disco, ou o relatório perde a causa."""
        result = self._degraded("text-8")
        assert result.status is AdaptationStatus.DEGRADED
        payload = result.diagnostics[0].to_dict()
        for required in ("originalValue", "resolvedValue", "fallbackKind", "reason"):
            assert required in payload, required
        assert payload["originalValue"] == "Gilroy Display"
        assert payload["sourceReference"]["file"].endswith(".xml")

    def test_a_clamp_keeps_both_values(self) -> None:
        from dataclasses import replace

        node = replace(ResolvedTextNode(id="x", text="oi"), opacity=1.5)
        payload = to_render_model(node).diagnostics[0].to_dict()
        assert payload["fallbackKind"] == "clamp"
        assert payload["originalValue"] == 1.5
        assert payload["resolvedValue"] == 1.0


class TestDynamicValuesAreNotFrozen:
    """A verificação mais importante do VS-05.

    Um token que volta como a cor que ele resolvia congelaria o tema no estado
    da execução que serializou. Trocar o esquema de cores deixaria de funcionar,
    e o defeito só apareceria para quem trocasse — muito depois, sem ligação
    aparente com a causa.
    """

    def test_nothing_dynamic_becomes_literal(self, corpus: tuple[str, Any, SliceResult]) -> None:
        _name, _declarations, result = corpus
        before, after = _round_trip(result.elements)
        frozen = assert_no_frozen_dynamics(before, after)
        assert not frozen, "\n".join(frozen)

    @pytest.mark.parametrize(
        ("element_id", "expected"),
        [
            ("text-4", {"token": "color.accent"}),
            ("reloadableText-6", {"bind": "game.title"}),
            ("text-7", {"text": "menu.play", "fallback": "menu.play"}),
        ],
    )
    def test_the_pending_form_is_still_pending_after_the_round_trip(
        self, element_id: str, expected: dict[str, Any]
    ) -> None:
        _declarations, result = _compile("vs04_positive")
        element = next(item for item in result.elements if item.id == element_id)
        reparsed = parse_document(document([element]))[0]
        candidates = [reparsed.text_content]
        if reparsed.typography is not None:
            candidates.append(reparsed.typography.color)
        assert expected in candidates, candidates

    def test_a_condition_is_still_a_condition(self) -> None:
        _declarations, result = _compile("vs04_positive")
        element = next(item for item in result.elements if item.id == "text-5")
        reparsed = parse_document(document([element]))[0]
        assert reparsed.typography is not None
        colour = reparsed.typography.color
        assert is_pending_value(colour)
        assert colour["when"] == {"op": "state", "state": "focused"}

    def test_the_frozen_detector_catches_a_real_freeze(self) -> None:
        """Detector que nunca acusa aprova qualquer serializador."""
        before = {"typography": {"color": {"token": "color.accent"}}}
        after = {"typography": {"color": "#ffd166"}}
        frozen = assert_no_frozen_dynamics(before, after)
        assert frozen and "congelou" in frozen[0]


class TestResolvedDtosAreDerivedNotCanonical:
    def test_a_resolved_node_carries_no_pending_value(self) -> None:
        _declarations, result = _compile("vs04_positive")
        for element in result.elements:
            node = build_text_node(
                element,
                resolver=_resolver(),
                box=LayoutBox(1920, 1080),
                fonts=FontProvider({name: name for name in PACKAGED_FONTS}),
            )
            for item in node.to_dict().values():
                assert not is_pending_value(item), item

    def test_the_canonical_document_is_the_contract_not_the_dto(self) -> None:
        """O DTO resolvido é produto descartável de UMA execução.

        Guardá-lo como documento do tema congelaria binding e token no estado
        daquela execução — o mesmo defeito que o detector acima procura, só que
        cometido de propósito.
        """
        _declarations, result = _compile("vs04_positive")
        payload = document(result.elements)
        assert "elements" in payload
        text = canonical_json(payload)
        assert "color.accent" in text, "o token precisa estar no documento"
        assert '"fontAssetHandle"' not in text, "handle é do DTO resolvido, não do contrato"


class TestNamespacePolicyIsConsistent:
    def test_no_published_path_is_also_forbidden(self) -> None:
        """`system.time` não pode ser legítimo e proibido ao mesmo tempo.

        Foi exatamente esse conflito que existiu entre o importador RetroFE e os
        registros padrão, e ele passou despercebido porque as duas listas viviam
        em módulos diferentes.
        """
        registries = default_registries()
        published = (
            set(registries.bindings.types)
            | set(registries.tokens.types)
            | set(registries.settings.types)
            | set(registries.assets.types)
        )
        clashes = sorted(path for path in published if forbidden_namespace(path) is not None)
        assert clashes == [], f"caminhos publicados E proibidos: {clashes}"

    def test_a_legitimate_system_path_is_allowed(self) -> None:
        assert forbidden_namespace("system.time") is None

    @pytest.mark.parametrize("namespace", FORBIDDEN_NAMESPACES)
    def test_each_forbidden_namespace_is_detected(self, namespace: str) -> None:
        assert forbidden_namespace(f"{namespace}whatever") == namespace

    def test_policy_wins_over_unknown_path(self) -> None:
        """A ordem é o defeito que o VS-04 encontrou.

        Quando a busca no registro vinha primeiro, um caminho proibido que
        também fosse desconhecido saía como `unsupported` — e `unsupported` vira
        trabalho futuro.
        """
        check = default_registries().check_deferred(
            DeferredValue(
                source_kind="bind",
                source_path="host.serialNumber",
                expected_type=ValueType.STRING,
                resolution_phase=ResolutionPhase.RUNTIME,
            )
        )
        assert check.ok is False
        assert check.policy is UnknownPathPolicy.FORBIDDEN

    def test_an_allowed_namespace_with_an_unknown_field_is_not_a_policy_refusal(self) -> None:
        """Campo desconhecido em namespace permitido é limitação, não recusa."""
        check = default_registries().check_deferred(
            DeferredValue(
                source_kind="bind",
                source_path="game.inexistente",
                expected_type=ValueType.STRING,
                resolution_phase=ResolutionPhase.RUNTIME,
            )
        )
        assert check.policy is not UnknownPathPolicy.FORBIDDEN


class TestOpaqueHandlesSurvive:
    @pytest.mark.parametrize(
        "family",
        [
            "A B",
            "A/B",
            "A-B",
            "Liberation Sans",
            "Ação Coração",
            "ゴシック",
            "MiXeD CaSe",
            "mixed case",
            "a" * 400,
        ],
    )
    def test_the_handle_is_valid_and_survives_serialization(self, family: str) -> None:
        handle = FontProvider({family: family}).resolve(family)
        assert handle is not None
        assert handle.handle is not None
        assert ASSET_HANDLE.match(handle.handle)
        restored = FontAssetHandle(
            key=handle.key,
            handle=handle.handle,
            origin=handle.origin,
            requested_family=handle.requested_family,
            resolved_family=handle.resolved_family,
        )
        assert restored.handle == handle.handle, "o handle não pode ser regenerado ao ler"

    @pytest.mark.parametrize(
        ("first", "second"),
        [("A B", "A/B"), ("A B", "A-B"), ("A/B", "A-B"), ("MiXeD CaSe", "mixed case")],
    )
    def test_similar_families_never_collide(self, first: str, second: str) -> None:
        """O slug sozinho colide. É o hash que separa."""
        left = FontProvider({first: first}).resolve(first)
        right = FontProvider({second: second}).resolve(second)
        assert left is not None
        assert right is not None
        assert left.handle != right.handle

    def test_the_family_cannot_be_reconstructed_from_the_handle(self) -> None:
        """O handle é opaco por contrato.

        Um consumidor que tentasse extrair a família do slug acertaria em
        "Gilroy" e erraria em "Ação Coração", que vira `font-<hash>`.
        """
        handle = FontProvider({"Ação Coração": "Ação Coração"}).resolve("Ação Coração")
        assert handle is not None
        assert handle.handle is not None
        assert "Ação" not in handle.handle
        assert handle.resolved_family == "Ação Coração", "o nome legível vive ao lado"


class TestCorruptionIsRefused:
    def _valid(self) -> dict[str, Any]:
        _declarations, result = _compile("vs04_positive")
        return document(result.elements[:1])

    def test_an_incompatible_schema_version_is_refused(self) -> None:
        payload = self._valid()
        payload["schemaVersion"] = 999
        with pytest.raises(SerializationError, match="schemaVersion"):
            parse_document(payload)

    def test_a_missing_schema_version_is_refused(self) -> None:
        payload = self._valid()
        del payload["schemaVersion"]
        with pytest.raises(SerializationError, match="schemaVersion"):
            parse_document(payload)

    def test_a_missing_elements_list_is_refused(self) -> None:
        with pytest.raises(SerializationError, match="elements"):
            parse_document({"schemaVersion": SCHEMA_VERSION})

    @pytest.mark.parametrize("field", ["id", "type"])
    def test_a_missing_required_field_is_refused(self, field: str) -> None:
        payload = self._valid()
        del payload["elements"][0][field]
        with pytest.raises(SerializationError, match=field):
            parse_document(payload)

    def test_an_unknown_field_is_refused(self) -> None:
        """Ignorar em silêncio produziria um tema incompleto que renderiza."""
        payload = self._valid()
        payload["elements"][0]["typography"]["inventado"] = 1
        with pytest.raises(SerializationError, match="desconhecido"):
            parse_document(payload)

    def test_an_unknown_alignment_is_refused(self) -> None:
        payload = self._valid()
        payload["elements"][0].setdefault("textLayout", {})["horizontalAlignment"] = "diagonal"
        with pytest.raises(SerializationError, match="alinhamento"):
            parse_document(payload)

    @pytest.mark.parametrize("kind", ["em", "rem", "vw", "logicalpx"])
    def test_an_unknown_dimension_unit_is_refused(self, kind: str) -> None:
        payload = self._valid()
        payload["elements"][0]["layout"]["x"] = {"kind": kind, "value": 10}
        with pytest.raises(ValueError, match="unidade fora do contrato"):
            parse_document(payload)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), True])
    def test_a_non_finite_dimension_is_refused(self, bad: Any) -> None:
        payload = self._valid()
        payload["elements"][0]["layout"]["x"] = {"kind": "logicalPx", "value": bad}
        with pytest.raises(ValueError, match="exige número"):
            parse_document(payload)

    def test_a_malformed_handle_is_refused(self) -> None:
        with pytest.raises(ValueError, match="gramática"):
            FontAssetHandle(key="x", handle="/home/user/font.ttf")

    def test_a_pending_value_in_a_resolved_dto_is_refused(self) -> None:
        node = ResolvedTextNode(id="x", text="oi")
        object.__setattr__(node, "color", {"token": "color.accent"})
        result = to_render_model(node)
        assert result.status is AdaptationStatus.FAILED
        assert result.model is None

    def test_an_element_that_is_not_a_mapping_is_refused(self) -> None:
        with pytest.raises((SerializationError, TypeError, AttributeError)):
            parse_document({"schemaVersion": SCHEMA_VERSION, "elements": ["texto solto"]})

    def test_a_duplicate_declaration_id_is_visible(self) -> None:
        """Ids que colidem fariam um veredito sobrescrever o outro."""
        declarations, _result = _compile("vs04_positive")
        ids = [item.declaration_id for item in declarations.declarations]
        assert len(ids) == len(set(ids))

    @pytest.mark.parametrize("bad", ["vermelho", "#fff", "rgba(1,2,3,0.5)", "", 42])
    def test_a_corrupt_colour_is_refused_on_read(self, bad: Any) -> None:
        """Verificado antes de escrever o teste: isto ERA aceito.

        Um documento com `"color": "vermelho"` passava pela leitura e só falhava
        no adapter, longe da causa — ou nunca, num caminho que não passasse por
        ele.
        """
        payload = self._valid()
        payload["elements"][0].setdefault("typography", {})["color"] = bad
        with pytest.raises(SerializationError, match="cor inválida"):
            parse_document(payload)

    def test_a_pending_colour_still_crosses_the_read(self) -> None:
        """Token resolve depois; validá-lo na leitura exigiria resolver ali."""
        payload = self._valid()
        payload["elements"][0].setdefault("typography", {})["color"] = {"token": "color.accent"}
        element = parse_document(payload)[0]
        assert element.typography is not None
        assert element.typography.color == {"token": "color.accent"}

    def test_a_duplicate_id_is_refused_when_reading_declarations(self) -> None:
        """Aceitar na leitura criaria o estado duplicado a partir de um arquivo."""
        declarations, _result = _compile("vs04_positive")
        payload = declarations.to_dict()
        payload["declarations"].append(payload["declarations"][0])
        with pytest.raises(ValueError, match="sourceDeclarationId duplicado"):
            DeclarationSet.from_dict(payload)

    def test_a_theme_cannot_read_another_theme_namespace(self) -> None:
        """Namespace privado de outro tema é recusa, não limitação."""
        with pytest.raises(ValueError, match="não pode acessar recurso"):
            validate_path("theme.outroTema.cor", theme_id="meuTema")

    def test_a_theme_reads_its_own_namespace(self) -> None:
        validate_path("theme.meuTema.cor", theme_id="meuTema")


class TestScopeLimitsStayGreen:
    def test_only_text_elements_are_compiled(self, corpus: tuple[str, Any, SliceResult]) -> None:
        _name, _declarations, result = corpus
        assert all(element.type == "text" for element in result.elements)

    def test_the_full_corpus_is_not_migrated(self, corpus: tuple[str, Any, SliceResult]) -> None:
        _name, declarations, _result = corpus
        assert declarations.source_property_count < 388

    def test_no_mask_is_implemented(self, corpus: tuple[str, Any, SliceResult]) -> None:
        _name, _declarations, result = corpus
        text = canonical_json(document(result.elements))
        for reserved in ("clipSpec", "maskStack", "hitTestShape"):
            assert reserved not in text, f"{reserved} é reserva do P0-08, não implementação"

    def test_no_qt_type_reaches_the_document(self, corpus: tuple[str, Any, SliceResult]) -> None:
        _name, _declarations, result = corpus
        text = canonical_json(document(result.elements))
        for marker in ("AlignLeft", "AlignHCenter", "PySide", "QQuick", "Qt."):
            assert marker not in text, f"{marker} pertence ao adapter, não ao IR"

    def test_no_scene_tree_is_introduced(self, corpus: tuple[str, Any, SliceResult]) -> None:
        """A fatia é plana. Filhos entrariam sem que ninguém tivesse projetado."""
        _name, _declarations, result = corpus
        for element in result.elements:
            assert not hasattr(element, "children")
            assert "children" not in element.to_dict()


class TestDiagnosticsAreStructured:
    def test_a_diagnostic_carries_more_than_prose(self) -> None:
        """Texto humano não pode ser a única informação.

        Um relatório que só tem frase obriga a interpretar português para
        automatizar qualquer coisa em cima dele.
        """
        from dataclasses import replace

        node = replace(ResolvedTextNode(id="gameTitle", text="oi"), opacity=1.5)
        payload = to_render_model(node).diagnostics[0].to_dict()
        for required in ("code", "target", "severity", "reason", "fallbackKind"):
            assert required in payload, required
        assert payload["code"].startswith("QML-ADAPTER-")

    def test_every_verdict_maps_back_to_its_declaration(
        self, corpus: tuple[str, Any, SliceResult]
    ) -> None:
        _name, declarations, result = corpus
        for entry in result.log.entries:
            declaration = declarations.by_id(entry.source)
            assert declaration is not None, entry.source
            assert declaration.source_reference.line

    def test_the_translation_log_is_serializable(
        self, corpus: tuple[str, Any, SliceResult]
    ) -> None:
        _name, _declarations, result = corpus
        payload = json.loads(json.dumps(result.log.to_dict(), ensure_ascii=False))
        assert payload["counts"]
        assert len(payload["translations"]) == len(result.log.entries)
