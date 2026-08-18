# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Estados nativos, transições e timeline declarativos da Theme Engine.

O pacote escolhe somente nomes fechados, durações e easings allowlisted. O
resolver devolve snapshots e um plano de reprodução já materializado; QML não
interpreta curva, não avalia expressão e não recebe código.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

DIAG_MOTION_REDUCED = "THEME-MOTION-REDUCED-001"
DIAG_MOTION_CLIP = "THEME-MOTION-CLIP-002"
MAX_TRANSITIONS = 32
MAX_TIMELINES = 8
MAX_CLIPS = 16
MAX_DURATION = 2000
NATIVE_STATES = (
    "normal",
    "focused",
    "selected",
    "pressed",
    "disabled",
    "loading",
    "missing",
    "error",
    "offline",
    "playing",
    "idle",
    "menuOpen",
)
EASINGS = frozenset(
    {
        "linear",
        "quadIn",
        "quadOut",
        "quadInOut",
        "cubicIn",
        "cubicOut",
        "cubicInOut",
        "quartIn",
        "quartOut",
        "quartInOut",
        "quintIn",
        "quintOut",
        "quintInOut",
        "expoIn",
        "expoOut",
        "expoInOut",
        "circIn",
        "circOut",
        "circInOut",
        "backIn",
        "backOut",
        "backInOut",
        "elasticIn",
        "elasticOut",
        "elasticInOut",
        "bounceIn",
        "bounceOut",
        "bounceInOut",
        "cubicBezier",
    }
)
_IDENTIFIER = re.compile(r"^[a-z][a-zA-Z0-9]{0,63}$")


def _number(value: Any, *, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"{name} exige número finito")
    number = float(value)
    if not low <= number <= high:
        raise ValueError(f"{name} fora de {low:g}..{high:g}")
    return number


def _duration(value: Any, *, name: str = "duration") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_DURATION:
        raise ValueError(f"{name} fora de 0..{MAX_DURATION}")
    return value


def _state_name(value: Any) -> str:
    if value not in NATIVE_STATES:
        raise ValueError(f"estado nativo desconhecido: {value!r}")
    return str(value)


@dataclass(frozen=True)
class MotionSnapshot:
    opacity: float = 1.0
    scale: float = 1.0
    translate_x: float = 0.0
    translate_y: float = 0.0

    def __post_init__(self) -> None:
        _number(self.opacity, name="opacity", low=0, high=1)
        _number(self.scale, name="scale", low=0.5, high=2)
        _number(self.translate_x, name="translateX", low=-256, high=256)
        _number(self.translate_y, name="translateY", low=-256, high=256)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any] | None) -> MotionSnapshot:
        payload = raw or {}
        unknown = set(payload) - {"opacity", "scale", "translateX", "translateY"}
        if unknown:
            raise ValueError(f"snapshot inválido: {sorted(unknown)}")
        return cls(
            opacity=_number(payload.get("opacity", 1), name="opacity", low=0, high=1),
            scale=_number(payload.get("scale", 1), name="scale", low=0.5, high=2),
            translate_x=_number(
                payload.get("translateX", 0), name="translateX", low=-256, high=256
            ),
            translate_y=_number(
                payload.get("translateY", 0), name="translateY", low=-256, high=256
            ),
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "opacity": self.opacity,
            "scale": self.scale,
            "translateX": self.translate_x,
            "translateY": self.translate_y,
        }


@dataclass(frozen=True)
class MotionTransition:
    id: str
    source: str
    target: str
    duration: int
    easing: str
    essential: bool = False
    bezier: tuple[float, float, float, float] | None = None

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.id):
            raise ValueError("transition.id inválido")
        _state_name(self.source)
        _state_name(self.target)
        _duration(self.duration)
        if self.easing not in EASINGS:
            raise ValueError("easing não permitido")
        if self.easing == "cubicBezier" and self.bezier is None:
            raise ValueError("cubicBezier exige x1,y1,x2,y2")
        if self.easing != "cubicBezier" and self.bezier is not None:
            raise ValueError("bezier pertence somente a cubicBezier")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> MotionTransition:
        allowed = {"id", "from", "to", "duration", "easing", "essential", "x1", "y1", "x2", "y2"}
        unknown = set(raw) - allowed
        if unknown or not {"id", "from", "to", "duration", "easing"} <= set(raw):
            raise ValueError("transition inválida")
        bezier = None
        if raw.get("easing") == "cubicBezier":
            bezier = (
                _number(raw.get("x1", 0.42), name="x1", low=0, high=1),
                _number(raw.get("y1", 0), name="y1", low=-2, high=2),
                _number(raw.get("x2", 0.58), name="x2", low=0, high=1),
                _number(raw.get("y2", 1), name="y2", low=-2, high=2),
            )
        elif {"x1", "y1", "x2", "y2"} & set(raw):
            raise ValueError("bezier pertence somente a cubicBezier")
        return cls(
            id=str(raw["id"]),
            source=_state_name(raw["from"]),
            target=_state_name(raw["to"]),
            duration=_duration(raw["duration"]),
            easing=str(raw["easing"]),
            essential=bool(raw.get("essential", False)),
            bezier=bezier,
        )

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "id": self.id,
            "from": self.source,
            "to": self.target,
            "duration": self.duration,
            "easing": self.easing,
            "essential": self.essential,
        }
        if self.bezier is not None:
            value["x1"], value["y1"], value["x2"], value["y2"] = self.bezier
        return value


