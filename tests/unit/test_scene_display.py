# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Display responsivo: estado fechado, vocabulário display.* e invalidação por eixo.

O tema consulta o display via bindings ``display.*``; o shell alimenta. Três
coisas são travadas aqui:

1. a FORMA do estado (tamanho lógico, dpr, orientação, safe areas por lado) —
   fechada, validada na construção, sem quarto valor de orientação;
2. o VOCABULÁRIO (campo, tipo publicado, geração de invalidação) — uma tabela
   única, da qual o registro de tipos deriva para não divergir;
3. a INVALIDAÇÃO por eixo — mudar a largura não pode recomputar quem só lê a
   altura, e um safe area que muda num lado não derruba quem lê o outro.
"""

from __future__ import annotations

from typing import Any

import pytest

from steamzero.domain import scene_value as value
from steamzero.domain.scene_display import (
    DISPLAY_BINDING_TYPES,
    DISPLAY_FIELDS,
    DisplaySpec,
    Orientation,
    SafeAreaInsets,
)
from steamzero.domain.scene_registry import default_registries
from steamzero.domain.scene_resolver import (
    DISPLAY_DEPENDENCIES,
    ResolutionContext,
    Resolver,
)
from steamzero.domain.scene_typing import ValueType


def _display(**overrides: Any) -> DisplaySpec:
    base: dict[str, Any] = {"logical_width": 1920.0, "logical_height": 1080.0, "dpr": 1.0}
    base.update(overrides)
    return DisplaySpec(**base)


def _context(display: DisplaySpec | None = None, **overrides: Any) -> ResolutionContext:
    base: dict[str, Any] = {
        "registries": default_registries(),
        "read_model": {"game.title": "Chrono Trigger"},
        "theme_id": "temaA",
    }
    base.update(overrides)
    if display is not None:
        base["display"] = display
    return ResolutionContext(**base)


def _resolver(display: DisplaySpec | None = None) -> Resolver:
    resolver = Resolver(_context(display))
    resolver.set_display(display or _display())
    return resolver


class TestDisplaySpec:
    def test_the_default_is_a_landscape_16_9(self) -> None:
        spec = DisplaySpec()
        assert spec.aspect_ratio == round(16 / 9, 4)
        assert spec.orientation is Orientation.LANDSCAPE

    def test_safe_areas_are_insets_not_absolutes(self) -> None:
        spec = _display(safe_area=SafeAreaInsets(left=24.0, top=0.0, right=24.0, bottom=48.0))
        assert spec.safe_area.left == 24.0
        assert spec.safe_area.bottom == 48.0

    @pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
    def test_a_non_positive_size_is_refused(self, bad: Any) -> None:
        with pytest.raises(ValueError, match="positiva"):
            _display(logical_width=bad)

    def test_a_boolean_size_is_refused(self) -> None:
        with pytest.raises(ValueError, match="exige número"):
            _display(logical_width=True)

    @pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), True])
    def test_a_non_positive_dpr_is_refused(self, bad: Any) -> None:
        with pytest.raises(ValueError, match="dpr"):
            _display(dpr=bad)

    @pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf"), True, "12"])
    def test_a_negative_or_malformed_safe_area_is_refused(self, bad: Any) -> None:
        with pytest.raises(ValueError, match="safe area"):
            SafeAreaInsets(left=bad)

    @pytest.mark.parametrize("bad", ["rotated", "LANDSCAPE", "", None])
    def test_an_unknown_orientation_is_refused(self, bad: Any) -> None:
        with pytest.raises(ValueError, match="orientação"):
            _display(orientation=bad)

    def test_the_spec_round_trips(self) -> None:
        spec = _display(
            logical_width=1280.0,
            logical_height=720.0,
            dpr=1.5,
            orientation=Orientation.PORTRAIT,
            safe_area=SafeAreaInsets(left=10.0, right=10.0),
        )
        assert DisplaySpec.from_dict(spec.to_dict()) == spec

    def test_aspect_ratio_is_width_over_height(self) -> None:
        assert _display(logical_width=1280.0, logical_height=720.0).aspect_ratio == round(
            1280.0 / 720.0, 4
        )


class TestDisplayVocabulary:
    def test_every_field_is_published_in_the_binding_registry(self) -> None:
        registries = default_registries()
        for field, (value_type, _getter) in DISPLAY_FIELDS.items():
            path = f"display.{field}"
            assert registries.bindings.type_of(path) is value_type, path

    def test_the_registry_types_are_derived_from_the_table(self) -> None:
        expected = {
            f"display.{field}": spec_type for field, (spec_type, _) in DISPLAY_FIELDS.items()
        }
        assert expected == DISPLAY_BINDING_TYPES

    def test_every_field_has_an_invalidation_generation(self) -> None:
        """Tabela e grafo não podem divergir: campo sem geração seria stale."""
        markers = {f"display:{field}" for field in DISPLAY_FIELDS}
        assert markers == set(DISPLAY_DEPENDENCIES)

    def test_a_wrong_expected_type_is_refused_at_compile_time(self) -> None:
        from steamzero.domain.scene_registry import DeferredValue, ResolutionPhase

        check = default_registries().check_deferred(
            DeferredValue(
                source_kind="bind",
                source_path="display.width",
                expected_type=ValueType.STRING,
                resolution_phase=ResolutionPhase.RUNTIME,
            )
        )
        assert check.ok is False
        assert "produz number" in (check.reason or "")

    def test_an_unknown_display_field_is_not_a_policy_refusal(self) -> None:
        from steamzero.domain.scene_registry import DeferredValue, ResolutionPhase

        check = default_registries().check_deferred(
            DeferredValue(
                source_kind="bind",
                source_path="display.someDay",
                expected_type=ValueType.NUMBER,
                resolution_phase=ResolutionPhase.RUNTIME,
            )
        )
        assert check.ok is False
        assert check.policy is not None and check.policy.value == "invalid"


class TestDisplayBindings:
    def test_a_display_binding_resolves_from_the_spec(self) -> None:
        resolver = _resolver(_display(logical_width=1280.0))
        resolved = resolver.resolve(value.bind("display.width"), ValueType.NUMBER, target="t.x")
        assert resolved.value == 1280.0
        assert resolved.dependencies == {"display:width"}
        assert resolved.phase.value == "runtime"

    def test_a_safe_area_binding_resolves_per_side(self) -> None:
        resolver = _resolver(
            _display(safe_area=SafeAreaInsets(left=24.0, top=0.0, right=24.0, bottom=48.0))
        )
        assert (
            resolver.resolve(
                value.bind("display.safeArea.bottom"), ValueType.NUMBER, target="t.y"
            ).value
            == 48.0
        )

    def test_orientation_resolves_as_a_string(self) -> None:
        resolver = _resolver(_display(orientation=Orientation.PORTRAIT))
        assert (
            resolver.resolve(
                value.bind("display.orientation"), ValueType.STRING, target="t.o"
            ).value
            == "portrait"
        )

    def test_aspect_ratio_records_both_axes(self) -> None:
        resolver = _resolver(_display(logical_width=1280.0, logical_height=720.0))
        resolved = resolver.resolve(
            value.bind("display.aspectRatio"), ValueType.NUMBER, target="t.r"
        )
        assert resolved.value == round(1280.0 / 720.0, 4)
        assert resolved.dependencies == {"display:aspectRatio"}

    def test_a_type_mismatch_is_refused(self) -> None:
        resolver = _resolver()
        with pytest.raises(Exception, match="produz number"):
            resolver.resolve(value.bind("display.width"), ValueType.STRING, target="t.x")

    def test_an_unknown_field_uses_the_fallback(self) -> None:
        resolver = _resolver()
        resolved = resolver.resolve(
            value.bind("display.inexistente", fallback=7), ValueType.NUMBER, target="t.x"
        )
        assert resolved.value == 7
        assert resolved.used_fallback is True

    def test_a_display_binding_does_not_depend_on_the_read_model(self) -> None:
        resolver = _resolver()
        resolver.resolve(value.bind("display.width"), ValueType.NUMBER, target="t.x")
        assert resolver.graph.dependencies_of("t.x") == {"display:width"}


class TestDisplayInvalidation:
    def _scene(self, resolver: Resolver) -> None:
        resolver.resolve(value.bind("display.width"), ValueType.NUMBER, target="t.width")
        resolver.resolve(value.bind("display.height"), ValueType.NUMBER, target="t.height")
        resolver.resolve(value.bind("display.aspectRatio"), ValueType.NUMBER, target="t.ratio")
        resolver.resolve(value.bind("display.safeArea.left"), ValueType.NUMBER, target="t.safeLeft")
        resolver.resolve(value.bind("game.title"), ValueType.STRING, target="t.text")

    def test_a_width_change_touches_only_width_and_ratio(self) -> None:
        resolver = _resolver()
        self._scene(resolver)
        affected = resolver.set_display(_display(logical_width=1280.0))
        assert affected == {"t.width", "t.ratio"}

    def test_a_height_change_touches_only_height_and_ratio(self) -> None:
        resolver = _resolver()
        self._scene(resolver)
        affected = resolver.set_display(_display(logical_height=720.0))
        assert affected == {"t.height", "t.ratio"}

    def test_a_safe_area_change_touches_only_its_own_side(self) -> None:
        resolver = _resolver()
        self._scene(resolver)
        affected = resolver.set_display(_display(safe_area=SafeAreaInsets(left=32.0)))
        assert affected == {"t.safeLeft"}

    def test_a_dpr_change_touches_only_dpr_readers(self) -> None:
        resolver = _resolver()
        resolver.resolve(value.bind("display.dpr"), ValueType.NUMBER, target="t.dpr")
        resolver.resolve(value.bind("display.width"), ValueType.NUMBER, target="t.width")
        affected = resolver.set_display(_display(dpr=1.5))
        assert affected == {"t.dpr"}

    def test_an_unchanged_display_recomputes_nothing(self) -> None:
        resolver = _resolver()
        self._scene(resolver)
        assert resolver.set_display(_display()) == frozenset()

    def test_a_change_that_was_reverted_serves_the_cached_value_again(self) -> None:
        resolver = _resolver()
        self._scene(resolver)
        first = resolver.resolve(value.bind("display.width"), ValueType.NUMBER, target="t.width")
        resolver.set_display(_display(logical_width=1280.0))
        resolver.resolve(value.bind("display.width"), ValueType.NUMBER, target="t.width")
        resolver.set_display(_display(logical_width=1920.0))
        again = resolver.resolve(value.bind("display.width"), ValueType.NUMBER, target="t.width")
        assert again.value == first.value == 1920.0

    def test_recomputing_after_a_change_hits_the_cache(self) -> None:
        resolver = _resolver()
        self._scene(resolver)
        resolver.set_display(_display(logical_width=1280.0))
        resolver.resolve(value.bind("display.width"), ValueType.NUMBER, target="t.width")
        before = resolver.stats.hits
        resolver.resolve(value.bind("display.width"), ValueType.NUMBER, target="t.width")
        assert resolver.stats.hits == before + 1

    def test_the_same_display_value_still_hits_the_cache(self) -> None:
        resolver = _resolver()
        resolver.resolve(value.bind("display.width"), ValueType.NUMBER, target="t.width")
        resolver.resolve(value.bind("display.width"), ValueType.NUMBER, target="t.width")
        assert resolver.stats.hits == 1

    def test_an_orientation_change_touches_only_orientation_readers(self) -> None:
        resolver = _resolver()
        resolver.resolve(value.bind("display.orientation"), ValueType.STRING, target="t.o")
        resolver.resolve(value.bind("display.width"), ValueType.NUMBER, target="t.width")
        affected = resolver.set_display(_display(orientation=Orientation.PORTRAIT))
        assert affected == {"t.o"}

    def test_a_display_change_never_touches_read_model_readers(self) -> None:
        resolver = _resolver()
        self._scene(resolver)
        affected = resolver.set_display(_display(logical_width=1280.0, dpr=2.0))
        assert "t.text" not in affected
