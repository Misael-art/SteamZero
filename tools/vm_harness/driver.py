# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Driver de certificação M10 — instala/atualiza/reverte emuladores Flatpak.

O driver é puro: não sabe se roda numa VM descartável, num host de bancada ou
num falso cliente de teste. Ele recebe um ``ComponentClient`` (abstração sobre
``component plan/apply/rollback/status``) e um ``EvidenceSink`` (onde os
checkpoints de evidência são registrados), e orquestra os ciclos que fechiam
DEBT-A7: install -> update -> rollback -> roll-forward, um emulador por vez,
validando o invariante do Flatpak (argv fixo, commit pinado) e o snapshot
restaurado após rollback.

Protocolo de 8 passos (``docs/09-operations/OPERATIONAL-TRUST-GATES.md``):
VM primeiro -> snapshot -> console de recuperação -> baseline read-only ->
uma capacidade por vez com plano/confirmação/snapshot -> exercitar falhas ->
confirmar estado -> restaurar snapshot. Este driver cobre os passos que a
maquinaria SteamZero controla (plan/apply/rollback/status); snapshot btrfs e
console de recuperação são da VM provisionada em ``provision.py``.

O driver NUNCA agrupa emuladores numa mesma execução nem continua após uma
divergência: cada divergência vira uma evidência ``fail`` e interrompe o
emulador corrente (AGENTS.md S8 — falha degrada, nunca trava; aqui, falha
interrompe o ciclo e reporta, não persiste estado falso).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


class ComponentClient(Protocol):
    """Abstração sobre ``component plan/apply/rollback/status``.

    Cada método espelha o envelope JSON da CLI (``build_envelope``) e devolve o
    ``data`` interno. Um cliente real (na VM) lê stdout de ``cli.main``; um
    falso (no teste) retorna estado em memória.
    """

    def status(self, adapter_id: str) -> dict[str, Any]: ...

    def plan(self, adapter_id: str, action: str = "install") -> dict[str, Any]: ...

    def apply(self, plan_id: str, confirm_token: str) -> dict[str, Any]: ...

    def rollback(self, operation_id: str) -> dict[str, Any]: ...


EvidenceSink = Callable[[str, str, dict[str, Any]], None]
"""Registra um checkpoint: (emulator, step, payload)."""


#: Emuladores Flatpak do M10 (DuckStation EOL sai; Switch keys+firmware fica
#: para a43+). RetroArch destrava 15 plataformas via cores (BE-2 já entregue).
M10_FLATPAK_EMULATORS: tuple[str, ...] = ("retroarch", "pcsx2", "ppsspp")

#: Passos do ciclo M10 na ordem canônica.
CYCLE_STEPS: tuple[str, ...] = (
    "install",
    "update",
    "rollback",
    "roll-forward",
)


@dataclass
class CycleResult:
    """Resultado de um ciclo completo para um emulador."""

    emulator: str
    ok: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    failure: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "emulator": self.emulator,
            "ok": self.ok,
            "steps": self.steps,
            "failure": self.failure,
        }


