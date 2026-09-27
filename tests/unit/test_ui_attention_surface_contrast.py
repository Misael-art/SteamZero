# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""UX-01: o texto dos avisos precisa permanecer legível no tema ativo.

A auditoria de 2026-09-26 registrou "o aviso global de perfil e o rodapé de
navegação aparecem com texto quase indistinguível do fundo" nas capturas live da
Central com tema escuro ativo. A causa é calculável, então é calculada aqui em
vez de dependida do analisador de pixels, que o próprio projeto registra como
medição não confiável (``GAP-UI-CONTRAST-MEASUREMENT``).

Duas falhas distintas aparecem na medição:

1. ``Main._contrastTextColor(superfície)`` recebia a superfície como texto. A
   luminância de um texto é ``NaN``, toda comparação falha e a função devolvia
   ``backgroundColor`` — escuro em tema escuro. O harness
   ``tests/qml/check_warning_surface_contrast.qml`` executa a função real; este
   módulo prova a regra contra os tokens dos quatro temas empacotados.
2. Três textos de aviso não passavam por nenhuma regra de contraste: os rótulos
   do botão de atenção da navegação, o retorno transitório de ação e o código de
   erro do cartão de conflito. Sobre superfícies fixas escuras, ``textMuted`` e
   ``warning`` do tema claro reprovam AA.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from steamzero.domain import themes  # noqa: E402
from ui_contrast_inventory import contrast_ratio  # noqa: E402

WCAG_AA_NORMAL = 4.5
#: Critério do próprio UX-01 para alto contraste.
HIGH_CONTRAST_MINIMUM = 7.0

#: Superfícies fixas sobre as quais o shell pinta avisos. Enquanto um aviso usar
#: uma dessas cores, a tinta tem de ser escolhida por contraste, não por token.
FIXED_WARNING_SURFACES = (
    "#24180b",  # banner de perfil, cartão de conflito, leitura parcial
    "#211a10",  # botão de atenção da navegação
    "#080d13",  # rodapé de navegação
    "#352020",  # faixa de erro da central
    "#35171b",  # retorno de ação com erro
    "#102b20",  # retorno de ação concluída
)

#: O que ``ThemeBridge`` impõe quando alto contraste está ativo (texto #ffffff
#: sobre fundo #000000), replicado do produto para a razão ser a mesma.
HIGH_CONTRAST_INKS = {"text": "#ffffff", "background": "#000000"}


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


def _resolved_colors() -> dict[str, dict[str, str]]:
    manifests = _packaged_manifests()
    resolver = themes.ThemeResolver(manifests)
    return {
        theme_id: resolver.resolve(theme_id).to_theme_qml_object()["resolved"]["color"]
        for theme_id in sorted(manifests)
    }


COLORS = _resolved_colors()


def _ink_for(colors: dict[str, str], surface: str) -> tuple[str, str]:
    """Mesma regra do QML: entre `text` e `background`, o que contrasta mais."""
    by_text = contrast_ratio(_rgb(colors["text"]), _rgb(surface))
    by_background = contrast_ratio(_rgb(colors["background"]), _rgb(surface))
    if by_text >= by_background:
        return colors["text"], by_text
    return colors["background"], by_background


def test_the_four_packaged_themes_are_all_measured() -> None:
    """Sem denominador, o restante da prova seria decorativo."""
    assert len(COLORS) >= 4, sorted(COLORS)
    for colors in COLORS.values():
        assert {"text", "background", "surface", "warning", "success", "danger"} <= set(colors)


@pytest.mark.parametrize("theme_id", sorted(COLORS))
@pytest.mark.parametrize("surface", FIXED_WARNING_SURFACES)
def test_warning_text_is_legible_on_every_fixed_surface(theme_id: str, surface: str) -> None:
    ink, ratio = _ink_for(COLORS[theme_id], surface)
    assert ratio >= WCAG_AA_NORMAL, (
        f"{theme_id}: tinta {ink} sobre a superfície fixa {surface} fica em {ratio:.2f}:1; "
        f"WCAG AA exige {WCAG_AA_NORMAL}:1"
    )


