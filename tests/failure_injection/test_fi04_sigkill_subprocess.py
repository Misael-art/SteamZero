# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""FI-04 (SIGKILL real): mata o processo de apply de verdade e recupera.

Esta é a variante exigida pelo gate (§13.6): SIGKILL genuíno (sem finally, sem
limpeza), em etapas reais do pipeline, seguido de recovery em processo novo.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from steamzero.core import fs, transaction

PROJECT = Path(__file__).parents[2]
RUNNER = Path(__file__).parent / "crash_runner.py"


def _spawn_apply_crash(
    state: Path, plan_id: str, token: str, crash_at: str
) -> subprocess.CompletedProcess[bytes]:
    env = {
        **os.environ,
        "XDG_STATE_HOME": str(state),
        "STEAMZERO_CRASH_AT": crash_at,
        "SZ_PLAN_ID": plan_id,
        "SZ_TOKEN": token,
        "PYTHONPATH": str(PROJECT / "src"),
    }
    return subprocess.run([sys.executable, str(RUNNER)], env=env, capture_output=True, timeout=60)


@pytest.mark.fi
@pytest.mark.parametrize(
    "crash_at", ["apply.intent", "apply.activate", "apply.done", "apply.commit"]
)
def test_real_sigkill_then_recover(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, crash_at: str
) -> None:
    state = tmp_path / "state"
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    fs.ensure_state_layout()

    target = sandbox / "cfg.ini"
    fs.write_atomic_text(target, "ESTADO-INICIAL")
    initial_hash = fs.hash_file(target)

    plan = transaction.plan_write_files({target: b"NOVO"}, root=sandbox)
    proc = _spawn_apply_crash(state, plan.plan_id, plan.confirm_token, crash_at)

    # o processo filho recebeu SIGKILL de verdade
    assert proc.returncode == -signal.SIGKILL, proc.stderr.decode(errors="replace")

    # recovery em processo novo (o pai) restaura o estado inicial byte-idêntico
    results = transaction.recover_all()
    assert len(results) == 1
    assert results[0].outcome == "rolled-back"
    assert target.read_text() == "ESTADO-INICIAL"
    assert fs.hash_file(target) == initial_hash
    stray = [p for p in sandbox.rglob(".*") if ".tmp." in p.name]
    assert stray == []
