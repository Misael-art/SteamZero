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
from datetime import datetime
from typing import Any

DIAG_SURFACE_SOURCE = "THEME-SURFACE-SOURCE-001"
DIAG_SURFACE_THUMBNAIL = "THEME-SURFACE-THUMBNAIL-002"
DIAG_SURFACE_ERROR = "THEME-SURFACE-ERROR-003"
DIAG_SURFACE_PROGRESS = "THEME-SURFACE-PROGRESS-004"
DIAG_SURFACE_WIDGET = "THEME-SURFACE-WIDGET-005"
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
        "clock",
        "statistics",
    }
)
WIDGET_KINDS = frozenset({"clock", "statistics"})
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
_JOBS = "download|install|update|scrape|import"
_PROGRESS_BINDING = re.compile(rf"^(?:osd\.(?:volume|brightness)|progress\.(?:{_JOBS})\.ratio)$")
_COUNTER_BINDING = re.compile(rf"^progress\.(?:{_JOBS})\.(?:current|total)$")
_COUNTER_TOKEN = re.compile(r"\{([a-z]+)\}")
PROGRESS_STYLES = ("linear", "circular", "segmented", "dotted")
SEGMENTED_STYLES = frozenset({"segmented", "dotted"})
MAX_SEGMENTS = 32
MAX_COUNTER_FORMAT = 32
DEFAULT_COUNTER_FORMAT = "{current}/{total}"
_CLOCK_SOURCE = re.compile(r"^clock\.iso$")
_STATISTICS_SOURCE = re.compile(r"^stats\.[a-z][a-zA-Z0-9]{0,31}$")
_CLOCK_FORMAT = re.compile(r"^HH:mm(?::ss)?$")
_STATISTICS_FORMAT = re.compile(r"^[^{}]{0,16}\{value\}[^{}]{0,16}$")
DEFAULT_CLOCK_FORMAT = "HH:mm"
DEFAULT_STATISTICS_FORMAT = "{value}"
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
class SurfaceCounter:
    """Contador ``{current}/{total}`` de um progresso, já filtrado e fechado."""

    current: str
    total: str
    format: str = DEFAULT_COUNTER_FORMAT

    def __post_init__(self) -> None:
        for name, binding in (("current", self.current), ("total", self.total)):
            if not isinstance(binding, str) or not _COUNTER_BINDING.fullmatch(binding):
                raise ValueError(f"counter.{name} fora da allowlist de progresso")
        if not isinstance(self.format, str) or not 1 <= len(self.format) <= MAX_COUNTER_FORMAT:
            raise ValueError("format de counter inválido")
        tokens = _COUNTER_TOKEN.findall(self.format)
        if (
            not tokens
            or set(tokens) - {"current", "total"}
            or self.format.count("{") != len(tokens)
            or self.format.count("}") != len(tokens)
        ):
            raise ValueError("format de counter inválido")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> SurfaceCounter:
        unknown = set(raw) - {"current", "total", "format"}
        if unknown or not {"current", "total"} <= set(raw):
            raise ValueError("counter inválido")
        return cls(
            current=str(raw["current"]),
            total=str(raw["total"]),
            format=str(raw.get("format", DEFAULT_COUNTER_FORMAT)),
        )

    def to_dict(self) -> dict[str, str]:
        return {"current": self.current, "total": self.total, "format": self.format}

    def render(self, current: int, total: int) -> str:
        return self.format.replace("{current}", str(current)).replace("{total}", str(total))


