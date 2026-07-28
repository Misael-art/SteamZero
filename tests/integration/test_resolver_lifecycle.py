# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""VS-06 — cache, invalidação por dependência e ciclo de vida.

Os orçamentos são CONJUNTOS exatos, não limiares. ``recomputed > 0`` passaria
com a implementação recomputando as 65 propriedades da fixture inteira, que é
justamente o defeito que esta etapa existe para impedir.

Política de concorrência: o resolver é confinado a uma thread, e isso é
verificado por assertion e não só documentado — o defeito que a política evita
(observar metade de uma atualização de gerações) não levanta exceção, produz uma
cena parcialmente atualizada que parece certa.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest

from steamzero.domain import scene_value as value
from steamzero.domain.retrofe_declarations import collect_declarations
from steamzero.domain.retrofe_text_slice import SliceResult, TextSliceCompiler
from steamzero.domain.scene_registry import default_registries
from steamzero.domain.scene_resolver import (
    GENERATION_BY_KIND,
    Generations,
    ResolutionContext,
    Resolver,
)
from steamzero.domain.scene_typing import ValueType

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "retrofe"


def _context(**overrides: Any) -> ResolutionContext:
    base: dict[str, Any] = {
        "registries": default_registries(),
        "tokens": {
            "color.palette.neutral.100": "#f2f6fb",
            "color.text.primary": {"token": "color.palette.neutral.100"},
            "color.accent": "#ffd166",
            "color.favorite": "#ff5d8f",
            "color.normal": "#8892a0",
        },
        "settings": {"showClock": True},
        "read_model": {"game.title": "Chrono Trigger", "game.favorite": False},
        "translations": {"action.play": "Jogar"},
        "assets": frozenset(),
        "states": frozenset(),
        "theme_id": "temaA",
    }
    base.update(overrides)
    return ResolutionContext(**base)


def _scene(resolver: Resolver) -> None:
    """Duas cadeias independentes, como a especificação define.

    `title.color` desce dois níveis de token; `favoriteBadge.color` usa outro
    ramo. É a separação que permite provar que uma mudança local não derruba o
    que não a usa.
    """
    resolver.resolve(value.token("color.text.primary"), ValueType.COLOR, target="title.color")
    resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="favoriteBadge.color")
    resolver.resolve("#101418", ValueType.COLOR, target="background.color")
    resolver.resolve(value.bind("game.title"), ValueType.STRING, target="title.text")
    resolver.resolve(value.localized("action.play"), ValueType.STRING, target="playButton.text")


class TestCacheHitAndMiss:
    def test_the_first_resolution_misses_and_the_second_hits(self) -> None:
        resolver = Resolver(_context())
        resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="a")
        resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="a")
        assert resolver.stats.misses == 1
        assert resolver.stats.hits == 1

    def test_an_unused_token_change_recomputes_nothing(self) -> None:
        """Orçamento zero. É o caso mais fácil de errar e o mais barato de provar."""
        resolver = Resolver(_context())
        _scene(resolver)
        affected = resolver.invalidate("token:color.inexistente")
        assert affected == frozenset()
        assert resolver.stats.invalidations == 0


class TestSelectiveTokenInvalidation:
    def test_a_deep_token_reaches_its_consumer_and_nothing_else(self) -> None:
        """`color.palette.neutral.100` → `color.text.primary` → `title.color`.

        Transitivo importa: sem ele o token do meio seria invalidado e o
        elemento continuaria servindo a cor antiga.
        """
        resolver = Resolver(_context())
        _scene(resolver)
        affected = resolver.invalidate("token:color.palette.neutral.100")
        assert affected == {"title.color"}

    def test_the_intermediate_token_also_reaches_the_consumer(self) -> None:
        resolver = Resolver(_context())
        _scene(resolver)
        assert resolver.invalidate("token:color.text.primary") == {"title.color"}

    def test_the_independent_branch_is_untouched(self) -> None:
        resolver = Resolver(_context())
        _scene(resolver)
        assert "favoriteBadge.color" not in resolver.invalidate("token:color.palette.neutral.100")

    def test_a_literal_property_is_never_invalidated_by_a_token(self) -> None:
        resolver = Resolver(_context())
        _scene(resolver)
        for dependency in ("token:color.accent", "token:color.text.primary"):
            assert "background.color" not in resolver.invalidate(dependency)


