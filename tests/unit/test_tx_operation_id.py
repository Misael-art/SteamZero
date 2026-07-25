# SPDX-License-Identifier: GPL-3.0-or-later
"""operationId em erros transacionais: verifica a propagação no pipeline apply."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from steamzero.core import errors, transaction


@pytest.fixture
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Estado do SteamZero em tmp_path: planos e journal não vazam para o host."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    return sandbox


def test_apply_precondition_error_has_no_operation_id(isolated_state: Path) -> None:
    """Erro de pré-condição (antes de op_id existir) NÃO carrega operationId."""
    plan = transaction.plan_write_files({isolated_state / "cfg.ini": b"novo"}, root=isolated_state)
    with pytest.raises(errors.SteamZeroError) as exc:
        transaction.apply(plan.plan_id, "token-errado")
    assert exc.value.code == "E-TX-CONFIRM-REQUIRED"
    assert exc.value.operation_id is None


def test_apply_mid_pipeline_error_carries_operation_id(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Erro SteamZeroError DENTRO do pipeline apply (após op_id) carrega operationId."""
    target = isolated_state / "cfg.ini"
    target.write_text("v0")
    plan = transaction.plan_write_files({target: b"v1"}, root=isolated_state)

    injected_detail = "falha simulada mid-apply pós-op_id"

    def _stage_failing(op_id: str, plan: Any, jrnl: Any) -> None:
        raise errors.SteamZeroError("E-TX-STALE-PLAN", detail=injected_detail)

    monkeypatch.setattr(transaction, "_stage", _stage_failing)
    with pytest.raises(errors.SteamZeroError) as exc:
        transaction.apply(plan.plan_id, plan.confirm_token)
    assert exc.value.code == "E-TX-STALE-PLAN"
    assert exc.value.detail == injected_detail
    assert exc.value.operation_id
    # O rollback rodou sob o mesmo op_id: o conteúdo original permanece.
    assert target.read_text() == "v0"
