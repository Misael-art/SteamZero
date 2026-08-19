# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Panels, cards, modals e drawers semânticos da Theme Engine.

O tema nomeia o papel do contêiner e a âncora; a engine resolve geometria,
scrim e empilhamento. Nada aqui abre janela, captura foco por conta própria ou
recebe QML do pacote. Contêiner que não cabe nos bounds é encolhido com
diagnóstico — nunca desenhado fora da tela.

Regra inegociável: o modal fica abaixo da faixa reservada ao erro crítico. Um
tema não consegue declarar profundidade que esconda uma falha do sistema.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

DIAG_CONTAINER_FIT = "THEME-CONTAINER-FIT-001"
MAX_CONTAINERS = 12
MAX_PADDING = 64.0
MAX_RADIUS = 48.0
MAX_ELEVATION = 4
CRITICAL_ERROR_Z = 90
SCRIM_Z = 40
_IDENTIFIER = re.compile(r"^[a-z][a-zA-Z0-9]{0,63}$")


class ContainerKind(StrEnum):
    PANEL = "panel"
    CARD = "card"
    MODAL = "modal"
    DRAWER = "drawer"


class ContainerAnchor(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"
    CENTER = "center"


_EDGE_ANCHORS = frozenset(
    {
        ContainerAnchor.LEFT,
        ContainerAnchor.RIGHT,
        ContainerAnchor.TOP,
        ContainerAnchor.BOTTOM,
    }
)
_EDGE_KINDS = frozenset({ContainerKind.PANEL, ContainerKind.DRAWER})
_BASE_Z: dict[ContainerKind, int] = {
    ContainerKind.PANEL: 10,
    ContainerKind.CARD: 12,
    ContainerKind.DRAWER: 30,
    ContainerKind.MODAL: 41,
}


def _number(value: Any, *, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"{name} exige número finito")
    number = float(value)
    if not low <= number <= high:
        raise ValueError(f"{name} fora de {low:g}..{high:g}")
    return number


@dataclass(frozen=True)
class ContainerBounds:
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
class ContainerRecipe:
    id: str
    kind: ContainerKind
    anchor: ContainerAnchor
    size: float = 0.35
    width: float | None = None
    height: float | None = None
    padding: float = 0.0
    radius: float = 0.0
    elevation: int = 0
    scrim_opacity: float = 0.0
    dismissible: bool = True

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.id):
            raise ValueError("container.id inválido")
        if self.kind in _EDGE_KINDS and self.anchor not in _EDGE_ANCHORS:
            raise ValueError(f"{self.kind.value} exige anchor de borda")
        if self.kind not in _EDGE_KINDS and self.anchor is not ContainerAnchor.CENTER:
            raise ValueError(f"{self.kind.value} exige anchor center")
        _number(self.size, name="size", low=0.1, high=0.9)
        for name, value in (("width", self.width), ("height", self.height)):
            if value is not None:
                _number(value, name=name, low=16, high=16384)
        if self.anchor is ContainerAnchor.CENTER and (self.width is None or self.height is None):
            raise ValueError("container central exige width e height")
        _number(self.padding, name="padding", low=0, high=MAX_PADDING)
        _number(self.radius, name="radius", low=0, high=MAX_RADIUS)
        if (
            isinstance(self.elevation, bool)
            or not isinstance(self.elevation, int)
            or not 0 <= self.elevation <= MAX_ELEVATION
        ):
            raise ValueError(f"elevation fora de 0..{MAX_ELEVATION}")
        _number(self.scrim_opacity, name="scrimOpacity", low=0, high=0.9)
        if self.scrim_opacity and self.kind is not ContainerKind.MODAL:
            raise ValueError("scrimOpacity só é válido em modal")

    @classmethod
    def from_dict(cls, container_id: str, raw: Mapping[str, Any]) -> ContainerRecipe:
        allowed = {
            "kind",
            "anchor",
            "size",
            "width",
            "height",
            "padding",
            "radius",
            "elevation",
            "scrimOpacity",
            "dismissible",
        }
        unknown = set(raw) - allowed
        if unknown or "kind" not in raw:
            raise ValueError(f"container inválido: {sorted(unknown)}")
        try:
            kind = ContainerKind(str(raw["kind"]))
        except ValueError:
            raise ValueError(f"container.kind desconhecido: {raw['kind']!r}") from None
        default_anchor = "left" if kind in _EDGE_KINDS else "center"
        try:
            anchor = ContainerAnchor(str(raw.get("anchor", default_anchor)))
        except ValueError:
            raise ValueError(f"container.anchor desconhecida: {raw.get('anchor')!r}") from None
        if "size" in raw and ("width" in raw or "height" in raw):
            raise ValueError("size e width/height são mutuamente exclusivos")
        return cls(
            id=container_id,
            kind=kind,
            anchor=anchor,
            size=_number(raw.get("size", 0.35), name="size", low=0.1, high=0.9),
            width=(
                _number(raw["width"], name="width", low=16, high=16384) if "width" in raw else None
            ),
            height=(
                _number(raw["height"], name="height", low=16, high=16384)
                if "height" in raw
                else None
            ),
            padding=_number(raw.get("padding", 0), name="padding", low=0, high=MAX_PADDING),
            radius=_number(raw.get("radius", 0), name="radius", low=0, high=MAX_RADIUS),
            elevation=raw.get("elevation", 0),
            scrim_opacity=_number(raw.get("scrimOpacity", 0), name="scrimOpacity", low=0, high=0.9),
            dismissible=raw.get("dismissible", True) is not False,
        )

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "kind": self.kind.value,
            "anchor": self.anchor.value,
            "padding": self.padding,
            "radius": self.radius,
            "elevation": self.elevation,
        }
        if self.anchor is ContainerAnchor.CENTER:
            value["width"] = self.width
            value["height"] = self.height
        else:
            value["size"] = self.size
        if self.kind is ContainerKind.MODAL:
            value["scrimOpacity"] = self.scrim_opacity
            value["dismissible"] = self.dismissible
        return value