class TestDependencyEdgesAreReplaced:
    """Aresta antiga que sobrevive é recomputação eterna de algo que mudou."""

    def test_switching_token_removes_the_previous_edge(self) -> None:
        context = _context()
        resolver = Resolver(context)
        resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="title.color")
        assert resolver.invalidate("token:color.accent") == {"title.color"}

        resolver.resolve(value.token("color.favorite"), ValueType.COLOR, target="title.color")
        assert resolver.invalidate("token:color.accent") == frozenset(), (
            "a aresta para o token antigo precisa ter sido removida"
        )
        assert resolver.invalidate("token:color.favorite") == {"title.color"}

    @pytest.mark.parametrize(
        ("first", "second", "expected_type", "kind"),
        [
            (value.bind("game.title"), value.bind("game.genre"), ValueType.STRING, "bind"),
            (
                value.localized("action.play"),
                value.localized("action.stop"),
                ValueType.STRING,
                "i18n",
            ),
            (
                value.setting("showClock"),
                value.setting("showBattery"),
                ValueType.BOOLEAN,
                "setting",
            ),
        ],
    )
    def test_switching_any_origin_removes_the_previous_edge(
        self, first: Any, second: Any, expected_type: ValueType, kind: str
    ) -> None:
        context = _context(
            read_model={"game.title": "Chrono", "game.genre": "RPG"},
            translations={"action.play": "Jogar", "action.stop": "Parar"},
            settings={"showClock": True, "showBattery": False},
        )
        resolver = Resolver(context)
        resolver.resolve(first, expected_type, target="p")
        before = resolver.graph.dependencies_of("p")
        resolver.resolve(second, expected_type, target="p")
        after = resolver.graph.dependencies_of("p")
        removed = before - after
        assert removed, f"{kind} não trocou de dependência; o teste não prova nada"
        for old_key in removed:
            assert resolver.invalidate(old_key) == frozenset(), (
                f"aresta antiga de {kind} sobreviveu: {old_key}"
            )
        for new_key in after:
            assert resolver.invalidate(new_key) == {"p"}, f"aresta nova de {kind} não existe"


class TestConditionBranchDependencies:
    """A condição depende do que decide E do ramo ATIVO — não dos dois ramos."""

    def _conditional(self) -> Any:
        return value.when(
            value.compare("equals", value.bind("game.favorite"), True),
            value.token("color.favorite"),
            value.token("color.normal"),
        )

    def test_only_the_active_branch_is_depended_on(self) -> None:
        context = _context(read_model={"game.favorite": False})
        resolver = Resolver(context)
        resolver.resolve(self._conditional(), ValueType.COLOR, target="item.color")
        dependencies = resolver.graph.dependencies_of("item.color")
        assert "bind:game.favorite" in dependencies
        assert "token:color.normal" in dependencies
        assert "token:color.favorite" not in dependencies, (
            "depender do ramo inativo faria a propriedade recomputar por uma cor "
            "que ela não está usando"
        )

    def test_the_inactive_branch_does_not_invalidate(self) -> None:
        context = _context(read_model={"game.favorite": False})
        resolver = Resolver(context)
        resolver.resolve(self._conditional(), ValueType.COLOR, target="item.color")
        assert resolver.invalidate("token:color.favorite") == frozenset()

    def test_flipping_the_condition_swaps_the_branch_dependency(self) -> None:
        """O ciclo completo que a especificação exige."""
        context = _context(read_model={"game.favorite": False})
        resolver = Resolver(context)
        conditional = self._conditional()
        first = resolver.resolve(conditional, ValueType.COLOR, target="item.color")
        assert first.value == "#8892a0"

        context.read_model = {"game.favorite": True}
        context.generations = Generations(read_model=1)
        second = resolver.resolve(conditional, ValueType.COLOR, target="item.color")
        assert second.value == "#ff5d8f", "o ramo novo precisa ser resolvido com o valor atual"

        dependencies = resolver.graph.dependencies_of("item.color")
        assert "token:color.favorite" in dependencies
        assert "token:color.normal" not in dependencies, (
            "manter os dois ramos faria a propriedade recomputar por uma cor inativa"
        )
        assert resolver.invalidate("token:color.normal") == frozenset()
        assert resolver.invalidate("token:color.favorite") == {"item.color"}


