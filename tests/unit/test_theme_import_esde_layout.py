# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Resolução de `<include>` de temas ES-DE, incluindo os includes por sistema."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.core.errors import SteamZeroError
from steamzero.domain.scene_esde import Selection
from steamzero.domain.theme_import_esde_layout import (
    MAX_INCLUDE_DEPTH,
    available_systems,
    resolve_includes,
)


def _write(root: Path, relative: str, body: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_static_includes_are_merged_into_one_tree(tmp_path: Path) -> None:
    _write(tmp_path, "colors.xml", "<theme><variables><bg>112233</bg></variables></theme>")
    entry = _write(
        tmp_path,
        "theme.xml",
        """<theme>
             <include>./colors.xml</include>
             <view name="system"><image name="art"><pos>0 0</pos></image></view>
           </theme>""",
    )

    result = resolve_includes(entry)

    assert result.report()["includedCount"] == 2
    assert [node.tag for node in result.root] == ["variables", "view"]


def test_per_system_include_resolves_the_chosen_system(tmp_path: Path) -> None:
    """Nos temas reais, 214 dos 231 XML são metadados por sistema.

    Sem seguir o include templado, o tema fica sem identidade de sistema —
    nome, descrição e cor do console não chegam.
    """
    _write(
        tmp_path,
        "_inc/systems/_metadata-global/snes.xml",
        "<theme><variables><systemName>Super Nintendo</systemName></variables></theme>",
    )
    entry = _write(
        tmp_path,
        "theme.xml",
        "<theme><include>./_inc/systems/_metadata-global/${system.theme}.xml</include></theme>",
    )

    chosen = resolve_includes(entry, system_id="snes")
    assert "Super Nintendo" in chosen.root.findtext("variables/systemName", "")

    # Sem sistema escolhido, o include é REGISTRADO e não seguido: escolher um
    # por conta própria daria ao tema a identidade de um console arbitrário.
    unchosen = resolve_includes(entry)
    assert unchosen.report()["systemIncludes"] == [
        "./_inc/systems/_metadata-global/${system.theme}.xml"
    ]
    assert unchosen.root.findtext("variables/systemName") is None


def test_include_target_can_be_a_theme_variable(tmp_path: Path) -> None:
    """`<include>${customizationPath}</include>` existe nos temas reais."""
    _write(tmp_path, "extra.xml", "<theme><variables><extra>sim</extra></variables></theme>")
    entry = _write(
        tmp_path,
        "theme.xml",
        """<theme>
             <variables><customizationPath>./extra.xml</customizationPath></variables>
             <include>${customizationPath}</include>
           </theme>""",
    )

    result = resolve_includes(entry)
    assert result.root.findtext("variables/extra") == "sim"


def test_unresolved_include_variable_is_not_reported_as_a_missing_file(tmp_path: Path) -> None:
    """Duas causas distintas que o relatório precisa separar.

    Um include cujo caminho depende de variável não selecionada NÃO é um arquivo
    ausente. Reportar como ausente culparia um arquivo chamado literalmente
    `${customizationPath}`, que nunca existiu e nunca vai existir — o erro
    apontaria para a causa errada.
    """
    entry = _write(tmp_path, "theme.xml", "<theme><include>${naoDefinida}</include></theme>")

    report = resolve_includes(entry).report()

    assert report["missing"] == []
    assert len(report["unresolved"]) == 1
    assert "naoDefinida" in report["unresolved"][0]


def test_resolved_variable_pointing_at_an_absent_file_is_reported_as_missing(
    tmp_path: Path,
) -> None:
    """O outro lado do par: aqui a variável resolve e o arquivo é que falta."""
    entry = _write(
        tmp_path,
        "theme.xml",
        """<theme>
             <variables><p>./nao-existe.xml</p></variables>
             <include>${p}</include>
           </theme>""",
    )

    report = resolve_includes(entry).report()

    assert report["unresolved"] == []
    assert report["missing"] == ["nao-existe.xml"]


def test_selection_decides_which_variables_reach_include_paths(tmp_path: Path) -> None:
    _write(tmp_path, "custom.xml", "<theme><variables><marca>custom</marca></variables></theme>")
    entry = _write(
        tmp_path,
        "theme.xml",
        """<theme>
             <colorScheme name="custom">
               <variables><path>./custom.xml</path></variables>
             </colorScheme>
             <include>${path}</include>
           </theme>""",
    )

    selected = resolve_includes(entry, selection=Selection(color_scheme="custom"))
    assert selected.root.findtext("variables/marca") == "custom"

    unselected = resolve_includes(entry, selection=Selection(color_scheme="blue"))
    assert unselected.report()["unresolved"]


@pytest.mark.parametrize("target", ["../../../etc/passwd", "/etc/passwd"])
def test_include_that_escapes_the_theme_root_is_refused(tmp_path: Path, target: str) -> None:
    """Tema é dado de terceiro: o include precisa cair ANTES de abrir o arquivo."""
    entry = _write(tmp_path / "theme", "theme.xml", f"<theme><include>{target}</include></theme>")

    report = resolve_includes(entry).report()

    assert report["includedCount"] == 1  # só o próprio ponto de entrada
    assert report["refused"] or report["missing"]
    assert "passwd" not in str(report["included"])


def test_symlinked_include_is_refused(tmp_path: Path) -> None:
    """`resolve()` colapsa o link, então comparar strings antes não bastaria."""
    outside = tmp_path / "fora.xml"
    outside.write_text("<theme><variables><vazou>sim</vazou></variables></theme>", encoding="utf-8")
    theme = tmp_path / "theme"
    theme.mkdir()
    (theme / "link.xml").symlink_to(outside)
    entry = _write(theme, "theme.xml", "<theme><include>./link.xml</include></theme>")

    result = resolve_includes(entry)

    assert result.root.findtext("variables/vazou") is None
    assert result.report()["refused"]


def test_include_cycle_terminates(tmp_path: Path) -> None:
    _write(tmp_path, "a.xml", "<theme><include>./b.xml</include></theme>")
    _write(tmp_path, "b.xml", "<theme><include>./a.xml</include></theme>")
    entry = _write(tmp_path, "theme.xml", "<theme><include>./a.xml</include></theme>")

    report = resolve_includes(entry).report()

    assert report["includedCount"] == 3  # cada arquivo lido uma vez só


def test_include_depth_is_bounded(tmp_path: Path) -> None:
    depth = MAX_INCLUDE_DEPTH + 4
    for index in range(depth):
        _write(tmp_path, f"n{index}.xml", f"<theme><include>./n{index + 1}.xml</include></theme>")
    entry = _write(tmp_path, "theme.xml", "<theme><include>./n0.xml</include></theme>")

    report = resolve_includes(entry).report()

    assert report["includedCount"] <= MAX_INCLUDE_DEPTH + 1
    assert any("profundidade" in item for item in report["refused"])


def test_non_theme_root_is_refused_not_merged(tmp_path: Path) -> None:
    """`capabilities.xml` declara variantes, não layout."""
    _write(tmp_path, "capabilities.xml", "<themeCapabilities><variant/></themeCapabilities>")
    entry = _write(tmp_path, "theme.xml", "<theme><include>./capabilities.xml</include></theme>")

    report = resolve_includes(entry).report()

    assert any("themeCapabilities" in item for item in report["refused"])


def test_invalid_system_id_is_refused(tmp_path: Path) -> None:
    entry = _write(tmp_path, "theme.xml", "<theme/>")

    with pytest.raises(SteamZeroError) as excinfo:
        resolve_includes(entry, system_id="../../etc")
    assert excinfo.value.code == "E-THEME-UNSAFE"


def test_available_systems_is_derived_from_the_theme_not_a_fixed_list(tmp_path: Path) -> None:
    for name in ("snes", "megadrive", "_default"):
        _write(tmp_path, f"_inc/systems/_metadata-global/{name}.xml", "<theme/>")

    # `_default` não é um sistema: é o fallback do tema.
    assert available_systems(tmp_path) == ["megadrive", "snes"]
