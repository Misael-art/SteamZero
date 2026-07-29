# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Cenários visuais canônicos, num lugar só.

Vivem aqui, e não dentro do teste, porque `update_qml_goldens.py` precisa
renderizar exatamente os mesmos cenários que o gate compara. Duas listas
separadas divergiriam, e a baseline passaria a descrever uma cena que o teste
não executa — o pior defeito possível num sistema de golden image, porque ele se
manifesta como aprovação.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from steamzero.domain.qml_render_model import QmlTextRenderModel, to_render_model
from steamzero.domain.resolved_node import (
    FontAssetHandle,
    FontOrigin,
    FontStyle,
    FontWeight,
    ResolvedGeometry,
    ResolvedTextNode,
    TextAlignment,
    TextVerticalAlignment,
)

#: A fonte EMPACOTADA em tests/fixtures/fonts/liberation-sans-2.1.5.
#: O harness isola o fontconfig nela, então é o arquivo do repositório que
#: renderiza — não o pacote da distribuição, que tem o mesmo nome de família e
#: hash diferente.
TEST_FONT = "Liberation Sans"


def _base() -> ResolvedTextNode:
    return ResolvedTextNode(
        id="gameTitle",
        text="Chrono Trigger",
        geometry=ResolvedGeometry(x=40.0, y=60.0, width=700.0, height=70.0),
        color="#F2F6FB",
        font_family=TEST_FONT,
        font_size=48.0,
        font_asset=FontAssetHandle(
            key=TEST_FONT,
            handle="asset://font/LiberationSans",
            origin=FontOrigin.PACKAGED,
            requested_family=TEST_FONT,
            resolved_family=TEST_FONT,
        ),
    )


@dataclass(frozen=True)
class Fixture:
    """Um cenário nomeado. O nome vira o arquivo da baseline."""

    name: str
    overrides: dict[str, object] = field(default_factory=dict)
    canvas: tuple[int, int] = (800, 240)
    background: str = "#101418"

    def node(self) -> ResolvedTextNode:
        return replace(_base(), **self.overrides)

    def model(self) -> QmlTextRenderModel:
        return to_render_model(self.node()).require_model()


#: Frase de acentuação portuguesa. FIXA: mudar o texto muda a baseline, e uma
#: baseline que muda por edição de conteúdo perde o sentido de baseline.
#:
#: Cobre agudo, circunflexo, til, cedilha, maiúscula acentuada, travessão e
#: pontuação — as classes que a métrica ASCII não exercita.
PORTUGUESE_SAMPLE = (
    "Configuração, resolução e conexão — Ação concluída.\n"
    "Às vezes, você poderá iniciar do último salvamento."
)

#: Os cenários que o gate compara. Cada um isola UMA propriedade: quando a
#: baseline muda, a lista já diz o que mudou, sem precisar abrir a imagem.
#:
#: Os oito primeiros são o conjunto histórico e NÃO mudam. Os dois últimos
#: entraram antes da primeira versão das baselines, de propósito: depois de
#: versionar, acrescentar cobertura ausente pareceria mudança de baseline.
FIXTURES: tuple[Fixture, ...] = (
    Fixture("text-baseline"),
    Fixture("text-centered", {"horizontal_alignment": TextAlignment.CENTER}),
    Fixture("text-right", {"horizontal_alignment": TextAlignment.END}),
    Fixture("text-bottom", {"vertical_alignment": TextVerticalAlignment.BOTTOM}),
    Fixture("text-bold", {"font_weight": FontWeight.BOLD}),
    Fixture("text-italic", {"font_style": FontStyle.ITALIC}),
    Fixture("text-translucent", {"opacity": 0.5}),
    Fixture("text-implicit-width", {"geometry": ResolvedGeometry(x=40.0, y=60.0)}),
    # visual-09: a quarta face. Frase longa de propósito — uma palavra curta
    # produz comparação fraca, porque inclinação e peso mal se distinguem em
    # poucos glifos.
    Fixture(
        "text-bold-italic",
        {
            "text": "Bold Italic — ZeroStim",
            "font_weight": FontWeight.BOLD,
            "font_style": FontStyle.ITALIC,
        },
    ),
    # visual-10: acentuação. Canvas maior e corpo menor porque a frase é longa;
    # cortá-la no canvas esconderia justamente os glifos que ela existe para
    # exercitar.
    Fixture(
        "text-portuguese-accents",
        {
            "text": PORTUGUESE_SAMPLE,
            "font_size": 28.0,
            "geometry": ResolvedGeometry(x=40.0, y=40.0, width=1120.0, height=140.0),
        },
        canvas=(1200, 220),
    ),
)

#: Índice estável `visual-NN`. Existe porque o relatório e a conversa usam a
#: numeração, e o nome do arquivo usa o identificador descritivo.
ORDINALS: dict[str, str] = {
    item.name: f"visual-{index:02d}" for index, item in enumerate(FIXTURES, start=1)
}

FIXTURES_BY_NAME: dict[str, Fixture] = {item.name: item for item in FIXTURES}

__all__ = ["FIXTURES", "FIXTURES_BY_NAME", "TEST_FONT", "Fixture"]