class TestIndeterminateIsReevaluated:
    def test_a_missing_source_does_not_freeze_the_fallback(self) -> None:
        """Congelar `indeterminate` deixaria a tela errada para sempre.

        O valor real chegou, e a propriedade continuaria mostrando o fallback
        escolhido quando a origem faltava.
        """
        conditional = value.when(
            value.compare("greaterThan", value.bind("game.rating"), 4),
            "#ffd166",
            "#8892a0",
        )
        context = _context(read_model={})
        resolver = Resolver(context)
        first = resolver.resolve(conditional, ValueType.COLOR, target="rating.color")
        # `indeterminate` NÃO escolhe o ramo `otherwise`: escolher seria decidir
        # sem base e produzir uma tela plausível e errada. O default seguro é
        # transparente, que some — sintoma visível.
        assert first.value == "#00000000"

        context.read_model = {"game.rating": 5}
        context.generations = Generations(read_model=1)
        second = resolver.resolve(conditional, ValueType.COLOR, target="rating.color")
        assert second.value == "#ffd166", "a origem apareceu; a condição precisa ser reavaliada"

    def test_the_active_diagnostic_clears_when_the_value_resolves(self) -> None:
        """Aviso que sobrevive à correção treina quem olha a ignorar avisos."""
        context = _context(translations={})
        resolver = Resolver(context)
        resolver.resolve(
            value.localized("action.play", fallback="Play"), ValueType.STRING, target="p.text"
        )
        assert any(item.target == "p.text" for item in resolver.diagnostics.active)

        context.translations = {"action.play": "Jogar"}
        context.generations = Generations(translation_catalog=1, locale="pt-BR")
        resolver.resolve(
            value.localized("action.play", fallback="Play"), ValueType.STRING, target="p.text"
        )
        assert not any(item.target == "p.text" for item in resolver.diagnostics.active)

    def test_the_historical_log_keeps_what_happened(self) -> None:
        """Apagar o histórico perderia que a tradução esteve ausente na importação."""
        context = _context(translations={})
        resolver = Resolver(context)
        resolver.resolve(
            value.localized("action.play", fallback="Play"), ValueType.STRING, target="p.text"
        )
        context.translations = {"action.play": "Jogar"}
        context.generations = Generations(translation_catalog=1)
        resolver.resolve(
            value.localized("action.play", fallback="Play"), ValueType.STRING, target="p.text"
        )
        assert resolver.diagnostics.entries, "o histórico não pode ser apagado"


class TestTranslationAndLocale:
    def test_only_localized_text_reacts_to_a_locale_change(self) -> None:
        resolver = Resolver(_context())
        _scene(resolver)
        assert resolver.graph.dependents_of("i18n:action.play") == {"playButton.text"}

    def test_an_unused_key_recomputes_nothing(self) -> None:
        resolver = Resolver(_context())
        _scene(resolver)
        assert resolver.invalidate("i18n:action.inexistente") == frozenset()

    def test_a_locale_change_does_not_touch_colours(self) -> None:
        context = _context()
        resolver = Resolver(context)
        _scene(resolver)
        before = resolver.stats.hits
        context.generations = Generations(locale="en-US")
        resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="favoriteBadge.color")
        assert resolver.stats.hits == before + 1, "cor não muda porque o idioma mudou"


