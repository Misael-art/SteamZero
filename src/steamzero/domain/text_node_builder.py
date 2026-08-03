# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Produz ``ResolvedTextNode`` a partir de ``ElementContract``.

É o último ponto em que valores pendentes existem. Depois daqui só há escalares,
e é isso que permite ao renderizador ser burro — e a dois renderizadores
diferentes desenharem a mesma coisa.

Determinismo importa: o mesmo contrato com o mesmo contexto produz exatamente o
mesmo nó, campo a campo. Sem isso, golden image e round-trip não teriam base.

Resolver percentual aqui, e não no renderizador, é decisão de fronteira: o
renderizador não conhece a caixa do pai nem o canvas de projeto, e dar-lhe esse
conhecimento o obrigaria a reimplementar layout.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from steamzero.domain.resolved_node import (
    FontAssetHandle,
    FontOrigin,
    FontStyle,
    FontWeight,
    ImageFillMode,
    ResolvedGeometry,
    ResolvedImageNode,
    ResolvedTextNode,
    TextAlignment,
    TextVerticalAlignment,
)
from steamzero.domain.scene_contract import (
    Alignment,
    DimensionUnit,
    DimensionValue,
    ElementContract,
)
from steamzero.domain.scene_resolver import Resolver
from steamzero.domain.scene_typing import ValueType

#: Alinhamento do contrato para o do nó. `JUSTIFY` sobrevive porque é decisão do
#: renderizador tratá-lo ou degradar — não do construtor.
_HORIZONTAL = {
    Alignment.START: TextAlignment.START,
    Alignment.CENTER: TextAlignment.CENTER,
    Alignment.END: TextAlignment.END,
    Alignment.JUSTIFY: TextAlignment.JUSTIFY,
}

_VERTICAL = {
    Alignment.START: TextVerticalAlignment.TOP,
    Alignment.CENTER: TextVerticalAlignment.MIDDLE,
    Alignment.END: TextVerticalAlignment.BOTTOM,
    Alignment.JUSTIFY: TextVerticalAlignment.TOP,
}

#: Peso numérico de volta para o nome canônico. Temas declaram 400, 700; o nó
#: guarda o nome, que não depende da convenção de nenhum backend.
_WEIGHT_BY_NUMBER = {
    100: FontWeight.THIN,
    200: FontWeight.EXTRA_LIGHT,
    300: FontWeight.LIGHT,
    400: FontWeight.NORMAL,
    500: FontWeight.MEDIUM,
    600: FontWeight.SEMI_BOLD,
    700: FontWeight.BOLD,
    800: FontWeight.EXTRA_BOLD,
    900: FontWeight.BLACK,
}


@dataclass(frozen=True)
class LayoutBox:
    """Caixa do pai e canvas, para resolver percentual e ``auto``."""

    width: float
    height: float
    x: float = 0.0
    y: float = 0.0


def _handle_id(family: str) -> str:
    """Identificador OPACO para a gramática de asset.

    Usar a família crua parecia natural e estava errado: "Liberation Sans" tem
    espaço, e a gramática `asset://<namespace>/<id>` não aceita — o handle
    passava na validação com "Gilroy" e explodia com qualquer nome real de duas
    palavras. O defeito só apareceu quando uma fixture usou uma fonte de
    verdade.

    O handle é opaco por contrato, então nada se perde ao derivá-lo: o nome
    legível continua em `requested_family` e `resolved_family`.
    """
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", family).strip("-")
    digest = hashlib.sha256(family.encode("utf-8")).hexdigest()[:8]
    return f"{slug[:96] or 'font'}-{digest}"


