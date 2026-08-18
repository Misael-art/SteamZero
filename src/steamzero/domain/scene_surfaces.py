# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Slots semânticos, galeria de saves e OSD por contrato público.

A Theme Engine só consome um read model sanitizado. Não abre o emulador, não
lê path privado e não aceita QML do pacote. Superfície ausente ou save sem
captura degrada com diagnóstico; erro crítico do OSD nunca some.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

DIAG_SURFACE_SOURCE = "THEME-SURFACE-SOURCE-001"
DIAG_SURFACE_THUMBNAIL = "THEME-SURFACE-THUMBNAIL-002"
DIAG_SURFACE_ERROR = "THEME-SURFACE-ERROR-003"
MAX_COMPONENTS = 16
MAX_ITEMS = 32
SEMANTIC_SLOTS = (
    "home",
    "library",
    "gameDetail",
    "search",
    "collections",
    "saveStates",
    "quickMenu",
    "osd",
    "empty",
    "loading",
    "error",
    "offline",
)
COMPONENT_KINDS = frozenset(
    {
        "gameGrid",
        "recentlyPlayed",
        "gameDetail",
        "saveGallery",
        "osd",
        "emptyState",
        "loadingState",
        "errorBanner",
        "offlineState",
        "progressBar",
    }
)
OSD_ITEMS = frozenset(
    {
        "volume",
        "mute",
        "brightness",
        "screenshot",
        "saveState",
        "loadState",
        "fastForward",
        "rewind",
        "pause",
        "control",
        "achievement",
        "network",
    }
)
_IDENTIFIER = re.compile(r"^[a-z][a-zA-Z0-9]{0,63}$")
_SOURCE_PATH = re.compile(r"^[a-z][a-zA-Z0-9]{0,31}(?:\.[a-z][a-zA-Z0-9]{0,31}){1,3}$")
_PROGRESS_BINDING = re.compile(r"^osd\.(volume|brightness)$")
_DEFAULT_KIND = {
    "empty": "emptyState",
    "loading": "loadingState",
    "error": "errorBanner",
    "offline": "offlineState",
    "osd": "osd",
    "saveStates": "saveGallery",
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


@dataclass(frozen=True)
class SurfaceComponent:
    id: str
    kind: str
    source: str | None = None
    max_items: int = 8
    items: tuple[str, ...] = ()
    progress_binding: str | None = None
    progress_fallback: float = 0.0

    def __post_init__(self) -> None:
        _identifier(self.id, name="component.id")
        if self.kind not in COMPONENT_KINDS:
            raise ValueError(f"kind de superfície desconhecido: {self.kind!r}")
        if self.source is not None and (
            not _SOURCE_PATH.fullmatch(self.source) or "__" in self.source
        ):
            raise ValueError("source inválido")
        if isinstance(self.max_items, bool) or not isinstance(self.max_items, int):
            raise ValueError("maxItems exige inteiro")
        if not 1 <= self.max_items <= MAX_ITEMS:
            raise ValueError(f"maxItems fora de 1..{MAX_ITEMS}")
        if self.kind == "osd":
            if not self.items:
                raise ValueError("osd exige items")
            unknown = set(self.items) - OSD_ITEMS
            if unknown:
                raise ValueError(f"item de OSD desconhecido: {sorted(unknown)}")
        if self.progress_binding is not None and not _PROGRESS_BINDING.fullmatch(
            self.progress_binding
        ):
            raise ValueError("binding de progresso inválido")
        _number(self.progress_fallback, name="progress.fallback", low=0, high=1)

    @classmethod
    def from_dict(cls, component_id: str, raw: Mapping[str, Any]) -> SurfaceComponent:
        allowed = {"kind", "source", "maxItems", "items", "progress"}
        unknown = set(raw) - allowed
        if unknown or "kind" not in raw:
            raise ValueError("component inválido")
        items = raw.get("items", [])
        if items and (
            not isinstance(items, list) or not all(isinstance(item, str) for item in items)
        ):
            raise ValueError("items inválidos")
        progress = raw.get("progress")
        binding = None
        fallback = 0.0
        if progress is not None:
            if not isinstance(progress, Mapping) or "binding" not in progress:
                raise ValueError("progress inválido")
            binding = str(progress["binding"])
            fallback = _number(progress.get("fallback", 0), name="progress.fallback", low=0, high=1)
        return cls(
            id=_identifier(component_id, name="component.id"),
            kind=str(raw["kind"]),
            source=str(raw["source"]) if "source" in raw else None,
            max_items=raw.get("maxItems", 8),
            items=tuple(str(item) for item in items),
            progress_binding=binding,
            progress_fallback=fallback,
        )

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"kind": self.kind}
        if self.source is not None:
            value["source"] = self.source
        if self.kind in {"saveGallery", "gameGrid", "recentlyPlayed"}:
            value["maxItems"] = self.max_items
        if self.items:
            value["items"] = list(self.items)
        if self.progress_binding is not None:
            value["progress"] = {
                "binding": self.progress_binding,
                "fallback": self.progress_fallback,
            }
        return value


