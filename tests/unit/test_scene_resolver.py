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


class TestCacheKeyIsComposite:
    """Cache que ignora contexto devolve a resposta certa para a pergunta errada."""

    @pytest.mark.parametrize(
        "changed",
        [
            {"locale": "en-US"},
            {"accessibility": "highContrast"},
            {"tokens": 1},
            {"read_model": 1},
            {"theme": 1},
            {"display": "tv"},
        ],
    )
    def test_generation_change_bypasses_the_cache(self, changed: dict) -> None:
        context = _context()
        resolver = Resolver(context)
        resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="a")
        context.generations = Generations(**changed)
        resolver.resolve(value.token("color.accent"), ValueType.COLOR, target="a")
        assert resolver.stats.misses == 2, "geração diferente não pode reusar cache"


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
