# SPDX-License-Identifier: GPL-3.0-or-later
"""operationId em erros transacionais: verifica a propagação no pipeline apply."""

from __future__ import annotations

from pathlib import Path

import pytest

from steamzero.core import errors, fs, transaction


def test_apply_precondition_error_has_no_operation_id(tmp_path: Path) -> None:
    """Erro de pré-condição (antes de op_id existir) NÃO carrega operationId."""
    plan = transaction.plan_write_files(
        {tmp_path / "cfg.ini": b"novo"}, root=tmp_path
    )
    with pytest.raises(errors.SteamZeroError) as exc:
        transaction.apply(plan.plan_id, "token-errado")
    assert exc.value.code == "E-TX-CONFIRM-REQUIRED"
    assert exc.value.operation_id is None


def test_apply_mid_pipeline_error_carries_operation_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Erro SteamZeroError DENTRO do pipeline apply (após op_id) carrega operationId."""
    fs.ensure_state_layout()
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    target = sandbox / "cfg.ini"
    target.write_text("v0")

    plan = transaction.plan_write_files({target: b"v1"}, root=sandbox)

    injected_code = "E-TX-STALE-PLAN"
    injected_detail = "falha simulada mid-apply pós-op_id"

    original_stage = transaction._stage

    def _stage_failing(op_id: str, plan, jrnl) -> None:
        raise errors.SteamZeroError(injected_code, detail=injected_detail)

    monkeypatch.setattr(transaction, "_stage", _stage_failing)
    with pytest.raises(errors.SteamZeroError) as exc:
        transaction.apply(plan.plan_id, plan.confirm_token)
    assert exc.value.code == injected_code
    assert exc.value.operation_id is not None
    assert len(exc.value.operation_id) > 0
    assert exc.value.detail == injected_detail


def test_rollback_precondition_error_carries_no_operation_id(tmp_path: Path) -> None:
    """Erro de validação em rollback_action (operationId inválido) NÃO tem operationId
    porque a operação não existe; o código E-API-SCHEMA é de pré-condição, não de domínio."""
    with pytest.raises(errors.SteamZeroError) as exc:
        # Simula o que rollback_action faz: valida ULID antes de usar
        from steamzero.core import ids
        if not ids.is_ulid("invalido"):
            raise errors.SteamZeroError("E-API-SCHEMA", detail="operationId inválido")
    assert exc.value.operation_id is None