@dataclass(frozen=True)
class SurfaceSlot:
    slot: str
    component: str

    def __post_init__(self) -> None:
        if self.slot not in SEMANTIC_SLOTS:
            raise ValueError(f"slot semântico desconhecido: {self.slot!r}")
        _identifier(self.component, name="slot.component")

    @classmethod
    def from_dict(cls, slot: str, raw: Mapping[str, Any]) -> SurfaceSlot:
        if set(raw) != {"component"}:
            raise ValueError("slot inválido")
        return cls(slot=slot, component=str(raw["component"]))


@dataclass(frozen=True)
class SurfaceBook:
    slots: Mapping[str, SurfaceSlot]
    components: Mapping[str, SurfaceComponent]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("schemaVersion de sceneSurfaces inválido")
        if not self.slots or not self.components:
            raise ValueError("sceneSurfaces exige slots e components")
        if len(self.components) > MAX_COMPONENTS:
            raise ValueError(f"components excede {MAX_COMPONENTS}")
        for slot in self.slots.values():
            if slot.component not in self.components:
                raise ValueError(f"slot referencia component ausente: {slot.component}")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> SurfaceBook:
        if set(raw) != {"schemaVersion", "slots", "components"}:
            raise ValueError("sceneSurfaces inválido")
        slots = raw["slots"]
        components = raw["components"]
        if not isinstance(slots, Mapping) or not isinstance(components, Mapping):
            raise ValueError("slots e components exigem objeto")
        parsed_components = {}
        for name, recipe in components.items():
            if not isinstance(recipe, Mapping):
                raise ValueError("component exige objeto")
            parsed_components[_identifier(name, name="component.id")] = SurfaceComponent.from_dict(
                str(name), recipe
            )
        parsed_slots = {}
        for name, recipe in slots.items():
            if not isinstance(recipe, Mapping):
                raise ValueError("slot exige objeto")
            parsed_slots[str(name)] = SurfaceSlot.from_dict(str(name), recipe)
        return cls(
            slots=parsed_slots, components=parsed_components, schema_version=raw["schemaVersion"]
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "slots": {name: {"component": slot.component} for name, slot in self.slots.items()},
            "components": {name: item.to_dict() for name, item in self.components.items()},
        }


@dataclass(frozen=True)
class SurfaceDiagnostic:
    code: str
    slot: str
    reason: str
    fallback: str = "safe"

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "slot": self.slot,
            "reason": self.reason,
            "fallback": self.fallback,
        }


@dataclass(frozen=True)
class ResolvedSurface:
    slot: str
    kind: str
    entries: tuple[Mapping[str, Any], ...] = ()
    items: tuple[str, ...] = ()
    progress: float = 0.0
    critical_visible: bool = False
    success: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "kind": self.kind,
            "entries": [dict(entry) for entry in self.entries],
            "items": list(self.items),
            "progress": self.progress,
            "criticalVisible": self.critical_visible,
            "success": self.success,
        }