@dataclass(frozen=True)
class MotionClip:
    state: str | None = None
    duration: int = 0
    transition: str | None = None

    def __post_init__(self) -> None:
        if (self.state is None) == (self.transition is None):
            raise ValueError("clip exige state ou transition")
        if self.state is not None:
            _state_name(self.state)
            _duration(self.duration)
        if self.transition is not None and not _IDENTIFIER.fullmatch(self.transition):
            raise ValueError("clip.transition inválido")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> MotionClip:
        if set(raw) == {"state", "duration"}:
            return cls(state=_state_name(raw["state"]), duration=_duration(raw["duration"]))
        if set(raw) == {"transition"}:
            return cls(transition=str(raw["transition"]))
        raise ValueError("clip inválido")


@dataclass(frozen=True)
class MotionTimeline:
    id: str
    kind: str
    clips: tuple[MotionClip, ...]
    repeat: int = 0

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.id):
            raise ValueError("timeline.id inválido")
        if self.kind not in {"sequence", "parallel"}:
            raise ValueError("timeline.kind inválido")
        if not self.clips or len(self.clips) > MAX_CLIPS:
            raise ValueError(f"clips fora de 1..{MAX_CLIPS}")
        if (
            isinstance(self.repeat, bool)
            or not isinstance(self.repeat, int)
            or not 0 <= self.repeat <= 8
        ):
            raise ValueError("repeat fora de 0..8")

    @classmethod
    def from_dict(cls, timeline_id: str, raw: Mapping[str, Any]) -> MotionTimeline:
        unknown = set(raw) - {"kind", "clips", "repeat"}
        if unknown or "kind" not in raw or "clips" not in raw:
            raise ValueError("timeline inválida")
        clips = raw["clips"]
        if not isinstance(clips, list) or not clips:
            raise ValueError("clips inválidos")
        if not all(isinstance(clip, Mapping) for clip in clips):
            raise ValueError("clips inválidos")
        return cls(
            id=timeline_id,
            kind=str(raw["kind"]),
            clips=tuple(MotionClip.from_dict(clip) for clip in clips),
            repeat=raw.get("repeat", 0),
        )

    def to_dict(self) -> dict[str, Any]:
        clips: list[dict[str, Any]] = []
        for clip in self.clips:
            if clip.transition is not None:
                clips.append({"transition": clip.transition})
            else:
                clips.append({"state": clip.state, "duration": clip.duration})
        return {"kind": self.kind, "repeat": self.repeat, "clips": clips}


@dataclass(frozen=True)
class MotionBook:
    states: Mapping[str, MotionSnapshot]
    transitions: Mapping[str, MotionTransition]
    timelines: Mapping[str, MotionTimeline]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("schemaVersion de sceneMotion inválido")
        if not self.states:
            raise ValueError("states exige ao menos uma entrada")
        unknown = set(self.states) - set(NATIVE_STATES)
        if unknown:
            raise ValueError(f"estado nativo desconhecido: {sorted(unknown)}")
        if len(self.transitions) > MAX_TRANSITIONS:
            raise ValueError(f"transitions excede {MAX_TRANSITIONS}")
        if len(self.timelines) > MAX_TIMELINES:
            raise ValueError(f"timelines excede {MAX_TIMELINES}")
        for timeline in self.timelines.values():
            for clip in timeline.clips:
                if clip.transition is not None and clip.transition not in self.transitions:
                    raise ValueError(f"timeline referencia transition ausente: {clip.transition}")

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> MotionBook:
        allowed = {"schemaVersion", "states", "transitions", "timelines"}
        unknown = set(raw) - allowed
        if unknown or "states" not in raw:
            raise ValueError("sceneMotion inválido")
        states = raw["states"]
        transitions = raw.get("transitions", [])
        timelines = raw.get("timelines", {})
        if not isinstance(states, Mapping) or not states:
            raise ValueError("states exige objeto")
        if not isinstance(transitions, list) or len(transitions) > MAX_TRANSITIONS:
            raise ValueError("transitions inválidas")
        if not isinstance(timelines, Mapping) or len(timelines) > MAX_TIMELINES:
            raise ValueError("timelines inválidas")
        parsed_states = {
            _state_name(name): MotionSnapshot.from_dict(
                snapshot if isinstance(snapshot, Mapping) else None
            )
            for name, snapshot in states.items()
        }
        parsed_transitions: dict[str, MotionTransition] = {}
        for entry in transitions:
            if not isinstance(entry, Mapping):
                raise ValueError("transition exige objeto")
            item = MotionTransition.from_dict(entry)
            parsed_transitions[item.id] = item
        parsed_timelines = {
            str(name): MotionTimeline.from_dict(str(name), recipe)
            for name, recipe in timelines.items()
            if isinstance(recipe, Mapping)
        }
        if len(parsed_timelines) != len(timelines):
            raise ValueError("timeline exige objeto")
        return cls(
            states=parsed_states,
            transitions=parsed_transitions,
            timelines=parsed_timelines,
            schema_version=raw.get("schemaVersion", 1),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "states": {name: snapshot.to_dict() for name, snapshot in self.states.items()},
            "transitions": [item.to_dict() for item in self.transitions.values()],
            "timelines": {name: timeline.to_dict() for name, timeline in self.timelines.items()},
        }


