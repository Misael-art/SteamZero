# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Layouts responsivos e repetidores declarativos da Theme Engine.

Esta é a fronteira entre a descrição declarativa do tema e o renderizador. O
tema escolhe somente um vocabulário fechado (grid/list/wheel/flow/stack, medidas,
breakpoints, offset converter e campos ``item.*``); o shell entrega o read
model; e o resultado já contém
geometria e valores escalares finais para QML. Nenhuma expressão, QML,
JavaScript ou caminho de objeto do Python atravessa esta camada.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

DIAG_LAYOUT_SOURCE = "THEME-LAYOUT-SOURCE-001"
DIAG_LAYOUT_LIMIT = "THEME-LAYOUT-LIMIT-002"

MAX_LAYOUTS = 16
MAX_ITEMS = 128
MAX_TEMPLATE_PROPERTIES = 12
MAX_DIMENSION = 2048.0
MAX_OUTLINE_WIDTH = 8.0
_IDENTIFIER = re.compile(r"^[a-z][a-zA-Z0-9-]{0,63}$")
_SOURCE_PATH = re.compile(r"^[a-z][a-zA-Z0-9]{0,31}(?:\.[a-z][a-zA-Z0-9]{0,31}){1,3}$")
_ITEM_BINDING = re.compile(r"^item\.([a-z][a-zA-Z0-9]{0,31}(?:\.[a-z][a-zA-Z0-9]{0,31})?)$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?$")


class LayoutKind(StrEnum):
    GRID = "grid"
    LIST = "list"
    WHEEL = "wheel"
    COVER_FLOW = "coverFlow"
    CAROUSEL = "carousel"
    FLOW = "flow"
    STACK = "stack"


_DEPTH_KINDS = frozenset(
    {LayoutKind.WHEEL, LayoutKind.COVER_FLOW, LayoutKind.CAROUSEL, LayoutKind.STACK}
)
_HORIZONTAL_DEFAULT_KINDS = frozenset(
    {LayoutKind.WHEEL, LayoutKind.COVER_FLOW, LayoutKind.CAROUSEL, LayoutKind.FLOW}
)


