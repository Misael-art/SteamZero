# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Integração do núcleo transacional: AC-TX-01..04, verify-fail, rollback (RB-3/4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.core import fs, journal, paths, transaction
from steamzero.core.errors import SteamZeroError


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    fs.ensure_state_layout()
    return sandbox, paths.state_home()


def test_happy_path_apply(env: tuple[Path, Path]) -> None:
    sandbox, _ = env
    target = sandbox / "cfg.ini"
    plan = transaction.plan_write_files({target: b"[core]\nx=1\n"}, root=sandbox)
    assert plan.rollback_guarantee == "G-FULL"
    result = transaction.apply(plan.plan_id, plan.confirm_token)
    assert result.status == "ok"
    assert target.read_bytes() == b"[core]\nx=1\n"
    records = journal.read_records(result.operation_id)
    assert journal.has_type(records, journal.COMMIT)
    # staging limpo após commit
    assert not paths.staging_for(result.operation_id).exists()


def test_ac_tx_04_confirm_required(env: tuple[Path, Path]) -> None:
    sandbox, _ = env
    target = sandbox / "c"
    plan = transaction.plan_write_files({target: b"v"}, root=sandbox)
    with pytest.raises(SteamZeroError) as ei:
        transaction.apply(plan.plan_id, "token-errado")
    assert ei.value.code == "E-TX-CONFIRM-REQUIRED"
    assert not target.exists()  # nenhuma mutação


def test_ac_tx_01_stale_plan_no_mutation(env: tuple[Path, Path]) -> None:
    sandbox, _ = env
    target = sandbox / "c"
    fs.write_atomic_text(target, "original")
    plan = transaction.plan_write_files({target: b"novo"}, root=sandbox)
    # alvo muda entre plan e apply -> precondição diverge
    fs.write_atomic_text(target, "mudou-por-fora")
    with pytest.raises(SteamZeroError) as ei:
        transaction.apply(plan.plan_id, plan.confirm_token)
    assert ei.value.code == "E-TX-STALE-PLAN"
    assert target.read_text() == "mudou-por-fora"  # intacto


def test_ac_tx_03_dry_run_no_writes(env: tuple[Path, Path]) -> None:
    sandbox, _ = env
    target = sandbox / "c"
    plan = transaction.plan_write_files({target: b"v"}, root=sandbox)
    result = transaction.apply(plan.plan_id, plan.confirm_token, dry_run=True)
    assert result.status == "dry-run"
    assert not target.exists()  # zero escrita no alvo
    # nenhum journal criado (nada aplicado)
    assert list(paths.journal_dir().glob("*.jsonl")) == []


def test_idempotence_second_apply_rejected(env: tuple[Path, Path]) -> None:
    sandbox, _ = env
    target = sandbox / "c"
    plan = transaction.plan_write_files({target: b"v"}, root=sandbox)
    transaction.apply(plan.plan_id, plan.confirm_token)
    # segundo apply do mesmo plano: já aplicado
    with pytest.raises(SteamZeroError) as ei:
        transaction.apply(plan.plan_id, plan.confirm_token)
    assert ei.value.code == "E-TX-STALE-PLAN"


def test_idempotent_replan_apply_same_state(env: tuple[Path, Path]) -> None:
    # AC-IN-02 no espírito: aplicar até o estado-alvo 2x = mesmo estado final
    sandbox, _ = env
    target = sandbox / "c"
    p1 = transaction.plan_write_files({target: b"final"}, root=sandbox)
    transaction.apply(p1.plan_id, p1.confirm_token)
    h1 = fs.hash_file(target)
    p2 = transaction.plan_write_files({target: b"final"}, root=sandbox)
    transaction.apply(p2.plan_id, p2.confirm_token)
    assert fs.hash_file(target) == h1


def test_verify_failure_triggers_rollback(env: tuple[Path, Path]) -> None:
    sandbox, _ = env
    target = sandbox / "c"
    fs.write_atomic_text(target, "orig")
    plan = transaction.plan_write_files({target: b"novo"}, root=sandbox)
    # smoke test que falha -> rollback automático (E-TX-VERIFY-FAILED)
    with pytest.raises(SteamZeroError) as ei:
        transaction.apply(
            plan.plan_id,
            plan.confirm_token,
            smoke=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )
    assert ei.value.code == "E-TX-VERIFY-FAILED"
    assert target.read_text() == "orig"  # restaurado


def test_explicit_rollback_after_apply(env: tuple[Path, Path]) -> None:
    sandbox, _ = env
    target = sandbox / "c"
    fs.write_atomic_text(target, "orig")
    plan = transaction.plan_write_files({target: b"novo"}, root=sandbox)
    result = transaction.apply(plan.plan_id, plan.confirm_token)
    rb = transaction.rollback(result.operation_id)
    assert rb.status == "rolled-back"
    assert target.read_text() == "orig"


def test_rb3_rollback_idempotent(env: tuple[Path, Path]) -> None:
    sandbox, _ = env
    target = sandbox / "c"
    fs.write_atomic_text(target, "orig")
    plan = transaction.plan_write_files({target: b"novo"}, root=sandbox)
    result = transaction.apply(plan.plan_id, plan.confirm_token)
    transaction.rollback(result.operation_id)
    first = target.read_text()
    transaction.rollback(result.operation_id)  # 2x = mesmo resultado
    assert target.read_text() == first == "orig"


def test_rb4_tampered_backup_fails_rollback(env: tuple[Path, Path]) -> None:
    # T-09 / RB-4: restauração de backup adulterado deve FALHAR (nunca sucesso otimista)
    sandbox, _ = env
    target = sandbox / "c"
    fs.write_atomic_text(target, "orig")
    plan = transaction.plan_write_files({target: b"novo"}, root=sandbox)
    result = transaction.apply(plan.plan_id, plan.confirm_token)
    # adultera o backup
    action_id = plan.actions[0].action_id
    fs.write_atomic_text(paths.backup_for(result.operation_id) / action_id, "ADULTERADO")
    with pytest.raises(SteamZeroError) as ei:
        transaction.rollback(result.operation_id)
    assert ei.value.code == "E-TX-ROLLBACK-FAILED"


def test_new_file_rollback_deletes(env: tuple[Path, Path]) -> None:
    # alvo não existia antes: rollback deve deletar (undo=delete)
    sandbox, _ = env
    target = sandbox / "novo.ini"
    plan = transaction.plan_write_files({target: b"conteudo"}, root=sandbox)
    result = transaction.apply(plan.plan_id, plan.confirm_token)
    assert target.exists()
    transaction.rollback(result.operation_id)
    assert not target.exists()


def test_containment_rejects_target_outside_root(env: tuple[Path, Path]) -> None:
    sandbox, _ = env
    outside = sandbox.parent / "outside.ini"
    with pytest.raises(SteamZeroError) as ei:
        transaction.plan_write_files({outside: b"x"}, root=sandbox)
    assert ei.value.code == "E-CONTENT-UNSAFE-PATH"


def test_space_preflight_blocks(env: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    # FI-06 (preflight): espaço insuficiente detectado antes de mutar
    sandbox, _ = env
    target = sandbox / "c"
    plan = transaction.plan_write_files({target: b"x" * 100}, root=sandbox)
    monkeypatch.setattr(fs, "free_space", lambda _p: 1)
    with pytest.raises(SteamZeroError) as ei:
        transaction.apply(plan.plan_id, plan.confirm_token)
    assert ei.value.code == "E-STORAGE-SPACE"
    assert not target.exists()