@dataclass(frozen=True)
class MotionDiagnostic:
    code: str
    reason: str
    fallback: str = "cut"

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "reason": self.reason, "fallback": self.fallback}


@dataclass(frozen=True)
class ResolvedTransition:
    id: str
    source: str
    target: str
    duration: int
    easing: str
    essential: bool
    bezier: tuple[float, float, float, float] | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "id": self.id,
            "from": self.source,
            "to": self.target,
            "duration": self.duration,
            "easing": self.easing,
            "essential": self.essential,
        }
        if self.bezier is not None:
            value["x1"], value["y1"], value["x2"], value["y2"] = self.bezier
        return value


@dataclass(frozen=True)
class MotionStep:
    state: str
    duration: int
    easing: str = "linear"

    def to_dict(self) -> dict[str, Any]:
        return {"state": self.state, "duration": self.duration, "easing": self.easing}


@dataclass(frozen=True)
class ResolvedTimeline:
    id: str
    kind: str
    steps: tuple[MotionStep, ...]
    total_duration: int
    repeat: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "repeat": self.repeat,
            "totalDuration": self.total_duration,
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass(frozen=True)
class MotionResolution:
    states: Mapping[str, MotionSnapshot]
    transitions: Mapping[str, ResolvedTransition]
    timelines: Mapping[str, ResolvedTimeline]
    diagnostics: tuple[MotionDiagnostic, ...] = ()

    def to_qml_object(self) -> dict[str, Any]:
        return {
            "states": {name: snapshot.to_dict() for name, snapshot in self.states.items()},
            "transitions": {name: item.to_dict() for name, item in self.transitions.items()},
            "timelines": {name: item.to_dict() for name, item in self.timelines.items()},
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


def _default_snapshot(name: str, declared: Mapping[str, MotionSnapshot]) -> MotionSnapshot:
    if name in declared:
        return declared[name]
    if name == "disabled":
        return MotionSnapshot(opacity=0.45)
    if name == "missing":
        return MotionSnapshot(opacity=0.35)
    if name == "offline":
        return MotionSnapshot(opacity=0.6)
    if name == "idle":
        return MotionSnapshot(opacity=0.85)
    if name == "loading":
        return MotionSnapshot(opacity=0.7)
    return MotionSnapshot()


def resolve_scene_motion(
    raw_book: Mapping[str, Any] | MotionBook,
    *,
    reduced_motion: bool = False,
) -> MotionResolution:
    book = raw_book if isinstance(raw_book, MotionBook) else MotionBook.from_dict(raw_book)
    states = {name: _default_snapshot(name, book.states) for name in NATIVE_STATES}
    diagnostics: list[MotionDiagnostic] = []
    transitions: dict[str, ResolvedTransition] = {}
    for transition in book.transitions.values():
        duration = transition.duration
        if reduced_motion and not transition.essential:
            duration = 0
            diagnostics.append(
                MotionDiagnostic(
                    code=DIAG_MOTION_REDUCED,
                    reason=f"transição '{transition.id}' zerada com reduced motion",
                )
            )
        transitions[transition.id] = ResolvedTransition(
            id=transition.id,
            source=transition.source,
            target=transition.target,
            duration=duration,
            easing=transition.easing,
            essential=transition.essential,
            bezier=transition.bezier,
        )
    timelines: dict[str, ResolvedTimeline] = {}
    for timeline in book.timelines.values():
        steps: list[MotionStep] = []
        durations: list[int] = []
        for clip in timeline.clips:
            if clip.transition is not None:
                item = transitions.get(clip.transition)
                if item is None:
                    diagnostics.append(
                        MotionDiagnostic(
                            code=DIAG_MOTION_CLIP,
                            reason=f"clip referencia transition ausente: {clip.transition}",
                        )
                    )
                    continue
                steps.append(
                    MotionStep(state=item.target, duration=item.duration, easing=item.easing)
                )
                durations.append(item.duration)
            else:
                state = clip.state
                if state is None:
                    continue
                steps.append(MotionStep(state=state, duration=clip.duration))
                durations.append(clip.duration)
        total = max(durations, default=0) if timeline.kind == "parallel" else sum(durations)
        timelines[timeline.id] = ResolvedTimeline(
            id=timeline.id,
            kind=timeline.kind,
            steps=tuple(steps),
            total_duration=total,
            repeat=timeline.repeat,
        )
    return MotionResolution(
        states=states,
        transitions=transitions,
        timelines=timelines,
        diagnostics=tuple(diagnostics),
    )