class LayoutDirection(StrEnum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


# O tema nomeia a semântica; a engine escolhe o caractere. É isso que impede um
# pacote de contrabandear glifo arbitrário, emoji ou marca de terceiro.
GLYPHS: dict[str, str] = {
    "none": "",
    "favorite": "★",
    "achievement": "✦",
    "download": "↓",
    "update": "↻",
    "warning": "⚠",
    "error": "✖",
    "network": "◈",
    "save": "▣",
    "offline": "⦸",
}
BADGE_VARIANTS: dict[str, tuple[str, str]] = {
    "neutral": ("#334155", "#f2f6fb"),
    "info": ("#0e7490", "#f2f6fb"),
    "success": ("#166534", "#f2f6fb"),
    "warning": ("#92400e", "#fff7ed"),
    "danger": ("#7f1d1d", "#fee2e2"),
}
LABEL_ROLES: dict[str, dict[str, Any]] = {
    "body": {"fontPixelSize": 16, "fontWeight": 400, "opacity": 1.0},
    "title": {"fontPixelSize": 20, "fontWeight": 600, "opacity": 1.0},
    "subtitle": {"fontPixelSize": 16, "fontWeight": 500, "opacity": 0.9},
    "meta": {"fontPixelSize": 13, "fontWeight": 400, "opacity": 0.75},
    "caption": {"fontPixelSize": 11, "fontWeight": 400, "opacity": 0.6},
}
MAX_BADGE_TEXT = 12

_PROPERTIES: dict[str, frozenset[str]] = {
    "text": frozenset(
        {
            "text",
            "color",
            "fontFamily",
            "fontPixelSize",
            "fontWeight",
            "fontItalic",
            "horizontalAlignment",
            "verticalAlignment",
            "visible",
            "opacity",
            "role",
        }
    ),
    "image": frozenset({"source", "fillMode", "visible", "opacity"}),
    "badge": frozenset({"text", "variant", "glyph", "visible", "opacity"}),
}
_TEXT_DEFAULTS: dict[str, Any] = {
    "text": "",
    "color": "#ffffff",
    "fontFamily": "",
    "fontPixelSize": 16,
    "fontWeight": 400,
    "fontItalic": False,
    "horizontalAlignment": "AlignLeft",
    "verticalAlignment": "AlignTop",
    "visible": True,
    "opacity": 1.0,
    "role": "body",
}
_IMAGE_DEFAULTS: dict[str, Any] = {
    "source": "",
    "fillMode": "PreserveAspectFit",
    "visible": True,
    "opacity": 1.0,
}
_BADGE_DEFAULTS: dict[str, Any] = {
    "text": "",
    "variant": "neutral",
    "glyph": "none",
    "visible": True,
    "opacity": 1.0,
}
_DEFAULTS_BY_KIND: dict[str, dict[str, Any]] = {
    "text": _TEXT_DEFAULTS,
    "image": _IMAGE_DEFAULTS,
    "badge": _BADGE_DEFAULTS,
}


def _number(value: Any, *, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"{name} exige número finito")
    number = float(value)
    if not low <= number <= high:
        raise ValueError(f"{name} fora de {low:g}..{high:g}")
    return number


def _identifier(value: Any, *, name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{name} inválido")
    return value


def _safe_scalar(value: Any, *, name: str) -> str | int | float | bool | None:
    if value is None or isinstance(value, str | int | float | bool):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"{name} exige escalar finito")
        return value
    raise ValueError(f"{name} aceita somente valor escalar ou binding")


@dataclass(frozen=True)
class LayoutBounds:
    width: float
    height: float
    x: float = 0.0
    y: float = 0.0

    def __post_init__(self) -> None:
        _number(self.width, name="bounds.width", low=1, high=16384)
        _number(self.height, name="bounds.height", low=1, high=16384)
        _number(self.x, name="bounds.x", low=-16384, high=16384)
        _number(self.y, name="bounds.y", low=-16384, high=16384)


@dataclass(frozen=True)
class LayoutItemSize:
    width: float
    height: float

    def __post_init__(self) -> None:
        _number(self.width, name="item.width", low=1, high=MAX_DIMENSION)
        _number(self.height, name="item.height", low=1, high=MAX_DIMENSION)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> LayoutItemSize:
        if set(raw) != {"width", "height"}:
            raise ValueError("item exige somente width e height")
        return cls(
            width=_number(raw["width"], name="item.width", low=1, high=MAX_DIMENSION),
            height=_number(raw["height"], name="item.height", low=1, high=MAX_DIMENSION),
        )


@dataclass(frozen=True)
class LayoutBreakpoint:
    columns: int
    min_width: float | None = None
    max_width: float | None = None

    def __post_init__(self) -> None:
        if isinstance(self.columns, bool) or not isinstance(self.columns, int):
            raise ValueError("breakpoint.columns exige inteiro")
        if not 1 <= self.columns <= 16:
            raise ValueError("breakpoint.columns fora de 1..16")
        if self.min_width is not None:
            _number(self.min_width, name="breakpoint.minWidth", low=0, high=16384)
        if self.max_width is not None:
            _number(self.max_width, name="breakpoint.maxWidth", low=0, high=16384)
        if (
            self.min_width is not None
            and self.max_width is not None
            and self.min_width > self.max_width
        ):
            raise ValueError("breakpoint mínimo maior que máximo")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> LayoutBreakpoint:
        unknown = set(raw) - {"columns", "minWidth", "maxWidth"}
        if unknown or "columns" not in raw:
            raise ValueError("breakpoint inválido")
        return cls(
            columns=raw["columns"],
            min_width=(
                _number(raw["minWidth"], name="breakpoint.minWidth", low=0, high=16384)
                if "minWidth" in raw
                else None
            ),
            max_width=(
                _number(raw["maxWidth"], name="breakpoint.maxWidth", low=0, high=16384)
                if "maxWidth" in raw
                else None
            ),
        )

    def matches(self, width: float) -> bool:
        return (self.min_width is None or width >= self.min_width) and (
            self.max_width is None or width <= self.max_width
        )


@dataclass(frozen=True)
class LayoutOffset:
    scale_step: float = 0.08
    opacity_step: float = 0.18
    min_scale: float = 0.7
    min_opacity: float = 0.35
    rotation_step: float = 0.0
    max_rotation: float = 0.0
    overlap: float = 1.0

    def __post_init__(self) -> None:
        _number(self.scale_step, name="offset.scaleStep", low=0, high=0.5)
        _number(self.opacity_step, name="offset.opacityStep", low=0, high=0.5)
        _number(self.min_scale, name="offset.minScale", low=0.25, high=1)
        _number(self.min_opacity, name="offset.minOpacity", low=0, high=1)
        _number(self.rotation_step, name="offset.rotationStep", low=0, high=60)
        _number(self.max_rotation, name="offset.maxRotation", low=0, high=70)
        _number(self.overlap, name="offset.overlap", low=0.25, high=1)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> LayoutOffset:
        unknown = set(raw) - {
            "scaleStep",
            "opacityStep",
            "minScale",
            "minOpacity",
            "rotationStep",
            "maxRotation",
            "overlap",
        }
        if unknown:
            raise ValueError("offset inválido")
        return cls(
            scale_step=_number(
                raw.get("scaleStep", 0.08), name="offset.scaleStep", low=0, high=0.5
            ),
            opacity_step=_number(
                raw.get("opacityStep", 0.18), name="offset.opacityStep", low=0, high=0.5
            ),
            min_scale=_number(raw.get("minScale", 0.7), name="offset.minScale", low=0.25, high=1),
            min_opacity=_number(
                raw.get("minOpacity", 0.35), name="offset.minOpacity", low=0, high=1
            ),
            rotation_step=_number(
                raw.get("rotationStep", 0), name="offset.rotationStep", low=0, high=60
            ),
            max_rotation=_number(
                raw.get("maxRotation", 0), name="offset.maxRotation", low=0, high=70
            ),
            overlap=_number(raw.get("overlap", 1), name="offset.overlap", low=0.25, high=1),
        )

    def apply(self, distance: int) -> tuple[float, float, int, float]:
        steps = abs(distance)
        scale = max(1.0 - steps * self.scale_step, self.min_scale)
        opacity = max(1.0 - steps * self.opacity_step, self.min_opacity)
        rotation = max(-self.max_rotation, min(self.max_rotation, distance * self.rotation_step))
        return (round(scale, 4), round(opacity, 4), 32 - steps, round(rotation, 4))

    def to_dict(self) -> dict[str, float]:
        return {
            "scaleStep": self.scale_step,
            "opacityStep": self.opacity_step,
            "minScale": self.min_scale,
            "minOpacity": self.min_opacity,
            "rotationStep": self.rotation_step,
            "maxRotation": self.max_rotation,
            "overlap": self.overlap,
        }


@dataclass(frozen=True)
class LayoutTreatment:
    """Tratamento visual de um item pela posição relativa ao centro."""

    scale: float | None = None
    opacity: float | None = None
    outline_width: float = 0.0
    outline_color: str = "#ffffff"

    def __post_init__(self) -> None:
        if self.scale is not None:
            _number(self.scale, name="highlight.scale", low=0.5, high=2)
        if self.opacity is not None:
            _number(self.opacity, name="highlight.opacity", low=0, high=1)
        _number(self.outline_width, name="highlight.outlineWidth", low=0, high=MAX_OUTLINE_WIDTH)
        if not isinstance(self.outline_color, str) or not _COLOR.fullmatch(self.outline_color):
            raise ValueError("highlight.outlineColor inválida")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], *, name: str) -> LayoutTreatment:
        unknown = set(raw) - {"scale", "opacity", "outlineWidth", "outlineColor"}
        if unknown:
            raise ValueError(f"{name} inválido: {sorted(unknown)}")
        return cls(
            scale=(
                _number(raw["scale"], name="highlight.scale", low=0.5, high=2)
                if "scale" in raw
                else None
            ),
            opacity=(
                _number(raw["opacity"], name="highlight.opacity", low=0, high=1)
                if "opacity" in raw
                else None
            ),
            outline_width=_number(
                raw.get("outlineWidth", 0),
                name="highlight.outlineWidth",
                low=0,
                high=MAX_OUTLINE_WIDTH,
            ),
            outline_color=str(raw.get("outlineColor", "#ffffff")),
        )

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "outlineWidth": self.outline_width,
            "outlineColor": self.outline_color,
        }
        if self.scale is not None:
            value["scale"] = self.scale
        if self.opacity is not None:
            value["opacity"] = self.opacity
        return value

    def apply(self, node: dict[str, Any]) -> None:
        """Sobrepõe o falloff do offset converter no item tratado."""
        if self.scale is not None:
            node["scale"] = self.scale
        if self.opacity is not None:
            node["opacity"] = self.opacity
        node["outlineWidth"] = self.outline_width
        node["outlineColor"] = self.outline_color