@pytest.mark.parametrize("surface", FIXED_WARNING_SURFACES)
def test_at_least_one_packaged_theme_reproves_the_blind_choice(surface: str) -> None:
    """Prova negativa: por que a tinta é calculada e não "sempre o fundo".

    Antes da correção a função degenerava exatamente nisso — com a razão em
    ``NaN`` toda comparação falhava e devolvia ``backgroundColor``. Se um dia o
    fundo bastar em todos os temas empacotados, o cálculo pode ser simplificado
    com segurança, e este teste é quem avisa a hora.
    """
    blind = {
        theme_id: contrast_ratio(_rgb(colors["background"]), _rgb(surface))
        for theme_id, colors in COLORS.items()
    }
    assert min(blind.values()) < WCAG_AA_NORMAL, (
        f"usar sempre `background` passaria em todos os temas sobre {surface}; "
        "a escolha por contraste pode ser simplificada junto com este teste"
    )


@pytest.mark.parametrize("surface", FIXED_WARNING_SURFACES)
def test_high_contrast_warning_text_reaches_seven(surface: str) -> None:
    """Alto contraste: #ffffff sobre as mesmas superfícies fixas, critério 7:1."""
    ratio = contrast_ratio(_rgb(HIGH_CONTRAST_INKS["text"]), _rgb(surface))
    assert ratio >= HIGH_CONTRAST_MINIMUM, (
        f"alto contraste: branco puro sobre {surface} fica em {ratio:.2f}:1, "
        f"e o critério de UX-01 pede {HIGH_CONTRAST_MINIMUM}:1"
    )


@pytest.mark.parametrize("theme_id", sorted(COLORS))
@pytest.mark.parametrize(
    ("token", "surface_token"),
    [
        ("warning", "surface"),
        ("success", "surface"),
        ("danger", "surface"),
        ("warning", "surfaceRaised"),
        ("success", "surfaceRaised"),
        ("danger", "surfaceRaised"),
        ("textMuted", "surface"),
        ("textMuted", "background"),
    ],
)
def test_status_semantic_text_is_legible_on_the_surfaces_it_uses(
    theme_id: str, token: str, surface_token: str
) -> None:
    """Estados de prontidão em verde/dourado/vermelho sobre as superfícies do tema."""
    colors = COLORS[theme_id]
    ratio = contrast_ratio(_rgb(colors[token]), _rgb(colors[surface_token]))
    assert ratio >= WCAG_AA_NORMAL, (
        f"{theme_id}: `{token}` ({colors[token]}) sobre `{surface_token}` "
        f"({colors[surface_token]}) fica em {ratio:.2f}:1 — abaixo de "
        f"{WCAG_AA_NORMAL}:1 para texto essencial"
    )


def test_the_worst_measured_pair_still_clears_aa() -> None:
    """O pior par da tabela é publicado com número, não como "todos passaram"."""
    worst_pair = ""
    worst_ratio = float("inf")
    for theme_id, colors in COLORS.items():
        for surface in FIXED_WARNING_SURFACES:
            ink, ratio = _ink_for(colors, surface)
            if ratio < worst_ratio:
                worst_pair = f"{theme_id}: {ink} sobre {surface}"
                worst_ratio = ratio
    assert worst_ratio > 0
    assert worst_ratio >= WCAG_AA_NORMAL, f"pior par medido {worst_pair} = {worst_ratio:.2f}:1"


#: Rótulos que não passavam por regra de contraste alguma: usavam direto a tinta
#: semântica do tema sobre uma superfície fixa escura.
REPLACED_INKS: tuple[tuple[str, str, str], ...] = (
    ("warning", "#211a10", "título do botão de atenção da navegação"),
    ("textMuted", "#211a10", "subtítulo 'Requer sua atenção'"),
    ("textMuted", "#24180b", "código E-DESKTOP-OWNER-CONFLICT no cartão de conflito"),
    ("text", "#102b20", "retorno de ação concluída"),
    ("text", "#35171b", "retorno de ação com erro"),
)


@pytest.mark.parametrize(("token", "surface", "where"), REPLACED_INKS)
def test_replaced_ink_actually_failed_in_a_packaged_theme(
    token: str, surface: str, where: str
) -> None:
    """Prova negativa: sem isto, trocar por tinta calculada não corrigiria nada."""
    ratios = {
        theme_id: contrast_ratio(_rgb(colors[token]), _rgb(surface))
        for theme_id, colors in COLORS.items()
    }
    worst_ratio = min(ratios.values())
    assert worst_ratio < WCAG_AA_NORMAL, (
        f"{where}: `{token}` sobre {surface} passava em todos os temas "
        f"({', '.join(f'{t}={r:.2f}' for t, r in sorted(ratios.items()))}); "
        "a correção deste ponto não estava tratando um defeito real"
    )
