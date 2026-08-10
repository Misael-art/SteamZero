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
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from steamzero.adapters.registry import AdapterRegistry


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

    def verify(self, adapter_id: str) -> dict[str, Any]: ...


EvidenceSink = Callable[[str, str, dict[str, Any]], None]
"""Registra um checkpoint: (emulator, step, payload)."""


#: Emuladores Flatpak do M10 (DuckStation EOL sai; Switch keys+firmware fica
#: para a43+). RetroArch destrava 15 plataformas via cores (BE-2 já entregue).
M10_FLATPAK_EMULATORS: tuple[str, ...] = ("retroarch", "pcsx2", "ppsspp")

#: Esperas entre tentativas de operações que dependem do DNS do guest; a
#: política do harness é repetir somente a indisponibilidade DNS (a resposta
#: do upstream pode levar ~5 s), nunca falhas reais do componente.
FLATHUB_RETRY_DELAYS: tuple[float, ...] = (5.0, 10.0, 20.0, 30.0)

#: Passos do ciclo M10 na ordem canônica.
CYCLE_STEPS: tuple[str, ...] = (
    "install",
    "update",
    "rollback",
    "roll-forward",
)

#: Protocolo de diagnóstico: uma única transação que deve voltar ao baseline.
#: Não inclui update nem roll-forward; serve para isolar rollback sem tocar os
#: demais emuladores do M10.
MINIMAL_CYCLE_STEPS: tuple[str, ...] = ("install", "verify", "rollback")


def m10_pinned_commits(registry: AdapterRegistry | None = None) -> dict[str, str]:
    """Deriva os commits Flatpak do contrato bundled, nunca de uma constante.

    A evidência de VM tem que afirmar o pin que o commit em teste declara. Ler
    os manifestos bundled evita uma segunda tabela que poderia ficar defasada
    quando o lock de um emulador for atualizado.
    """
    bundled = registry or AdapterRegistry.bundled()
    pins: dict[str, str] = {}
    for adapter_id in M10_FLATPAK_EMULATORS:
        source = bundled.get(adapter_id).preferred_source("flatpak", allow_eol=False)
        if source.version is None:
            raise ValueError(f"{adapter_id} não declara commit Flatpak")
        pins[adapter_id] = source.version
    return pins


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


def _install_with_dns_retry(
    client: ComponentClient,
    emulator: str,
    *,
    plan_invalid: str,
) -> dict[str, Any] | None:
    """plan install -> apply repetindo somente indisponibilidade DNS.

    O plano é single-use, então cada tentativa replaneja. Levanta
    ``ValueError(plan_invalid)`` quando o plano é inválido/noop (cabe ao
    chamador registrar a falha). Falhas reais do apply re-lançam: a política
    do harness (mesma de ``_configure_flathub``) é repetir só "could not
    resolve hostname", nunca aceitar erro como sucesso.
    """
    for _attempt, delay in enumerate((*FLATHUB_RETRY_DELAYS, 0.0), start=1):
        plan_response = client.plan(emulator, "install")
        plan_id = plan_response.get("planId")
        confirm = plan_response.get("confirmToken")
        if not plan_id or not confirm or plan_response.get("action") == "noop":
            raise ValueError(f"{plan_invalid}: {plan_response}")
        try:
            op = client.apply(plan_id, confirm)
        except Exception as exc:
            if "could not resolve hostname" not in str(exc).lower() or delay == 0.0:
                raise
            time.sleep(delay)
            continue
        if op.get("operationId"):
            return op
        combined = json.dumps(op, sort_keys=True).lower()
        if "could not resolve hostname" not in combined or delay == 0.0:
            return op
        time.sleep(delay)
    raise AssertionError("loop de retry DNS deveria ter terminado")