class TestReadModelIsSelective:
    def test_only_the_consumers_of_a_path_are_reachable(self) -> None:
        resolver = Resolver(_context())
        _scene(resolver)
        assert resolver.graph.dependents_of("bind:game.title") == {"title.text"}

    def test_an_unused_field_recomputes_nothing(self) -> None:
        resolver = Resolver(_context())
        _scene(resolver)
        assert resolver.invalidate("bind:game.publisher") == frozenset()

    def test_invalidation_is_by_path_not_by_whole_model(self) -> None:
        """`invalidate("bind:game.title")`, não `invalidateEntireReadModel()`."""
        resolver = Resolver(_context())
        _scene(resolver)
        affected = resolver.invalidate("bind:game.title")
        assert affected == {"title.text"}
        assert len(affected) < len(resolver.graph.targets)


class TestStateVariants:
    def test_a_state_condition_records_its_dependency(self) -> None:
        """Verificado antes de escrever: o resolver NÃO registrava isto.

        Enquanto a chave continha todas as gerações, a ausência era mascarada.
        Com invalidação seletiva, o item continuaria pintado como focado depois
        de perder o foco.
        """
        resolver = Resolver(_context())
        resolver.resolve(
            value.when(value.in_state("focused"), "#ffffff", "#000000"),
            ValueType.COLOR,
            target="item.color",
        )
        assert "state:focused" in resolver.graph.dependencies_of("item.color")

    def test_a_state_change_reaches_only_state_sensitive_properties(self) -> None:
        resolver = Resolver(_context())
        _scene(resolver)
        resolver.resolve(
            value.when(value.in_state("focused"), "#ffffff", "#000000"),
            ValueType.COLOR,
            target="item.color",
        )
        assert resolver.invalidate("state:focused") == {"item.color"}

    def test_the_state_value_actually_changes(self) -> None:
        context = _context(states=frozenset())
        resolver = Resolver(context)
        conditional = value.when(value.in_state("focused"), "#ffffff", "#000000")
        assert resolver.resolve(conditional, ValueType.COLOR, target="i.color").value == "#000000"
        context.states = frozenset({"focused"})
        context.generations = Generations(state_variant="focused")
        assert resolver.resolve(conditional, ValueType.COLOR, target="i.color").value == "#ffffff"


class TestThemeSettingsAreIndependent:
    def test_a_settings_change_leaves_the_theme_generation_alone(self) -> None:
        context = _context()
        resolver = Resolver(context)
        _scene(resolver)
        resolver.resolve(value.setting("showClock"), ValueType.BOOLEAN, target="clock.visible")

        context.generations = Generations(theme_settings=1)
        assert context.generations.theme == 0, "configuração não recarrega o tema"
        before = resolver.stats.misses
        resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="favoriteBadge.color")
        assert resolver.stats.misses == before, "cor de token não depende de configuração"


class TestElementLifecycle:
    def test_a_forgotten_element_is_not_recomputed(self) -> None:
        resolver = Resolver(_context())
        _scene(resolver)
        assert resolver.invalidate("token:color.accent") == {"favoriteBadge.color"}

        resolver.forget("favoriteBadge.color")
        assert resolver.invalidate("token:color.accent") == frozenset()
        assert "favoriteBadge.color" not in resolver.graph.targets

    def test_no_edge_points_at_a_forgotten_element(self) -> None:
        resolver = Resolver(_context())
        _scene(resolver)
        edges_before = resolver.graph.edge_count
        resolver.forget("title.color")
        assert resolver.graph.edge_count < edges_before
        assert resolver.graph.dependencies_of("title.color") == frozenset()

    def test_no_cache_entry_survives_the_element(self) -> None:
        resolver = Resolver(_context())
        _scene(resolver)
        entries_before = resolver.active_cache_entries
        resolver.forget("title.text")
        assert resolver.active_cache_entries == entries_before - 1


class TestViewLifecycle:
    def test_unloading_a_view_removes_all_of_its_elements(self) -> None:
        resolver = Resolver(_context())
        for index in range(3):
            resolver.resolve(
                value.token("color.accent"), ValueType.COLOR, target=f"viewA.item{index}.color"
            )
        resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="viewB.item.color")

        removed = resolver.forget_prefix("viewA.")
        assert len(removed) == 3
        assert resolver.invalidate("token:color.accent") == {"viewB.item.color"}