@dataclass(frozen=True)
class SurfaceResolution:
    slots: Mapping[str, ResolvedSurface]
    diagnostics: tuple[SurfaceDiagnostic, ...] = ()

    def to_qml_object(self) -> dict[str, Any]:
        return {
            "slots": {name: item.to_dict() for name, item in self.slots.items()},
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


def _read_path(read_model: Mapping[str, Any], source: str) -> Any:
    current: Any = read_model
    for part in source.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _osd_section(read_model: Mapping[str, Any]) -> Mapping[str, Any]:
    section = read_model.get("osd")
    return section if isinstance(section, Mapping) else {}


def _critical_error(read_model: Mapping[str, Any]) -> Mapping[str, Any] | None:
    error = _osd_section(read_model).get("criticalError")
    return error if isinstance(error, Mapping) else None


def _progress_for(component: SurfaceComponent, read_model: Mapping[str, Any]) -> float:
    if component.progress_binding is None:
        return component.progress_fallback
    value = _read_path(read_model, component.progress_binding)
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return component.progress_fallback
    return max(0.0, min(1.0, float(value)))


def _gallery_entries(
    component: SurfaceComponent,
    read_model: Mapping[str, Any],
    slot: str,
    diagnostics: list[SurfaceDiagnostic],
) -> tuple[Mapping[str, Any], ...]:
    if component.source is None:
        diagnostics.append(
            SurfaceDiagnostic(
                code=DIAG_SURFACE_SOURCE, slot=slot, reason="saveGallery exige source"
            )
        )
        return ()
    source = _read_path(read_model, component.source)
    if not isinstance(source, list):
        diagnostics.append(
            SurfaceDiagnostic(
                code=DIAG_SURFACE_SOURCE,
                slot=slot,
                reason=f"source '{component.source}' ausente ou não é lista",
            )
        )
        return ()
    entries: list[dict[str, Any]] = []
    for index, raw in enumerate(source[: component.max_items]):
        if not isinstance(raw, Mapping):
            continue
        has_thumb = raw.get("hasThumbnail") is True
        if not has_thumb:
            diagnostics.append(
                SurfaceDiagnostic(
                    code=DIAG_SURFACE_THUMBNAIL,
                    slot=slot,
                    reason=f"item {index} sem captura; placeholder seguro",
                    fallback="placeholder",
                )
            )
        label = raw.get("label")
        entries.append(
            {
                "title": label if isinstance(label, str) and label else "Slot vazio",
                "timestamp": raw.get("timestamp") if isinstance(raw.get("timestamp"), str) else "",
                "playtime": raw.get("playtime") if isinstance(raw.get("playtime"), str) else "",
                "compatible": raw.get("compatible") is True,
                "thumbnailFallback": not has_thumb,
            }
        )
    return tuple(entries)


def _default_component(slot: str) -> SurfaceComponent:
    kind = _DEFAULT_KIND.get(slot, "emptyState")
    items = ("volume", "pause") if kind == "osd" else ()
    return SurfaceComponent(id="fallback" + slot[0].upper() + slot[1:], kind=kind, items=items)


def resolve_scene_surfaces(
    raw_book: Mapping[str, Any] | SurfaceBook,
    read_model: Mapping[str, Any],
) -> SurfaceResolution:
    book = raw_book if isinstance(raw_book, SurfaceBook) else SurfaceBook.from_dict(raw_book)
    diagnostics: list[SurfaceDiagnostic] = []
    critical = _critical_error(read_model)
    slots: dict[str, ResolvedSurface] = {}
    for slot_name in SEMANTIC_SLOTS:
        declared = book.slots.get(slot_name)
        component = (
            book.components[declared.component]
            if declared is not None
            else _default_component(slot_name)
        )
        if slot_name == "error" and critical is not None:
            component = SurfaceComponent(id="forcedError", kind="errorBanner")
        entries: tuple[Mapping[str, Any], ...] = ()
        items: tuple[str, ...] = ()
        progress = 0.0
        critical_visible = False
        success = False
        if component.kind == "saveGallery":
            entries = _gallery_entries(component, read_model, slot_name, diagnostics)
        elif component.kind == "osd":
            items = component.items
            progress = _progress_for(component, read_model)
            critical_visible = critical is not None
            claimed_success = _osd_section(read_model).get("success") is True
            success = claimed_success and not critical_visible
            if critical_visible:
                diagnostics.append(
                    SurfaceDiagnostic(
                        code=DIAG_SURFACE_ERROR,
                        slot=slot_name,
                        reason="erro crítico permanece visível; sucesso não é publicado",
                        fallback="errorBanner",
                    )
                )
        slots[slot_name] = ResolvedSurface(
            slot=slot_name,
            kind=component.kind,
            entries=entries,
            items=items,
            progress=progress,
            critical_visible=critical_visible,
            success=success,
        )
    return SurfaceResolution(slots=slots, diagnostics=tuple(diagnostics))
