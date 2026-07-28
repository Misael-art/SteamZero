# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Compilação de layouts RetroFE para o IR de cena.

RetroFE é declarativo — o tema é uma máquina de estados de animação disparada por
navegação, sem código —, o que o torna o primeiro emissor certo do IR: cobre
menu, metadados, relógio e eventos sem exigir execução de terceiros.

As fixtures são sintéticas, mas reproduzem defeitos REAIS encontrados no layout
Aeon Nox: comentários com hífens em excesso, tags de fechamento trocadas e
atributo duplicado. Layouts do mundo real não são XML bem formado, e um
compilador que só aceita XML correto não compila tema nenhum.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.scene_retrofe import compile_layout, fidelity_report

_SCHEMA = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "src"
        / "steamzero"
        / "schemas"
        / "ir-scene-v1.schema.json"
    ).read_text(encoding="utf-8")
)

_MINIMAL = """<layout width="1920" height="1080">
  <image src="bg.png" x="0" y="0" width="1920" height="1080" layer="0"/>
  <reloadableText type="title" x="center" y="100" fontSize="48" layer="5">
    <onEnter><set duration="0.2"><animate type="alpha" to="1"/></set></onEnter>
    <onExit><set duration="0.2"><animate type="alpha" to="0"/></set></onExit>
  </reloadableText>
  <reloadableText type="time" x="1800" y="40" layer="9"/>
  <reloadableImage type="logo" x="center" y="center" maxWidth="400"/>
  <menu type="custom" orientation="horizontal" scrollTime="0.2" x="0" y="910">
    <itemDefaults alpha="0.2" xOrigin="center" height="90"/>
    <item xOffset="-480"/>
    <item xOffset="0" alpha="1"/>
    <item xOffset="480"/>
  </menu>
</layout>"""


def _compile(xml: str = _MINIMAL, **kw: object) -> dict[str, object]:
    kw.setdefault("theme_id", "retrofe.teste")
    return compile_layout(xml, **kw)  # type: ignore[arg-type]


def _elements(scene: dict[str, object]) -> list[dict[str, object]]:
    views = scene["views"]
    assert isinstance(views, list)
    return list(views[0]["elements"])


class TestContract:
    def test_compiled_scene_validates(self) -> None:
        jsonschema.validate(_compile(), _SCHEMA)

    def test_origin_declares_the_source_family(self) -> None:
        """A UI credita o autor e declara fidelidade em vez de prometê-la."""
        scene = _compile(name="Teste", author="Autor", license_id="MIT")
        assert scene["origin"] == {
            "family": "retrofe",
            "author": "Autor",
            "license": "MIT",
        }

    def test_malformed_xml_is_the_only_fatal_case(self) -> None:
        with pytest.raises(SteamZeroError, match="layout RetroFE inválido"):
            _compile("<layout><image")


class TestRealWorldDefects:
    """Layouts reais não são XML bem formado. Os três defeitos são do Aeon Nox."""

    def test_comments_with_long_dashes_are_tolerated(self) -> None:
        xml = """<layout>
          <!---------------------------------------->
          <!-- Sons -->
          <image src="a.png"/>
        </layout>"""
        scene = _compile(xml)
        assert len(_elements(scene)) == 1
        assert any("comentários" in d["reason"] for d in scene["degraded"])  # type: ignore[index]

    def test_mismatched_closing_tags_are_repaired(self) -> None:
        """No Aeon Nox são 301 tags trocadas: <onMenuJumpEnter> fecha </onMenuEnter>."""
        xml = """<layout>
          <reloadableText type="title">
            <onMenuJumpEnter><set duration=".1"><animate type="alpha" to="1"/></set></onMenuEnter>
          </reloadableText>
        </layout>"""
        scene = _compile(xml)
        assert len(_elements(scene)) == 1
        assert any("reparadas" in d["reason"] for d in scene["degraded"])  # type: ignore[index]

    def test_duplicate_attribute_keeps_the_first(self) -> None:
        xml = '<layout><image src="a.png" alpha="0.5" alpha="1"/></layout>'
        scene = _compile(xml)
        element = _elements(scene)[0]
        assert element["layout"]["alpha"] == 0.5  # type: ignore[index]
        assert any("duplicado" in d["reason"] for d in scene["degraded"])  # type: ignore[index]

    def test_every_repair_is_recorded(self) -> None:
        """Corrigir em silêncio esconderia que o arquivo de origem foi tocado."""
        xml = """<layout>
          <!------------>
          <image src="a.png" alpha="1" alpha="0"/>
          <text><onEnter><set duration="1"><animate type="alpha" to="1"/></set></onExit></text>
        </layout>"""
        reasons = " ".join(d["reason"] for d in _compile(xml)["degraded"])  # type: ignore[index]
        assert "comentários" in reasons
        assert "duplicado" in reasons


