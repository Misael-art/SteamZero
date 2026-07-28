# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Modelo de valor do IR — qualquer propriedade, qualquer origem.

A distinção entre `boundText` e `boundImage` obrigava o autor a escolher o TIPO
DE ELEMENTO por causa da origem do dado. O efeito colateral era arquitetural:
cor não podia vir de configuração, opacidade não podia vir de estado, e
visibilidade não podia depender da existência de uma mídia — porque essas
propriedades não eram "elementos".

Duas travas que estes testes protegem: não há expressão executável, e nada é
descartado em silêncio.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from steamzero.domain import scene_value as value
from steamzero.domain.scene_value import TranslationLog, Verdict

_SCHEMA = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "src"
        / "steamzero"
        / "schemas"
        / "ir-value-v1.schema.json"
    ).read_text(encoding="utf-8")
)
_VALIDATOR = jsonschema.Draft202012Validator({"$ref": "#/$defs/value", **_SCHEMA})


def _valid(candidate: object) -> None:
    _VALIDATOR.validate(candidate)


class TestOriginsAreInterchangeable:
    """O ponto do modelo: a MESMA propriedade aceita qualquer origem."""

    @pytest.mark.parametrize(
        "candidate",
        [
            "#ff0000",
            42,
            True,
            None,
        ],
    )
    def test_literals_are_values(self, candidate: object) -> None:
        _valid(candidate)

    def test_token_is_a_value(self) -> None:
        _valid(value.token("color.text.primary"))

    def test_binding_is_a_value(self) -> None:
        _valid(value.bind("game.title"))

    def test_namespaced_media_path_is_a_value(self) -> None:
        """Slot de mídia vira caminho extensível, não enum fechado."""
        _valid(value.bind("media.image.packaging.box.front"))

    def test_asset_is_a_value(self) -> None:
        _valid(value.asset("assets/bg.webp"))

    def test_localized_key_is_a_value(self) -> None:
        _valid(value.localized("ui.play", fallback="Jogar"))

    def test_theme_setting_is_a_value(self) -> None:
        """Permite cor vinculada a preferência sem o tema ler nada do sistema."""
        _valid(value.setting("accentColor", fallback=value.token("color.accent")))


class TestWhatTheOldModelForbade:
    """Casos que eram impossíveis com boundText/boundImage."""

    def test_color_can_depend_on_focus(self) -> None:
        candidate = value.when(
            value.in_state("focused"),
            value.token("color.focusRing"),
            value.token("color.border"),
        )
        _valid(candidate)

    def test_visibility_can_depend_on_media_existing(self) -> None:
        candidate = value.when(value.compare("exists", value.bind("media.video.preview")), 1.0, 0.0)
        _valid(candidate)

    def test_volume_can_depend_on_a_setting(self) -> None:
        _valid(value.setting("uiVolume", fallback=0.5))

    def test_condition_can_combine_state_and_capability(self) -> None:
        candidate = value.when(
            value.all_of(value.in_state("selected"), value.has_capability("video.hdr")),
            1.0,
        )
        _valid(candidate)


class TestNoExecutableExpression:
    """Condição é comparação declarativa, validável por schema."""

    def test_unknown_operator_is_refused_at_construction(self) -> None:
        with pytest.raises(ValueError, match="operador desconhecido"):
            value.compare("evaluate", 1, 2)

    def test_unknown_state_is_refused(self) -> None:
        with pytest.raises(ValueError, match="estado desconhecido"):
            value.in_state("inventado")

    def test_arbitrary_object_is_not_a_value(self) -> None:
        with pytest.raises(jsonschema.ValidationError):
            _valid({"exec": "rm -rf /"})

    def test_condition_with_free_expression_is_refused(self) -> None:
        with pytest.raises(jsonschema.ValidationError):
            _valid({"when": {"expr": "game.year > 1990"}, "then": 1})


