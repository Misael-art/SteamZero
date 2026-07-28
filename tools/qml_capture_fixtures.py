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

#: Fonte do sistema, presente em qualquer Linux com fontconfig. Empacotar uma
#: fonte própria é do VS-07; fixar a família aqui já faz a substituição
#: silenciosa reprovar, que é o risco imediato.
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


#: Os cenários que o gate compara. Cada um isola UMA propriedade: quando a
#: baseline muda, a lista já diz o que mudou, sem precisar abrir a imagem.
FIXTURES: tuple[Fixture, ...] = (
    Fixture("text-baseline"),
    Fixture("text-centered", {"horizontal_alignment": TextAlignment.CENTER}),
    Fixture("text-right", {"horizontal_alignment": TextAlignment.END}),
    Fixture("text-bottom", {"vertical_alignment": TextVerticalAlignment.BOTTOM}),
    Fixture("text-bold", {"font_weight": FontWeight.BOLD}),
    Fixture("text-italic", {"font_style": FontStyle.ITALIC}),
    Fixture("text-translucent", {"opacity": 0.5}),
    Fixture("text-implicit-width", {"geometry": ResolvedGeometry(x=40.0, y=60.0)}),
)

FIXTURES_BY_NAME: dict[str, Fixture] = {item.name: item for item in FIXTURES}

__all__ = ["FIXTURES", "FIXTURES_BY_NAME", "TEST_FONT", "Fixture"]