class FontProvider:
    """Emite ``FontAssetHandle`` a partir da chave lógica declarada pelo tema.

    Implementação de referência: o shell real valida o pacote, calcula hash e
    emite um handle opaco. O contrato é o mesmo — a chave entra, o handle sai, e
    caminho do host nunca atravessa.
    """

    def __init__(
        self,
        packaged: dict[str, str] | None = None,
        *,
        system_family: str = "sans-serif",
    ) -> None:
        self._packaged = packaged or {}
        self._system_family = system_family

    def resolve(
        self, key: str | None, *, declared_fallback: tuple[str, ...] = ()
    ) -> FontAssetHandle | None:
        if not key:
            return None
        if key in self._packaged:
            family = self._packaged[key]
            return FontAssetHandle(
                key=key,
                handle=f"asset://font/{_handle_id(key)}",
                origin=FontOrigin.PACKAGED,
                requested_family=family,
                resolved_family=family,
            )
        for candidate in declared_fallback:
            # Fallback declarado pelo autor vence a escolha automática do
            # sistema: é o que ele escreveu que quer quando a primeira falha.
            if candidate in self._packaged.values():
                return FontAssetHandle(
                    key=key,
                    handle=f"asset://font/{_handle_id(candidate)}",
                    origin=FontOrigin.FALLBACK_DECLARED,
                    requested_family=key,
                    resolved_family=candidate,
                    fallback_reason=f"fonte '{key}' não está no pacote",
                )
        return FontAssetHandle(
            key=key,
            handle=f"asset://font/{_handle_id(self._system_family)}",
            origin=FontOrigin.FALLBACK_SYSTEM,
            requested_family=key,
            resolved_family=self._system_family,
            fallback_reason=f"fonte '{key}' ausente e sem fallback declarado no pacote",
        )


def _dimension(value: Any, extent: float, *, default: float = 0.0) -> float | None:
    """Converte dimensão para pixel lógico. ``auto`` devolve ``None``.

    ``None`` significa "o renderizador dimensiona pelo conteúdo" — é diferente de
    zero, que significaria caixa sem tamanho.
    """
    if value is None:
        return default
    if isinstance(value, DimensionValue):
        if value.unit is DimensionUnit.AUTO:
            return None
        if value.unit is DimensionUnit.PERCENT:
            return round(extent * (value.value or 0.0) / 100.0, 4)
        return float(value.value or 0.0)
    if isinstance(value, int | float):
        return float(value)
    return default


def build_text_node(
    element: ElementContract,
    *,
    resolver: Resolver,
    box: LayoutBox | None = None,
    fonts: FontProvider | None = None,
) -> ResolvedTextNode:
    """Resolve um contrato de texto até valores finais.

    ``box`` é aceito por compatibilidade e, quando informado, define a caixa de
    referência do resolver. A fonte da verdade é
    ``ResolutionContext.generations.reference_width/height``: mantê-la num só
    lugar é o que permite invalidar por eixo quando a resolução muda.
    """
    if box is not None:
        resolver.set_reference_box(box.width, box.height)
    provider = fonts or FontProvider()
    diagnostics_before = len(resolver.diagnostics.entries)

    def resolve(value: Any, expected: ValueType, name: str, default: Any) -> Any:
        if value is None:
            return default
        return resolver.resolve(
            value,
            expected,
            target=f"{element.id}.{name}",
            reference=element.source_reference,
        ).value

    typography = element.typography
    text_layout = element.text_layout

    text = resolve(element.text_content, ValueType.STRING, "text", "")
    color = resolve(typography.color if typography else None, ValueType.COLOR, "color", "#000000")
    font_size = resolve(
        typography.font_size if typography else None, ValueType.NUMBER, "fontSize", 16.0
    )
    family = resolve(
        typography.font_family if typography else None, ValueType.STRING, "fontFamily", None
    )
    weight_value = resolve(
        typography.font_weight if typography else None, ValueType.NUMBER, "fontWeight", 400
    )
    visible = resolve(element.visible, ValueType.BOOLEAN, "visible", True)
    opacity = resolve(element.opacity, ValueType.NUMBER, "opacity", 1.0)

    font_asset = provider.resolve(
        str(family) if family else None,
        declared_fallback=typography.font_fallback if typography else (),
    )

    layout = element.layout
    # Passa pelo resolver, e não pelo conversor local, para que a dependência da
    # caixa de referência entre no GRAFO. Converter aqui produzia o número certo
    # e deixava o layout stale: trocar a resolução não invalidava nada, porque
    # nada sabia que aquele valor dependia da largura da view.
    geometry = ResolvedGeometry(
        x=resolver.resolve_dimension(layout.x, axis="width", target=f"{element.id}.x") or 0.0,
        y=resolver.resolve_dimension(layout.y, axis="height", target=f"{element.id}.y") or 0.0,
        width=(
            resolver.resolve_dimension(layout.width, axis="width", target=f"{element.id}.width")
            if layout.width is not None
            else None
        ),
        height=(
            resolver.resolve_dimension(layout.height, axis="height", target=f"{element.id}.height")
            if layout.height is not None
            else None
        ),
    )

    horizontal = TextAlignment.START
    vertical = TextVerticalAlignment.TOP
    if text_layout is not None:
        if text_layout.horizontal_alignment is not None:
            horizontal = _HORIZONTAL[text_layout.horizontal_alignment]
        if text_layout.vertical_alignment is not None:
            vertical = _VERTICAL[text_layout.vertical_alignment]

    style = FontStyle.NORMAL
    if typography is not None and isinstance(typography.font_style, str):
        try:
            style = FontStyle(typography.font_style)
        except ValueError:
            style = FontStyle.NORMAL

    emitted = tuple(entry.to_dict() for entry in resolver.diagnostics.entries[diagnostics_before:])

    return ResolvedTextNode(
        id=element.id,
        text=str(text) if text is not None else "",
        geometry=geometry,
        visible=bool(visible),
        opacity=float(opacity),
        color=str(color),
        font_family=(
            font_asset.resolved_family if font_asset else (str(family) if family else None)
        ),
        font_asset=font_asset,
        font_size=float(font_size),
        font_weight=_WEIGHT_BY_NUMBER.get(int(weight_value or 400), FontWeight.NORMAL),
        font_style=style,
        horizontal_alignment=horizontal,
        vertical_alignment=vertical,
        source_reference=element.source_reference,
        resolution_diagnostics=emitted,
    )


