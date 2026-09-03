# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Do tema instalado até a cena desenhável.

Os três testes de regressão daqui vêm de defeitos medidos no host em
2026-09-03, não de hipótese: sem eles a cena compilava com cobertura alta e
não desenhava nada.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain import scene_esde, theme_assets, theme_scene

THEME_ID = "org.test.esde"


def _install(root: Path, store_root: Path, files: dict[str, str]) -> theme_assets.ThemeAssetStore:
    store = theme_assets.ThemeAssetStore(store_root)
    assets: dict[str, dict[str, str]] = {}
    for relative, payload in files.items():
        stored = store.put(relative, payload.encode("utf-8"))
        assets[relative] = {"digest": stored.digest}
    manifest = {
        "schemaVersion": 1,
        "kind": "steamzero-theme-v1",
        "id": THEME_ID,
        "name": "Teste",
        "version": "deadbeef",
        "license": "CC0-1.0",
        "assets": assets,
    }
    directory = root / THEME_ID
    directory.mkdir(parents=True)
    (directory / "theme.json").write_text(json.dumps(manifest), encoding="utf-8")
    return store


def test_geometry_nested_in_a_selection_block_is_followed(tmp_path: Path) -> None:
    """``<aspectRatio><include>`` é como o tema publica a geometria.

    Seguir só o include de topo preservava o bloco na árvore sem nunca abrir o
    arquivo: no xmb-menu real isso deixava 2 de 27 elementos posicionados, e
    uma cena sem posição não desenha por mais completa que a compilação pareça.
    """
    files = {
        "theme.xml": (
            "<theme><aspectRatio name='16:10'>"
            "<include>./geometria.xml</include>"
            "</aspectRatio></theme>"
        ),
        "geometria.xml": (
            "<theme><view name='system'>"
            "<image name='fundo'><pos>0.1 0.2</pos><size>0.5 0.6</size>"
            "<path>./arte.png</path></image>"
            "</view></theme>"
        ),
        "arte.png": "png",
    }
    store = _install(tmp_path / "themes", tmp_path / "blobs", files)

    rendered = theme_scene.render_scene(
        THEME_ID,
        themes_root=tmp_path / "themes",
        store=store,
        selection=scene_esde.Selection(aspect_ratio="16:10"),
        workspace=tmp_path / "work",
    )

    element = rendered["scene"]["views"][0]["elements"][0]
    assert element["layout"]["x"] == pytest.approx(0.1)
    assert element["layout"]["width"] == pytest.approx(0.5)
    assert element["source"].startswith("file://")


def test_a_deselected_aspect_ratio_is_not_followed_nor_reported_as_missing(
    tmp_path: Path,
) -> None:
    """A geometria de 4:3 não pode vazar sobre a de 16:10.

    E o arquivo não seguido não é "ausente": confundir os dois faria o
    relatório culpar um arquivo que existe.
    """
    files = {
        "theme.xml": (
            "<theme>"
            "<aspectRatio name='16:10'><include>./a.xml</include></aspectRatio>"
            "<aspectRatio name='4:3'><include>./b.xml</include></aspectRatio>"
            "</theme>"
        ),
        "a.xml": (
            "<theme><view name='system'><image name='x'><pos>0.1 0.1</pos></image></view></theme>"
        ),
        "b.xml": (
            "<theme><view name='system'><image name='y'><pos>0.9 0.9</pos></image></view></theme>"
        ),
    }
    store = _install(tmp_path / "themes", tmp_path / "blobs", files)

    rendered = theme_scene.render_scene(
        THEME_ID,
        themes_root=tmp_path / "themes",
        store=store,
        selection=scene_esde.Selection(aspect_ratio="16:10"),
        workspace=tmp_path / "work",
    )

    names = {element.get("name") for element in rendered["scene"]["views"][0]["elements"]}
    assert names == {"x"}
    assert rendered["includes"]["missing"] == []


def test_one_element_split_across_files_becomes_one_drawable_element(tmp_path: Path) -> None:
    """Arte num arquivo e posição noutro descrevem o MESMO elemento.

    Empilhá-los produzia um elemento com arte e sem posição e outro com
    posição e sem arte — nenhum dos dois desenhável, que foi exatamente o que
    a medição no xmb-menu mostrou.
    """
    # Include simples de propósito: isola a mesclagem por nome da correção de
    # include aninhado. Um teste que dependesse das duas não provaria nenhuma.
    files = {
        "theme.xml": (
            "<theme>"
            "<view name='system'><image name='capa'><path>./arte.png</path></image></view>"
            "<include>./pos.xml</include>"
            "</theme>"
        ),
        "pos.xml": (
            "<theme><view name='system'>"
            "<image name='capa'><pos>0.25 0.35</pos><size>0.4 0.4</size></image>"
            "</view></theme>"
        ),
        "arte.png": "png",
    }
    store = _install(tmp_path / "themes", tmp_path / "blobs", files)

    rendered = theme_scene.render_scene(
        THEME_ID, themes_root=tmp_path / "themes", store=store, workspace=tmp_path / "work"
    )

    elements = rendered["scene"]["views"][0]["elements"]
    assert len(elements) == 1, "o elemento partido entre arquivos virou dois"
    assert elements[0]["source"].startswith("file://")
    assert elements[0]["layout"]["x"] == pytest.approx(0.25)


def test_an_asset_missing_from_the_store_is_reported_not_hidden(tmp_path: Path) -> None:
    """Cena que esconde asset faltante parece completa e mente sobre fidelidade."""
    files = {
        "theme.xml": (
            "<theme><view name='system'>"
            "<image name='capa'><pos>0.1 0.1</pos><size>0.2 0.2</size>"
            "<path>./ausente.png</path></image>"
            "</view></theme>"
        ),
    }
    store = _install(tmp_path / "themes", tmp_path / "blobs", files)

    rendered = theme_scene.render_scene(
        THEME_ID, themes_root=tmp_path / "themes", store=store, workspace=tmp_path / "work"
    )

    assert rendered["assets"]["missing"] == ["ausente.png"]
    assert "source" not in rendered["scene"]["views"][0]["elements"][0]


def test_a_system_template_stays_unresolved_without_a_system(tmp_path: Path) -> None:
    """Escolher um sistema por conta própria daria ao tema um console arbitrário."""
    files = {
        "theme.xml": (
            "<theme><view name='system'>"
            "<image name='sys'><pos>0 0</pos><size>1 1</size>"
            "<path>./_inc/${system.theme}.png</path></image>"
            "</view></theme>"
        ),
        "_inc/snes.png": "png",
    }
    store = _install(tmp_path / "themes", tmp_path / "blobs", files)

    without = theme_scene.render_scene(
        THEME_ID, themes_root=tmp_path / "themes", store=store, workspace=tmp_path / "work"
    )
    assert without["assets"]["awaitingSystem"], "template sem sistema deveria ficar pendente"

    with_system = theme_scene.render_scene(
        THEME_ID,
        themes_root=tmp_path / "themes",
        store=store,
        system_id="snes",
        workspace=tmp_path / "work",
    )
    assert with_system["assets"]["resolved"] == 1


def test_a_theme_that_is_not_installed_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "themes").mkdir()
    with pytest.raises(SteamZeroError):
        theme_scene.render_scene(
            "org.test.ausente",
            themes_root=tmp_path / "themes",
            store=theme_assets.ThemeAssetStore(tmp_path / "blobs"),
            workspace=tmp_path / "work",
        )
