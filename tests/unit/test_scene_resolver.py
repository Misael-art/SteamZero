# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Etapa B do P0-03 — resolver, cache e invalidação por dependência.

Três propriedades importam mais que a resolução em si:

O grafo permite invalidar por ramo. Sem ele, mudar uma cor recomputaria os 866
elementos que a varredura mediu.

O ciclo perigoso não é `token → token`, é `token → setting → token`: atravessa
sistemas e escapa de checagem local. O diagnóstico precisa mostrar o caminho,
porque saber que existe ciclo sem saber onde não ajuda ninguém.

A chave de cache é composta. Ignorar locale ou perfil de acessibilidade produz
cache que devolve a resposta certa para a pergunta errada — pior que não ter.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from steamzero.domain import scene_value as value
from steamzero.domain.scene_registry import default_registries
from steamzero.domain.scene_resolver import (
    DIAG_CYCLE,
    DIAG_MISSING_ASSET,
    DIAG_TYPE,
    DIAG_UNKNOWN_BINDING,
    DIAG_UNKNOWN_TOKEN,
    Generations,
    ResolutionContext,
    ResolutionError,
    Resolver,
)
from steamzero.domain.scene_typing import SourceReference, ValueType


def _context(**overrides: object) -> ResolutionContext:
    base: dict[str, object] = {
        "registries": default_registries(),
        "tokens": {
            "color.text.primary": {"token": "color.palette.neutral.100"},
            "color.palette.neutral.100": "#f2f6fb",
            "color.accent": "#13bdf2",
        },
        "read_model": {
            "game.title": "Chrono Trigger",
            "game.year": 1995,
            "game.favorite": True,
        },
        "translations": {"ui.play": "Jogar"},
    }
    base.update(overrides)
    return ResolutionContext(**base)  # type: ignore[arg-type]


class TestResolutionOfEachOrigin:
    def test_literal(self) -> None:
        resolver = Resolver(_context())
        assert resolver.resolve("#ff0000", ValueType.COLOR, target="a").value == "#ff0000"

    def test_token_chain_is_followed(self) -> None:
        resolver = Resolver(_context())
        result = resolver.resolve(value.token("color.text.primary"), ValueType.COLOR, target="a")
        assert result.value == "#f2f6fb"
        assert result.dependencies == {
            "token:color.text.primary",
            "token:color.palette.neutral.100",
        }

    def test_binding(self) -> None:
        resolver = Resolver(_context())
        result = resolver.resolve(value.bind("game.title"), ValueType.STRING, target="a")
        assert result.value == "Chrono Trigger"
        assert result.phase.value == "runtime"

    def test_translation(self) -> None:
        resolver = Resolver(_context())
        assert resolver.resolve(value.localized("ui.play"), ValueType.STRING, target="a").value == (
            "Jogar"
        )

    def test_missing_translation_uses_the_authored_fallback(self) -> None:
        """Degradação prevista: o autor escreveu o texto de origem para isto."""
        resolver = Resolver(_context())
        result = resolver.resolve(
            value.localized("ui.inexistente", fallback="Play"), ValueType.STRING, target="a"
        )
        assert result.value == "Play"
        assert result.used_fallback is True

    def test_conditional_picks_the_branch(self) -> None:
        resolver = Resolver(_context())
        candidate = value.when(
            value.compare("equals", value.bind("game.favorite"), True), "#ffd700", "#ffffff"
        )
        result = resolver.resolve(candidate, ValueType.COLOR, target="a")
        assert result.value == "#ffd700"
        assert result.phase.value == "runtime", "condicional muda com o estado"

    def test_state_condition_is_evaluated(self) -> None:
        resolver = Resolver(_context(states=frozenset({"focused"})))
        candidate = value.when(value.in_state("focused"), "#ffffff", "#888888")
        assert resolver.resolve(candidate, ValueType.COLOR, target="a").value == "#ffffff"

    def test_capability_condition_is_evaluated(self) -> None:
        resolver = Resolver(_context(capabilities=frozenset({"video.hdr"})))
        candidate = value.when(value.has_capability("video.hdr"), 1.0, 0.5)
        assert resolver.resolve(candidate, ValueType.NUMBER, target="a").value == 1.0


