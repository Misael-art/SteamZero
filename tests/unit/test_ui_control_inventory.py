# SPDX-License-Identifier: GPL-3.0-or-later
"""Concurrency must accelerate the live QML matrix without weakening it."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import ui_control_inventory as matrix  # noqa: E402


def test_scenario_probes_are_bounded_and_return_in_input_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paths = [tmp_path / f"scenario-{index}.json" for index in range(8)]
    active = 0
    peak = 0
    lock = threading.Lock()

    def probe(*, scenario: Path | None = None) -> dict:
        nonlocal active, peak
        assert scenario is not None
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            # Later inputs finish first; map must still preserve input order.
            time.sleep(0.01 * (len(paths) - paths.index(scenario)))
            return {"context": {"scenario": scenario.stem}, "controls": []}
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(matrix, "run_probe", probe)

    results = matrix._run_scenarios(paths)

    assert [result["context"]["scenario"] for result in results] == [path.stem for path in paths]
    assert 1 < peak <= matrix.SCENARIO_PROBE_WORKERS


def test_nonzero_qml_return_code_fails_even_if_probe_output_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(matrix, "QML", "/usr/bin/qml6")
    monkeypatch.setattr(
        matrix.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=17,
            stdout="PROBE-CONTEXT {}\nPROBE-CONTROL {}",
            stderr="QML process aborted",
        ),
    )

    with pytest.raises(SystemExit, match="return code 17"):
        matrix.run_probe()


def test_qml_timeout_is_not_converted_into_a_partial_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(matrix, "QML", "/usr/bin/qml6")

    def timeout(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired("qml6", timeout=400)

    monkeypatch.setattr(matrix.subprocess, "run", timeout)

    with pytest.raises(subprocess.TimeoutExpired):
        matrix.run_probe()