class TestThemeLifecycle:
    def test_a_reloaded_theme_does_not_serve_the_previous_values(self) -> None:
        context = _context(tokens={"color.accent": "#111111"})
        resolver = Resolver(context)
        first = resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="a.color")
        assert first.value == "#111111"

        resolver.forget_theme()
        context.tokens = {"color.accent": "#222222"}
        context.generations = Generations(theme=1)
        second = resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="a.color")
        assert second.value == "#222222"

    def test_identical_element_ids_in_two_themes_do_not_collide(self) -> None:
        context = _context(tokens={"color.accent": "#111111"})
        context.theme_id = "temaA"
        resolver = Resolver(context)
        resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="gameTitle.color")

        context.theme_id = "temaB"
        context.tokens = {"color.accent": "#222222"}
        second = resolver.resolve(
            value.token("color.accent"), ValueType.COLOR, target="gameTitle.color"
        )
        assert second.value == "#222222"

    def test_unloading_a_theme_clears_the_active_diagnostics(self) -> None:
        context = _context(translations={})
        resolver = Resolver(context)
        resolver.resolve(
            value.localized("action.play", fallback="Play"), ValueType.STRING, target="p.text"
        )
        assert resolver.diagnostics.active
        resolver.forget_theme()
        assert resolver.diagnostics.active == ()
        assert resolver.diagnostics.entries, "o histórico sobrevive ao descarregamento"


class TestBatchedUpdates:
    def test_a_property_is_dropped_once_per_batch(self) -> None:
        """Sem lote, quatro origens mudando recomputariam a mesma propriedade
        quatro vezes, e alguém veria o texto novo com a cor velha."""
        resolver = Resolver(_context())
        resolver.resolve(
            value.when(
                value.compare("equals", value.bind("game.favorite"), False),
                value.token("color.normal"),
                value.token("color.accent"),
            ),
            ValueType.COLOR,
            target="item.color",
        )
        before = resolver.stats.invalidations
        with resolver.batch():
            resolver.invalidate("bind:game.favorite")
            resolver.invalidate("token:color.normal")
        assert resolver.stats.invalidations == before + 1, (
            "duas origens da mesma propriedade precisam derrubá-la uma vez só"
        )

    def test_the_batch_still_invalidates(self) -> None:
        resolver = Resolver(_context())
        _scene(resolver)
        with resolver.batch():
            resolver.invalidate("token:color.accent")
        resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="favoriteBadge.color")
        assert resolver.stats.misses == 6, "5 da cena, 1 do recálculo após o lote"


class TestNoStaleResults:
    @pytest.mark.parametrize("cycles", [1, 3])
    def test_flipping_a_value_back_returns_the_original(self, cycles: int) -> None:
        """A → B → A. Detecta aresta antiga, cache contaminado e geração errada."""
        context = _context(tokens={"color.accent": "#111111"})
        resolver = Resolver(context)
        original = resolver.resolve(
            value.token("color.accent"), ValueType.COLOR, target="a.color"
        ).value

        generation = 0
        for _ in range(cycles):
            generation += 1
            context.tokens = {"color.accent": "#222222"}
            context.generations = Generations(tokens=generation)
            resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="a.color")
            generation += 1
            context.tokens = {"color.accent": "#111111"}
            context.generations = Generations(tokens=generation)
            final = resolver.resolve(
                value.token("color.accent"), ValueType.COLOR, target="a.color"
            ).value

        assert final == original

    def test_flipping_a_condition_back_returns_the_original(self) -> None:
        conditional = value.when(
            value.compare("equals", value.bind("game.favorite"), True),
            value.token("color.favorite"),
            value.token("color.normal"),
        )
        context = _context(read_model={"game.favorite": False})
        resolver = Resolver(context)
        original = resolver.resolve(conditional, ValueType.COLOR, target="i.color").value

        for generation, favorite in ((1, True), (2, False)):
            context.read_model = {"game.favorite": favorite}
            context.generations = Generations(read_model=generation)
            final = resolver.resolve(conditional, ValueType.COLOR, target="i.color").value

        assert final == original
        assert resolver.graph.dependencies_of("i.color") >= {
            "bind:game.favorite",
            "token:color.normal",
        }

    def test_flipping_the_locale_back_returns_the_original(self) -> None:
        context = _context(translations={"action.play": "Jogar"})
        resolver = Resolver(context)
        original = resolver.resolve(
            value.localized("action.play"), ValueType.STRING, target="p.text"
        ).value

        context.translations = {"action.play": "Play"}
        context.generations = Generations(locale="en-US", translation_catalog=1)
        resolver.resolve(value.localized("action.play"), ValueType.STRING, target="p.text")

        context.translations = {"action.play": "Jogar"}
        context.generations = Generations(locale="pt-BR", translation_catalog=2)
        final = resolver.resolve(
            value.localized("action.play"), ValueType.STRING, target="p.text"
        ).value
        assert final == original