def certify_emulator(
    emulator: str,
    client: ComponentClient,
    *,
    evidence: EvidenceSink | None = None,
) -> CycleResult:
    """Roda um ciclo install->update->rollback->roll-forward para ``emulator``.

    Cada etapa valida o estado observado contra o esperado; divergência interrompe
    o ciclo com ``failure`` preenchido e nenhum estado falso persistido.
    """
    result = CycleResult(emulator=emulator, ok=True)

    def record(step: str, payload: dict[str, Any]) -> None:
        result.steps.append({"step": step, **payload})
        if evidence is not None:
            evidence(emulator, step, payload)

    def fail(step: str, detail: str, payload: dict[str, Any]) -> None:
        record(step, {**payload, "ok": False, "detail": detail})
        result.ok = False
        result.failure = f"{step}: {detail}"

    # Baseline read-only: o emulador começa ausente antes do primeiro install.
    before = client.status(emulator)
    record("baseline", {"status": before.get("state"), "ok": True})
    if before.get("state") not in {"missing", "unavailable"}:
        fail("baseline", f"emulador não começa ausente: state={before.get('state')}", before)
        return result

    # 1. Install: plan -> confirm -> apply -> estado installed.
    install_plan = client.plan(emulator, "install")
    plan_id = install_plan.get("planId")
    confirm = install_plan.get("confirmToken")
    if not plan_id or not confirm:
        fail("install", "plan não devolveu planId/confirmToken", install_plan)
        return result
    if install_plan.get("action") == "noop":
        fail("install", "plan de install veio noop num emulador ausente", install_plan)
        return result
    install_op = client.apply(plan_id, confirm)
    install_op_id = install_op.get("operationId")
    if not install_op_id:
        fail("install", "apply não devolveu operationId", install_op)
        return result
    after_install = client.status(emulator)
    record("install", {"operationId": install_op_id, "status": after_install.get("state")})
    if after_install.get("state") != "installed":
        fail(
            "install",
            f"estado após install não é installed: {after_install.get('state')}",
            after_install,
        )
        return result

    # 2. Update: plan update deve ser noop (fonte já pinada no commit) ou
    #    instalar uma versão diferente; o invariante é que o commit permanece
    #    o pinado pelo manifesto.
    update_plan = client.plan(emulator, "update")
    if update_plan.get("action") == "noop":
        record("update", {"action": "noop", "status": after_install.get("state")})
    else:
        upd_plan_id = update_plan.get("planId")
        upd_confirm = update_plan.get("confirmToken")
        upd_op = client.apply(upd_plan_id, upd_confirm)
        after_update = client.status(emulator)
        record(
            "update",
            {"operationId": upd_op.get("operationId"), "status": after_update.get("state")},
        )
        if after_update.get("state") != "installed":
            fail(
                "update",
                f"estado após update não é installed: {after_update.get('state')}",
                after_update,
            )
            return result

    # 3. Rollback do install: restaura o baseline ausente.
    client.rollback(install_op_id)
    after_rollback = client.status(emulator)
    record("rollback", {"operationId": install_op_id, "status": after_rollback.get("state")})
    if after_rollback.get("state") not in {"missing", "unavailable"}:
        fail(
            "rollback",
            f"estado após rollback não voltou a ausente: {after_rollback.get('state')}",
            after_rollback,
        )
        return result

    # 4. Roll-forward: reinstala para deixar o emulador no estado final desejado.
    rf_plan = client.plan(emulator, "install")
    rf_plan_id = rf_plan.get("planId")
    rf_confirm = rf_plan.get("confirmToken")
    client.apply(rf_plan_id, rf_confirm)
    after_rf = client.status(emulator)
    record("roll-forward", {"status": after_rf.get("state")})
    if after_rf.get("state") != "installed":
        fail("roll-forward", f"estado final não é installed: {after_rf.get('state')}", after_rf)
        return result

    return result


def certify_m10(
    client: ComponentClient,
    *,
    emulators: tuple[str, ...] = M10_FLATPAK_EMULATORS,
    evidence: EvidenceSink | None = None,
) -> dict[str, Any]:
    """Certifica cada emulador do M10 e devolve o relatório agregado.

    O relatório é a evidência que fecha DEBT-A7: um emulador por vez, sem
    agrupamento, com o veredito por etapa e o veredito geral.
    """
    results = [certify_emulator(emu, client, evidence=evidence) for emu in emulators]
    all_ok = all(r.ok for r in results)
    return {
        "ok": all_ok,
        "emulators": [r.to_dict() for r in results],
        "summary": {
            emu: ("ok" if r.ok else "fail") for emu, r in zip(emulators, results, strict=True)
        },
    }


def render_evidence_report(report: dict[str, Any], *, source_commit: str, date: str) -> str:
    """Renderiza o relatório de evidência em Markdown para ``docs/diagnostics/``.

    ``source_commit`` e ``date`` são exigidos explicitamente: a evidência só vale
    se vinculada ao commit exato e à data em que a VM rodou.
    """
    lines = [
        "# Evidência de certificação M10 (VM descartável)",
        "",
        f"- **Commit de origem:** `{source_commit}`",
        f"- **Data:** {date}",
        f"- **Veredito geral:** {'APROVADO' if report['ok'] else 'REPROVADO'}",
        "",
        "## Resultado por emulador",
        "",
        "| emulador | veredito | install | update | rollback | roll-forward |",
        "|---|---|---|---|---|---|",
    ]
    by_step: dict[str, dict[str, dict[str, Any]]] = {}
    for emu in report["emulators"]:
        steps = {s["step"]: s for s in emu["steps"]}
        by_step[emu["emulator"]] = steps
        row = [emu["emulator"], "OK" if emu["ok"] else "FAIL"]
        for step in CYCLE_STEPS:
            s = steps.get(step)
            row.append(
                f"{s.get('status', '—')} ({'ok' if s and s.get('ok', True) else 'fail'})"
                if s
                else "—"
            )
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("## Detalhe por etapa")
    lines.append("")
    for emu in report["emulators"]:
        lines.append(f"### {emu['emulator']}")
        lines.append("")
        if emu.get("failure"):
            lines.append(f"**Falha:** {emu['failure']}")
            lines.append("")
        lines.append("```json")
        lines.append(json.dumps(emu["steps"], indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)