def build_image_node(
    element: ElementContract,
    *,
    resolver: Resolver,
    box: LayoutBox | None = None,
) -> ResolvedImageNode:
    """Resolve um contrato de imagem até valores finais.

    Sem ``image_content`` não há o que desenhar, e não existe default legítimo
    (texto vazio é texto; imagem sem origem é apenas defeito de autor). Recusar
    aqui, na construção, é o mesmo comportamento dos casos ``invalid`` do
    compilador: o erro aparece onde o tema foi descrito.
    """
    if element.image_content is None:
        raise ValueError(f"elemento de imagem sem imageContent: {element.id!r}")

    if box is not None:
        resolver.set_reference_box(box.width, box.height)
    diagnostics_before = len(resolver.diagnostics.entries)

    def resolve(value: Any, expected: ValueType, name: str, default: Any) -> Any:
        if value is None:
            return default
        return resolver.resolve(
            value,
            expected,
            target=f"{element.id}.{name}",
            reference=element.source_reference,
        ).value

    source = resolve(element.image_content, ValueType.MEDIA, "imageContent", None)
    visible = resolve(element.visible, ValueType.BOOLEAN, "visible", True)
    opacity = resolve(element.opacity, ValueType.NUMBER, "opacity", 1.0)

    layout = element.layout
    geometry = ResolvedGeometry(
        x=resolver.resolve_dimension(layout.x, axis="width", target=f"{element.id}.x") or 0.0,
        y=resolver.resolve_dimension(layout.y, axis="height", target=f"{element.id}.y") or 0.0,
        width=(
            resolver.resolve_dimension(layout.width, axis="width", target=f"{element.id}.width")
            if layout.width is not None
            else None
        ),
        height=(
            resolver.resolve_dimension(layout.height, axis="height", target=f"{element.id}.height")
            if layout.height is not None
            else None
        ),
    )

    emitted = tuple(entry.to_dict() for entry in resolver.diagnostics.entries[diagnostics_before:])

    return ResolvedImageNode(
        id=element.id,
        source=str(source) if source is not None else "",
        geometry=geometry,
        visible=bool(visible),
        opacity=float(opacity),
        fill_mode=ImageFillMode.CROP,
        source_reference=element.source_reference,
        resolution_diagnostics=emitted,
    )
