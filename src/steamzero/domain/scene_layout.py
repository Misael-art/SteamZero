# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Layouts responsivos e repetidores declarativos da Theme Engine.

Esta é a fronteira entre a descrição declarativa do tema e o renderizador. O
tema escolhe somente um vocabulário fechado (grid/list, medidas, breakpoints e
campos ``item.*``); o shell entrega o read model; e o resultado já contém
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
_IDENTIFIER = re.compile(r"^[a-z][a-zA-Z0-9-]{0,63}$")
_SOURCE_PATH = re.compile(r"^[a-z][a-zA-Z0-9]{0,31}(?:\.[a-z][a-zA-Z0-9]{0,31}){1,3}$")
_ITEM_BINDING = re.compile(r"^item\.([a-z][a-zA-Z0-9]{0,31}(?:\.[a-z][a-zA-Z0-9]{0,31})?)$")
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?$")


class LayoutKind(StrEnum):
    GRID = "grid"
    LIST = "list"


class LayoutDirection(StrEnum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


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
        }
    ),
    "image": frozenset({"source", "fillMode", "visible", "opacity"}),
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
}
_IMAGE_DEFAULTS: dict[str, Any] = {
    "source": "",
    "fillMode": "PreserveAspectFit",
    "visible": True,
    "opacity": 1.0,
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
        if self.kind is LayoutKind.LIST and self.breakpoints:
            raise ValueError("list não aceita breakpoints")
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
        try:
            direction = LayoutDirection(str(raw.get("direction", "vertical")))
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
        if self.kind is LayoutKind.LIST:
            value["direction"] = self.direction.value
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
    values = dict(_TEXT_DEFAULTS if template.kind == "text" else _IMAGE_DEFAULTS)
    for name, value in template.properties.items():
        if isinstance(value, Mapping):
            resolved = _item_value(item, str(value["binding"]))
            values[name] = value.get("fallback") if resolved is None or resolved == "" else resolved
        else:
            values[name] = value
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
        entries: list[ResolvedLayoutEntry] = []
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
            if recipe.kind is LayoutKind.GRID:
                column = index % columns
                row = index // columns
                x = bounds.x + column * (recipe.item.width + recipe.gap)
                y = bounds.y + row * (recipe.item.height + recipe.gap)
            elif recipe.direction is LayoutDirection.VERTICAL:
                x = bounds.x
                y = bounds.y + index * (recipe.item.height + recipe.gap)
            else:
                x = bounds.x + index * (recipe.item.width + recipe.gap)
                y = bounds.y
            node = _node_for(
                recipe.template,
                raw_item,
                None,
                index,
                LayoutBounds(x=x, y=y, width=bounds.width, height=bounds.height),
                recipe.item,
            )
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