@dataclass(frozen=True)
class ContainerBook:
    containers: Mapping[str, ContainerRecipe]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("schemaVersion de sceneContainers inválido")
        if not self.containers or len(self.containers) > MAX_CONTAINERS:
            raise ValueError(f"containers exige 1..{MAX_CONTAINERS} entradas")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> ContainerBook:
        if set(raw) != {"schemaVersion", "containers"}:
            raise ValueError("sceneContainers inválido")
        declared = raw["containers"]
        if not isinstance(declared, Mapping):
            raise ValueError("containers exige objeto")
        parsed: dict[str, ContainerRecipe] = {}
        for name, recipe in declared.items():
            if not isinstance(recipe, Mapping):
                raise ValueError("container exige objeto")
            if not _IDENTIFIER.fullmatch(str(name)):
                raise ValueError("container.id inválido")
            parsed[str(name)] = ContainerRecipe.from_dict(str(name), recipe)
        return cls(containers=parsed, schema_version=raw["schemaVersion"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "containers": {name: item.to_dict() for name, item in self.containers.items()},
        }


@dataclass(frozen=True)
class ContainerDiagnostic:
    code: str
    container: str
    reason: str
    fallback: str = "clamped"

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "container": self.container,
            "reason": self.reason,
            "fallback": self.fallback,
        }


@dataclass(frozen=True)
class ResolvedContainer:
    id: str
    kind: str
    x: float
    y: float
    width: float
    height: float
    padding: float
    radius: float
    elevation: int
    z: int
    scrim: float = 0.0
    scrim_z: int = 0
    blocks_input: bool = False
    dismissible: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "padding": self.padding,
            "radius": self.radius,
            "elevation": self.elevation,
            "z": self.z,
            "scrim": self.scrim,
            "scrimZ": self.scrim_z,
            "blocksInput": self.blocks_input,
            "dismissible": self.dismissible,
        }


@dataclass(frozen=True)
class ContainerResolution:
    containers: Mapping[str, ResolvedContainer]
    critical_error_z: int = CRITICAL_ERROR_Z
    diagnostics: tuple[ContainerDiagnostic, ...] = ()

    def to_qml_object(self) -> dict[str, Any]:
        return {
            "containers": {name: item.to_dict() for name, item in self.containers.items()},
            "criticalErrorZ": self.critical_error_z,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


def _geometry(
    recipe: ContainerRecipe, bounds: ContainerBounds
) -> tuple[float, float, float, float, bool]:
    """Geometria final em pixels; devolve também se precisou encolher."""
    if recipe.anchor is ContainerAnchor.CENTER:
        width = min(float(recipe.width or 0), bounds.width)
        height = min(float(recipe.height or 0), bounds.height)
        clamped = width < float(recipe.width or 0) or height < float(recipe.height or 0)
        return (
            bounds.x + (bounds.width - width) / 2,
            bounds.y + (bounds.height - height) / 2,
            width,
            height,
            clamped,
        )
    if recipe.anchor in {ContainerAnchor.LEFT, ContainerAnchor.RIGHT}:
        width = bounds.width * recipe.size
        x = bounds.x if recipe.anchor is ContainerAnchor.LEFT else bounds.x + bounds.width - width
        return (x, bounds.y, width, bounds.height, False)
    height = bounds.height * recipe.size
    y = bounds.y if recipe.anchor is ContainerAnchor.TOP else bounds.y + bounds.height - height
    return (bounds.x, y, bounds.width, height, False)


def resolve_scene_containers(
    raw_book: Mapping[str, Any] | ContainerBook,
    *,
    bounds: ContainerBounds,
) -> ContainerResolution:
    """Resolve contêineres semânticos para geometria, scrim e empilhamento finais.

    O QML recebe pixels e z-index prontos: não calcula âncora, não decide o que
    bloqueia entrada e não escolhe onde o erro crítico entra na pilha.
    """
    book = raw_book if isinstance(raw_book, ContainerBook) else ContainerBook.from_dict(raw_book)
    containers: dict[str, ResolvedContainer] = {}
    diagnostics: list[ContainerDiagnostic] = []
    for name, recipe in book.containers.items():
        x, y, width, height, clamped = _geometry(recipe, bounds)
        if clamped:
            diagnostics.append(
                ContainerDiagnostic(
                    code=DIAG_CONTAINER_FIT,
                    container=name,
                    reason="contêiner maior que os bounds; encolhido para caber",
                )
            )
        is_modal = recipe.kind is ContainerKind.MODAL
        containers[name] = ResolvedContainer(
            id=name,
            kind=recipe.kind.value,
            x=round(x, 4),
            y=round(y, 4),
            width=round(width, 4),
            height=round(height, 4),
            padding=min(recipe.padding, min(width, height) / 2),
            radius=recipe.radius,
            elevation=recipe.elevation,
            z=_BASE_Z[recipe.kind],
            scrim=recipe.scrim_opacity if is_modal else 0.0,
            scrim_z=SCRIM_Z if is_modal else 0,
            blocks_input=is_modal,
            dismissible=recipe.dismissible,
        )
    return ContainerResolution(
        containers=containers,
        critical_error_z=CRITICAL_ERROR_Z,
        diagnostics=tuple(diagnostics),
    )