class TestDependencyInvalidation:
    """Mudança localizada não pode recompilar a cena inteira."""

    def _prepared(self) -> Resolver:
        resolver = Resolver(_context())
        resolver.resolve(value.token("color.text.primary"), ValueType.COLOR, target="title.color")
        resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="badge.color")
        return resolver

    def test_only_dependents_are_invalidated(self) -> None:
        resolver = self._prepared()
        affected = resolver.invalidate("token:color.palette.neutral.100")
        assert affected == {"title.color"}
        assert "badge.color" not in affected

    def test_invalidation_is_transitive(self) -> None:
        """A paleta alimenta o token que alimenta o elemento."""
        resolver = self._prepared()
        assert "title.color" in resolver.invalidate("token:color.palette.neutral.100")

    def test_unrelated_dependency_invalidates_nothing(self) -> None:
        assert self._prepared().invalidate("token:color.inexistente") == frozenset()

    def test_second_resolution_hits_the_cache(self) -> None:
        resolver = Resolver(_context())
        for _ in range(2):
            resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="a")
        assert resolver.stats.hits == 1
        assert resolver.stats.misses == 1

    def test_resolution_after_invalidation_recomputes(self) -> None:
        resolver = Resolver(_context())
        resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="a")
        resolver.invalidate("token:color.accent")
        resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="a")
        assert resolver.stats.misses == 2

    def test_graph_reports_dependencies_of_a_target(self) -> None:
        resolver = self._prepared()
        assert "token:color.accent" in resolver.graph.dependencies_of("badge.color")


class TestCacheKeyFollowsTheDependencies:
    """CONTRATO ALTERADO no VS-06, e a mudança é o ponto da etapa.

    Antes: qualquer geração diferente invalidava tudo, porque a chave continha
    todas elas. Era correto e caríssimo — trocar de idioma recompunha as 65
    propriedades da fixture, incluindo as que só têm literais.

    Agora a chave olha só as gerações que a propriedade REALMENTE usa. O teste
    ficou mais forte, não mais fraco: antes ele só afirmava que a geração
    invalida; agora afirma também que uma geração não relacionada NÃO invalida,
    que é a metade onde mora o desperdício.
    """

    def _resolve_twice(self, dependency: Any, changed: dict, **context_args: Any) -> int:
        context = _context(**context_args)
        resolver = Resolver(context)
        resolver.resolve(dependency, ValueType.COLOR, target="a")
        context.generations = Generations(**changed)
        resolver.resolve(dependency, ValueType.COLOR, target="a")
        return resolver.stats.misses

    @pytest.mark.parametrize("changed", [{"tokens": 1}, {"theme": 1}])
    def test_a_generation_the_value_uses_invalidates_it(self, changed: dict) -> None:
        assert self._resolve_twice(value.token("color.accent"), changed) == 2

    @pytest.mark.parametrize(
        "changed",
        [
            {"locale": "en-US"},
            {"accessibility": "highContrast"},
            {"display": "tv"},
            {"read_model": 1},
            {"translation_catalog": 1},
            {"asset_registry": 1},
            {"state_variant": "focused"},
        ],
    )
    def test_an_unrelated_generation_does_not_invalidate(self, changed: dict) -> None:
        """Uma cor de token não muda porque o idioma mudou."""
        assert self._resolve_twice(value.token("color.accent"), changed) == 1

    def test_a_literal_survives_every_generation_change(self) -> None:
        """Literal não depende de nada. Nada que mude o alcança."""
        context = _context()
        resolver = Resolver(context)
        resolver.resolve("#ffffff", ValueType.COLOR, target="a")
        context.generations = Generations(
            theme_settings=9,
            tokens=9,
            read_model=9,
            translation_catalog=9,
            asset_registry=9,
            locale="en-US",
            accessibility="highContrast",
            display="tv",
            state_variant="focused",
        )
        resolver.resolve("#ffffff", ValueType.COLOR, target="a")
        assert resolver.stats.misses == 1
        assert resolver.stats.hits == 1

    def test_reloading_the_theme_invalidates_even_a_literal(self) -> None:
        """`theme` entra em toda impressão: recarregar troca o documento inteiro."""
        context = _context()
        resolver = Resolver(context)
        resolver.resolve("#ffffff", ValueType.COLOR, target="a")
        context.generations = Generations(theme=1)
        resolver.resolve("#ffffff", ValueType.COLOR, target="a")
        assert resolver.stats.misses == 2

    def test_a_binding_follows_the_read_model_generation(self) -> None:
        context = _context(read_model={"game.title": "Chrono"})
        resolver = Resolver(context)
        resolver.resolve(value.bind("game.title"), ValueType.STRING, target="a")
        context.generations = Generations(read_model=1)
        resolver.resolve(value.bind("game.title"), ValueType.STRING, target="a")
        assert resolver.stats.misses == 2

    def test_a_translation_follows_locale_and_catalog(self) -> None:
        for changed in ({"locale": "en-US"}, {"translation_catalog": 1}):
            context = _context(translations={"menu.play": "Jogar"})
            resolver = Resolver(context)
            resolver.resolve(value.localized("menu.play"), ValueType.STRING, target="a")
            context.generations = Generations(**changed)
            resolver.resolve(value.localized("menu.play"), ValueType.STRING, target="a")
            assert resolver.stats.misses == 2, changed

    def test_the_theme_identity_is_part_of_the_key(self) -> None:
        """Dois temas podem declarar o mesmo `gameTitle.color`.

        Sem a identidade na chave, o segundo tema serviria o valor do primeiro —
        e o sintoma seria uma cor teimosa que não muda ao trocar de tema.
        """
        context = _context(tokens={"color.accent": "#111111"})
        context.theme_id = "temaA"
        resolver = Resolver(context)
        first = resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="a")
        context.theme_id = "temaB"
        context.tokens = {"color.accent": "#222222"}
        second = resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="a")
        assert first.value != second.value


