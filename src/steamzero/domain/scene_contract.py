# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato canônico de elemento: layout, transformação, aparência, tipografia.

Todo nó visual herda a mesma estrutura, e cada propriedade aceita ``Value<T>`` —
literal, token, asset, binding, tradução, configuração ou condicional — desde que
o tipo seja compatível.

Três decisões de projeto que o contrato trava:

**Dimensão é tipo fechado.** ``logicalPx``, ``percent`` e ``auto``, e nada mais.
Não há ``calc()``, ``expr`` nem fórmula: dimensão calculada seria uma linguagem
de expressão entrando pela porta dos fundos, e o projeto já decidiu que tema não
executa código.

**Namespaces reservados, não implementados.** ``effects``, ``stateVariants``,
``interaction``, ``accessibility`` e ``performance`` existem no contrato como
espaço reservado. Declará-los agora evita redesenhar o elemento depois; marcá-los
como concluídos seria falso.

**Nada é aproximado sem registro.** Toda conversão que não é exata produz
veredito, e o veredito carrega a origem no arquivo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from steamzero.domain.scene_typing import SourceReference, ValueType


class DimensionUnit(StrEnum):
    """Unidades aceitas. Fechado de propósito."""

    LOGICAL_PX = "logicalPx"
    PERCENT = "percent"
    AUTO = "auto"


@dataclass(frozen=True)
class DimensionValue:
    """Uma medida. ``auto`` não carrega número; as demais carregam."""

    unit: DimensionUnit
    value: float | None = None

    def __post_init__(self) -> None:
        # O conjunto só é fechado se alguém fechar. Sem esta checagem, um
        # `unit="em"` vindo de um tema importado passa por todas as comparações
        # `is` abaixo sem casar com nenhuma, sobrevive à construção, e só falha
        # na conversão para float — longe da causa e sem dizer qual tema errou.
        if not isinstance(self.unit, DimensionUnit):
            raise ValueError(
                f"unidade fora do contrato: {self.unit!r}; "
                f"conhecidas: {[member.value for member in DimensionUnit]}"
            )
        if self.unit is DimensionUnit.AUTO:
            if self.value is not None:
                raise ValueError("auto não aceita valor numérico")
            return
        if self.value is None:
            raise ValueError(f"{self.unit.value} exige valor")
        if self.unit is DimensionUnit.PERCENT and not -1000.0 <= self.value <= 1000.0:
            raise ValueError(f"percentual fora da faixa: {self.value}")
        if self.unit is DimensionUnit.LOGICAL_PX and not -16384.0 <= self.value <= 16384.0:
            raise ValueError(f"dimensão fora da faixa: {self.value}")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": self.unit.value}
        if self.value is not None:
            payload["value"] = self.value
        return payload

    @classmethod
    def px(cls, value: float) -> DimensionValue:
        return cls(DimensionUnit.LOGICAL_PX, value)

    @classmethod
    def percent(cls, value: float) -> DimensionValue:
        return cls(DimensionUnit.PERCENT, value)

    @classmethod
    def auto(cls) -> DimensionValue:
        return cls(DimensionUnit.AUTO)


@dataclass(frozen=True)
class ColorValue:
    """Cor RGBA em sRGB.

    Espaço de cor é explícito desde já, mesmo com um valor só: acrescentar HDR
    depois vira campo novo, não migração de todos os temas existentes.
    """

    red: int
    green: int
    blue: int
    alpha: float = 1.0
    space: str = "sRGB"

    def __post_init__(self) -> None:
        for name, channel in (("red", self.red), ("green", self.green), ("blue", self.blue)):
            if not 0 <= channel <= 255:
                raise ValueError(f"canal {name} fora de 0..255: {channel}")
        if not 0.0 <= self.alpha <= 1.0:
            raise ValueError(f"alpha fora de 0..1: {self.alpha}")

    @classmethod
    def from_hex(cls, value: str) -> ColorValue:
        raw = value.lstrip("#")
        if len(raw) not in {6, 8}:
            raise ValueError(f"cor hexadecimal inválida: {value!r}")
        try:
            channels = [int(raw[i : i + 2], 16) for i in range(0, len(raw), 2)]
        except ValueError:
            raise ValueError(f"cor hexadecimal inválida: {value!r}") from None
        alpha = channels[3] / 255 if len(channels) == 4 else 1.0
        return cls(channels[0], channels[1], channels[2], round(alpha, 4))

    def to_hex(self) -> str:
        base = f"#{self.red:02x}{self.green:02x}{self.blue:02x}"
        if self.alpha >= 1.0:
            return base
        return base + f"{round(self.alpha * 255):02x}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "red": self.red,
            "green": self.green,
            "blue": self.blue,
            "alpha": self.alpha,
            "space": self.space,
        }


