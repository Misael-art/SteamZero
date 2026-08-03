# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Estado do display: tamanho lógico, dpr, orientação e safe areas.

O tema NÃO descreve o display — ele consulta via bindings ``display.*`` e o
shell alimenta. Este módulo fecha a FORMA desse estado: o que o shell entrega e
o que o tema pode ler, com o vocabulário travado aqui e no registro de tipos.

A invalidação é por eixo (ver ``scene_resolver.DISPLAY_DEPENDENCIES``): trocar a
largura não pode recomputar quem só depende da altura, e um safe area que muda
num lado não pode derrubar a cena inteira. Por isso cada campo tem geração
própria no resolver, e por isso o vocabulário é uma tabela: a tabela é o ponto
único onde campo, tipo e geração nascem juntos, sem chance de divergir.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Any

from steamzero.domain.scene_typing import ValueType


class Orientation(StrEnum):
    """Fechado. O shell normaliza; o tema nunca vê um quarto valor."""

    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"
    LANDSCAPE_FLIPPED = "landscapeFlipped"
    PORTRAIT_FLIPPED = "portraitFlipped"


@dataclass(frozen=True)
class SafeAreaInsets:
    """Recuo seguro por lado, em pixel lógico.

    É o que mantém a UI longe de entalhe, canto arredondado e barra do sistema.
    Um lado NEGATIVO é contradição física — recusado aqui, não no renderizador.
    """

    left: float = 0.0
    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0

    def __post_init__(self) -> None:
        for name, value in (
            ("left", self.left),
            ("top", self.top),
            ("right", self.right),
            ("bottom", self.bottom),
        ):
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueError(f"safe area {name} exige número, recebeu {value!r}")
            if not isfinite(value) or value < 0:
                raise ValueError(f"safe area {name} fora do aceitável: {value}")

    def to_dict(self) -> dict[str, float]:
        return {"left": self.left, "top": self.top, "right": self.right, "bottom": self.bottom}


@dataclass(frozen=True)
class DisplaySpec:
    """O que o shell entrega sobre o display onde o tema renderiza.

    Tamanho em pixel lógico — dpr é campo separado, porque o autor de tema
    escreve em pixel lógico e o renderizador aplica o dpr no fim, nunca no meio
    do layout.
    """

    logical_width: float = 1920.0
    logical_height: float = 1080.0
    dpr: float = 1.0
    orientation: Orientation = Orientation.LANDSCAPE
    safe_area: SafeAreaInsets = SafeAreaInsets()

    def __post_init__(self) -> None:
        for name, value in (
            ("logical_width", self.logical_width),
            ("logical_height", self.logical_height),
        ):
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueError(f"{name} exige número, recebeu {value!r}")
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} precisa ser positiva, recebeu {value!r}")
        if isinstance(self.dpr, bool) or not isinstance(self.dpr, int | float):
            raise ValueError(f"dpr exige número, recebeu {self.dpr!r}")
        if not isfinite(self.dpr) or self.dpr <= 0:
            raise ValueError(f"dpr precisa ser positivo, recebeu {self.dpr!r}")
        if not isinstance(self.orientation, Orientation):
            raise ValueError(
                f"orientação fora do contrato: {self.orientation!r}; "
                f"conhecidas: {[member.value for member in Orientation]}"
            )

    @property
    def aspect_ratio(self) -> float:
        return round(self.logical_width / self.logical_height, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "logicalWidth": self.logical_width,
            "logicalHeight": self.logical_height,
            "dpr": self.dpr,
            "orientation": self.orientation.value,
            "safeArea": self.safe_area.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DisplaySpec:
        raw = payload.get("orientation")
        try:
            orientation = Orientation(str(raw))
        except ValueError:
            raise ValueError(
                f"orientação fora do contrato: {raw!r}; "
                f"conhecidas: {[member.value for member in Orientation]}"
            ) from None
        safe = SafeAreaInsets(**{k: float(v) for k, v in payload.get("safeArea", {}).items()})
        return cls(
            logical_width=float(payload["logicalWidth"]),
            logical_height=float(payload["logicalHeight"]),
            dpr=float(payload.get("dpr", 1.0)),
            orientation=orientation,
            safe_area=safe,
        )


#: Vocabulário fechado dos bindings ``display.*``.
#:
#: A tupla é (tipo publicado, leitor). O tipo aqui e o tipo no registro de tipos
#: vêm DA MESMA tabela — ver ``DISPLAY_BINDING_TYPES`` — para que um não divirja
#: do outro sem quebra de teste.
DISPLAY_FIELDS: dict[str, tuple[ValueType, Callable[[DisplaySpec], Any]]] = {
    "width": (ValueType.NUMBER, lambda spec: spec.logical_width),
    "height": (ValueType.NUMBER, lambda spec: spec.logical_height),
    "aspectRatio": (ValueType.NUMBER, lambda spec: spec.aspect_ratio),
    "dpr": (ValueType.NUMBER, lambda spec: spec.dpr),
    "orientation": (ValueType.STRING, lambda spec: spec.orientation.value),
    "safeArea.left": (ValueType.NUMBER, lambda spec: spec.safe_area.left),
    "safeArea.top": (ValueType.NUMBER, lambda spec: spec.safe_area.top),
    "safeArea.right": (ValueType.NUMBER, lambda spec: spec.safe_area.right),
    "safeArea.bottom": (ValueType.NUMBER, lambda spec: spec.safe_area.bottom),
}

#: Caminhos completos publicados no registro de bindings, derivados da tabela.
#: Derivar é deliberado: declarar os tipos num segundo lugar permitiria que a
#: tabela e o registro divergissem sem quebrar nenhum teste.
DISPLAY_BINDING_TYPES: dict[str, ValueType] = {
    f"display.{field}": spec_type for field, (spec_type, _getter) in DISPLAY_FIELDS.items()
}