class TestCycleDetection:
    def test_cycle_across_origins_is_detected(self) -> None:
        """token → setting → token: atravessa sistemas e escapa de checagem local."""
        context = _context(
            tokens={"color.a": {"setting": "accent"}, "color.b": {"token": "color.a"}},
            settings={"accent": {"token": "color.b"}},
        )
        with pytest.raises(ResolutionError) as excinfo:
            Resolver(context).resolve(value.token("color.a"), ValueType.COLOR, target="a")
        assert excinfo.value.code == DIAG_CYCLE

    def test_cycle_diagnostic_shows_the_full_path(self) -> None:
        """Saber que existe ciclo sem saber onde não ajuda ninguém."""
        context = _context(
            tokens={"color.a": {"setting": "accent"}, "color.b": {"token": "color.a"}},
            settings={"accent": {"token": "color.b"}},
        )
        with pytest.raises(ResolutionError) as excinfo:
            Resolver(context).resolve(value.token("color.a"), ValueType.COLOR, target="a")
        assert excinfo.value.to_dict()["cyclePath"] == [
            "token:color.a",
            "setting:accent",
            "token:color.b",
            "token:color.a",
        ]

    def test_self_referencing_token_is_a_cycle(self) -> None:
        context = _context(tokens={"color.a": {"token": "color.a"}})
        with pytest.raises(ResolutionError) as excinfo:
            Resolver(context).resolve(value.token("color.a"), ValueType.COLOR, target="a")
        assert excinfo.value.code == DIAG_CYCLE


class TestDiagnosticsCarryOrigin:
    def test_error_includes_file_and_line(self) -> None:
        resolver = Resolver(_context())
        reference = SourceReference("layouts/arcade.xml", line=183, element="gameTitle")
        with pytest.raises(ResolutionError) as excinfo:
            resolver.resolve(
                value.token("color.inexistente"),
                ValueType.COLOR,
                target="a",
                reference=reference,
            )
        assert "layouts/arcade.xml:183" in str(excinfo.value)
        assert excinfo.value.to_dict()["sourceReference"]["element"] == "gameTitle"

    @pytest.mark.parametrize(
        ("candidate", "code"),
        [
            (value.token("color.inexistente"), DIAG_UNKNOWN_TOKEN),
            (value.bind("game.inexistente"), DIAG_UNKNOWN_BINDING),
        ],
    )
    def test_stable_codes(self, candidate: dict, code: str) -> None:
        with pytest.raises(ResolutionError) as excinfo:
            Resolver(_context()).resolve(candidate, ValueType.STRING, target="a")
        assert excinfo.value.code == code

    def test_type_mismatch_from_registry_is_refused(self) -> None:
        """fontSize = binding(game.title), sem fallback."""
        with pytest.raises(ResolutionError) as excinfo:
            Resolver(_context()).resolve(value.bind("game.title"), ValueType.NUMBER, target="a")
        assert excinfo.value.code == DIAG_TYPE

    def test_missing_asset_is_reported(self) -> None:
        context = _context(assets=frozenset({"assets/ok.png"}))
        with pytest.raises(ResolutionError) as excinfo:
            Resolver(context).resolve(value.asset("assets/sumiu.png"), ValueType.MEDIA, target="a")
        assert excinfo.value.code == DIAG_MISSING_ASSET


