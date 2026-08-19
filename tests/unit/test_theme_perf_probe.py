# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Contrato da sonda de desempenho: agregação honesta, sem número inventado."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_TOOL = Path(__file__).resolve().parents[2] / "tools" / "theme_perf_probe.py"
_SPEC = importlib.util.spec_from_file_location("theme_perf_probe", _TOOL)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - defesa de ambiente
    raise RuntimeError(f"não foi possível carregar {_TOOL}")
probe = importlib.util.module_from_spec(_SPEC)
# Registrar antes de executar: `dataclass` resolve o módulo por
# ``sys.modules[cls.__module__]`` e falharia com o módulo ainda ausente.
sys.modules[_SPEC.name] = probe
_SPEC.loader.exec_module(probe)


def test_summary_reports_percentiles_over_the_real_samples() -> None:
    summary = probe.summarize([10.0, 12.0, 11.0, 40.0, 12.5])
    assert summary.frames == 5
    assert summary.avg_ms == 17.1
    assert summary.p50_ms == 12.0
    assert summary.max_ms == 40.0
    # O pico não pode ser diluído na média: é ele que denuncia engasgo.
    assert summary.p95_ms == 40.0


def test_percentile_never_reads_past_the_end_of_the_sample() -> None:
    summary = probe.summarize([8.0])
    assert summary.frames == 1
    assert summary.p95_ms == 8.0
    assert summary.max_ms == 8.0


def test_empty_measurement_is_refused_instead_of_reported_as_perfect() -> None:
    with pytest.raises(ValueError, match="nenhuma amostra"):
        probe.summarize([])


def test_report_shape_declares_what_was_not_measured() -> None:
    summary = probe.summarize([16.0, 17.0])
    payload = summary.to_dict()
    assert set(payload) == {"frames", "avgFrameTimeMs", "p50Ms", "p95Ms", "maxMs"}
    # VRAM e FPS de tela ficam fora do dicionário de frame time de propósito:
    # a sonda mede o render loop, e o relatório precisa dizer isso.
    assert "fps" not in payload
    assert "vram" not in payload
