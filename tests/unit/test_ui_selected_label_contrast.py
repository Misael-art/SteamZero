# SPDX-License-Identifier: GPL-3.0-or-later
"""O rotulo do item selecionado precisa ser legivel em TODO tema empacotado.

O delegate de seletor troca o fundo para o acento forte quando `checked`. Antes
ele deixava o rotulo em `textColor`, e no tema claro isso dava 1,95:1 contra os
4,5 exigidos: dava para adivinhar "Global", nao para ler.

Nenhuma cor FIXA resolve. No tema claro `text` reprova (1,95) e `background`
passa (7,02); no escuro e o inverso (4,53 contra 3,53). Por isso o QML escolhe,
entre os dois, o que contrasta mais com o fundo selecionado — e este teste
prova a regra contra os tokens REAIS de cada tema empacotado, nao contra um
exemplo escolhido a dedo.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from steamzero.domain import themes  # noqa: E402
from ui_contrast_inventory import contrast_ratio  # noqa: E402

WCAG_AA_NORMAL = 4.5


def _rgb(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def _packaged_manifests() -> dict[str, themes.ThemeManifest]:
    manifests: dict[str, themes.ThemeManifest] = {}
    for directory in sorted((ROOT / "src" / "steamzero" / "themes").iterdir()):
        manifest = directory / "theme.json"
        if manifest.is_file():
            loaded = themes.ThemeManifest.from_dict(
                json.loads(manifest.read_text(encoding="utf-8"))
            )
            manifests[loaded.id] = loaded
    return manifests


def _colors(theme_id: str) -> dict[str, str]:
    manifests = _packaged_manifests()
    resolved = themes.ThemeResolver(manifests).resolve(theme_id).to_theme_qml_object()
    payload = resolved["resolved"]
    return payload["color"] if "color" in payload else payload["tokens"]["color"]


def _selected_label(colors: dict[str, str]) -> tuple[str, float]:
    """Mesma regra do QML: entre `text` e `background`, o que contrasta mais."""
    selected = _rgb(colors["accentStrong"])
    by_text = contrast_ratio(_rgb(colors["text"]), selected)
    by_background = contrast_ratio(_rgb(colors["background"]), selected)
    if by_text >= by_background:
        return "text", by_text
    return "background", by_background


@pytest.mark.parametrize("theme_id", sorted(_packaged_manifests()))
def test_selected_label_is_legible_in_every_packaged_theme(theme_id: str) -> None:
    colors = _colors(theme_id)
    chosen, ratio = _selected_label(colors)
    assert ratio >= WCAG_AA_NORMAL, (
        f"{theme_id}: rótulo do item selecionado ficaria em {ratio:.2f}:1 sobre "
        f"{colors['accentStrong']} escolhendo `{chosen}`; WCAG AA exige "
        f"{WCAG_AA_NORMAL}:1 para texto normal"
    )


def test_no_fixed_choice_would_work_for_every_theme() -> None:
    """Por que a escolha e calculada, e nao uma cor fixa.

    Se algum dia UMA das duas passar em todos os temas, esta guarda cai e alguem
    pode simplificar o QML com seguranca. Enquanto ela reprovar, simplificar
    reintroduz o defeito.
    """
    fixed_text_fails: list[str] = []
    fixed_background_fails: list[str] = []
    for theme_id in sorted(_packaged_manifests()):
        colors = _colors(theme_id)
        selected = _rgb(colors["accentStrong"])
        if contrast_ratio(_rgb(colors["text"]), selected) < WCAG_AA_NORMAL:
            fixed_text_fails.append(theme_id)
        if contrast_ratio(_rgb(colors["background"]), selected) < WCAG_AA_NORMAL:
            fixed_background_fails.append(theme_id)
    assert fixed_text_fails, "usar sempre `text` passaria em todos os temas; simplifique o QML"
    assert fixed_background_fails, (
        "usar sempre `background` passaria em todos os temas; simplifique o QML"
    )