class TestFallbackIsDeterministic:
    def test_unknown_token_falls_back(self) -> None:
        resolver = Resolver(_context())
        result = resolver.resolve(
            value.token("color.inexistente", fallback="#000000"), ValueType.COLOR, target="a"
        )
        assert result.value == "#000000"
        assert result.used_fallback is True

    def test_fallback_is_type_checked(self) -> None:
        with pytest.raises(ResolutionError):
            Resolver(_context()).resolve(
                value.token("color.inexistente", fallback="naoEhCor"),
                ValueType.COLOR,
                target="a",
            )

    def test_excessive_depth_is_refused(self) -> None:
        tokens = {f"color.t{index}": {"token": f"color.t{index + 1}"} for index in range(12)}
        with pytest.raises(ResolutionError) as excinfo:
            Resolver(_context(tokens=tokens)).resolve(
                value.token("color.t0"), ValueType.COLOR, target="a"
            )
        assert excinfo.value.code in {"THEME-RESOLUTION-DEPTH-002", DIAG_UNKNOWN_TOKEN}


class TestNamespaceIsEnforcedAtResolution:
    def test_other_theme_namespace_is_refused(self) -> None:
        context = _context(theme_id="neonGrid")
        with pytest.raises(ResolutionError):
            Resolver(context).resolve(
                value.bind("theme.outroTema.cor"), ValueType.COLOR, target="a"
            )


class TestTernaryConditionLogic:
    """Correção obrigatória: incompatibilidade não pode virar `false`.

    Tratar como falso selecionaria o ramo `otherwise` e produziria uma interface
    de aparência válida e SEMANTICAMENTE ERRADA — pior que uma que falha
    visivelmente.
    """

    def _incompatible(self) -> dict:
        return value.when(
            value.compare("greaterThan", value.bind("game.title"), 1990),
            "#ff0000",
            "#00ff00",
        )

    def test_incompatible_comparison_does_not_choose_otherwise(self) -> None:
        resolver = Resolver(_context())
        result = resolver.resolve(self._incompatible(), ValueType.COLOR, target="a")
        assert result.value != "#00ff00", "não pode cair no ramo else sem base"
        assert result.used_fallback is True

    def test_indeterminate_uses_the_declared_fallback(self) -> None:
        resolver = Resolver(_context())
        candidate = dict(self._incompatible())
        candidate["fallback"] = "#123456"
        result = resolver.resolve(candidate, ValueType.COLOR, target="a")
        assert result.value == "#123456"

    def test_indeterminate_without_fallback_uses_the_safe_default(self) -> None:
        """Transparente: não desenha nada visualmente errado."""
        resolver = Resolver(_context())
        result = resolver.resolve(self._incompatible(), ValueType.COLOR, target="a")
        assert result.value == "#00000000"

    def test_structured_diagnostic_is_emitted(self) -> None:
        resolver = Resolver(_context())
        reference = SourceReference("layouts/arcade.xml", line=183, element="gameTitle")
        resolver.resolve(
            self._incompatible(), ValueType.COLOR, target="title.fontSize", reference=reference
        )
        emitted = resolver.diagnostics.to_list()
        assert emitted[0]["code"] == "THEME-CONDITION-TYPE-MISMATCH-001"
        assert emitted[0]["property"] == "title.fontSize"
        assert emitted[0]["resolution"] == "fallback"
        assert emitted[0]["sourceReference"]["line"] == 183

    def test_diagnostic_is_deduplicated(self) -> None:
        """Uma lista de 500 itens emitiria 500 avisos idênticos por frame."""
        resolver = Resolver(_context())
        for _ in range(50):
            resolver._cache.clear()
            resolver.resolve(self._incompatible(), ValueType.COLOR, target="a")
        assert len(resolver.diagnostics.entries) == 1

    def test_indeterminate_propagates_through_and(self) -> None:
        """`and` só é falso se um operando for comprovadamente falso."""
        resolver = Resolver(_context(states=frozenset()))
        candidate = value.when(
            value.all_of(
                value.compare("greaterThan", value.bind("game.title"), 1990),
                value.in_state("focused"),
            ),
            "#ff0000",
            "#00ff00",
        )
        result = resolver.resolve(candidate, ValueType.COLOR, target="a")
        # state=focused é FALSO comprovado, então o `and` inteiro é falso.
        assert result.value == "#00ff00"

    def test_indeterminate_survives_when_nothing_is_conclusive(self) -> None:
        resolver = Resolver(_context(states=frozenset({"focused"})))
        candidate = value.when(
            value.all_of(
                value.compare("greaterThan", value.bind("game.title"), 1990),
                value.in_state("focused"),
            ),
            "#ff0000",
            "#00ff00",
        )
        result = resolver.resolve(candidate, ValueType.COLOR, target="a")
        assert result.used_fallback is True

    def test_missing_operand_is_indeterminate_not_false(self) -> None:
        resolver = Resolver(_context())
        candidate = value.when(
            value.compare("greaterThan", value.bind("game.inexistente", fallback=None), 10),
            "#ff0000",
            "#00ff00",
        )
        result = resolver.resolve(candidate, ValueType.COLOR, target="a")
        assert result.value != "#00ff00"