class GradientKind(StrEnum):
    LINEAR = "linear"
    RADIAL = "radial"


@dataclass(frozen=True)
class GradientStop:
    position: float
    color: ColorValue

    def __post_init__(self) -> None:
        if not 0.0 <= self.position <= 1.0:
            raise ValueError(f"posição de stop fora de 0..1: {self.position}")

    def to_dict(self) -> dict[str, Any]:
        return {"position": self.position, "color": self.color.to_dict()}


@dataclass(frozen=True)
class GradientValue:
    """Gradiente com stops ordenados.

    Menos de dois stops não é gradiente — é cor sólida disfarçada, e aceitar
    produziria um render que não corresponde ao que o autor escreveu.
    """

    kind: GradientKind
    stops: tuple[GradientStop, ...]
    angle: float = 0.0

    def __post_init__(self) -> None:
        if len(self.stops) < 2:
            raise ValueError("gradiente exige ao menos dois stops")
        positions = [stop.position for stop in self.stops]
        if positions != sorted(positions):
            raise ValueError("stops precisam estar em ordem crescente")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "angle": self.angle,
            "stops": [stop.to_dict() for stop in self.stops],
        }


class Alignment(StrEnum):
    START = "start"
    CENTER = "center"
    END = "end"
    JUSTIFY = "justify"


class WrapMode(StrEnum):
    NONE = "none"
    WORD = "word"
    CHARACTER = "character"


class ElideMode(StrEnum):
    NONE = "none"
    START = "start"
    MIDDLE = "middle"
    END = "end"


class TextTransform(StrEnum):
    NONE = "none"
    UPPERCASE = "uppercase"
    LOWERCASE = "lowercase"
    CAPITALIZE = "capitalize"


class TextDirection(StrEnum):
    AUTO = "auto"
    LTR = "ltr"
    RTL = "rtl"


@dataclass
class TypographySpec:
    """Família, estilo e aparência do texto.

    ``font_fallback`` é lista porque fonte ausente é o caso comum, não a exceção:
    um tema importado referencia fontes que o pacote pode não trazer, e cair para
    a fonte do sistema com registro é melhor que texto invisível.
    """

    font_family: Any = None
    font_asset: Any = None
    font_fallback: tuple[str, ...] = ()
    fallback_by_script: dict[str, str] = field(default_factory=dict)

    font_size: Any = None
    font_weight: Any = None
    font_style: Any = None
    font_stretch: Any = None

    line_height: Any = None
    letter_spacing: Any = None
    word_spacing: Any = None

    color: Any = None
    stroke_color: Any = None
    stroke_width: Any = None
    shadow: Any = None

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "fontFamily": self.font_family,
                "fontAsset": self.font_asset,
                "fontFallback": list(self.font_fallback) or None,
                "fallbackByScript": self.fallback_by_script or None,
                "fontSize": self.font_size,
                "fontWeight": self.font_weight,
                "fontStyle": self.font_style,
                "fontStretch": self.font_stretch,
                "lineHeight": self.line_height,
                "letterSpacing": self.letter_spacing,
                "wordSpacing": self.word_spacing,
                "color": self.color,
                "strokeColor": self.stroke_color,
                "strokeWidth": self.stroke_width,
                "shadow": self.shadow,
            }
        )