def certify_emulator(
    emulator: str,
    client: ComponentClient,
    *,
    expected_commit: str,
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

    def installed(step: str, observed: dict[str, Any], operation_id: str | None = None) -> bool:
        payload: dict[str, Any] = {
            "status": observed.get("state"),
            "commit": observed.get("version"),
            "expectedCommit": expected_commit,
            "ok": True,
        }
        if operation_id is not None:
            payload["operationId"] = operation_id
        record(step, payload)
        if observed.get("state") != "installed":
            fail(step, f"estado não é installed: {observed.get('state')}", observed)
            return False
        if observed.get("version") != expected_commit:
            fail(
                step,
                f"commit Flatpak diverge: {observed.get('version')} != {expected_commit}",
                observed,
            )
            return False
        verified = client.verify(emulator)
        if verified.get("verified") is not True:
            fail(step, "component verify não confirmou o deployment pinado", verified)
            return False
        return True

    # Baseline read-only: o emulador começa ausente antes do primeiro install.
    before = client.status(emulator)
    record("baseline", {"status": before.get("state"), "ok": True})
    if before.get("state") not in {"missing", "unavailable"}:
        fail("baseline", f"emulador não começa ausente: state={before.get('state')}", before)
        return result

    # 1. Install: plan -> confirm -> apply -> estado installed (retry DNS).
    try:
        install_op = _install_with_dns_retry(
            client, emulator, plan_invalid="plan de install veio noop num emulador ausente"
        )
    except ValueError as exc:
        fail("install", str(exc), {})
        return result
    install_op_id = install_op.get("operationId")
    if not install_op_id:
        fail("install", "apply não devolveu operationId", install_op)
        return result
    after_install = client.status(emulator)
    if not installed("install", after_install, str(install_op_id)):
        return result

    # 2. Update: plan update deve ser noop (fonte já pinada no commit) ou
    #    instalar uma versão diferente; o invariante é que o commit permanece
    #    o pinado pelo manifesto.
    update_plan = client.plan(emulator, "update")
    if update_plan.get("action") == "noop":
        if not installed("update", after_install):
            return result
    else:
        upd_plan_id = update_plan.get("planId")
        upd_confirm = update_plan.get("confirmToken")
        if not upd_plan_id or not upd_confirm:
            fail("update", "plan de update não devolveu planId/confirmToken", update_plan)
            return result
        upd_op = client.apply(upd_plan_id, upd_confirm)
        if not upd_op.get("operationId"):
            fail("update", "apply de update não devolveu operationId", upd_op)
            return result
        after_update = client.status(emulator)
        if not installed("update", after_update, str(upd_op["operationId"])):
            return result

    # 3. Rollback do install: restaura o baseline ausente.
    client.rollback(install_op_id)
    after_rollback = client.status(emulator)
    record(
        "rollback",
        {"operationId": install_op_id, "status": after_rollback.get("state"), "ok": True},
    )
    if after_rollback.get("state") not in {"missing", "unavailable"}:
        fail(
            "rollback",
            f"estado após rollback não voltou a ausente: {after_rollback.get('state')}",
            after_rollback,
        )
        return result

    # 4. Roll-forward: reinstala para deixar o emulador no estado final desejado.
    try:
        rf_op = _install_with_dns_retry(
            client, emulator, plan_invalid="plan de roll-forward não é aplicável"
        )
    except ValueError as exc:
        fail("roll-forward", str(exc), {})
        return result
    if not rf_op.get("operationId"):
        fail("roll-forward", "apply não devolveu operationId", rf_op)
        return result
    after_rf = client.status(emulator)
    if not installed("roll-forward", after_rf, str(rf_op["operationId"])):
        return result

    return result


def certify_emulator_minimal(
    emulator: str,
    client: ComponentClient,
    *,
    expected_commit: str,
    evidence: EvidenceSink | None = None,
) -> CycleResult:
    """Roda somente ``install -> verify -> rollback`` para diagnóstico.

    Este protocolo não é certificação M10 completa: ele existe para obter uma
    causa concreta de rollback sem instalar PCSX2/PPSSPP nem deixar um
    roll-forward no guest. O resultado sempre termina no baseline ausente.
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

    before = client.status(emulator)
    record("baseline", {"status": before.get("state"), "ok": True})
    if before.get("state") not in {"missing", "unavailable"}:
        fail("baseline", f"emulador não começa ausente: state={before.get('state')}", before)
        return result

    try:
        install_op = _install_with_dns_retry(
            client,
            emulator,
            plan_invalid="plan de install não é aplicável no baseline ausente",
        )
    except ValueError as exc:
        fail("install", str(exc), {})
        return result
    install_op_id = install_op.get("operationId")
    if not install_op_id:
        fail("install", "apply não devolveu operationId", install_op)
        return result
    after_install = client.status(emulator)
    install_payload = {
        "operationId": install_op_id,
        "status": after_install.get("state"),
        "commit": after_install.get("version"),
        "expectedCommit": expected_commit,
        "ok": True,
    }
    record("install", install_payload)
    if after_install.get("state") != "installed":
        fail("install", f"estado não é installed: {after_install.get('state')}", after_install)
        return result
    if after_install.get("version") != expected_commit:
        fail(
            "install",
            f"commit Flatpak diverge: {after_install.get('version')} != {expected_commit}",
            after_install,
        )
        return result

    verified = client.verify(emulator)
    record("verify", {**verified, "ok": verified.get("verified") is True})
    if verified.get("verified") is not True:
        fail("verify", "component verify não confirmou o deployment pinado", verified)
        return result

    rollback = client.rollback(str(install_op_id))
    after_rollback = client.status(emulator)
    record(
        "rollback",
        {
            "operationId": install_op_id,
            "rollback": rollback,
            "status": after_rollback.get("state"),
            "ok": True,
        },
    )
    if after_rollback.get("state") not in {"missing", "unavailable"}:
        fail(
            "rollback",
            f"estado após rollback não voltou a ausente: {after_rollback.get('state')}",
            after_rollback,
        )
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
    pins = m10_pinned_commits()
    missing_pins = set(emulators).difference(pins)
    if missing_pins:
        raise ValueError(f"emulador M10 sem pin Flatpak: {sorted(missing_pins)}")
    results = [
        certify_emulator(emu, client, expected_commit=pins[emu], evidence=evidence)
        for emu in emulators
    ]
    all_ok = all(r.ok for r in results)
    return {
        "ok": all_ok,
        "pins": pins,
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
    display_steps = MINIMAL_CYCLE_STEPS if report.get("protocol") == "minimal" else CYCLE_STEPS
    lines = [
        "# Evidência de certificação M10 (VM descartável)",
        "",
        f"- **Commit de origem:** `{source_commit}`",
        f"- **Data:** {date}",
        f"- **Veredito geral:** {'APROVADO' if report['ok'] else 'REPROVADO'}",
        f"- **Protocolo:** {report.get('protocol', 'full')}",
        "",
        "## Resultado por emulador",
        "",
        "| emulador | veredito | " + " | ".join(display_steps) + " |",
        "|---|---|" + "---|" * len(display_steps),
    ]
    by_step: dict[str, dict[str, dict[str, Any]]] = {}
    for emu in report["emulators"]:
        steps_by_name = {s["step"]: s for s in emu["steps"]}
        by_step[emu["emulator"]] = steps_by_name
        row = [emu["emulator"], "OK" if emu["ok"] else "FAIL"]
        for step in display_steps:
            s = steps_by_name.get(step)
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