@dataclass(frozen=True)
class SurfaceComponent:
    id: str
    kind: str
    source: str | None = None
    max_items: int = 8
    items: tuple[str, ...] = ()
    progress_binding: str | None = None
    progress_fallback: float = 0.0
    style: str = "linear"
    segments: int = 0
    counter: SurfaceCounter | None = None
    format: str | None = None

    def __post_init__(self) -> None:
        self._validate_progress()
        self._validate_widget()
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

    def _validate_progress(self) -> None:
        if self.style not in PROGRESS_STYLES:
            raise ValueError(f"style de progresso desconhecido: {self.style!r}")
        if self.style != "linear" and self.kind != "progressBar":
            raise ValueError("style de progresso só é válido em progressBar")
        if isinstance(self.segments, bool) or not isinstance(self.segments, int):
            raise ValueError("segments exige inteiro")
        if self.segments and self.style not in SEGMENTED_STYLES:
            raise ValueError("segments exige style segmented ou dotted")
        if self.segments and not 2 <= self.segments <= MAX_SEGMENTS:
            raise ValueError(f"segments fora de 2..{MAX_SEGMENTS}")
        if self.counter is not None and self.kind != "progressBar":
            raise ValueError("counter só é válido em progressBar")

    def _validate_widget(self) -> None:
        """Widget lê um único caminho público e formata com tokens fechados."""
        if self.kind not in WIDGET_KINDS:
            if self.format is not None:
                raise ValueError("format só é válido em clock ou statistics")
            return
        if self.source is None:
            raise ValueError(f"source é obrigatório em {self.kind}")
        pattern = _CLOCK_SOURCE if self.kind == "clock" else _STATISTICS_SOURCE
        if not pattern.fullmatch(self.source):
            raise ValueError(f"source de {self.kind} fora da allowlist")
        shape = _CLOCK_FORMAT if self.kind == "clock" else _STATISTICS_FORMAT
        if not shape.fullmatch(self.resolved_format):
            raise ValueError(f"format de {self.kind} inválido")

    @property
    def resolved_format(self) -> str:
        if self.format is not None:
            return self.format
        return DEFAULT_CLOCK_FORMAT if self.kind == "clock" else DEFAULT_STATISTICS_FORMAT

    @property
    def resolved_segments(self) -> int:
        """Faixas efetivas: estilo segmentado sem declaração cai no padrão fechado."""
        if self.style not in SEGMENTED_STYLES:
            return 0
        return self.segments or 8

    @classmethod
    def from_dict(cls, component_id: str, raw: Mapping[str, Any]) -> SurfaceComponent:
        allowed = {
            "kind",
            "source",
            "maxItems",
            "items",
            "progress",
            "style",
            "segments",
            "counter",
            "format",
        }
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
        counter = raw.get("counter")
        if counter is not None and not isinstance(counter, Mapping):
            raise ValueError("counter inválido")
        return cls(
            id=_identifier(component_id, name="component.id"),
            kind=str(raw["kind"]),
            source=str(raw["source"]) if "source" in raw else None,
            max_items=raw.get("maxItems", 8),
            items=tuple(str(item) for item in items),
            progress_binding=binding,
            progress_fallback=fallback,
            style=str(raw.get("style", "linear")),
            segments=raw.get("segments", 0),
            counter=SurfaceCounter.from_dict(counter) if counter is not None else None,
            format=str(raw["format"]) if "format" in raw else None,
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
        if self.kind in WIDGET_KINDS:
            value["format"] = self.resolved_format
        if self.kind == "progressBar":
            value["style"] = self.style
            if self.segments:
                value["segments"] = self.segments
            if self.counter is not None:
                value["counter"] = self.counter.to_dict()
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
    style: str = "linear"
    segments: int = 0
    filled_segments: int = 0
    sweep: float = 0.0
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "kind": self.kind,
            "entries": [dict(entry) for entry in self.entries],
            "items": list(self.items),
            "progress": self.progress,
            "criticalVisible": self.critical_visible,
            "success": self.success,
            "style": self.style,
            "segments": self.segments,
            "filledSegments": self.filled_segments,
            "sweep": self.sweep,
            "label": self.label,
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


def _counter_label(
    component: SurfaceComponent,
    read_model: Mapping[str, Any],
    slot: str,
    diagnostics: list[SurfaceDiagnostic],
) -> str:
    """Materializa ``{current}/{total}``; sem número real a barra fica sem rótulo.

    O contador nunca inventa valor: fonte ausente, negativa ou não numérica gera
    diagnóstico e devolve rótulo vazio, mantendo a barra e o valor visíveis.
    """
    counter = component.counter
    if counter is None:
        return ""
    resolved: list[int] = []
    for name, binding in (("current", counter.current), ("total", counter.total)):
        value = _read_path(read_model, binding)
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
            or value < 0
        ):
            diagnostics.append(
                SurfaceDiagnostic(
                    code=DIAG_SURFACE_PROGRESS,
                    slot=slot,
                    reason=f"contador '{name}' ausente ou não numérico em '{binding}'",
                    fallback="valueOnly",
                )
            )
            return ""
        resolved.append(int(value))
    return counter.render(resolved[0], resolved[1])


def _widget_label(
    component: SurfaceComponent,
    read_model: Mapping[str, Any],
    slot: str,
    diagnostics: list[SurfaceDiagnostic],
) -> str:
    """Formata clock e statistics no domínio, sem relógio próprio nem I/O.

    A hora vem do shell como ISO já localizado; o widget apenas a formata com
    tokens fechados. Fonte ausente ou fora de formato não vira texto inventado:
    devolve rótulo vazio com diagnóstico.
    """
    source = component.source or ""
    value = _read_path(read_model, source)
    fmt = component.resolved_format
    if component.kind == "clock":
        try:
            moment = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            moment = None
        if moment is None:
            diagnostics.append(
                SurfaceDiagnostic(
                    code=DIAG_SURFACE_WIDGET,
                    slot=slot,
                    reason=f"relógio '{source}' ausente ou fora do formato ISO",
                    fallback="noLabel",
                )
            )
            return ""
        return (
            fmt.replace("HH", f"{moment.hour:02d}")
            .replace("mm", f"{moment.minute:02d}")
            .replace("ss", f"{moment.second:02d}")
        )
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or value < 0
    ):
        diagnostics.append(
            SurfaceDiagnostic(
                code=DIAG_SURFACE_WIDGET,
                slot=slot,
                reason=f"estatística '{source}' ausente ou não numérica",
                fallback="noLabel",
            )
        )
        return ""
    return fmt.replace("{value}", str(int(value)))


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
        segments = 0
        filled_segments = 0
        sweep = 0.0
        label = ""
        if component.kind in WIDGET_KINDS:
            label = _widget_label(component, read_model, slot_name, diagnostics)
        elif component.kind == "progressBar":
            progress = _progress_for(component, read_model)
            segments = component.resolved_segments
            if segments:
                filled_segments = max(0, min(segments, round(progress * segments)))
            if component.style == "circular":
                sweep = round(progress * 360.0, 2)
            label = _counter_label(component, read_model, slot_name, diagnostics)
        elif component.kind == "saveGallery":
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
            style=component.style,
            segments=segments,
            filled_segments=filled_segments,
            sweep=sweep,
            label=label,
        )
    return SurfaceResolution(slots=slots, diagnostics=tuple(diagnostics))
