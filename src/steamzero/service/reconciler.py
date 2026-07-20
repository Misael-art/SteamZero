# SPDX-License-Identifier: GPL-3.0-or-later
"""Reconciliador read-only do ambiente da sessão Steam."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable
from typing import Any

from steamzero.core import log
from steamzero.core.state import StateStore
from steamzero.runtime import observe_session_environment

Probe = Callable[[], dict[str, Any]]
StoreFactory = Callable[[], StateStore]
Clock = Callable[[], float]


class ResumeGapDetector:
    """Detecta retomada sem privilégios pela diferença BOOTTIME-MONOTONIC.

    ``CLOCK_BOOTTIME`` avança durante o suspend; ``monotonic`` não. A primeira
    amostra apenas estabelece a baseline para que reiniciar o daemon não seja
    confundido com uma retomada do sistema.
    """

    def __init__(
        self,
        *,
        monotonic: Clock = time.monotonic,
        boottime: Clock | None = None,
        threshold: float = 1.5,
    ) -> None:
        self._monotonic = monotonic
        self._boottime = boottime or _boottime
        self._threshold = max(0.5, min(threshold, 60.0))
        self._previous: tuple[float, float] | None = None

    def sample(self) -> float | None:
        current = (self._monotonic(), self._boottime())
        previous = self._previous
        self._previous = current
        if previous is None:
            return None
        awake_delta = max(0.0, current[0] - previous[0])
        boot_delta = max(0.0, current[1] - previous[1])
        suspended = boot_delta - awake_delta
        return round(suspended, 3) if suspended >= self._threshold else None


class SessionEnvironmentReconciler:
    def __init__(
        self,
        *,
        probe: Probe = observe_session_environment,
        store_factory: StoreFactory = StateStore,
        resume_detector: ResumeGapDetector | None = None,
        interval: float = 5.0,
    ) -> None:
        self._probe = probe
        self._store_factory = store_factory
        self._resume_detector = resume_detector or ResumeGapDetector()
        self._interval = max(1.0, min(interval, 300.0))
        self._logger = log.get_logger()

    def sample(self) -> dict[str, Any]:
        snapshot = self._probe()
        suspended_seconds = self._resume_detector.sample()
        material = _material_state(snapshot)
        encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(encoded).hexdigest()
        with self._store_factory() as store:
            store.migrate()
            if suspended_seconds is not None:
                store.record_session_resume(suspended_seconds)
            previous = store.get_session_environment()
            if previous is not None and previous["digest"] == digest:
                return {
                    "status": "noop",
                    "digest": digest,
                    "changes": [],
                    "resumedAfterSeconds": suspended_seconds,
                }
            changes = _changes(previous, material)
            store.save_session_environment(snapshot, digest, changes=changes)
        return {
            "status": "changed",
            "digest": digest,
            "changes": changes,
            "resumedAfterSeconds": suspended_seconds,
        }

    def run(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                result = self.sample()
                if result["status"] == "changed":
                    self._logger.info("session.environment.changed", changes=result["changes"])
                if result["resumedAfterSeconds"] is not None:
                    self._logger.info(
                        "session.resume.observed",
                        suspendedSeconds=result["resumedAfterSeconds"],
                    )
            except Exception as exc:
                self._logger.warning("session.environment.probe-failed", error=type(exc).__name__)
            stop.wait(self._interval)


def _boottime() -> float:
    clock = getattr(time, "CLOCK_BOOTTIME", None)
    if clock is None:
        return time.monotonic()
    return time.clock_gettime(clock)


def _material_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    device = _as_dict(snapshot.get("device"))
    session = _as_dict(snapshot.get("session"))
    power = _as_dict(snapshot.get("power"))
    network = _as_dict(snapshot.get("network"))
    displays = _as_list(snapshot.get("displays"))
    volumes = _as_list(snapshot.get("volumes"))
    return {
        "device": {"kind": device.get("kind"), "signals": device.get("signals", {})},
        "session": {"id": session.get("id"), "type": session.get("type")},
        "power": {"onAC": power.get("onAC")},
        "network": {"online": network.get("online")},
        "displays": sorted(
            (
                {
                    "name": row.get("name"),
                    "connected": row.get("connected"),
                    "enabled": row.get("enabled"),
                    "preferredMode": row.get("preferredMode"),
                    "edidSha256": row.get("edidSha256"),
                }
                for row in displays
                if isinstance(row, dict)
            ),
            key=lambda row: str(row["name"]),
        ),
        "volumes": sorted(
            (
                {
                    "uuid": row.get("uuid"),
                    "role": row.get("role"),
                    "mountpoint": row.get("mountpoint"),
                    "fstype": row.get("fstype"),
                }
                for row in volumes
                if isinstance(row, dict)
            ),
            key=lambda row: str(row["uuid"]),
        ),
    }


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _changes(previous: dict[str, Any] | None, current: dict[str, Any]) -> list[str]:
    if previous is None:
        return ["initial"]
    try:
        old_payload = json.loads(str(previous["payload_json"]))
    except (KeyError, TypeError, json.JSONDecodeError):
        return ["recovered-invalid-snapshot"]
    old = _material_state(old_payload if isinstance(old_payload, dict) else {})
    return [key for key in current if old.get(key) != current.get(key)] or ["digest"]
