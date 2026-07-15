# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Núcleo transacional (TRANSACTION-MODEL, ROLLBACK-GUARANTEES).

Pipeline canônico para toda mutação (aqui: escrita de conjunto de arquivos
geridos — RT-05, base de config writes):

    scan -> plan(confirmToken + precondições) -> preview -> apply
    apply: backup -> stage -> (intent -> activate atômico -> done)* -> verify
           -> test -> commit

Garantias:
- confirmToken single-use com validade; ausência/erro => E-TX-CONFIRM-REQUIRED (AC-TX-04).
- precondições (fingerprints) revalidadas no apply; divergência => E-TX-STALE-PLAN
  sem qualquer mutação (AC-TX-01).
- journal WAL fsync por registro; crash (SIGKILL) em qualquer etapa => recovery
  determinístico restaura o estado inicial byte-idêntico (AC-TX-02).
- dry-run não escreve fora de state/staging (AC-TX-03).
- rollback verificado por hash (RB-4); idempotente (RB-3); manifesto preservado
  em falha parcial (RB-5).

Crash gates (``STEAMZERO_CRASH_AT`` ou ``set_crash_hook``) só existem para teste
de injeção de falha — nunca disparam em produção sem a variável/hook.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import signal
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from steamzero.core import fs, ids, journal, paths
from steamzero.core.errors import SteamZeroError

_SPACE_MARGIN = 8 * 1024 * 1024  # 8 MiB de margem no preflight
_DEFAULT_TTL_S = 3600

# --- crash gates (somente teste) ------------------------------------------
CrashHook = Callable[[str], None]
_crash_hook: CrashHook | None = None


class SimulatedKill(BaseException):
    """Aborto abrupto in-process (simula SIGKILL — não deve ser capturado)."""


def set_crash_hook(hook: CrashHook | None) -> None:
    global _crash_hook
    _crash_hook = hook


def _maybe_crash(stage: str) -> None:
    if _crash_hook is not None:
        _crash_hook(stage)
    at = os.environ.get("STEAMZERO_CRASH_AT")
    if at and at == stage:
        os.kill(os.getpid(), signal.SIGKILL)


def _now() -> datetime:
    return datetime.now(UTC)


