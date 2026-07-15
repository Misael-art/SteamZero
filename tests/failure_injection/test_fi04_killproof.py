# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""FI-04 (in-process): kill em CADA etapa do pipeline -> recovery determinístico.

Para cada etapa e para os dois casos (alvo pré-existente / alvo ausente),
abortamos o apply abruptamente (SimulatedKill), então rodamos o recovery e
exigimos (AC-TX-02 + ROLLBACK-TESTS §6):
- estado restaurado byte-idêntico (ou ausente, se não existia);
- zero temporários órfãos;
- journal consistente (registro terminal presente).

A variante SIGKILL real está em test_fi04_sigkill_subprocess.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.core import fs, journal, paths, transaction

# etapas antes do commit -> recovery deve REVERTER
PRE_COMMIT_STAGES = [
    "apply.begin",
    "apply.stage",
    "apply.backup",
    "apply.intent",
    "apply.activate",
    "apply.done",
    "apply.verify",
    "apply.commit",
]


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    fs.ensure_state_layout()
    return sandbox


def _crash_at(stage: str) -> None:
    def hook(s: str) -> None:
        if s == stage:
            raise transaction.SimulatedKill

    transaction.set_crash_hook(hook)


def _assert_clean(sandbox: Path) -> None:
    # zero temporários órfãos em qualquer lugar do sandbox ou do staging
    for base in (sandbox, paths.staging_dir()):
        stray = [p for p in base.rglob(".*") if ".tmp." in p.name]
        assert stray == [], f"tmps órfãos: {stray}"


@pytest.mark.fi
@pytest.mark.parametrize("stage", PRE_COMMIT_STAGES)
def test_kill_each_stage_existing_target_rolls_back(env: Path, stage: str) -> None:
    sandbox = env
    target = sandbox / "cfg.ini"
    fs.write_atomic_text(target, "ESTADO-INICIAL")
    initial_hash = fs.hash_file(target)

    plan = transaction.plan_write_files({target: b"NOVO-CONTEUDO"}, root=sandbox)
    _crash_at(stage)
    try:
        with pytest.raises(transaction.SimulatedKill):
            transaction.apply(plan.plan_id, plan.confirm_token)
    finally:
        transaction.set_crash_hook(None)

    results = transaction.recover_all()
    assert len(results) == 1
    assert results[0].outcome == "rolled-back", f"etapa {stage}: {results[0].outcome}"
    assert target.read_text() == "ESTADO-INICIAL"
    assert fs.hash_file(target) == initial_hash
    assert journal.is_terminal(journal.read_records(results[0].operation_id))
    _assert_clean(sandbox)


@pytest.mark.fi
@pytest.mark.parametrize("stage", PRE_COMMIT_STAGES)
def test_kill_each_stage_absent_target_rolls_back(env: Path, stage: str) -> None:
    sandbox = env
    target = sandbox / "novo.ini"  # não existe antes

    plan = transaction.plan_write_files({target: b"NOVO"}, root=sandbox)
    _crash_at(stage)
    try:
        with pytest.raises(transaction.SimulatedKill):
            transaction.apply(plan.plan_id, plan.confirm_token)
    finally:
        transaction.set_crash_hook(None)

    results = transaction.recover_all()
    assert results[0].outcome == "rolled-back", f"etapa {stage}: {results[0].outcome}"
    assert not target.exists(), f"etapa {stage}: alvo deveria ter sido removido"
    _assert_clean(sandbox)


@pytest.mark.fi
def test_kill_after_commit_keeps(env: Path) -> None:
    # crash após o registro de commit -> recovery MANTÉM (roll-forward)
    sandbox = env
    target = sandbox / "cfg.ini"
    fs.write_atomic_text(target, "v0")
    plan = transaction.plan_write_files({target: b"v1-commitado"}, root=sandbox)
    _crash_at("apply.after-commit")
    try:
        with pytest.raises(transaction.SimulatedKill):
            transaction.apply(plan.plan_id, plan.confirm_token)
    finally:
        transaction.set_crash_hook(None)

    results = transaction.recover_all()
    assert results[0].outcome == "kept"
    assert target.read_bytes() == b"v1-commitado"
    assert not paths.staging_for(results[0].operation_id).exists()
    _assert_clean(sandbox)


@pytest.mark.fi
def test_recovery_is_idempotent(env: Path) -> None:
    sandbox = env
    target = sandbox / "cfg.ini"
    fs.write_atomic_text(target, "v0")
    plan = transaction.plan_write_files({target: b"v1"}, root=sandbox)
    _crash_at("apply.done")
    try:
        with pytest.raises(transaction.SimulatedKill):
            transaction.apply(plan.plan_id, plan.confirm_token)
    finally:
        transaction.set_crash_hook(None)
    r1 = transaction.recover_all()
    assert r1[0].outcome == "rolled-back"
    r2 = transaction.recover_all()  # 2ª vez não muda estado
    assert r2[0].outcome == "already-terminal"
    assert target.read_text() == "v0"