class TestUntrustedInput:
    @pytest.mark.parametrize(
        "path", ["../../etc/passwd", "/etc/passwd", "assets/../x.png", "bg.webp"]
    )
    def test_hostile_asset_path_is_refused(self, path: str) -> None:
        with pytest.raises(ValueError, match="asset inválido"):
            value.asset(path)

    @pytest.mark.parametrize("path", ["Game.Title", "game", "game..title", "1game.title"])
    def test_malformed_binding_path_is_refused(self, path: str) -> None:
        with pytest.raises(ValueError, match="binding inválido"):
            value.bind(path)

    def test_unknown_format_is_refused(self) -> None:
        with pytest.raises(ValueError, match="formato desconhecido"):
            value.bind("game.playTime", fmt="hexadecimal")


class TestReactivity:
    """O runtime precisa saber o que reavaliar quando o estado muda."""

    def test_literal_is_static(self) -> None:
        assert value.is_dynamic("#ff0000") is False

    @pytest.mark.parametrize(
        "candidate",
        [
            value.bind("game.title"),
            value.token("color.accent"),
            value.setting("accent"),
            value.when(value.in_state("focused"), 1, 0),
        ],
    )
    def test_derived_values_are_dynamic(self, candidate: dict) -> None:
        assert value.is_dynamic(candidate) is True

    def test_referenced_paths_are_collected_recursively(self) -> None:
        """Permite assinar exatamente o que a cena usa."""
        candidate = value.when(
            value.compare("exists", value.bind("media.video.preview")),
            value.bind("game.title"),
            value.bind("game.shortName"),
        )
        assert value.referenced_paths(candidate) == {
            "media.video.preview",
            "game.title",
            "game.shortName",
        }

    def test_static_value_references_nothing(self) -> None:
        assert value.referenced_paths("#fff") == set()


class TestTranslationLog:
    """Nada descartado em silêncio: cada propriedade recebe veredito."""

    def test_verdicts_are_counted(self) -> None:
        log = TranslationLog()
        log.record("fontColor", Verdict.EXACT, target="color")
        log.record("reflection", Verdict.UNSUPPORTED)
        log.record("onKeyPress", Verdict.IGNORED_BY_POLICY, detail="tema não lê tecla")
        assert log.counts() == {"exact": 1, "unsupported": 1, "ignoredByPolicy": 1}

    def test_fidelity_measures_properties_not_elements(self) -> None:
        """A métrica antiga contava elementos e dava 89% enquanto a cor sumia."""
        log = TranslationLog()
        for _ in range(3):
            log.record("x", Verdict.EXACT)
        log.record("fontColor", Verdict.UNSUPPORTED)
        assert log.fidelity() == 0.75

    def test_fallback_counts_as_kept(self) -> None:
        log = TranslationLog()
        log.record("color", Verdict.FALLBACK, detail="herdado do tema base")
        assert log.fidelity() == 1.0

    def test_policy_refusal_is_distinct_from_unsupported(self) -> None:
        """Uma é limitação nossa e vira trabalho; a outra é recusa deliberada."""
        log = TranslationLog()
        log.record("reflection", Verdict.UNSUPPORTED)
        log.record("readRawKey", Verdict.IGNORED_BY_POLICY)
        counts = log.counts()
        assert counts["unsupported"] == 1
        assert counts["ignoredByPolicy"] == 1

    def test_empty_log_is_full_fidelity(self) -> None:
        assert TranslationLog().fidelity() == 1.0

    def test_log_is_bounded(self) -> None:
        """Layout hostil não vira consumo de memória."""
        log = TranslationLog()
        for index in range(5000):
            log.record(f"p{index}", Verdict.EXACT)
        assert len(log.entries) <= 4096

    def test_report_carries_everything_needed_to_audit(self) -> None:
        log = TranslationLog()
        log.record("fontColor", Verdict.EXACT, target="color")
        report = log.to_dict()
        assert set(report) == {"fidelity", "counts", "translations"}
        assert report["translations"][0]["target"] == "color"