# ===========================================================================
# Modelos
# ===========================================================================
@dataclass(frozen=True)
class FileAction:
    action_id: str
    target: str
    new_hash: str
    new_size: int
    new_content_b64: str

    def new_content(self) -> bytes:
        return base64.b64decode(self.new_content_b64)

    def to_dict(self) -> dict[str, Any]:
        return {
            "actionId": self.action_id,
            "target": self.target,
            "newHash": self.new_hash,
            "newSize": self.new_size,
            "newContentB64": self.new_content_b64,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> FileAction:
        return FileAction(
            action_id=d["actionId"],
            target=d["target"],
            new_hash=d["newHash"],
            new_size=d["newSize"],
            new_content_b64=d["newContentB64"],
        )


@dataclass(frozen=True)
class Precondition:
    target: str
    fingerprint: str | None

    def to_dict(self) -> dict[str, Any]:
        return {"target": self.target, "fingerprint": self.fingerprint}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Precondition:
        return Precondition(target=d["target"], fingerprint=d["fingerprint"])


@dataclass
class Plan:
    plan_id: str
    confirm_token: str
    kind: str
    root: str
    created_at: str
    expires_at: str
    status: str  # pending | applied | aborted
    rollback_guarantee: str
    requirements: dict[str, Any]
    actions: list[FileAction]
    preconditions: list[Precondition]
    preview: str
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "planId": self.plan_id,
            "confirmToken": self.confirm_token,
            "kind": self.kind,
            "root": self.root,
            "createdAt": self.created_at,
            "expiresAt": self.expires_at,
            "status": self.status,
            "rollbackGuarantee": self.rollback_guarantee,
            "requirements": self.requirements,
            "actions": [a.to_dict() for a in self.actions],
            "preconditions": [p.to_dict() for p in self.preconditions],
            "preview": self.preview,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Plan:
        return Plan(
            plan_id=d["planId"],
            confirm_token=d["confirmToken"],
            kind=d["kind"],
            root=d["root"],
            created_at=d["createdAt"],
            expires_at=d["expiresAt"],
            status=d["status"],
            rollback_guarantee=d["rollbackGuarantee"],
            requirements=d["requirements"],
            actions=[FileAction.from_dict(a) for a in d["actions"]],
            preconditions=[Precondition.from_dict(p) for p in d["preconditions"]],
            preview=d["preview"],
            schema_version=d.get("schemaVersion", 1),
        )


@dataclass
class ApplyResult:
    operation_id: str
    status: str
    actions: list[str] = field(default_factory=list)


@dataclass
class RollbackResult:
    operation_id: str
    status: str  # rolled-back | rollback-failed
    restored: list[str] = field(default_factory=list)


@dataclass
class RecoveryResult:
    operation_id: str
    outcome: str  # kept | rolled-back | already-terminal | clean | rollback-failed


# ===========================================================================
# scan / plan / preview
# ===========================================================================
def _fingerprint(target: Path) -> str | None:
    return fs.hash_file(target) if target.exists() else None


def _save_plan(plan: Plan) -> None:
    fs.ensure_dir(paths.plans_dir())
    fs.write_atomic_text(
        paths.plan_path(plan.plan_id),
        json.dumps(plan.to_dict(), sort_keys=True, ensure_ascii=False),
    )


def load_plan(plan_id: str) -> Plan:
    path = paths.plan_path(plan_id)
    if not path.exists():
        raise SteamZeroError("E-TX-STALE-PLAN", detail=f"plano {plan_id} não encontrado")
    return Plan.from_dict(json.loads(path.read_text(encoding="utf-8")))


def plan_write_files(
    files: dict[Path, bytes], *, root: Path, kind: str = "config.write", ttl_s: int = _DEFAULT_TTL_S
) -> Plan:
    """Gera (scan+plan) um plano de escrita de arquivos geridos. Não muta alvos.

    Escreve apenas o próprio plano em ``state/plans/`` (permitido: state).
    Containment de cada alvo é validado no momento do plano.
    """
    fs.ensure_state_layout()
    root_r = Path(os.path.realpath(root))
    actions: list[FileAction] = []
    preconditions: list[Precondition] = []
    total_new = 0
    total_existing = 0
    for target, content in sorted(files.items(), key=lambda kv: str(kv[0])):
        resolved = fs.resolve_within(root_r, target)
        actions.append(
            FileAction(
                action_id=ids.new_ulid(),
                target=str(resolved),
                new_hash=fs.hash_bytes(content),
                new_size=len(content),
                new_content_b64=base64.b64encode(content).decode("ascii"),
            )
        )
        preconditions.append(Precondition(target=str(resolved), fingerprint=_fingerprint(resolved)))
        total_new += len(content)
        if resolved.exists():
            total_existing += resolved.stat().st_size
    requirements = {"spaceBytes": 2 * total_new + total_existing + _SPACE_MARGIN}
    now = _now()
    plan = Plan(
        plan_id=ids.new_ulid(),
        confirm_token=secrets.token_urlsafe(24),
        kind=kind,
        root=str(root_r),
        created_at=now.isoformat(),
        expires_at=(now + timedelta(seconds=ttl_s)).isoformat(),
        status="pending",
        rollback_guarantee="G-FULL",
        requirements=requirements,
        actions=actions,
        preconditions=preconditions,
        preview=_render_preview(kind, actions, "G-FULL"),
    )
    _save_plan(plan)
    return plan


def _render_preview(kind: str, actions: list[FileAction], guarantee: str) -> str:
    lines = [f"Operação: {kind}", f"Garantia de rollback: {guarantee}", "Arquivos:"]
    lines.extend(f"  - {a.target} ({a.new_size} bytes)" for a in actions)
    return "\n".join(lines)


def preview(plan: Plan) -> str:
    return plan.preview


# ===========================================================================
# apply
# ===========================================================================
def apply(
    plan_id: str,
    confirm_token: str,
    *,
    smoke: Callable[[], None] | None = None,
    dry_run: bool = False,
) -> ApplyResult:
    """Aplica o plano após validar token e precondições. Ver módulo para garantias."""
    plan = load_plan(plan_id)
    if plan.status != "pending":
        raise SteamZeroError(
            "E-TX-STALE-PLAN", detail=f"plano não está pendente (status={plan.status})"
        )
    if confirm_token != plan.confirm_token:
        raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="confirmToken ausente ou incorreto")
    if _now() > datetime.fromisoformat(plan.expires_at):
        raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="confirmToken expirado")

    _revalidate_preconditions(plan)
    _preflight_space(plan)

    if dry_run:
        return ApplyResult(
            operation_id="", status="dry-run", actions=[a.action_id for a in plan.actions]
        )

    op_id = ids.new_ulid()
    jrnl = journal.Journal(op_id)
    try:
        jrnl.begin(plan_id=plan_id, kind=plan.kind)
        _maybe_crash("apply.begin")

        _stage(op_id, plan, jrnl)
        _maybe_crash("apply.stage")

        undo_map = _backup(op_id, plan, jrnl)
        _maybe_crash("apply.backup")

        _apply_actions(op_id, plan, jrnl, undo_map)

        _verify(op_id, plan, jrnl)
        _smoke(op_id, jrnl, smoke)

        jrnl.stage("commit")
        _maybe_crash("apply.commit")
        jrnl.commit()
        _maybe_crash("apply.after-commit")
    finally:
        jrnl.close()

    _mark_plan(plan, "applied")
    fs.remove_tree(paths.staging_for(op_id))
    return ApplyResult(operation_id=op_id, status="ok", actions=[a.action_id for a in plan.actions])