class TestTheGraphDoesNotGrow:
    def test_load_and_unload_cycles_return_to_the_baseline(self) -> None:
        """Crescimento monotônico é vazamento, mesmo sem medir memória."""
        resolver = Resolver(_context())
        baseline_edges = resolver.graph.edge_count
        baseline_entries = resolver.active_cache_entries
        baseline_active = len(resolver.diagnostics.active)

        for _ in range(5):
            _scene(resolver)
            resolver.invalidate("token:color.accent")
            for target in list(resolver.graph.targets):
                resolver.forget(target)

        assert resolver.graph.edge_count == baseline_edges
        assert resolver.active_cache_entries == baseline_entries
        assert len(resolver.diagnostics.active) == baseline_active

    def test_switching_dependencies_repeatedly_does_not_accumulate_edges(self) -> None:
        resolver = Resolver(_context())
        for index in range(20):
            token = "color.accent" if index % 2 else "color.favorite"
            resolver.resolve(value.token(token), ValueType.COLOR, target="a.color")
        assert len(resolver.graph.dependencies_of("a.color")) == 1
        assert resolver.graph.edge_count == 1


class TestConcurrencyPolicyIsExplicit:
    def test_the_policy_is_declared(self) -> None:
        assert Resolver.THREAD_POLICY == "single-thread confined"

    def test_another_thread_is_refused(self) -> None:
        """Documentar não basta.

        O defeito que a política evita — observar metade de uma atualização de
        gerações — não levanta exceção: produz uma cena parcialmente atualizada
        que parece correta.
        """
        resolver = Resolver(_context())
        failure: list[BaseException] = []

        def use_from_another_thread() -> None:
            try:
                resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="a")
            except RuntimeError as exc:
                failure.append(exc)

        thread = threading.Thread(target=use_from_another_thread)
        thread.start()
        thread.join()
        assert failure, "uso em outra thread precisa ser recusado"
        assert "single-thread confined" in str(failure[0])