class TestMissingTranslationIsAccounted:
    """Correção obrigatória: precisa ser `fallback`, não `exact`."""

    def test_reports_used_fallback(self) -> None:
        resolver = Resolver(_context())
        result = resolver.resolve(
            value.localized("ui.inexistente", fallback="Play"), ValueType.STRING, target="a"
        )
        assert result.used_fallback is True

    def test_diagnostic_once_per_key_and_locale(self) -> None:
        resolver = Resolver(_context())
        for _ in range(30):
            resolver._cache.clear()
            resolver.resolve(
                value.localized("ui.inexistente", fallback="Play"),
                ValueType.STRING,
                target="a",
            )
        assert len(resolver.diagnostics.entries) == 1

    def test_diagnostic_names_the_locale(self) -> None:
        resolver = Resolver(_context())
        resolver.resolve(
            value.localized("ui.inexistente", fallback="Play"), ValueType.STRING, target="a"
        )
        assert "pt-BR" in resolver.diagnostics.to_list()[0]["message"]


class TestSourceIdentityIsPreserved:
    """Token e configuração compartilham o algoritmo sem perder identidade."""

    def test_generations_distinguish_settings_from_theme(self) -> None:
        """Uma configuração muda sem reinstalar o tema.

        A versão anterior provava isto com um TOKEN, que não depende de
        configuração nenhuma — passava porque a chave antiga continha todas as
        gerações, e teria passado igual se as duas fossem a mesma variável. O
        veículo precisa ser um valor que realmente use a configuração.
        """
        context = _context(settings={"accent": "#ffd166"})
        resolver = Resolver(context)
        resolver.resolve(value.setting("accent"), ValueType.COLOR, target="a")
        context.generations = Generations(theme_settings=1)
        resolver.resolve(value.setting("accent"), ValueType.COLOR, target="a")
        assert resolver.stats.misses == 2, "configuração precisa invalidar quem a usa"

    def test_a_settings_change_does_not_touch_a_token(self) -> None:
        """A outra metade: independente quer dizer independente nos dois sentidos."""
        context = _context(tokens={"color.accent": "#ffd166"})
        resolver = Resolver(context)
        resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="a")
        context.generations = Generations(theme_settings=1)
        resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="a")
        assert resolver.stats.hits == 1

    @pytest.mark.parametrize(
        ("changed", "dependency", "expected_type"),
        [
            ({"translation_catalog": 1}, value.localized("menu.play"), ValueType.STRING),
            ({"asset_registry": 1}, value.asset("assets/logo.png"), ValueType.MEDIA),
            ({"state_variant": "focused"}, None, ValueType.COLOR),
        ],
    )
    def test_each_generation_invalidates_what_depends_on_it(
        self, changed: dict, dependency: Any, expected_type: ValueType
    ) -> None:
        state_value = value.when(value.in_state("focused"), "#ffffff", "#000000")
        target_value = dependency if dependency is not None else state_value
        context = _context(
            translations={"menu.play": "Jogar"},
            assets=frozenset({"assets/logo.png"}),
            states=frozenset(),
        )
        resolver = Resolver(context)
        resolver.resolve(target_value, expected_type, target="a")
        context.generations = Generations(**changed)
        resolver.resolve(target_value, expected_type, target="a")
        assert resolver.stats.misses == 2, changed