@dataclass(frozen=True)
class LayoutHighlight:
    """Destaque central e, opcionalmente, tratamento dos vizinhos imediatos."""

    centre: LayoutTreatment
    adjacent: LayoutTreatment | None = None

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> LayoutHighlight:
        adjacent = raw.get("adjacent")
        if adjacent is not None and not isinstance(adjacent, Mapping):
            raise ValueError("highlight.adjacent exige objeto")
        centre_raw = {key: value for key, value in raw.items() if key != "adjacent"}
        return cls(
            centre=LayoutTreatment.from_dict(centre_raw, name="highlight"),
            adjacent=(
                LayoutTreatment.from_dict(adjacent, name="highlight.adjacent")
                if adjacent is not None
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        value = self.centre.to_dict()
        if self.adjacent is not None:
            value["adjacent"] = self.adjacent.to_dict()
        return value


@dataclass(frozen=True)
class LayoutTemplate:
    kind: str
    id: str
    properties: Mapping[str, str | int | float | bool | None | Mapping[str, str]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        if self.kind not in _PROPERTIES:
            raise ValueError(f"template.kind desconhecido: {self.kind!r}")
        _identifier(self.id, name="template.id")
        if len(self.properties) > MAX_TEMPLATE_PROPERTIES:
            raise ValueError("template.properties excede limite")
        unknown = set(self.properties) - _PROPERTIES[self.kind]
        if unknown:
            raise ValueError(f"template.properties não permitidas: {sorted(unknown)}")
        for name, value in self.properties.items():
            if isinstance(value, Mapping):
                if set(value) - {"binding", "fallback"} or "binding" not in value:
                    raise ValueError(f"template.properties.{name} binding inválido")
                binding = value["binding"]
                if not isinstance(binding, str) or not _ITEM_BINDING.fullmatch(binding):
                    raise ValueError(f"template.properties.{name} binding inválido")
                if "fallback" in value:
                    _safe_scalar(value["fallback"], name=f"template.properties.{name}.fallback")
            else:
                _safe_scalar(value, name=f"template.properties.{name}")
        self._validate_property_types()

    def _validate_property_types(self) -> None:
        for name, value in self.properties.items():
            if isinstance(value, Mapping):
                continue
            if name == "color" and (not isinstance(value, str) or not _COLOR.fullmatch(value)):
                raise ValueError("template.properties.color inválida")
            if name == "fontPixelSize":
                _number(value, name="template.properties.fontPixelSize", low=8, high=128)
            if name == "opacity":
                _number(value, name="template.properties.opacity", low=0, high=1)
            if name in {"visible", "fontItalic"} and not isinstance(value, bool):
                raise ValueError(f"template.properties.{name} exige booleano")
            if name == "glyph" and value not in GLYPHS:
                raise ValueError(f"template.properties.glyph desconhecido: {value!r}")
            if name == "variant" and value not in BADGE_VARIANTS:
                raise ValueError(f"template.properties.variant desconhecida: {value!r}")
            if name == "role" and value not in LABEL_ROLES:
                raise ValueError(f"template.properties.role desconhecido: {value!r}")
            if name == "fillMode" and value not in {
                "Stretch",
                "PreserveAspectFit",
                "PreserveAspectCrop",
                "Original",
            }:
                raise ValueError("template.properties.fillMode inválido")
            if name == "horizontalAlignment" and value not in {
                "AlignLeft",
                "AlignHCenter",
                "AlignRight",
                "AlignJustify",
            }:
                raise ValueError("template.properties.horizontalAlignment inválido")
            if name == "verticalAlignment" and value not in {
                "AlignTop",
                "AlignVCenter",
                "AlignBottom",
            }:
                raise ValueError("template.properties.verticalAlignment inválido")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> LayoutTemplate:
        unknown = set(raw) - {"kind", "id", "properties"}
        if unknown or "kind" not in raw or "id" not in raw:
            raise ValueError("template inválido")
        properties = raw.get("properties", {})
        if not isinstance(properties, Mapping):
            raise ValueError("template.properties exige objeto")
        return cls(
            kind=str(raw["kind"]),
            id=_identifier(raw["id"], name="template.id"),
            properties=properties,
        )


@dataclass(frozen=True)
class LayoutRecipe:
    id: str
    source: str
    kind: LayoutKind
    item: LayoutItemSize
    template: LayoutTemplate
    gap: float = 0.0
    max_items: int = MAX_ITEMS
    columns: int = 1
    direction: LayoutDirection = LayoutDirection.VERTICAL
    selected: int = 0
    offset: LayoutOffset | None = None
    highlight: LayoutHighlight | None = None
    breakpoints: tuple[LayoutBreakpoint, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.id, name="layout.id")
        if not _SOURCE_PATH.fullmatch(self.source) or "__" in self.source:
            raise ValueError("source inválido")
        _number(self.gap, name="gap", low=0, high=256)
        if (
            isinstance(self.max_items, bool)
            or not isinstance(self.max_items, int)
            or not 1 <= self.max_items <= MAX_ITEMS
        ):
            raise ValueError(f"maxItems fora de 1..{MAX_ITEMS}")
        if (
            isinstance(self.columns, bool)
            or not isinstance(self.columns, int)
            or not 1 <= self.columns <= 16
        ):
            raise ValueError("columns fora de 1..16")
        if (
            isinstance(self.selected, bool)
            or not isinstance(self.selected, int)
            or not 0 <= self.selected <= MAX_ITEMS - 1
        ):
            raise ValueError("selected fora de 0..127")
        if self.kind is not LayoutKind.GRID and self.breakpoints:
            raise ValueError(f"{self.kind.value} não aceita breakpoints")
        if self.kind is LayoutKind.COVER_FLOW and self.direction is not LayoutDirection.HORIZONTAL:
            raise ValueError("coverFlow só é horizontal")
        if self.offset is not None and self.kind not in _DEPTH_KINDS:
            raise ValueError("offset só é válido em wheel, coverFlow, carousel ou stack")
        if self.highlight is not None and self.kind not in _DEPTH_KINDS:
            raise ValueError(
                "highlight exige layout com centro: wheel, coverFlow, carousel ou stack"
            )
        ranges: list[tuple[float, float]] = []
        for point in self.breakpoints:
            low = point.min_width if point.min_width is not None else float("-inf")
            high = point.max_width if point.max_width is not None else float("inf")
            for other_low, other_high in ranges:
                if low <= other_high and other_low <= high:
                    raise ValueError("breakpoints se sobrepõem")
            ranges.append((low, high))

    @classmethod
    def from_dict(cls, layout_id: str, raw: Mapping[str, Any]) -> LayoutRecipe:
        allowed = {
            "source",
            "kind",
            "item",
            "template",
            "gap",
            "maxItems",
            "columns",
            "direction",
            "selected",
            "offset",
            "highlight",
            "breakpoints",
        }
        unknown = set(raw) - allowed
        required = {"source", "kind", "item", "template"}
        if unknown or not required <= set(raw):
            raise ValueError("layout inválido")
        try:
            kind = LayoutKind(str(raw["kind"]))
        except ValueError:
            raise ValueError("kind inválido") from None
        if kind is LayoutKind.FLOW and "columns" in raw:
            raise ValueError("flow calcula columns a partir dos bounds")
        try:
            direction_default = "horizontal" if kind in _HORIZONTAL_DEFAULT_KINDS else "vertical"
            direction = LayoutDirection(str(raw.get("direction", direction_default)))
        except ValueError:
            raise ValueError("direction inválida") from None
        item = raw["item"]
        template = raw["template"]
        breakpoints = raw.get("breakpoints", [])
        if not isinstance(item, Mapping):
            raise ValueError("item exige objeto")
        if not isinstance(template, Mapping):
            raise ValueError("template exige objeto")
        if not isinstance(breakpoints, list) or len(breakpoints) > 8:
            raise ValueError("breakpoints inválidos")
        if not all(isinstance(point, Mapping) for point in breakpoints):
            raise ValueError("breakpoints inválidos")
        offset_raw = raw.get("offset")
        if offset_raw is not None and not isinstance(offset_raw, Mapping):
            raise ValueError("offset exige objeto")
        highlight_raw = raw.get("highlight")
        if highlight_raw is not None and not isinstance(highlight_raw, Mapping):
            raise ValueError("highlight exige objeto")
        return cls(
            id=_identifier(layout_id, name="layout.id"),
            source=str(raw["source"]),
            kind=kind,
            item=LayoutItemSize.from_dict(item),
            template=LayoutTemplate.from_dict(template),
            gap=_number(raw.get("gap", 0), name="gap", low=0, high=256),
            max_items=raw.get("maxItems", MAX_ITEMS),
            columns=raw.get("columns", 1),
            direction=direction,
            selected=raw.get("selected", 0),
            offset=LayoutOffset.from_dict(offset_raw) if offset_raw is not None else None,
            highlight=(
                LayoutHighlight.from_dict(highlight_raw) if highlight_raw is not None else None
            ),
            breakpoints=tuple(LayoutBreakpoint.from_dict(point) for point in breakpoints),
        )

    def columns_for(self, width: float) -> int:
        for point in self.breakpoints:
            if point.matches(width):
                return point.columns
        return self.columns

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "source": self.source,
            "kind": self.kind.value,
            "item": {"width": self.item.width, "height": self.item.height},
            "template": {
                "kind": self.template.kind,
                "id": self.template.id,
                "properties": dict(self.template.properties),
            },
            "gap": self.gap,
            "maxItems": self.max_items,
        }
        if self.kind is LayoutKind.GRID:
            value["columns"] = self.columns
        if self.kind in {LayoutKind.LIST, LayoutKind.FLOW}:
            value["direction"] = self.direction.value
        if self.kind in _DEPTH_KINDS:
            value["direction"] = self.direction.value
            value["selected"] = self.selected
            if self.offset is not None:
                value["offset"] = self.offset.to_dict()
            if self.highlight is not None:
                value["highlight"] = self.highlight.to_dict()
        if self.breakpoints:
            value["breakpoints"] = [
                {
                    key: value
                    for key, value in (
                        ("columns", point.columns),
                        ("minWidth", point.min_width),
                        ("maxWidth", point.max_width),
                    )
                    if value is not None
                }
                for point in self.breakpoints
            ]
        return value


@dataclass(frozen=True)
class LayoutRecipeBook:
    layouts: Mapping[str, LayoutRecipe]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("schemaVersion de sceneLayouts inválido")
        if not self.layouts or len(self.layouts) > MAX_LAYOUTS:
            raise ValueError(f"layouts exige 1..{MAX_LAYOUTS} entradas")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> LayoutRecipeBook:
        if set(raw) != {"schemaVersion", "layouts"}:
            raise ValueError("sceneLayouts inválido")
        layouts = raw["layouts"]
        if not isinstance(layouts, Mapping):
            raise ValueError("layouts exige objeto")
        if len(layouts) > MAX_LAYOUTS:
            raise ValueError(f"layouts excede {MAX_LAYOUTS}")
        parsed: dict[str, LayoutRecipe] = {}
        for layout_id, recipe in layouts.items():
            if not isinstance(recipe, Mapping):
                raise ValueError("layout exige objeto")
            parsed[_identifier(layout_id, name="layout.id")] = LayoutRecipe.from_dict(
                layout_id, recipe
            )
        return cls(layouts=parsed, schema_version=raw["schemaVersion"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "layouts": {key: value.to_dict() for key, value in self.layouts.items()},
        }


@dataclass(frozen=True)
class LayoutDiagnostic:
    code: str
    layout: str
    reason: str
    fallback: str = "empty"

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "layout": self.layout,
            "reason": self.reason,
            "fallback": self.fallback,
        }


@dataclass(frozen=True)
class ResolvedLayoutEntry:
    index: int
    x: float
    y: float
    width: float
    height: float
    node: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.node)


@dataclass(frozen=True)
class ResolvedLayout:
    id: str
    kind: LayoutKind
    columns: int
    entries: tuple[ResolvedLayoutEntry, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "columns": self.columns,
            "entries": [entry.to_dict() for entry in self.entries],
        }


@dataclass(frozen=True)
class SceneLayoutResolution:
    layouts: Mapping[str, ResolvedLayout]
    diagnostics: tuple[LayoutDiagnostic, ...] = ()

    def to_qml_object(self) -> dict[str, Any]:
        return {
            "layouts": {layout_id: layout.to_dict() for layout_id, layout in self.layouts.items()},
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


def _wrap_distance(index: int, selected: int, count: int) -> int:
    if count <= 0:
        return 0
    raw = (index - selected) % count
    if raw > count // 2:
        return raw - count
    return raw


def _carousel_point(
    bounds: LayoutBounds, item: LayoutItemSize, distance: int, count: int
) -> tuple[float, float]:
    center_x = bounds.x + (bounds.width - item.width) / 2
    center_y = bounds.y + (bounds.height - item.height) / 2
    if count <= 1:
        return center_x, center_y
    radius_x = max((bounds.width - item.width) / 2, 1.0)
    radius_y = max((bounds.height - item.height) / 2, 1.0)
    theta = 2.0 * math.pi * distance / count
    return (
        round(center_x + radius_x * math.sin(theta), 4),
        round(center_y - radius_y * math.cos(theta), 4),
    )


def _flow_tracks(recipe: LayoutRecipe, bounds: LayoutBounds, count: int) -> tuple[int, int, bool]:
    """Quantas faixas cabem no eixo de quebra, quantas colunas saem e se degradou.

    Horizontal quebra em linhas pela largura; vertical quebra em colunas pela
    altura. Item maior que os bounds não some: a faixa é fixada em 1 e o chamador
    registra diagnóstico.
    """
    if recipe.direction is LayoutDirection.HORIZONTAL:
        span, extent = bounds.width, recipe.item.width
    else:
        span, extent = bounds.height, recipe.item.height
    fitted = int((span + recipe.gap) // (extent + recipe.gap))
    tracks = max(fitted, 1)
    if recipe.direction is LayoutDirection.HORIZONTAL:
        columns = tracks
    else:
        columns = max(1, math.ceil(count / tracks)) if count else 1
    return tracks, columns, fitted < 1


def _apply_highlight(
    highlight: LayoutHighlight | None, node: dict[str, Any], distance: int
) -> None:
    """Marca centro e vizinhos e sobrepõe o tratamento declarado.

    Sem ``highlight`` o item continua exatamente no falloff do offset converter;
    o contorno fica em zero para que o QML não precise decidir nada.
    """
    node["highlighted"] = distance == 0
    treats_adjacent = highlight is not None and highlight.adjacent is not None
    node["adjacent"] = treats_adjacent and abs(distance) == 1
    node.setdefault("outlineWidth", 0.0)
    node.setdefault("outlineColor", "#ffffff")
    if highlight is None:
        return
    if distance == 0:
        highlight.centre.apply(node)
    elif highlight.adjacent is not None and abs(distance) == 1:
        highlight.adjacent.apply(node)


def _materialize_badge(values: dict[str, Any]) -> None:
    """Resolve glifo, cores e visibilidade de um badge semântico.

    O caractere e o par de cores pertencem à engine: o tema só nomeia semântica
    e variante. Valor vindo de binding que caia fora da allowlist degrada para o
    padrão em vez de chegar cru ao renderizador. Badge sem texto e sem glifo fica
    invisível — pílula vazia é ruído, não informação.
    """
    glyph = values.get("glyph")
    if not isinstance(glyph, str) or glyph not in GLYPHS:
        glyph = "none"
    variant = values.get("variant")
    if not isinstance(variant, str) or variant not in BADGE_VARIANTS:
        variant = "neutral"
    text = values.get("text")
    text = text if isinstance(text, str) else ""
    if len(text) > MAX_BADGE_TEXT:
        text = text[:MAX_BADGE_TEXT] + "…"
    background, foreground = BADGE_VARIANTS[variant]
    values["glyph"] = glyph
    values["glyphChar"] = GLYPHS[glyph]
    values["variant"] = variant
    values["text"] = text
    values["background"] = background
    values["foreground"] = foreground
    values["visible"] = values.get("visible") is not False and bool(text or GLYPHS[glyph])


def _read_path(read_model: Mapping[str, Any], source: str) -> Any:
    current: Any = read_model
    for part in source.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _item_value(item: Mapping[str, Any], binding: str) -> Any:
    matched = _ITEM_BINDING.fullmatch(binding)
    if matched is None:
        return None
    current: Any = item
    for part in matched.group(1).split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current if current is None or isinstance(current, str | int | float | bool) else None


def _node_for(
    template: LayoutTemplate,
    item: Mapping[str, Any],
    entry: ResolvedLayoutEntry | None,
    index: int,
    bounds: LayoutBounds,
    size: LayoutItemSize,
) -> dict[str, Any]:
    del entry
    values = dict(_DEFAULTS_BY_KIND[template.kind])
    role = template.properties.get("role")
    if isinstance(role, str) and role in LABEL_ROLES:
        # O papel semântico entra antes das propriedades explícitas: declarar
        # "meta" e um fontPixelSize próprio mantém o override do tema.
        values.update(LABEL_ROLES[role])
    for name, value in template.properties.items():
        if isinstance(value, Mapping):
            resolved = _item_value(item, str(value["binding"]))
            values[name] = value.get("fallback") if resolved is None or resolved == "" else resolved
        else:
            values[name] = value
    if template.kind == "badge":
        _materialize_badge(values)
    return {
        "kind": template.kind,
        "id": f"{template.id}-{index}",
        "x": bounds.x,
        "y": bounds.y,
        "width": size.width,
        "height": size.height,
        **values,
    }


def resolve_scene_layouts(
    book: LayoutRecipeBook,
    read_model: Mapping[str, Any],
    *,
    bounds: LayoutBounds,
) -> SceneLayoutResolution:
    """Resolve receitas para modelos finais consumíveis por ``SceneRepeater``.

    Fonte ausente ou de tipo incompatível nunca some silenciosamente: a receita
    continua presente, sem entradas, e devolve diagnóstico explícito. O QML
    recebe somente os nós materializados; logo não lê o modelo de dados nem
    interpreta bindings.
    """
    layouts: dict[str, ResolvedLayout] = {}
    diagnostics: list[LayoutDiagnostic] = []
    for layout_id, recipe in book.layouts.items():
        columns = recipe.columns_for(bounds.width) if recipe.kind is LayoutKind.GRID else 1
        source = _read_path(read_model, recipe.source)
        if not isinstance(source, list):
            diagnostics.append(
                LayoutDiagnostic(
                    code=DIAG_LAYOUT_SOURCE,
                    layout=layout_id,
                    reason=f"source '{recipe.source}' ausente ou não é lista",
                )
            )
            layouts[layout_id] = ResolvedLayout(layout_id, recipe.kind, columns)
            continue
        if len(source) > recipe.max_items:
            diagnostics.append(
                LayoutDiagnostic(
                    code=DIAG_LAYOUT_LIMIT,
                    layout=layout_id,
                    reason=f"source '{recipe.source}' truncado em {recipe.max_items} itens",
                )
            )
        accepted: list[tuple[int, Mapping[str, Any]]] = []
        for index, raw_item in enumerate(source[: recipe.max_items]):
            if not isinstance(raw_item, Mapping):
                diagnostics.append(
                    LayoutDiagnostic(
                        code=DIAG_LAYOUT_SOURCE,
                        layout=layout_id,
                        reason=f"item {index} de '{recipe.source}' não é objeto",
                    )
                )
                continue
            accepted.append((index, raw_item))
        tracks = 1
        if recipe.kind is LayoutKind.FLOW:
            tracks, columns, degraded = _flow_tracks(recipe, bounds, len(accepted))
            if degraded:
                diagnostics.append(
                    LayoutDiagnostic(
                        code=DIAG_LAYOUT_LIMIT,
                        layout=layout_id,
                        reason=f"item de '{recipe.source}' não cabe nos bounds do flow",
                        fallback="singleTrack",
                    )
                )
        selected = recipe.selected
        if accepted:
            selected = min(max(selected, 0), len(accepted) - 1)
        if recipe.offset is not None:
            offset = recipe.offset
        elif recipe.kind is LayoutKind.COVER_FLOW:
            offset = LayoutOffset(
                scale_step=0.1,
                opacity_step=0.15,
                min_scale=0.65,
                min_opacity=0.4,
                rotation_step=28.0,
                max_rotation=55.0,
                overlap=0.45,
            )
        else:
            offset = LayoutOffset()
        entries: list[ResolvedLayoutEntry] = []
        for display_index, (index, raw_item) in enumerate(accepted):
            if recipe.kind is LayoutKind.GRID:
                column = display_index % columns
                row = display_index // columns
                x = bounds.x + column * (recipe.item.width + recipe.gap)
                y = bounds.y + row * (recipe.item.height + recipe.gap)
                extras: dict[str, Any] = {}
            elif recipe.kind is LayoutKind.FLOW:
                if recipe.direction is LayoutDirection.HORIZONTAL:
                    column, row = display_index % tracks, display_index // tracks
                else:
                    column, row = display_index // tracks, display_index % tracks
                x = bounds.x + column * (recipe.item.width + recipe.gap)
                y = bounds.y + row * (recipe.item.height + recipe.gap)
                extras = {}
            elif recipe.kind is LayoutKind.STACK:
                distance = display_index - selected
                scale, fade, z_index, _rotation = offset.apply(distance)
                center_x = bounds.x + (bounds.width - recipe.item.width) / 2
                center_y = bounds.y + (bounds.height - recipe.item.height) / 2
                peek = distance * recipe.gap
                if recipe.direction is LayoutDirection.HORIZONTAL:
                    x, y = center_x + peek, center_y
                else:
                    x, y = center_x, center_y + peek
                extras = {"scale": scale, "z": z_index, "distance": distance}
            elif recipe.kind is LayoutKind.CAROUSEL:
                distance = _wrap_distance(display_index, selected, len(accepted))
                scale, fade, z_index, _rotation = offset.apply(distance)
                x, y = _carousel_point(bounds, recipe.item, distance, len(accepted))
                extras = {"scale": scale, "z": z_index, "distance": distance}
            elif recipe.kind in {LayoutKind.WHEEL, LayoutKind.COVER_FLOW}:
                distance = display_index - selected
                scale, fade, z_index, rotation_y = offset.apply(distance)
                if recipe.kind is LayoutKind.WHEEL and recipe.direction is LayoutDirection.VERTICAL:
                    step = recipe.item.height + recipe.gap
                    x = bounds.x + (bounds.width - recipe.item.width) / 2
                    y = bounds.y + (bounds.height - recipe.item.height) / 2 + distance * step
                else:
                    width_step = recipe.item.width * (
                        offset.overlap if recipe.kind is LayoutKind.COVER_FLOW else 1.0
                    )
                    step = width_step + recipe.gap
                    x = bounds.x + (bounds.width - recipe.item.width) / 2 + distance * step
                    y = bounds.y + (bounds.height - recipe.item.height) / 2
                extras = {"scale": scale, "z": z_index, "distance": distance}
                if recipe.kind is LayoutKind.COVER_FLOW:
                    extras["rotationY"] = rotation_y
            elif recipe.direction is LayoutDirection.VERTICAL:
                x = bounds.x
                y = bounds.y + display_index * (recipe.item.height + recipe.gap)
                extras = {}
            else:
                x = bounds.x + display_index * (recipe.item.width + recipe.gap)
                y = bounds.y
                extras = {}
            node = _node_for(
                recipe.template,
                raw_item,
                None,
                index,
                LayoutBounds(x=x, y=y, width=bounds.width, height=bounds.height),
                recipe.item,
            )
            if extras:
                node = dict(node)
                node.update(extras)
                if recipe.kind in _DEPTH_KINDS:
                    base = node.get("opacity", 1.0)
                    if isinstance(base, int | float) and not isinstance(base, bool):
                        node["opacity"] = round(float(base) * fade, 4)
                    _apply_highlight(recipe.highlight, node, distance)
            entries.append(
                ResolvedLayoutEntry(
                    index=index,
                    x=x,
                    y=y,
                    width=recipe.item.width,
                    height=recipe.item.height,
                    node=node,
                )
            )
        layouts[layout_id] = ResolvedLayout(layout_id, recipe.kind, columns, tuple(entries))
    return SceneLayoutResolution(layouts=layouts, diagnostics=tuple(diagnostics))
