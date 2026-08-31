# SPDX-License-Identifier: GPL-3.0-or-later
"""Contraste de controles desabilitados passa WCAG AA.

Radiografia 2026-08-31: `palette.disabled.buttonText/text` era `#667481` sobre
o fundo desabilitado `#122131` (3,40:1) e o LauncherGamePage usava `#5f6b85`
sobre `#0a0f16` (3,59:1) — os dois reprovavam AA (4,5) para texto normal. O
correto e' que um controle desabilitado continue legivel, mesmo que a acao
esteja inativa. Corrigido para `#8b93a8`, que passa com folga em ambos os
fundos; este teste trava a regressao usando a mesma formula do projeto
(`ui_contrast_inventory`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from ui_contrast_inventory import contrast_ratio  # noqa: E402

WCAG_AA_NORMAL = 4.5

# Pares (texto desabilitado, fundo desabilitado) usados na UI.
DISABLED_PAIRS: list[tuple[str, str, str]] = [
    ("#8b93a8", "#122131", "central palette.disabled"),
    ("#8b93a8", "#0a0f16", "LauncherGamePage ação desabilitada"),
]


def _rgb(value: str) -> tuple[int, int, int]:
    text = value.lstrip("#")
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


@pytest.mark.parametrize("fg,bg,where", DISABLED_PAIRS)
def test_disabled_control_text_passes_wcag_aa(fg: str, bg: str, where: str) -> None:
    ratio = contrast_ratio(_rgb(fg), _rgb(bg))
    assert ratio >= WCAG_AA_NORMAL, (
        f"{where}: texto desabilitado {fg} sobre {bg} fica em {ratio:.2f}:1; "
        f"WCAG AA exige {WCAG_AA_NORMAL}:1 para texto normal"
    )


def test_old_disabled_values_regress_too_far() -> None:
    """Prova negativa: os valores antigos reprovam (não deixar voltar)."""
    old_pairs = [
        ("#667481", "#122131"),
        ("#5f6b85", "#0a0f16"),
    ]
    for fg, bg in old_pairs:
        assert contrast_ratio(_rgb(fg), _rgb(bg)) < WCAG_AA_NORMAL, (
            f"o valor antigo {fg} sobre {bg} passaria a passar; a correção é desnecessária"
        )
