# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Testes do driver de certificação M10 (DEBT-A7).

O driver é puro: recebe um ``ComponentClient`` injetável. Estes testes usam um
``FakeComponentClient`` em memória que espelha o contrato da CLI
(``component plan/apply/rollback/status``). A VM real (virt-install/cloud-init)
roda fora da suíte, sob autorização do operador.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from vm_harness.driver import (
    CYCLE_STEPS,
    certify_emulator,
    certify_m10,
    render_evidence_report,
)


class FakeComponentClient:
    """Cliente de componente determinístico para o driver.

    Mantém estado em memória (installed/missing) e gera planId/confirmToken/
    operationId opacos como a CLI real. ``plan(action='update')`` devolve noop
    porque a fonte Flatpak já está pinada no commit do manifesto.
    """

    def __init__(self) -> None:
        self._state: dict[str, str] = {}  # adapter_id -> "installed" | "missing"
        self._plans: dict[str, dict[str, Any]] = {}  # planId -> plan envelope
        self._counter = 0

    def status(self, adapter_id: str) -> dict[str, Any]:
        return {"id": adapter_id, "state": self._state.get(adapter_id, "missing")}

    def plan(self, adapter_id: str, action: str = "install") -> dict[str, Any]:
        current = self._state.get(adapter_id, "missing")
        if action == "install" and current == "installed":
            return {"planId": None, "confirmToken": None, "action": "noop"}
        if action == "update":
            # Fonte Flatpak pinada: update é noop (mesmo commit do manifesto).
            return {"planId": None, "confirmToken": None, "action": "noop"}
        self._counter += 1
        plan_id = f"plan-{adapter_id}-{self._counter}"
        confirm = secrets.token_urlsafe(16)
        envelope = {"planId": plan_id, "confirmToken": confirm, "action": action}
        self._plans[plan_id] = envelope
        return envelope

    def apply(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        plan = self._plans[plan_id]
        assert plan["confirmToken"] == confirm_token  # token de confirmação casado
        adapter_id = plan_id.split("-")[1]
        action = plan["action"]
        if action == "install":
            self._state[adapter_id] = "installed"
        elif action == "uninstall":
            self._state[adapter_id] = "missing"
        op_id = f"op-{plan_id}"
        return {"operationId": op_id, "status": "committed"}

    def rollback(self, operation_id: str) -> dict[str, Any]:
        # operation_id = "op-plan-<adapter>-<n>"; adapter é o segundo token.
        adapter_id = operation_id.split("-")[2]
        self._state[adapter_id] = "missing"
        return {"operationId": operation_id, "status": "rolled-back"}


def test_certify_emulator_happy_path() -> None:
    # Ciclo completo install->update(noop)->rollback->roll-forward fica verde.
    client = FakeComponentClient()
    result = certify_emulator("pcsx2", client)
    assert result.ok is True
    assert result.failure is None
    steps = [s["step"] for s in result.steps]
    assert steps[0] == "baseline"
    for expected in CYCLE_STEPS:
        assert expected in steps
    # Estado final: installed (roll-forward).
    assert client.status("pcsx2")["state"] == "installed"


def test_certify_emulator_records_evidence_via_sink() -> None:
    # O EvidenceSink recebe cada checkpoint na ordem, com o emulador certo.
    client = FakeComponentClient()
    seen: list[tuple[str, str]] = []
    certify_emulator(
        "ppsspp", client, evidence=lambda emu, step, _payload: seen.append((emu, step))
    )
    assert seen[0] == ("ppsspp", "baseline")
    assert ("ppsspp", "install") in seen
    assert ("ppsspp", "rollback") in seen
    assert ("ppsspp", "roll-forward") in seen
    assert all(emu == "ppsspp" for emu, _ in seen)


def test_certify_emulator_fails_when_not_absent_at_baseline() -> None:
    # Emulador já installed no baseline: divergência, ciclo interrompe, sem falso.
    client = FakeComponentClient()
    client._state["retroarch"] = "installed"  # simula estado sujo antes do ciclo
    result = certify_emulator("retroarch", client)
    assert result.ok is False
    assert result.failure is not None
    assert "baseline" in result.failure


def test_certify_emulator_fails_when_install_does_not_reach_installed() -> None:
    # Apply que não leva a installed: divergência registrada, ciclo para.
    client = FakeComponentClient()

    def _broken_apply(plan_id: str, confirm_token: str) -> dict[str, Any]:
        return {"operationId": "op-x", "status": "committed"}  # não muda estado

    client.apply = _broken_apply  # type: ignore[method-assign]
    result = certify_emulator("pcsx2", client)
    assert result.ok is False
    assert "install" in (result.failure or "")


def test_certify_emulator_fails_when_rollback_does_not_restore_absent() -> None:
    # Rollback que não restaura o baseline ausente: divergência registrada.
    client = FakeComponentClient()

    original_rollback = client.rollback

    def _noop_rollback(operation_id: str) -> dict[str, Any]:
        return {"operationId": operation_id, "status": "rolled-back"}  # não restaura

    client.rollback = _noop_rollback  # type: ignore[method-assign]
    result = certify_emulator("ppsspp", client)
    assert result.ok is False
    assert "rollback" in (result.failure or "")
    # restore para não vazar estado entre asserções
    client.rollback = original_rollback  # type: ignore[method-assign]


def test_certify_m10_aggregates_all_emulators() -> None:
    # certify_m10 roda cada emulador e agrega o veredito geral.
    client = FakeComponentClient()
    report = certify_m10(client)
    assert report["ok"] is True
    assert set(report["summary"]) == {"retroarch", "pcsx2", "ppsspp"}
    assert all(v == "ok" for v in report["summary"].values())
    assert len(report["emulators"]) == 3


def test_certify_m10_reports_failure_when_one_emulator_breaks() -> None:
    # Um emulador quebrado reprova o geral, mas os outros ainda correm.
    client = FakeComponentClient()
    result = certify_emulator("pcsx2", client)  # pré-instala para sujar baseline
    assert result.ok  # sanity: o ciclo happy-path deixa installed
    # Agora pcsx2 está installed; novo certify deve falhar no baseline.
    report = certify_m10(client)
    assert report["ok"] is False
    assert report["summary"]["retroarch"] == "ok"  # os limpos ainda passam
    assert report["summary"]["pcsx2"] == "fail"


def test_render_evidence_report_includes_commit_and_verdict(tmp_path: Path) -> None:
    # O relatório renderizado vincula commit + data + veredito por etapa.
    client = FakeComponentClient()
    report = certify_m10(client)
    md = render_evidence_report(report, source_commit="abc123def456", date="2026-08-06")
    assert "abc123def456" in md
    assert "2026-08-06" in md
    assert "APROVADO" in md
    for emu in ("retroarch", "pcsx2", "ppsspp"):
        assert emu in md
    # Tabela de resultado por emulador presente.
    assert "| emulador | veredito" in md
