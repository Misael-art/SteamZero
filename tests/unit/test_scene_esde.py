# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Compilação de temas ES-DE para o IR de cena."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.scene_esde import (
    Selection,
    available_selections,
    collect_variables,
    compile_theme,
    fidelity_report,
    interpolate,
)

_THEME = """
<theme>
  <variables>
    <accent>0.25 0.5</accent>
    <bodySize>0.02</bodySize>
  </variables>
  <view name="system,gamelist">
    <image name="background">
      <pos>0 0</pos>
      <size>1 1</size>
      <path>./art/background.webp</path>
      <zIndex>5</zIndex>
    </image>
  </view>
  <view name="gamelist">
    <text name="title">
      <pos>${accent}</pos>
      <fontSize>${bodySize}</fontSize>
      <metadata>name</metadata>
      <color>FF8800</color>
    </text>
  </view>
</theme>
"""


def _elements(scene: dict, view_id: str) -> list[dict]:
    return next(view["elements"] for view in scene["views"] if view["id"] == view_id)


def test_grouped_view_names_are_expanded_to_each_view() -> None:
    """`<view name="system,gamelist">` declara o MESMO conteúdo para as duas."""
    scene = compile_theme(_THEME, theme_id="demo")

    assert {view["id"] for view in scene["views"]} == {"system", "gamelist"}
    assert [element["name"] for element in _elements(scene, "system")] == ["background"]
    # A gamelist recebe o comum E o específico, nessa ordem.
    assert [element["name"] for element in _elements(scene, "gamelist")] == ["background", "title"]