class TestBindings:
    def test_metadata_binding_is_resolved(self) -> None:
        binding = next(e["binding"] for e in _elements(_compile()) if e.get("kind") == "boundText")
        assert binding == {"source": "metadata", "field": "title"}

    def test_clock_is_a_system_value_not_metadata(self) -> None:
        """`type="time"` é o relógio: não pertence ao jogo."""
        bindings = [e.get("binding") for e in _elements(_compile())]
        assert {"source": "system", "field": "time"} in bindings

    def test_media_binding_is_resolved(self) -> None:
        bindings = [e.get("binding") for e in _elements(_compile())]
        assert {"source": "media", "field": "logo"} in bindings

    def test_launchbox_prefix_maps_to_the_same_field(self) -> None:
        """`lb_year` do LaunchBox é o mesmo campo semântico que `year`."""
        scene = _compile('<layout><reloadableText type="lb_year"/></layout>')
        assert _elements(scene)[0]["binding"]["field"] == "year"  # type: ignore[index]

    def test_theme_specific_art_maps_to_the_base_slot(self) -> None:
        """RetroFE nomeia arte própria como "fanart - Nome do Tema"."""
        scene = _compile('<layout><reloadableImage type="fanart - Aeon Nox"/></layout>')
        assert _elements(scene)[0]["binding"]["field"] == "fanart"  # type: ignore[index]

    def test_unknown_field_degrades_instead_of_becoming_empty(self) -> None:
        """Campo desconhecido virando texto vazio seria falha invisível."""
        scene = _compile('<layout><reloadableText type="inventado"/></layout>')
        assert _elements(scene) == []
        assert any("não suportado" in d["reason"] for d in scene["degraded"])  # type: ignore[index]


class TestEvents:
    def test_navigation_events_become_timelines(self) -> None:
        element = next(e for e in _elements(_compile()) if e.get("kind") == "boundText")
        assert set(element["on"]) == {"enter", "exit"}  # type: ignore[index]

    def test_animation_target_can_be_a_keyword(self) -> None:
        """RetroFE anima para posição relativa; recusar descartaria animação válida."""
        xml = """<layout><image src="a.png">
          <onEnter><set duration="1"><animate type="y" to="center"/></set></onEnter>
        </image></layout>"""
        scene = _compile(xml)
        jsonschema.validate(scene, _SCHEMA)
        animation = _elements(scene)[0]["on"]["enter"][0]["animations"][0]  # type: ignore[index]
        assert animation["to"] == "center"

    def test_non_animatable_property_degrades(self) -> None:
        xml = """<layout><image src="a.png">
          <onEnter><set duration="1"><animate type="rotationZ" to="90"/></set></onEnter>
        </image></layout>"""
        scene = _compile(xml)
        assert any("não animável" in d["reason"] for d in scene["degraded"])  # type: ignore[index]


class TestMenuHierarchy:
    def test_menu_carries_orientation_and_items(self) -> None:
        menu = next(e for e in _elements(_compile()) if e.get("kind") == "menu")["menu"]
        assert menu["orientation"] == "horizontal"  # type: ignore[index]
        assert len(menu["items"]) == 3  # type: ignore[index]
        assert menu["visibleItems"] == 3  # type: ignore[index]

    def test_item_defaults_are_preserved(self) -> None:
        menu = next(e for e in _elements(_compile()) if e.get("kind") == "menu")["menu"]
        assert menu["itemDefaults"]["alpha"] == 0.2  # type: ignore[index]

    def test_unknown_orientation_falls_back_and_records(self) -> None:
        scene = _compile('<layout><menu orientation="espiral"/></layout>')
        menu = _elements(scene)[0]["menu"]
        assert menu["orientation"] == "horizontal"  # type: ignore[index]
        assert any("orientação" in d["reason"] for d in scene["degraded"])  # type: ignore[index]


class TestAssetsAreUntrusted:
    """Caminho vindo de tema é dado externo."""

    @pytest.mark.parametrize(
        "src", ["../../etc/passwd", "/etc/passwd", "http://x.test/a.png", "a.exe"]
    )
    def test_hostile_asset_path_is_refused(self, src: str) -> None:
        scene = _compile(f'<layout><image src="{src}"/></layout>')
        assert _elements(scene) == []
        assert any("recusado" in d["reason"] for d in scene["degraded"])  # type: ignore[index]

    def test_accepted_asset_is_confined_to_assets(self) -> None:
        scene = _compile('<layout><image src="images/bg.png"/></layout>')
        assert _elements(scene)[0]["asset"] == "assets/images/bg.png"


class TestFidelityReport:
    def test_report_measures_coverage(self) -> None:
        report = fidelity_report(_compile())
        assert report["elements"] == 5
        assert 0.0 <= report["coverage"] <= 1.0

    def test_degraded_elements_lower_the_coverage(self) -> None:
        """Fidelidade é declarada a partir do que ficou de fora, não prometida."""
        xml = '<layout><sound src="a.wav"/><image src="a.png"/></layout>'
        report = fidelity_report(_compile(xml))
        assert report["elements"] == 1
        assert report["degraded"] >= 1
        assert report["coverage"] < 1.0