def _revalidate_preconditions(plan: Plan) -> None:
    for pc in plan.preconditions:
        if _fingerprint(Path(pc.target)) != pc.fingerprint:
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"precondição mudou: {pc.target}")


def _preflight_space(plan: Plan) -> None:
    needed = int(plan.requirements.get("spaceBytes", 0))
    if fs.free_space(Path(plan.root)) < needed:
        raise SteamZeroError(
            "E-STORAGE-SPACE", detail=f"necessários ~{needed} bytes livres em {plan.root}"
        )


def _stage(op_id: str, plan: Plan, jrnl: journal.Journal) -> None:
    jrnl.stage("stage")
    for a in plan.actions:
        fs.stage_bytes(op_id, a.action_id, a.new_content())


def _backup(op_id: str, plan: Plan, jrnl: journal.Journal) -> dict[str, dict[str, Any]]:
    jrnl.stage("backup")
    entries: list[fs.BackupEntry] = []
    undo_map: dict[str, dict[str, Any]] = {}
    for a in plan.actions:
        tgt = Path(a.target)
        if tgt.exists():
            entry = fs.backup_file(op_id, tgt, a.action_id)
            entries.append(entry)
            undo_map[a.action_id] = {
                "op": "restore",
                "target": a.target,
                "backupRel": a.action_id,
                "expectHash": entry.hash,
            }
        else:
            undo_map[a.action_id] = {
                "op": "delete",
                "target": a.target,
                "backupRel": None,
                "expectHash": None,
            }
    _write_backup_manifest(op_id, entries)
    return undo_map


def _write_backup_manifest(op_id: str, entries: list[fs.BackupEntry]) -> None:

    manifest = {
        "schemaVersion": 1,
        "operationId": op_id,
        "createdAt": _now().isoformat(),
        "entries": [{"relpath": e.relpath, "hash": e.hash, "size": e.size} for e in entries],
    }
    fs.ensure_dir(paths.backup_for(op_id))
    fs.write_atomic_text(
        paths.backup_for(op_id) / "manifest.json",
        json.dumps(manifest, sort_keys=True, ensure_ascii=False),
    )


def _apply_actions(
    op_id: str, plan: Plan, jrnl: journal.Journal, undo_map: dict[str, dict[str, Any]]
) -> None:
    jrnl.stage("apply")
    for a in plan.actions:
        jrnl.intent(a.action_id, undo=undo_map[a.action_id])
        _maybe_crash("apply.intent")
        fs.write_atomic(Path(a.target), a.new_content())
        _maybe_crash("apply.activate")
        jrnl.done(a.action_id)
        _maybe_crash("apply.done")