class TestTernaryTruthTables:
    """Tabela completa. Formalizada porque semântica de condição não pode ser
    inferida do código — precisa ser afirmação executável."""

    _AND: ClassVar[dict[tuple[str, str], str]] = {
        ("true", "true"): "true",
        ("true", "false"): "false",
        ("true", "indeterminate"): "indeterminate",
        ("false", "true"): "false",
        ("false", "false"): "false",
        ("false", "indeterminate"): "false",
        ("indeterminate", "true"): "indeterminate",
        ("indeterminate", "false"): "false",
        ("indeterminate", "indeterminate"): "indeterminate",
    }
    _OR: ClassVar[dict[tuple[str, str], str]] = {
        ("true", "true"): "true",
        ("true", "false"): "true",
        ("true", "indeterminate"): "true",
        ("false", "true"): "true",
        ("false", "false"): "false",
        ("false", "indeterminate"): "indeterminate",
        ("indeterminate", "true"): "true",
        ("indeterminate", "false"): "indeterminate",
        ("indeterminate", "indeterminate"): "indeterminate",
    }

    @pytest.mark.parametrize(("pair", "expected"), sorted(_AND.items()))
    def test_conjunction(self, pair: tuple[str, str], expected: str) -> None:
        from steamzero.domain.scene_resolver import Truth, _conjunction

        operands = [Truth(pair[0]), Truth(pair[1])]
        assert _conjunction(operands) == Truth(expected)

    @pytest.mark.parametrize(("pair", "expected"), sorted(_OR.items()))
    def test_disjunction(self, pair: tuple[str, str], expected: str) -> None:
        from steamzero.domain.scene_resolver import Truth, _disjunction

        operands = [Truth(pair[0]), Truth(pair[1])]
        assert _disjunction(operands) == Truth(expected)

    @pytest.mark.parametrize(
        ("operand", "expected"),
        [("true", "false"), ("false", "true"), ("indeterminate", "indeterminate")],
    )
    def test_negation(self, operand: str, expected: str) -> None:
        from steamzero.domain.scene_resolver import Truth, _negate

        assert _negate(Truth(operand)) == Truth(expected)

    def test_short_circuit_only_when_determined(self) -> None:
        """`true AND indeterminate` NÃO pode colapsar para verdadeiro.

        Colapsar escolheria o ramo `then` sem base — o espelho do defeito que a
        lógica ternária existe para corrigir.
        """
        from steamzero.domain.scene_resolver import Truth, _conjunction, _disjunction

        assert _conjunction([Truth.TRUE, Truth.INDETERMINATE]) is Truth.INDETERMINATE
        assert _disjunction([Truth.FALSE, Truth.INDETERMINATE]) is Truth.INDETERMINATE


class TestAbsenceIsNotOneThing:
    """`None` para tudo confundia quatro situações distintas."""

    def test_absence_states_are_distinct(self) -> None:
        from steamzero.domain.scene_resolver import EXPLICIT_NULL, MISSING, UNRESOLVED

        assert len({MISSING, UNRESOLVED, EXPLICIT_NULL}) == 3

    def test_exists_is_deterministic_over_absence(self) -> None:
        """exists e missing EXISTEM para testar presença: precisam decidir."""
        from steamzero.domain.scene_resolver import MISSING, Truth, _compare

        assert _compare("exists", MISSING, None) is Truth.FALSE
        assert _compare("missing", MISSING, None) is Truth.TRUE
        assert _compare("exists", "Chrono Trigger", None) is Truth.TRUE
        assert _compare("missing", "Chrono Trigger", None) is Truth.FALSE

    def test_unresolved_is_also_absent_for_presence_tests(self) -> None:
        from steamzero.domain.scene_resolver import UNRESOLVED, Truth, _compare

        assert _compare("exists", UNRESOLVED, None) is Truth.FALSE

    def test_ordinary_comparison_over_absence_is_indeterminate(self) -> None:
        """Só exists/missing têm licença para decidir diante de ausência."""
        from steamzero.domain.scene_resolver import MISSING, UNRESOLVED, Truth, _compare

        for absent in (MISSING, UNRESOLVED):
            assert _compare("greaterThan", absent, 10) is Truth.INDETERMINATE
            assert _compare("equals", absent, "x") is Truth.INDETERMINATE