class TestRecomputationBudgetOnTheRealFixture:
    """Orçamentos sobre as 65 propriedades do VS-04, em conjuntos exatos."""

    @pytest.fixture(scope="class")
    @staticmethod
    def compiled() -> SliceResult:
        path = FIXTURES / "vs04_positive.xml"
        declarations = collect_declarations(
            path.read_text(encoding="utf-8"), file="retrofe/vs04_positive.xml"
        )
        return TextSliceCompiler(
            palette={"accent": "#ffd166"},
            packaged_fonts=frozenset({"Liberation Sans"}),
            translations=frozenset({"menu.play"}),
        ).compile(declarations)

    def _resolved(self, compiled: SliceResult) -> Resolver:
        context = _context(
            tokens={"color.accent": "#ffd166"},
            read_model={"game.title": "Chrono Trigger"},
            translations={"menu.play": "Jogar"},
            states=frozenset({"focused"}),
        )
        resolver = Resolver(context)
        for element in compiled.elements:
            if element.typography is not None and element.typography.color is not None:
                resolver.resolve(
                    element.typography.color, ValueType.COLOR, target=f"{element.id}.color"
                )
            if element.text_content is not None:
                resolver.resolve(
                    element.text_content, ValueType.STRING, target=f"{element.id}.text"
                )
        return resolver

    def test_a_token_change_touches_only_its_consumer(self, compiled: SliceResult) -> None:
        resolver = self._resolved(compiled)
        affected = resolver.invalidate("token:color.accent")
        assert affected == {"text-4.color"}, (
            f"orçamento estourado: {sorted(affected)}. Uma cor não pode recompor a cena."
        )

    def test_a_binding_change_touches_only_its_consumer(self, compiled: SliceResult) -> None:
        resolver = self._resolved(compiled)
        assert resolver.invalidate("bind:game.title") == {"reloadableText-6.text"}

    def test_a_translation_change_touches_only_localized_text(self, compiled: SliceResult) -> None:
        resolver = self._resolved(compiled)
        assert resolver.invalidate("i18n:menu.play") == {"text-7.text"}

    def test_a_state_change_touches_only_the_conditional_element(
        self, compiled: SliceResult
    ) -> None:
        resolver = self._resolved(compiled)
        assert resolver.invalidate("state:focused") == {"text-5.color"}

    def test_the_scene_is_never_fully_invalidated_by_one_change(
        self, compiled: SliceResult
    ) -> None:
        resolver = self._resolved(compiled)
        total = len(resolver.graph.targets)
        assert total >= 10, "cena pequena demais para o orçamento significar algo"
        for dependency in (
            "token:color.accent",
            "bind:game.title",
            "i18n:menu.play",
            "state:focused",
        ):
            affected = resolver.invalidate(dependency)
            assert len(affected) < total / 2, (
                f"{dependency} invalidou {len(affected)} de {total} propriedades"
            )


class TestGenerationMappingIsComplete:
    """Um tipo de dependência sem geração serviria valor stale para sempre."""

    @pytest.mark.parametrize(
        "kind", ["token", "bind", "setting", "i18n", "asset", "state", "capability"]
    )
    def test_every_dependency_kind_maps_to_a_generation(self, kind: str) -> None:
        assert GENERATION_BY_KIND.get(kind), f"{kind} não tem geração associada"

    def test_the_theme_generation_is_always_part_of_the_fingerprint(self) -> None:
        fingerprint = Generations().fingerprint(frozenset())
        assert any(name == "theme" for name, _value in fingerprint)


class TestChangingTheExpressionInvalidates:
    """Descoberto no VS-06: a chave é (tema, alvo) e não continha a expressão.

    Trocar `title.color` de um token para outro servia o valor ANTIGO, porque o
    alvo não mudou. Confiar em quem chama lembrar de bumpar a geração é contrato
    implícito — e contrato implícito é o que produz tela desatualizada sem
    ninguém saber por quê.
    """

    def test_a_new_expression_is_not_served_from_the_old_entry(self) -> None:
        context = _context(tokens={"color.a": "#111111", "color.b": "#222222"})
        resolver = Resolver(context)
        first = resolver.resolve(value.token("color.a"), ValueType.COLOR, target="p")
        second = resolver.resolve(value.token("color.b"), ValueType.COLOR, target="p")
        assert first.value == "#111111"
        assert second.value == "#222222"

    def test_the_same_expression_still_hits(self) -> None:
        """A correção não pode custar o cache: expressão igual continua servindo."""
        resolver = Resolver(_context())
        expression = value.token("color.accent")
        resolver.resolve(expression, ValueType.COLOR, target="p")
        resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="p")
        assert resolver.stats.hits == 1, "expressão equivalente precisa reusar o cache"

    def test_a_literal_change_is_also_detected(self) -> None:
        resolver = Resolver(_context())
        assert resolver.resolve("#111111", ValueType.COLOR, target="p").value == "#111111"
        assert resolver.resolve("#222222", ValueType.COLOR, target="p").value == "#222222"