def _verify(op_id: str, plan: Plan, jrnl: journal.Journal) -> None:
    jrnl.stage("verify")
    for a in plan.actions:
        if fs.hash_file(Path(a.target)) != a.new_hash:
            jrnl.close()
            _do_rollback(op_id, reason="verify-failed")
            raise SteamZeroError(
                "E-TX-VERIFY-FAILED",
                operation_id=op_id,
                auto_action="rollback automático executado",
                detail=f"hash divergente em {a.target}",
            )
    _maybe_crash("apply.verify")


def _smoke(op_id: str, jrnl: journal.Journal, smoke: Callable[[], None] | None) -> None:
    jrnl.stage("test")
    if smoke is None:
        return
    try:
        smoke()
    except SimulatedKill:
        raise
    except Exception as exc:  # smoke test de terceiros: qualquer falha => rollback
        jrnl.close()
        _do_rollback(op_id, reason="smoke-failed")
        raise SteamZeroError(
            "E-TX-VERIFY-FAILED",
            operation_id=op_id,
            auto_action="rollback automático executado",
            detail=f"smoke test falhou: {exc}",
        ) from exc


def _mark_plan(plan: Plan, status: str) -> None:
    plan.status = status
    _save_plan(plan)


# ===========================================================================
# rollback / recovery
# ===========================================================================
def rollback(operation_id: str, *, reason: str = "manual") -> RollbackResult:
    """Rollback explícito de uma operação (restaura backup, verificado)."""
    return _do_rollback(operation_id, reason=reason)


def _do_rollback(operation_id: str, *, reason: str) -> RollbackResult:
    records = journal.read_records(operation_id)
    if journal.has_type(records, journal.ROLLBACK):
        return RollbackResult(operation_id, "rolled-back")  # idempotente (RB-3)

    intents = [r for r in records if r.get("type") == "action.intent"]
    restored: list[str] = []
    for rec in reversed(intents):
        undo = rec["undo"]
        target = Path(undo["target"])
        if undo["op"] == "restore":
            _restore_one(operation_id, target, undo)
        else:
            fs.remove_file(target)
        restored.append(str(target))

    # zero temporários órfãos (ROLLBACK-TESTS §6)
    fs.remove_tree(paths.staging_for(operation_id))
    with journal.Journal(operation_id) as jrnl:
        jrnl.rollback(reason=reason)
    return RollbackResult(operation_id, "rolled-back", restored)


def _restore_one(operation_id: str, target: Path, undo: dict[str, Any]) -> None:
    backup_path = paths.backup_for(operation_id) / undo["backupRel"]
    if not backup_path.exists():
        raise SteamZeroError(
            "E-TX-ROLLBACK-FAILED",
            operation_id=operation_id,
            detail=f"backup ausente para {target}",
        )
    data = backup_path.read_bytes()
    fs.write_atomic(target, data)
    if fs.hash_file(target) != undo["expectHash"]:  # RB-4: rollback verificado
        raise SteamZeroError(
            "E-TX-ROLLBACK-FAILED",
            operation_id=operation_id,
            detail=f"hash pós-restauração divergente em {target}",
        )


def recover_operation(operation_id: str) -> RecoveryResult:
    """Recupera uma operação após crash: commit=>mantém; senão=>rollback."""
    records = journal.read_records(operation_id)
    if not records:
        return RecoveryResult(operation_id, "clean")
    if journal.has_type(records, journal.COMMIT):
        fs.remove_tree(paths.staging_for(operation_id))
        return RecoveryResult(operation_id, "kept")
    if journal.has_type(records, journal.ROLLBACK):
        return RecoveryResult(operation_id, "already-terminal")
    try:
        _do_rollback(operation_id, reason="crash-recovery")
        return RecoveryResult(operation_id, "rolled-back")
    except SteamZeroError as exc:
        if exc.code == "E-TX-ROLLBACK-FAILED":
            return RecoveryResult(operation_id, "rollback-failed")
        raise


def recover_all() -> list[RecoveryResult]:
    """Varre o journal dir e recupera toda operação não-terminal (pós-reboot)."""
    jdir = paths.journal_dir()
    if not jdir.is_dir():
        return []
    results: list[RecoveryResult] = []
    for entry in sorted(jdir.glob("*.jsonl")):
        results.append(recover_operation(entry.stem))
    return results