@dataclass
class TextLayoutSpec:
    """Como o texto ocupa a caixa."""

    horizontal_alignment: Alignment | None = None
    vertical_alignment: Alignment | None = None
    wrap: WrapMode | None = None
    max_lines: Any = None
    elide: ElideMode | None = None
    overflow: str | None = None
    auto_fit: Any = None
    minimum_font_size: Any = None
    maximum_font_size: Any = None
    text_transform: TextTransform | None = None
    direction: TextDirection | None = None
    language: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "horizontalAlignment": _enum(self.horizontal_alignment),
                "verticalAlignment": _enum(self.vertical_alignment),
                "wrap": _enum(self.wrap),
                "maxLines": self.max_lines,
                "elide": _enum(self.elide),
                "overflow": self.overflow,
                "autoFit": self.auto_fit,
                "minimumFontSize": self.minimum_font_size,
                "maximumFontSize": self.maximum_font_size,
                "textTransform": _enum(self.text_transform),
                "direction": _enum(self.direction),
                "language": self.language,
            }
        )


@dataclass
class LayoutSpec:
    x: Any = None
    y: Any = None
    width: Any = None
    height: Any = None
    min_width: Any = None
    min_height: Any = None
    max_width: Any = None
    max_height: Any = None
    margin: Any = None
    padding: Any = None
    gap: Any = None
    horizontal_alignment: Alignment | None = None
    vertical_alignment: Alignment | None = None
    aspect_ratio: str | None = None
    anchor: str | None = None
    pivot: str | None = None
    safe_area_behavior: str | None = None

    def validate(self) -> None:
        """Regras que só fazem sentido entre campos.

        Mínimo maior que máximo é contradição que renderiza silenciosamente
        errado; melhor recusar na compilação.
        """
        for low, high, name in (
            (self.min_width, self.max_width, "largura"),
            (self.min_height, self.max_height, "altura"),
        ):
            comparable = (
                isinstance(low, DimensionValue)
                and isinstance(high, DimensionValue)
                and low.unit is high.unit
                and low.value is not None
                and high.value is not None
            )
            if comparable and low.value > high.value:
                raise ValueError(f"{name} mínima maior que a máxima")

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "x": _dim(self.x),
                "y": _dim(self.y),
                "width": _dim(self.width),
                "height": _dim(self.height),
                "minWidth": _dim(self.min_width),
                "minHeight": _dim(self.min_height),
                "maxWidth": _dim(self.max_width),
                "maxHeight": _dim(self.max_height),
                "margin": self.margin,
                "padding": self.padding,
                "gap": self.gap,
                "horizontalAlignment": _enum(self.horizontal_alignment),
                "verticalAlignment": _enum(self.vertical_alignment),
                "aspectRatio": self.aspect_ratio,
                "anchor": self.anchor,
                "pivot": self.pivot,
                "safeAreaBehavior": self.safe_area_behavior,
            }
        )


@dataclass
class TransformSpec:
    translate_x: Any = None
    translate_y: Any = None
    scale_x: Any = None
    scale_y: Any = None
    rotation: Any = None
    skew_x: Any = None
    skew_y: Any = None
    mirror_x: Any = None
    mirror_y: Any = None
    transform_origin: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "translateX": _dim(self.translate_x),
                "translateY": _dim(self.translate_y),
                "scaleX": self.scale_x,
                "scaleY": self.scale_y,
                "rotation": self.rotation,
                "skewX": self.skew_x,
                "skewY": self.skew_y,
                "mirrorX": self.mirror_x,
                "mirrorY": self.mirror_y,
                "transformOrigin": self.transform_origin,
            }
        )


@dataclass
class AppearanceSpec:
    background: Any = None
    border: Any = None
    border_radius: Any = None
    shadow: Any = None
    blend_mode: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _compact(
            {
                "background": _color(self.background),
                "border": self.border,
                "borderRadius": _dim(self.border_radius),
                "shadow": self.shadow,
                "blendMode": self.blend_mode,
            }
        )