def test_properties_are_child_elements_not_attributes() -> None:
    """Diferença estrutural medida entre ES-DE e RetroFE."""
    scene = compile_theme(_THEME, theme_id="demo")
    background = _elements(scene, "system")[0]

    assert background["kind"] == "image"
    assert background["layout"] == {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
    assert background["asset"] == "art/background.webp"
    assert background["appearance"]["layer"] == 5


def test_variables_are_interpolated_including_whole_pairs() -> None:
    """Uma variável pode conter o par inteiro: `<pos>${accent}</pos>`.

    Medido nos temas reais (`${badgepos}`, `${imagepos}`): a interpolação
    acontece ANTES da leitura do par, senão o valor chegaria como texto.
    """
    scene = compile_theme(_THEME, theme_id="demo")
    title = _elements(scene, "gamelist")[1]

    assert title["layout"]["x"] == 0.25
    assert title["layout"]["y"] == 0.5
    assert title["layout"]["fontSize"] == 0.02
    assert title["binding"] == {"source": "metadata", "field": "title"}
    assert title["appearance"]["color"] == "#ff8800"


def test_unresolved_variable_degrades_the_property_not_the_element() -> None:
    xml = """
    <theme><view name="system">
      <image name="art"><pos>0.1 0.1</pos><size>${naoDeclarada}</size></image>
    </view></theme>
    """
    scene = compile_theme(xml, theme_id="demo")
    element = _elements(scene, "system")[0]

    # A posição sobrevive; só o tamanho cai.
    assert element["layout"] == {"x": 0.1, "y": 0.1}
    assert any("naoDeclarada" in entry["reason"] for entry in scene["degraded"])


def test_selection_chooses_which_variables_apply() -> None:
    """Variáveis moram em blocos de seleção; herdar de todos misturaria idiomas.

    Medido: 3406 variáveis em `<language>`, 1433 em `<fontSize>`. Sem escolher,
    o último bloco lido venceria por acidente de ordem.
    """
    xml = """
    <theme>
      <fontSize name="small"><variables><body>0.01</body></variables></fontSize>
      <fontSize name="large"><variables><body>0.05</body></variables></fontSize>
      <view name="system"><text name="t"><fontSize>${body}</fontSize></text></view>
    </theme>
    """
    small = compile_theme(xml, theme_id="d", selection=Selection(font_size="small"))
    large = compile_theme(xml, theme_id="d", selection=Selection(font_size="large"))

    assert _elements(small, "system")[0]["layout"]["fontSize"] == 0.01
    assert _elements(large, "system")[0]["layout"]["fontSize"] == 0.05
    # Sem seleção, a variável NÃO resolve — em vez de escolher uma por acaso.
    unset = compile_theme(xml, theme_id="d")
    assert any("body" in entry["reason"] for entry in unset["degraded"])


def test_variant_contributes_its_own_views() -> None:
    """`<variant>` carrega views próprias — 148 nos arquivos medidos."""
    xml = """
    <theme>
      <view name="system"><image name="comum"><pos>0 0</pos></image></view>
      <variant name="detailed">
        <view name="system"><image name="extra"><pos>1 1</pos></image></view>
      </variant>
    </theme>
    """
    plain = compile_theme(xml, theme_id="d")
    detailed = compile_theme(xml, theme_id="d", selection=Selection(variant="detailed"))

    assert [e["name"] for e in _elements(plain, "system")] == ["comum"]
    assert [e["name"] for e in _elements(detailed, "system")] == ["comum", "extra"]


def test_variant_named_all_applies_to_any_selected_variant() -> None:
    xml = """
    <theme>
      <variant name="all">
        <view name="system"><image name="sempre"><pos>0 0</pos></image></view>
      </variant>
    </theme>
    """
    scene = compile_theme(xml, theme_id="d", selection=Selection(variant="qualquer"))
    assert [e["name"] for e in _elements(scene, "system")] == ["sempre"]


@pytest.mark.parametrize(
    "path",
    [
        "../../../etc/passwd",
        "/etc/passwd",
        "https://exemplo.invalido/art.png",
        "..\\windows\\system32\\art.png",
        "payload.sh",
    ],
)
def test_asset_paths_that_escape_the_theme_are_refused(path: str) -> None:
    """Caminho de asset vem de tema de terceiro: travessia, caminho absoluto e
    esquema de URL são as três formas de sair do tema, e as três caem."""
    xml = f"""
    <theme><view name="system">
      <image name="art"><pos>0 0</pos><path>{path}</path></image>
    </view></theme>
    """
    scene = compile_theme(xml, theme_id="d")
    element = _elements(scene, "system")[0]

    assert "asset" not in element
    assert any("asset recusado" in entry["reason"] for entry in scene["degraded"])


def test_unknown_element_degrades_without_killing_the_scene() -> None:
    xml = """
    <theme><view name="system">
      <inventado name="x"><pos>0 0</pos></inventado>
      <image name="valido"><pos>1 1</pos></image>
    </view></theme>
    """
    scene = compile_theme(xml, theme_id="d")

    assert [e["name"] for e in _elements(scene, "system")] == ["valido"]
    assert any(entry["element"] == "inventado" for entry in scene["degraded"])


def test_out_of_range_values_degrade_instead_of_deforming_the_scene() -> None:
    """`fontSize` é fração de tela; 40 deformaria a cena inteira."""
    xml = """
    <theme><view name="system">
      <text name="t"><pos>0 0</pos><fontSize>40</fontSize></text>
    </view></theme>
    """
    scene = compile_theme(xml, theme_id="d")

    assert "fontSize" not in _elements(scene, "system")[0]["layout"]
    assert any("fora de faixa" in entry["reason"] for entry in scene["degraded"])


def test_element_without_any_understood_property_is_dropped() -> None:
    """Nó vazio inflaria a cobertura declarada sem desenhar um pixel."""
    xml = (
        '<theme><view name="system">'
        '<image name="vazio"><desconhecido>x</desconhecido></image>'
        "</view></theme>"
    )
    scene = compile_theme(xml, theme_id="d")

    assert _elements(scene, "system") == []
    assert any("sem propriedade compreendida" in e["reason"] for e in scene["degraded"])


def test_include_is_recorded_as_unresolved_rather_than_ignored() -> None:
    """A cena fica incompleta em relação à origem; esconder isso mentiria sobre
    a fidelidade."""
    xml = "<theme><include>./../theme.xml</include></theme>"
    scene = compile_theme(xml, theme_id="d")

    assert any("não resolvido" in entry["reason"] for entry in scene["degraded"])


def test_malformed_xml_is_fatal_but_unknown_content_is_not() -> None:
    with pytest.raises(SteamZeroError) as excinfo:
        compile_theme("<theme><view>", theme_id="d")
    assert excinfo.value.code == "E-THEME-MANIFEST"


def test_capabilities_file_is_refused_because_it_is_not_a_layout() -> None:
    """`capabilities.xml` declara variantes, não layout: raiz diferente."""
    with pytest.raises(SteamZeroError) as excinfo:
        compile_theme("<themeCapabilities><variant/></themeCapabilities>", theme_id="d")
    assert "themeCapabilities" in (excinfo.value.detail or "")


def test_interpolate_terminates_on_a_reference_cycle_and_reports_it() -> None:
    """Ciclo é dado de terceiro: precisa terminar, e precisa ser REPORTADO.

    Terminar em silêncio devolveria `${a}` como se fosse valor literal, e a
    propriedade viraria lixo textual sem registro — exatamente o que o módulo
    promete não fazer.
    """
    resolved, unresolved = interpolate("${a}", {"a": "${b}", "b": "${a}"})

    assert "${" in resolved
    assert unresolved  # o ciclo aparece no relatório em vez de sumir


def test_available_selections_enumerates_what_the_theme_declares() -> None:
    xml = """
    <theme>
      <variant name="detailed,simple"><view name="system"/></variant>
      <colorScheme name="dark"><variables><c>1</c></variables></colorScheme>
    </theme>
    """
    options = available_selections(ET.fromstring(xml))  # noqa: S314 - fixture deste teste

    assert options["variant"] == ["detailed", "simple"]
    assert options["colorScheme"] == ["dark"]


def test_selection_block_that_does_not_match_is_ignored_entirely() -> None:
    """O que impede vazamento entre variantes."""
    xml = """
    <theme>
      <colorScheme name="dark"><variables><bg>000000</bg></variables></colorScheme>
      <colorScheme name="light"><variables><bg>ffffff</bg></variables></colorScheme>
    </theme>
    """
    root = ET.fromstring(xml)  # noqa: S314 - fixture deste teste
    variables = collect_variables(root, Selection(color_scheme="dark"))
    assert variables == {"bg": "000000"}


def test_fidelity_report_declares_coverage_and_assets() -> None:
    scene = compile_theme(_THEME, theme_id="demo")
    report = fidelity_report(scene)

    assert report["elements"] == 3
    assert sorted(report["views"]) == ["gamelist", "system"]
    assert report["assets"] == ["art/background.webp"]
    assert 0.0 < report["coverage"] <= 1.0