#: Namespaces previstos e NÃO implementados nesta entrega. Existem no contrato
#: para que acrescentá-los depois não exija redesenhar o elemento.
RESERVED_NAMESPACES = ("effects", "stateVariants", "interaction", "accessibility", "performance")


@dataclass
class ElementContract:
    """Estrutura comum a todo nó visual."""

    id: str
    type: str
    role: str | None = None
    tags: tuple[str, ...] = ()
    z_index: int | None = None
    source_reference: SourceReference | None = None
    debug_label: str | None = None
    extension_data: dict[str, Any] = field(default_factory=dict)

    visible: Any = None
    enabled: Any = None
    opacity: Any = None
    clip: Any = None
    overflow: Any = None

    layout: LayoutSpec = field(default_factory=LayoutSpec)
    transform: TransformSpec = field(default_factory=TransformSpec)
    appearance: AppearanceSpec = field(default_factory=AppearanceSpec)
    typography: TypographySpec | None = None
    text_layout: TextLayoutSpec | None = None
    #: Conteúdo de um elemento de texto. Aceita ``Value<T>`` como qualquer outra
    #: propriedade — literal, binding, tradução ou condicional.
    text_content: Any = None

    def validate(self) -> None:
        self.layout.validate()

    def to_dict(self) -> dict[str, Any]:
        payload = _compact(
            {
                "id": self.id,
                "type": self.type,
                "role": self.role,
                "tags": list(self.tags) or None,
                "zIndex": self.z_index,
                "sourceReference": (
                    self.source_reference.to_dict() if self.source_reference else None
                ),
                "debugLabel": self.debug_label,
                "extensionData": self.extension_data or None,
                "visible": self.visible,
                "enabled": self.enabled,
                "opacity": self.opacity,
                "clip": self.clip,
                "overflow": self.overflow,
                "textContent": self.text_content,
            }
        )
        for name, spec in (
            ("layout", self.layout),
            ("transform", self.transform),
            ("appearance", self.appearance),
            ("typography", self.typography),
            ("textLayout", self.text_layout),
        ):
            if spec is None:
                continue
            rendered = spec.to_dict()
            if rendered:
                payload[name] = rendered
        return payload


#: Tipo aceito por cada propriedade do contrato comum, para o resolver consultar.
CONTRACT_PROPERTY_TYPES: dict[str, ValueType] = {
    "visible": ValueType.BOOLEAN,
    "enabled": ValueType.BOOLEAN,
    "opacity": ValueType.NUMBER,
    "clip": ValueType.BOOLEAN,
    "x": ValueType.DIMENSION,
    "y": ValueType.DIMENSION,
    "width": ValueType.DIMENSION,
    "height": ValueType.DIMENSION,
    "rotation": ValueType.NUMBER,
    "scaleX": ValueType.NUMBER,
    "scaleY": ValueType.NUMBER,
    "background": ValueType.COLOR,
    "color": ValueType.COLOR,
    "strokeColor": ValueType.COLOR,
    "strokeWidth": ValueType.NUMBER,
    "fontFamily": ValueType.STRING,
    "fontAsset": ValueType.FONT,
    "fontSize": ValueType.NUMBER,
    "fontWeight": ValueType.NUMBER,
    "lineHeight": ValueType.NUMBER,
    "letterSpacing": ValueType.NUMBER,
    "wordSpacing": ValueType.NUMBER,
    "maxLines": ValueType.NUMBER,
    "minimumFontSize": ValueType.NUMBER,
    "maximumFontSize": ValueType.NUMBER,
    "textContent": ValueType.STRING,
}


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in payload.items() if item is not None}


def _enum(item: Any) -> Any:
    return item.value if isinstance(item, StrEnum) else item


def _dim(item: Any) -> Any:
    return item.to_dict() if isinstance(item, DimensionValue) else item


def _color(item: Any) -> Any:
    if isinstance(item, ColorValue | GradientValue):
        return item.to_dict()
    return item
