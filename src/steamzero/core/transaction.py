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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from steamzero.core import fs, ids, journal, paths
from steamzero.core.errors import SteamZeroError

_SPACE_MARGIN = 8 * 1024 * 1024  # 8 MiB de margem no preflight
_DEFAULT_TTL_S = 3600
_REPAIR_ROLLBACK_REASONS = frozenset(
    {"apply-failed", "verify-failed", "smoke-failed", "crash-recovery"}
)

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
    kind: str = "write"  # write | move | copy | symlink | delete
    source: str | None = None

    def new_content(self) -> bytes:
        return base64.b64decode(self.new_content_b64)

    def to_dict(self) -> dict[str, Any]:
        return {
            "actionId": self.action_id,
            "target": self.target,
            "newHash": self.new_hash,
            "newSize": self.new_size,
            "newContentB64": self.new_content_b64,
            "kind": self.kind,
            "source": self.source,
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> FileAction:
        return FileAction(
            action_id=d["actionId"],
            target=d["target"],
            new_hash=d["newHash"],
            new_size=d["newSize"],
            new_content_b64=d["newContentB64"],
            kind=d.get("kind", "write"),
            source=d.get("source"),
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
    if target.is_symlink():
        return f"symlink:{os.readlink(target)}"
    return fs.hash_file(target) if target.exists() else None


def _resolve_target_within(root: Path, candidate: Path) -> Path:
    """Confina um alvo sem seguir o último componente se ele for symlink."""
    absolute = candidate if candidate.is_absolute() else Path.cwd() / candidate
    parent = Path(os.path.realpath(absolute.parent))
    target = parent / absolute.name
    if target != root and root not in target.parents:
        raise SteamZeroError(
            "E-CONTENT-UNSAFE-PATH", detail=f"{candidate!s} escapa da raiz {root!s}"
        )
    return target


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
    files: dict[Path, bytes],
    *,
    root: Path,
    kind: str = "config.write",
    ttl_s: int = _DEFAULT_TTL_S,
    removals: set[Path] | None = None,
    skip_unchanged: bool = False,
    requirements_extra: dict[str, Any] | None = None,
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
        resolved = _resolve_target_within(root_r, target)
        if resolved.is_symlink():
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail=f"escrita recusou destino symlink: {resolved}"
            )
        fingerprint = _fingerprint(resolved)
        if skip_unchanged and fingerprint == fs.hash_bytes(content):
            preconditions.append(Precondition(target=str(resolved), fingerprint=fingerprint))
            continue
        actions.append(
            FileAction(
                action_id=ids.new_ulid(),
                target=str(resolved),
                new_hash=fs.hash_bytes(content),
                new_size=len(content),
                new_content_b64=base64.b64encode(content).decode("ascii"),
            )
        )
        preconditions.append(Precondition(target=str(resolved), fingerprint=fingerprint))
        total_new += len(content)
        if resolved.exists():
            total_existing += resolved.stat().st_size
    written_targets = {Path(action.target) for action in actions}
    for requested in sorted(removals or set(), key=str):
        resolved = _resolve_target_within(root_r, requested)
        if resolved in written_targets:
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"write e delete duplicados: {resolved}")
        if not resolved.is_symlink() and not resolved.is_file():
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"remoção inválida: {resolved}")
        fingerprint = _fingerprint(resolved)
        actions.append(
            FileAction(
                action_id=ids.new_ulid(),
                target=str(resolved),
                new_hash="",
                new_size=0,
                new_content_b64="",
                kind="delete",
            )
        )
        preconditions.append(Precondition(target=str(resolved), fingerprint=fingerprint))
        total_existing += resolved.stat().st_size
    requirements = {"spaceBytes": 2 * total_new + total_existing + _SPACE_MARGIN}
    requirements.update(requirements_extra or {})
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


def plan_move_files(
    moves: dict[Path, Path],
    *,
    root: Path,
    kind: str = "library.organize",
    ttl_s: int = _DEFAULT_TTL_S,
    writes: dict[Path, bytes] | None = None,
) -> Plan:
    """Planeja renomes/movimentos confinados sem embutir conteúdo no plano.

    Cada origem e destino tem fingerprint congelado. Destinos existentes são
    recusados (nunca há overwrite implícito) e cadeias/ciclos de movimento não
    são aceitos; o chamador deve produzir um layout sem colisões.
    """
    fs.ensure_state_layout()
    root_r = Path(os.path.realpath(root))
    resolved_moves: list[tuple[Path, Path]] = []
    for source, target in moves.items():
        src = fs.resolve_within(root_r, source)
        dst = _resolve_target_within(root_r, target)
        if src == dst:
            continue
        if src.is_symlink() or not src.is_file():
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"origem inválida: {src}")
        resolved_moves.append((src, dst))

    sources = {src for src, _ in resolved_moves}
    targets = [dst for _, dst in resolved_moves]
    if len(set(targets)) != len(targets):
        raise SteamZeroError("E-TX-STALE-PLAN", detail="dois movimentos têm o mesmo destino")
    if sources.intersection(targets):
        raise SteamZeroError(
            "E-TX-STALE-PLAN", detail="cadeias/ciclos de movimento não são suportados"
        )

    actions: list[FileAction] = []
    preconditions: list[Precondition] = []
    total_size = 0
    for src, dst in sorted(resolved_moves, key=lambda pair: str(pair[1])):
        if dst.exists() or dst.is_symlink():
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"destino já existe: {dst}")
        digest = fs.hash_file(src)
        size = src.stat().st_size
        actions.append(
            FileAction(
                action_id=ids.new_ulid(),
                target=str(dst),
                new_hash=digest,
                new_size=size,
                new_content_b64="",
                kind="move",
                source=str(src),
            )
        )
        preconditions.extend(
            (
                Precondition(target=str(src), fingerprint=digest),
                Precondition(target=str(dst), fingerprint=None),
            )
        )
        total_size += size

    occupied_targets = set(targets)
    for requested_target, content in sorted((writes or {}).items(), key=lambda item: str(item[0])):
        target = _resolve_target_within(root_r, requested_target)
        if target in occupied_targets:
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"destino duplicado: {target}")
        if target.is_symlink():
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail=f"escrita recusou destino symlink: {target}"
            )
        occupied_targets.add(target)
        actions.append(
            FileAction(
                action_id=ids.new_ulid(),
                target=str(target),
                new_hash=fs.hash_bytes(content),
                new_size=len(content),
                new_content_b64=base64.b64encode(content).decode("ascii"),
            )
        )
        preconditions.append(Precondition(target=str(target), fingerprint=_fingerprint(target)))
        total_size += len(content)

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
        requirements={"spaceBytes": 2 * total_size + _SPACE_MARGIN},
        actions=actions,
        preconditions=preconditions,
        preview=_render_preview(kind, actions, "G-FULL"),
    )
    _save_plan(plan)
    return plan


def plan_copy_files(
    copies: Mapping[Path, Path] | Sequence[tuple[Path, Path]],
    *,
    root: Path,
    kind: str = "content.copy",
    ttl_s: int = _DEFAULT_TTL_S,
    requirements_extra: dict[str, Any] | None = None,
    writes: dict[Path, bytes] | None = None,
    replace_existing: bool = False,
    removals: set[Path] | None = None,
) -> Plan:
    """Planeja cópias verificadas de arquivos regulares para uma raiz confinada.

    O conteúdo não é serializado no JSON do plano. A origem fica congelada por
    hash e é novamente copiada para staging durante ``apply`` antes da ativação.
    """
    fs.ensure_state_layout()
    root_r = Path(os.path.realpath(root))
    actions: list[FileAction] = []
    preconditions: list[Precondition] = []
    targets: set[Path] = set()
    total_size = 0
    copy_items = copies.items() if isinstance(copies, Mapping) else copies
    for requested_source, requested_target in copy_items:
        if requested_source.is_symlink():
            raise SteamZeroError("E-TX-STALE-PLAN", detail="origem de cópia é symlink")
        source = Path(os.path.realpath(requested_source))
        if not source.is_file():
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"origem de cópia inválida: {source}")
        target = _resolve_target_within(root_r, requested_target)
        if target in targets:
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"destino duplicado: {target}")
        if target.is_symlink() or (target.exists() and not replace_existing):
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"destino já existe: {target}")
        if target.exists() and not target.is_file():
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"destino não é arquivo: {target}")
        targets.add(target)
        digest = fs.hash_file(source)
        size = source.stat().st_size
        actions.append(
            FileAction(
                action_id=ids.new_ulid(),
                target=str(target),
                new_hash=digest,
                new_size=size,
                new_content_b64="",
                kind="copy",
                source=str(source),
            )
        )
        preconditions.extend(
            (
                Precondition(target=str(source), fingerprint=digest),
                Precondition(target=str(target), fingerprint=_fingerprint(target)),
            )
        )
        total_size += size

    for requested_target, content in sorted((writes or {}).items(), key=lambda item: str(item[0])):
        target = _resolve_target_within(root_r, requested_target)
        if target in targets:
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"destino duplicado: {target}")
        targets.add(target)
        actions.append(
            FileAction(
                action_id=ids.new_ulid(),
                target=str(target),
                new_hash=fs.hash_bytes(content),
                new_size=len(content),
                new_content_b64=base64.b64encode(content).decode("ascii"),
            )
        )
        preconditions.append(Precondition(target=str(target), fingerprint=_fingerprint(target)))
        total_size += len(content)

    for requested in sorted(removals or set(), key=str):
        target = _resolve_target_within(root_r, requested)
        if target in targets:
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"cópia e remoção duplicadas: {target}")
        if target.is_symlink() or not target.is_file():
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"remoção inválida: {target}")
        targets.add(target)
        actions.append(
            FileAction(
                action_id=ids.new_ulid(),
                target=str(target),
                new_hash="",
                new_size=0,
                new_content_b64="",
                kind="delete",
            )
        )
        preconditions.append(Precondition(target=str(target), fingerprint=_fingerprint(target)))
        total_size += target.stat().st_size

    extra = requirements_extra or {}
    if "spaceBytes" in extra:
        raise SteamZeroError(
            "E-API-SCHEMA", detail="requirements_extra não pode substituir spaceBytes"
        )
    requirements = {**extra, "spaceBytes": 2 * total_size + _SPACE_MARGIN}
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


def plan_symlink_files(
    links: dict[Path, Path],
    *,
    root: Path,
    kind: str = "content.link",
    ttl_s: int = _DEFAULT_TTL_S,
    replace_existing: bool = False,
) -> Plan:
    """Planeja links ``origem -> destino`` sob uma raiz de consumidores.

    A origem pode viver fora de ``root`` (o BIOS store central é o caso
    canônico), mas deve ser arquivo regular verificável. O destino precisa estar
    ausente e confinado à raiz. Um chamador explícito pode substituir apenas
    outro symlink, preservando restauração integral no rollback.
    """
    fs.ensure_state_layout()
    root_r = Path(os.path.realpath(root))
    actions: list[FileAction] = []
    preconditions: list[Precondition] = []
    targets: set[Path] = set()
    for source, requested_target in links.items():
        if source.is_symlink():
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail=f"origem de link não pode ser symlink: {source}"
            )
        src = Path(os.path.realpath(source))
        if not src.is_file():
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"origem de link inválida: {src}")
        target = _resolve_target_within(root_r, requested_target)
        if target.exists() and not target.is_symlink():
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"destino de link já existe: {target}")
        if target.is_symlink() and not replace_existing:
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"destino de link já existe: {target}")
        if target in targets:
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"destino duplicado: {target}")
        targets.add(target)
        digest = fs.hash_file(src)
        size = src.stat().st_size
        actions.append(
            FileAction(
                action_id=ids.new_ulid(),
                target=str(target),
                new_hash=digest,
                new_size=size,
                new_content_b64="",
                kind="symlink",
                source=str(src),
            )
        )
        preconditions.extend(
            (
                Precondition(target=str(src), fingerprint=digest),
                Precondition(target=str(target), fingerprint=_fingerprint(target)),
            )
        )

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
        requirements={"spaceBytes": _SPACE_MARGIN},
        actions=actions,
        preconditions=preconditions,
        preview=_render_preview(kind, actions, "G-FULL"),
    )
    _save_plan(plan)
    return plan


def _render_preview(kind: str, actions: list[FileAction], guarantee: str) -> str:
    total_size = sum(action.new_size for action in actions)
    lines = [
        f"Operação: {kind}",
        f"Garantia de rollback: {guarantee}",
        f"Arquivos afetados: {len(actions)} · {total_size} bytes no total",
        "",
    ]
    for index, action in enumerate(actions, start=1):
        label = {
            "copy": "Copiar",
            "move": "Mover",
            "symlink": "Vincular",
            "delete": "Remover",
        }.get(action.kind, "Gravar")
        lines.append(f"{index}. {label} · {action.new_size} bytes")
        if action.source:
            lines.append(f"   Origem: {action.source}")
        lines.append(f"   Destino: {action.target}")
        lines.append("")
    return "\n".join(lines)


def preview(plan: Plan) -> str:
    return plan.preview


def abort(plan_id: str, confirm_token: str) -> Plan:
    """Aborta plano pendente sem tocar nos alvos; operação idempotente."""
    plan = load_plan(plan_id)
    if confirm_token != plan.confirm_token:
        raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="confirmToken ausente ou incorreto")
    if plan.status == "applied":
        raise SteamZeroError("E-TX-STALE-PLAN", detail="plano já aplicado")
    if plan.status != "aborted":
        _mark_plan(plan, "aborted")
    return plan


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
    """Aplica e encerra a autorização após qualquer tentativa confirmada."""
    plan = load_plan(plan_id)
    if plan.status != "pending":
        raise SteamZeroError(
            "E-TX-STALE-PLAN", detail=f"plano não está pendente (status={plan.status})"
        )
    if confirm_token != plan.confirm_token:
        raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="confirmToken ausente ou incorreto")
    if _now() > datetime.fromisoformat(plan.expires_at):
        _mark_plan(plan, "aborted")
        raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="confirmToken expirado")
    if _operation_ids_for_plan(plan_id):
        raise SteamZeroError(
            "E-TX-STALE-PLAN",
            detail="tentativa interrompida; execute recovery antes de replanejar",
        )
    if dry_run:
        return _apply_unterminalized(
            plan_id,
            confirm_token,
            smoke=smoke,
            dry_run=True,
        )
    try:
        return _apply_unterminalized(plan_id, confirm_token, smoke=smoke)
    except Exception:
        current = load_plan(plan_id)
        if current.status == "pending":
            _mark_plan(current, "aborted")
        raise


def _apply_unterminalized(
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

    _validate_plan_paths(plan)
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
        _record_operation_state(op_id, "applying")
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
        _record_operation_state(op_id, "committed")
        _maybe_crash("apply.after-commit")
    except Exception as exc:
        jrnl.close()
        _do_rollback(op_id, reason="apply-failed")
        if isinstance(exc, SteamZeroError) and exc.operation_id is None:
            exc.operation_id = op_id
        raise
    finally:
        jrnl.close()

    _mark_plan(plan, "applied")
    fs.remove_tree(paths.staging_for(op_id))
    return ApplyResult(operation_id=op_id, status="ok", actions=[a.action_id for a in plan.actions])


def _revalidate_preconditions(plan: Plan) -> None:
    for pc in plan.preconditions:
        if _fingerprint(Path(pc.target)) != pc.fingerprint:
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"precondição mudou: {pc.target}")


def _validate_plan_paths(plan: Plan) -> None:
    root = Path(plan.root)
    targets: set[Path] = set()
    for action in plan.actions:
        if action.kind not in {"write", "move", "copy", "symlink", "delete"}:
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"ação inválida: {action.kind}")
        target = _resolve_target_within(root, Path(action.target))
        if target in targets:
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"destino duplicado: {target}")
        targets.add(target)
        if action.kind in {"move", "copy", "symlink"}:
            if action.source is None:
                raise SteamZeroError("E-TX-STALE-PLAN", detail=f"{action.kind} sem origem")
            if action.kind == "move":
                fs.resolve_within(root, Path(action.source))
            elif Path(action.source).is_symlink() or not Path(action.source).is_file():
                raise SteamZeroError("E-TX-STALE-PLAN", detail=f"origem de {action.kind} inválida")


def _preflight_space(plan: Plan) -> None:
    needed = int(plan.requirements.get("spaceBytes", 0))
    if fs.free_space(Path(plan.root)) < needed:
        raise SteamZeroError(
            "E-STORAGE-SPACE", detail=f"necessários ~{needed} bytes livres em {plan.root}"
        )


def _stage(op_id: str, plan: Plan, jrnl: journal.Journal) -> None:
    jrnl.stage("stage")
    for a in plan.actions:
        if a.kind == "write":
            fs.stage_bytes(op_id, a.action_id, a.new_content())
        elif a.kind == "copy":
            if a.source is None:
                raise SteamZeroError("E-TX-STALE-PLAN", detail="cópia sem origem")
            staged = paths.staging_for(op_id) / a.action_id
            fs.copy_file_atomic(Path(a.source), staged)
            if fs.hash_file(staged) != a.new_hash or _fingerprint(Path(a.source)) != a.new_hash:
                raise SteamZeroError(
                    "E-TX-STALE-PLAN", detail=f"origem mudou durante staging: {a.source}"
                )


def _backup(op_id: str, plan: Plan, jrnl: journal.Journal) -> dict[str, dict[str, Any]]:
    jrnl.stage("backup")
    entries: list[fs.BackupEntry] = []
    undo_map: dict[str, dict[str, Any]] = {}
    for a in plan.actions:
        target = Path(a.target)
        if a.kind == "move":
            if a.source is None:  # defesa em profundidade; validado antes
                raise SteamZeroError("E-TX-STALE-PLAN", detail="movimento sem origem")
            source = Path(a.source)
            entry = fs.backup_file(op_id, source, a.action_id)
            entries.append(entry)
            undo_map[a.action_id] = {
                "op": "move-restore",
                "source": a.source,
                "target": a.target,
                "backupRel": a.action_id,
                "expectHash": entry.hash,
            }
        elif target.is_symlink():
            source = Path(os.path.realpath(target))
            if not source.is_file():
                raise SteamZeroError(
                    "E-TX-STALE-PLAN", detail=f"symlink de destino está quebrado: {target}"
                )
            undo_map[a.action_id] = {
                "op": "restore-symlink",
                "target": a.target,
                "source": str(source),
                "backupRel": None,
                "expectHash": _fingerprint(target),
                "appliedFingerprint": (f"symlink:{a.source}" if a.kind == "symlink" else None),
            }
        elif target.exists():
            entry = fs.backup_file(op_id, target, a.action_id)
            entries.append(entry)
            undo_map[a.action_id] = {
                "op": "restore",
                "target": a.target,
                "backupRel": a.action_id,
                "expectHash": entry.hash,
                # O que ESTE plano deixaria no alvo. Sem isso, o restore
                # sobrescreve o que estiver lá — inclusive um arquivo alheio que
                # tenha aparecido depois do backup.
                "appliedHash": a.new_hash if a.kind in {"copy", "write"} else None,
            }
        else:
            undo_map[a.action_id] = {
                "op": "delete",
                "target": a.target,
                "backupRel": None,
                # `write` ficava de fora e o `expectHash` saía None, o que
                # PULAVA o guard do rollback: um arquivo estrangeiro que
                # aparecesse depois do backup era removido sem conferência.
                # Agora toda criação registra o que ESPERA encontrar, e o
                # rollback só remove o que reconhece como nosso.
                "expectHash": (
                    a.new_hash
                    if a.kind in {"copy", "write"}
                    else f"symlink:{a.source}"
                    if a.kind == "symlink"
                    else None
                ),
                "expectKind": a.kind,
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


_MISSING = object()


def _expected_fingerprints(plan: Plan) -> dict[str, str | None]:
    """Fingerprint que o PLANO registrou para cada alvo, por caminho."""
    return {p.target: p.fingerprint for p in plan.preconditions}


# ===========================================================================
# Custódia durável (FI-06)
#
# As primitivas abaixo embrulham a custódia com registros de journal e pontos
# de crash determinísticos. A sequência é sempre:
#
#     custody.intent  (fsync) -> tomar a entrada (rename atômico)
#     custody.taken   (fsync) -> verificar -> publicar/remover/restaurar
#     custody.released(fsync) -> liberar a entrada sob custódia
#
# Um crash entre quaisquer dois passos deixa registros pendentes que o
# recovery resolve (reconcile) ANTES de qualquer decisão — inclusive antes de
# declarar kept para uma operação commitada.
# ===========================================================================


def _custody_dest(holding: Path, custody_id: str) -> Path:
    """Caminho da entrada sob custódia da TENTATIVA ``custody_id``.

    O nome carrega o custodyId (único por ciclo): dois ciclos do mesmo
    ``action_id`` (apply e rollback) nunca compartilham caminho, então um
    recovery não esbarra na entrada de uma tentativa anterior nem a libera por
    engano correlacionando só o actionId.
    """
    return holding / f"custody.{custody_id}"


def _next_custody_id(jrnl: journal.Journal, action_id: str) -> str:
    """Identidade de tentativa de custódia: única dentro da operação.

    Deriva da sequência do journal (barata, sem varrer registros) e é gravada
    em ``intent``/``taken``/``released`` — a correlação de ciclos é por
    custodyId, nunca por actionId.
    """
    return f"{action_id}.{jrnl.seq}"


def _custody_identity(custody: Path) -> str:
    """Identidade da entrada sob custódia: hash (regular) ou readlink (symlink)."""
    if custody.is_symlink():
        return f"symlink:{os.readlink(custody)}"
    return fs.hash_file(custody)


def _accepted_identities(undo: dict[str, Any]) -> set[str]:
    """Identidades que o rollback reconhece como legítimas para a ação."""
    aceitos: set[str] = set()
    for key in ("expectHash", "appliedHash", "appliedFingerprint"):
        valor = undo.get(key)
        if valor:
            aceitos.add(str(valor))
    if undo.get("op") == "restore-symlink":
        origem = undo.get("source")
        if origem:
            aceitos.add(f"symlink:{origem}")
    return aceitos


def _reconcile_custody(operation_id: str, records: list[dict[str, Any]]) -> None:
    """Resolve toda custódia pendente da operação; idempotente e não destrutivo.

    A reconciliação PARTE de todo ``custody.intent`` não terminado (sem
    ``custody.released`` correspondente), NÃO só dos ``custody.taken``: um crash
    entre o rename e o registro da tomada deixa a entrada na quarentena com
    apenas o intent — e o recovery precisa saber que o rename aconteceu. A
    correlação é por tentativa (caminho da custódia, que embute o custodyId),
    nunca só por actionId: o mesmo actionId participa de ciclos distintos
    (apply e rollback).

    Cada tentativa não terminada é fechada de uma destas formas:

    - SEM custódia física (``custody`` não existe) e alvo intacto → a tomada
      não aconteceu; fecha o intent como ``absent`` (nada a resolver);
    - custódia existe (o rename aconteceu, mesmo sem ``custody.taken``) e o
      alvo está vago → devolução: a entrada volta ao lugar;
    - custódia existe e o alvo está ocupado: a entrada é a que o undo
      reconhece (hash/readlink) → libera a custódia; senão → falha FECHADA
      preservando AMBOS (alvo ocupado + custódia divergente nunca são
      destruídos) e o rollback falha com o caminho preservado;
    - ciclo terminal → nenhuma custódia pode permanecer: ao fechar, o arquivo
      sob custódia é devolvido ou removido — nunca fica órfão.

    Rodar de novo não muda estado e não destrói o que não reconhece.
    """
    undos = {r["actionId"]: r.get("undo", {}) for r in records if r.get("type") == "action.intent"}
    intents = {r.get("custody") or "": r for r in records if r.get("type") == "custody.intent"}
    released = {r.get("custody") for r in records if r.get("type") == "custody.released"}
    pendentes = [
        r for r in records if r.get("type") == "custody.intent" and r.get("custody") not in released
    ]
    restos = [
        r
        for r in records
        if r.get("type") == "custody.released"
        and not r.get("returned")
        and r.get("custody")
        and (Path(r["custody"]).exists() or Path(r["custody"]).is_symlink())
    ]
    if not pendentes and not restos:
        return

    def falha(detalhe: str) -> None:
        raise SteamZeroError(
            "E-TX-ROLLBACK-FAILED",
            operation_id=operation_id,
            detail=detalhe,
        )

    with journal.Journal(operation_id) as jrnl:
        for rec in pendentes:
            action_id = rec["actionId"]
            custody_id = rec.get("custodyId") or rec["actionId"]
            custody = Path(rec["custody"])
            target = Path(rec["target"])
            if not custody.exists() and not custody.is_symlink():
                # case 1: sem entrada física => a tomada não aconteceu
                jrnl.custody_released(
                    action_id,
                    custody_id=custody_id,
                    custody=str(custody),
                    returned=False,
                    reason="absent",
                )
                continue
            intent = intents.get(str(custody)) or {}
            purpose = intent.get("purpose", "publish")
            undo = undos.get(action_id) or {}
            ocupado = target.exists() or target.is_symlink()
            reconhecida = _custody_identity(custody) in _accepted_identities(undo)
            if purpose == "publish":
                if not ocupado:
                    fs.return_custody(custody, target)
                    jrnl.custody_released(
                        action_id,
                        custody_id=custody_id,
                        custody=str(custody),
                        returned=True,
                        reason="returned",
                    )
                elif reconhecida:
                    # A entrada é duplicata byte-a-byte do backup (identidade
                    # aceita): liberá-la não destrói nada, e o estado final fica
                    # SEM órfão. O alvo ocupado por terceiro sobrevive; quem
                    # falhará é o undo da ação, que recusa sobrescrever intruso.
                    fs.release_custody(custody)
                    jrnl.custody_released(
                        action_id,
                        custody_id=custody_id,
                        custody=str(custody),
                        returned=False,
                        reason="done",
                    )
                else:
                    falha(f"alvo reocupado e custódia divergente do backup: {target}")
            elif purpose == "remove":
                expected = undo.get("expectHash")
                if expected is None or _custody_identity(custody) == str(expected):
                    fs.release_custody(custody)
                    jrnl.custody_released(
                        action_id,
                        custody_id=custody_id,
                        custody=str(custody),
                        returned=False,
                        reason="done",
                    )
                else:
                    falha(f"custódia de remoção divergente: {custody}")
            else:  # restore
                if not ocupado:
                    fs.return_custody(custody, target)
                    jrnl.custody_released(
                        action_id,
                        custody_id=custody_id,
                        custody=str(custody),
                        returned=True,
                        reason="returned",
                    )
                elif reconhecida:
                    fs.release_custody(custody)
                    jrnl.custody_released(
                        action_id,
                        custody_id=custody_id,
                        custody=str(custody),
                        returned=False,
                        reason="done",
                    )
                else:
                    falha(f"alvo do restore reocupado e custódia divergente: {target}")
        for rec in restos:
            action_id = rec["actionId"]
            custody = Path(rec["custody"])
            if not custody.exists() and not custody.is_symlink():
                continue
            undo = undos.get(action_id) or {}
            custody_id = rec.get("custodyId") or rec["actionId"]
            if _custody_identity(custody) in _accepted_identities(undo):
                fs.release_custody(custody)
            else:
                falha(f"custódia liberada reapareceu divergente: {custody}")


def _has_rollback_evidence(records: list[dict[str, Any]]) -> bool:
    """True se há trabalho de rollback interrompido (mesmo com COMMIT no journal).

    Uma operação commitada com custódia pendente, restos de liberação ou
    registros de propósito remove/restore NÃO pode ser declarada kept: algo foi
    retirado do lugar e o recovery precisa terminar o trabalho antes de decidir.

    A correlação de ciclos é por tentativa (caminho da custódia, que embute o
    custodyId), nunca por actionId: o mesmo actionId aparece em ciclos distintos
    (apply e rollback) e correlacionar por ele mistura tentativas — o P1.
    """
    taken = [r for r in records if r.get("type") == "custody.taken"]
    released = {r.get("custody") for r in records if r.get("type") == "custody.released"}
    if any(r.get("custody") not in released for r in taken):
        return True
    for r in records:
        if r.get("type") == "custody.released" and not r.get("returned"):
            cust = r.get("custody")
            if cust and (Path(cust).exists() or Path(cust).is_symlink()):
                return True
        if r.get("type") == "custody.intent" and r.get("purpose") in {"remove", "restore"}:
            return True
    return False


def _publish_verified_tx(
    jrnl: journal.Journal,
    action_id: str,
    path: Path,
    content: bytes,
    expect_hash: str,
    holding: Path,
) -> None:
    """Publica sobre alvo existente com custódia registrada no journal.

    O temporário só é criado DEPOIS da tomada da custódia: um crash nos pontos
    de custódia não deixa temporário órfão no diretório do alvo.
    """
    custody_id = _next_custody_id(jrnl, action_id)
    custody_dest = _custody_dest(holding, custody_id)
    jrnl.custody_intent(
        action_id,
        custody_id=custody_id,
        target=str(path),
        custody=str(custody_dest),
        purpose="publish",
        expected=expect_hash,
    )
    _maybe_crash("custody.intent")
    custody = fs.take_custody_named(path, custody_dest)
    if custody is None:
        tmp = fs.write_tmp(path.parent, content)
        try:
            fs.publish_link(tmp, path)
        except BaseException:
            fs.discard_tmp(tmp)
            raise
        jrnl.custody_released(
            action_id,
            custody_id=custody_id,
            custody=str(custody_dest),
            returned=False,
            reason="absent",
        )
        return
    jrnl.custody_taken(
        action_id,
        custody_id=custody_id,
        target=str(path),
        custody=str(custody_dest),
    )
    _maybe_crash("custody.taken")
    if fs.hash_file(custody) != expect_hash:
        fs.return_custody(custody, path)
        jrnl.custody_released(
            action_id,
            custody_id=custody_id,
            custody=str(custody_dest),
            returned=True,
            reason="mismatch",
        )
        raise SteamZeroError("E-TX-STALE-PLAN", detail=f"alvo mudou antes de publicar: {path}")
    tmp = fs.write_tmp(path.parent, content)
    try:
        fs.publish_link(tmp, path)
    except OSError:
        fs.discard_tmp(tmp)
        fs.return_custody(custody, path)
        jrnl.custody_released(
            action_id,
            custody_id=custody_id,
            custody=str(custody_dest),
            returned=True,
            reason="occupied",
        )
        raise
    _maybe_crash("custody.postlink")
    jrnl.custody_released(
        action_id,
        custody_id=custody_id,
        custody=str(custody_dest),
        returned=False,
        reason="done",
    )
    fs.release_custody(custody)
    _maybe_crash("custody.release")


def _remove_verified_tx(
    jrnl: journal.Journal,
    action_id: str,
    path: Path,
    expected: str | None,
    holding: Path,
    *,
    mismatch_code: str,
) -> None:
    """Remove ``path`` só se for o que esperávamos — com custódia registrada."""
    custody_id = _next_custody_id(jrnl, action_id)
    custody_dest = _custody_dest(holding, custody_id)
    jrnl.custody_intent(
        action_id,
        custody_id=custody_id,
        target=str(path),
        custody=str(custody_dest),
        purpose="remove",
        expected=expected,
    )
    _maybe_crash("custody.intent")
    custody = fs.take_custody_named(path, custody_dest)
    if custody is None:
        jrnl.custody_released(
            action_id,
            custody_id=custody_id,
            custody=str(custody_dest),
            returned=False,
            reason="absent",
        )
        return
    jrnl.custody_taken(
        action_id,
        custody_id=custody_id,
        target=str(path),
        custody=str(custody_dest),
    )
    _maybe_crash("custody.taken")
    if expected is not None and _custody_identity(custody) != expected:
        fs.return_custody(custody, path)
        jrnl.custody_released(
            action_id,
            custody_id=custody_id,
            custody=str(custody_dest),
            returned=True,
            reason="mismatch",
        )
        raise SteamZeroError(
            mismatch_code, detail=f"rollback recusou remover arquivo alterado: {path}"
        )
    jrnl.custody_released(
        action_id,
        custody_id=custody_id,
        custody=str(custody_dest),
        returned=False,
        reason="done",
    )
    fs.release_custody(custody)
    _maybe_crash("custody.release")


def _restore_verified_tx(
    jrnl: journal.Journal,
    action_id: str,
    operation_id: str,
    backup: Path,
    target: Path,
    accepted: set[str],
    holding: Path,
    undo: dict[str, Any],
) -> None:
    """Restaura ``backup`` sobre ``target`` sem sobrescrever o inesperado."""
    custody_id = _next_custody_id(jrnl, action_id)
    custody_dest = _custody_dest(holding, custody_id)
    jrnl.custody_intent(
        action_id,
        custody_id=custody_id,
        target=str(target),
        custody=str(custody_dest),
        purpose="restore",
        expected=undo.get("expectHash"),
    )
    _maybe_crash("custody.intent")
    custody = fs.take_custody_named(target, custody_dest)
    if custody is not None:
        jrnl.custody_taken(
            action_id,
            custody_id=custody_id,
            target=str(target),
            custody=str(custody_dest),
        )
        _maybe_crash("custody.taken")
        if _custody_identity(custody) not in accepted:
            fs.return_custody(custody, target)
            jrnl.custody_released(
                action_id,
                custody_id=custody_id,
                custody=str(custody_dest),
                returned=True,
                reason="mismatch",
            )
            raise SteamZeroError(
                "E-TX-ROLLBACK-FAILED",
                operation_id=operation_id,
                detail=f"rollback recusou sobrescrever arquivo alterado: {target}",
            )
    try:
        fs.copy_exclusive(backup, target)
    except BaseException:
        if custody is not None:
            fs.return_custody(custody, target)
            jrnl.custody_released(
                action_id,
                custody_id=custody_id,
                custody=str(custody_dest),
                returned=True,
                reason="error",
            )
        raise
    _maybe_crash("custody.postlink")
    if custody is not None:
        jrnl.custody_released(
            action_id,
            custody_id=custody_id,
            custody=str(custody_dest),
            returned=False,
            reason="done",
        )
        fs.release_custody(custody)
    else:
        jrnl.custody_released(
            action_id,
            custody_id=custody_id,
            custody=str(custody_dest),
            returned=False,
            reason="absent",
        )
    _maybe_crash("custody.release")


def _publish_symlink_tx(
    jrnl: journal.Journal,
    action_id: str,
    source: Path,
    target: Path,
    holding: Path,
    *,
    expected_readlink: str | None,
    purpose: str,
) -> None:
    """Publica symlink por link exclusivo, com custódia registrada."""
    custody_id = _next_custody_id(jrnl, action_id)
    custody_dest = _custody_dest(holding, custody_id)
    jrnl.custody_intent(
        action_id,
        custody_id=custody_id,
        target=str(target),
        custody=str(custody_dest),
        purpose=purpose,
        expected=expected_readlink,
    )
    _maybe_crash("custody.intent")
    custody = fs.take_custody_named(target, custody_dest)
    if custody is not None:
        jrnl.custody_taken(
            action_id,
            custody_id=custody_id,
            target=str(target),
            custody=str(custody_dest),
        )
        _maybe_crash("custody.taken")
        if not custody.is_symlink():
            fs.return_custody(custody, target)
            jrnl.custody_released(
                action_id,
                custody_id=custody_id,
                custody=str(custody_dest),
                returned=True,
                reason="mismatch",
            )
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"destino de link já existe: {target}")
        if expected_readlink is not None and os.readlink(custody) != expected_readlink:
            fs.return_custody(custody, target)
            jrnl.custody_released(
                action_id,
                custody_id=custody_id,
                custody=str(custody_dest),
                returned=True,
                reason="mismatch",
            )
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail=f"link mudou antes de publicar: {target}"
            )
    tmp = fs.make_symlink_tmp(target.parent, target.name, source)
    try:
        fs.publish_symlink(tmp, target)
    except FileExistsError as exc:
        fs.discard_tmp(tmp)
        if custody is not None:
            fs.return_custody(custody, target)
            jrnl.custody_released(
                action_id,
                custody_id=custody_id,
                custody=str(custody_dest),
                returned=True,
                reason="occupied",
            )
            raise SteamZeroError(
                "E-TX-STALE-PLAN", detail=f"destino de link já existe: {target}"
            ) from exc
        raise SteamZeroError(
            "E-TX-STALE-PLAN", detail=f"destino de link já existe: {target}"
        ) from exc
    except BaseException:
        fs.discard_tmp(tmp)
        if custody is not None:
            fs.return_custody(custody, target)
            jrnl.custody_released(
                action_id,
                custody_id=custody_id,
                custody=str(custody_dest),
                returned=True,
                reason="error",
            )
        raise
    _maybe_crash("custody.postlink")
    if custody is not None:
        jrnl.custody_released(
            action_id,
            custody_id=custody_id,
            custody=str(custody_dest),
            returned=False,
            reason="done",
        )
        fs.release_custody(custody)
    else:
        jrnl.custody_released(
            action_id,
            custody_id=custody_id,
            custody=str(custody_dest),
            returned=False,
            reason="absent",
        )
    _maybe_crash("custody.release")


def _publish_move_tx(
    jrnl: journal.Journal,
    action_id: str,
    source: Path,
    target: Path,
    holding: Path,
) -> None:
    """Move ``source`` para ``target`` sem substituir nada que apareça."""
    custody_id = _next_custody_id(jrnl, action_id)
    custody_dest = _custody_dest(holding, custody_id)
    jrnl.custody_intent(
        action_id,
        custody_id=custody_id,
        target=str(target),
        custody=str(custody_dest),
        purpose="publish",
        expected=None,
    )
    _maybe_crash("custody.intent")
    custody = fs.take_custody_named(target, custody_dest)
    _maybe_crash("custody.taken")
    if custody is not None:
        fs.return_custody(custody, target)
        jrnl.custody_released(
            action_id,
            custody_id=custody_id,
            custody=str(custody_dest),
            returned=True,
            reason="occupied",
        )
        raise SteamZeroError("E-TX-STALE-PLAN", detail=f"destino já existe: {target}")
    try:
        fs.move_file_noreplace(source, target)
    except FileExistsError as exc:
        jrnl.custody_released(
            action_id,
            custody_id=custody_id,
            custody=str(custody_dest),
            returned=False,
            reason="occupied",
        )
        raise SteamZeroError("E-TX-STALE-PLAN", detail=f"destino já existe: {target}") from exc
    except BaseException:
        jrnl.custody_released(
            action_id,
            custody_id=custody_id,
            custody=str(custody_dest),
            returned=False,
            reason="error",
        )
        raise
    _maybe_crash("custody.postlink")
    jrnl.custody_released(
        action_id,
        custody_id=custody_id,
        custody=str(custody_dest),
        returned=False,
        reason="done",
    )
    _maybe_crash("custody.release")


def _apply_actions(
    op_id: str, plan: Plan, jrnl: journal.Journal, undo_map: dict[str, dict[str, Any]]
) -> None:
    jrnl.stage("apply")
    holding = paths.quarantine_for(op_id)
    for a in plan.actions:
        jrnl.intent(a.action_id, undo=undo_map[a.action_id])
        _maybe_crash("apply.intent")
        if a.kind == "move":
            if a.source is None:  # defesa em profundidade; validado antes
                raise SteamZeroError("E-TX-STALE-PLAN", detail="movimento sem origem")
            source = Path(a.source)
            target = Path(a.target)
            if _fingerprint(source) != a.new_hash or _fingerprint(target) is not None:
                raise SteamZeroError(
                    "E-TX-STALE-PLAN", detail=f"movimento mudou durante apply: {a.source}"
                )
            _publish_move_tx(jrnl, a.action_id, source, target, holding)
        elif a.kind == "copy":
            if a.source is None:
                raise SteamZeroError("E-TX-STALE-PLAN", detail="cópia sem origem")
            source = Path(a.source)
            target = Path(a.target)
            staged = paths.staging_for(op_id) / a.action_id
            if _fingerprint(source) != a.new_hash or _fingerprint(staged) != a.new_hash:
                raise SteamZeroError(
                    "E-TX-STALE-PLAN", detail=f"cópia mudou durante apply: {a.source}"
                )
            fs.copy_file_atomic(staged, target)
        elif a.kind == "symlink":
            if a.source is None:  # defesa em profundidade; validado antes
                raise SteamZeroError("E-TX-STALE-PLAN", detail="symlink sem origem")
            source = Path(a.source)
            target = Path(a.target)
            if _fingerprint(source) != a.new_hash:
                raise SteamZeroError(
                    "E-TX-STALE-PLAN", detail=f"link mudou durante apply: {a.target}"
                )
            # Na substituição autorizada (replace_existing), o link legítimo a
            # preservar é o que JÁ ESTÁ no alvo (registrado no undo), não o
            # destino novo do plano.
            undo = undo_map[a.action_id]
            expected_readlink: str | None = None
            if undo.get("op") == "restore-symlink" and undo.get("expectHash"):
                obturado = str(undo["expectHash"])
                expected_readlink = (
                    obturado[len("symlink:") :] if obturado.startswith("symlink:") else obturado
                )
            _publish_symlink_tx(
                jrnl,
                a.action_id,
                source,
                target,
                holding,
                expected_readlink=expected_readlink,
                purpose="publish",
            )
        elif a.kind == "delete":
            _remove_verified_tx(
                jrnl,
                a.action_id,
                Path(a.target),
                undo_map[a.action_id].get("expectHash"),
                holding,
                mismatch_code="E-TX-STALE-PLAN",
            )
        else:
            # A janela que a revalidação de preconditions NÃO cobre.
            #
            # `_revalidate_preconditions` roda uma vez, no início do apply, e
            # depois ainda acontecem staging e backup. Um arquivo estrangeiro
            # criado nesse intervalo era copiado para o backup e então
            # SOBRESCRITO por esta linha, com a operação retornando `ok` — a
            # garantia de nunca destruir arquivo alheio valia só até o staging.
            #
            # A política vem do próprio plano: quando a precondição registrou o
            # alvo como AUSENTE, a publicação é uma criação exclusiva, que é a
            # única forma atômica de garantir que não se sobrescreve nada.
            # Quando o alvo existia, o fingerprint é reconferido imediatamente
            # antes de publicar, em vez de só no começo da operação.
            target = Path(a.target)
            expected = _expected_fingerprints(plan).get(str(target), _MISSING)
            if expected is not _MISSING and _fingerprint(target) != expected:
                raise SteamZeroError(
                    "E-TX-STALE-PLAN",
                    detail=f"alvo mudou durante apply: {a.target}",
                )
            if expected is None or expected is _MISSING:
                fs.write_atomic(target, a.new_content(), must_not_exist=True)
            else:
                # A conferência acima é barata e pega o caso comum, mas sozinha
                # deixa janela até o `rename`. A publicação vai condicionada à
                # identidade, com custódia durável registrada no journal.
                _publish_verified_tx(
                    jrnl, a.action_id, target, a.new_content(), str(expected), holding
                )
        _maybe_crash("apply.activate")
        jrnl.done(a.action_id)
        _maybe_crash("apply.done")


def _verify(op_id: str, plan: Plan, jrnl: journal.Journal) -> None:
    jrnl.stage("verify")
    for a in plan.actions:
        target = Path(a.target)
        if a.kind == "delete":
            valid = not target.exists() and not target.is_symlink()
        elif a.kind == "symlink":
            valid = (
                a.source is not None
                and target.is_symlink()
                and Path(os.path.realpath(target)) == Path(os.path.realpath(a.source))
                and _fingerprint(Path(a.source)) == a.new_hash
            )
        else:
            valid = target.exists() and fs.hash_file(target) == a.new_hash
        if not valid:
            jrnl.close()
            _do_rollback(op_id, reason="verify-failed")
            raise SteamZeroError(
                "E-TX-VERIFY-FAILED",
                operation_id=op_id,
                auto_action="rollback automático executado",
                detail=f"hash divergente em {a.target}",
            )
        if a.kind == "move" and a.source is not None and Path(a.source).exists():
            jrnl.close()
            _do_rollback(op_id, reason="verify-failed")
            raise SteamZeroError(
                "E-TX-VERIFY-FAILED",
                operation_id=op_id,
                auto_action="rollback automático executado",
                detail=f"origem ainda existe após movimento: {a.source}",
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
    if not journal.has_type(records, "operation.begin"):
        raise SteamZeroError(
            "E-TX-STALE-PLAN",
            operation_id=operation_id,
            detail="operação não encontrada para rollback",
        )
    if journal.has_type(records, journal.ROLLBACK):
        return RollbackResult(operation_id, "rolled-back")  # idempotente (RB-3)

    # Fecha qualquer custódia pendente de um crash anterior (FI-06). Idempotente;
    # rodar de novo não muda estado e não destrói o que não reconhece.
    _reconcile_custody(operation_id, records)

    intents = [r for r in records if r.get("type") == "action.intent"]
    holding = paths.quarantine_for(operation_id)
    restored: list[str] = []
    with journal.Journal(operation_id) as jrnl:
        for rec in reversed(intents):
            undo = rec["undo"]
            action_id = rec["actionId"]
            target = Path(undo["target"])
            if undo["op"] == "restore":
                _restore_one(jrnl, action_id, operation_id, target, undo, holding)
            elif undo["op"] == "restore-symlink":
                _restore_symlink(
                    jrnl,
                    action_id,
                    target,
                    undo,
                    holding,
                    repair=reason in _REPAIR_ROLLBACK_REASONS,
                )
            elif undo["op"] == "move-restore":
                _restore_move(jrnl, action_id, operation_id, undo, holding)
            elif undo["op"] == "delete":
                expected = undo.get("expectHash")
                current = _fingerprint(target)
                repairable_symlink = (
                    reason in _REPAIR_ROLLBACK_REASONS
                    and undo.get("expectKind") == "symlink"
                    and target.is_symlink()
                )
                if (
                    expected is not None
                    and current not in {None, expected}
                    and not repairable_symlink
                ):
                    raise SteamZeroError(
                        "E-TX-ROLLBACK-FAILED",
                        operation_id=operation_id,
                        detail=f"rollback recusou remover arquivo alterado: {target}",
                    )
                # Symlink e move têm semântica de identidade própria (o "conteúdo"
                # é o alvo do link) e guard próprio acima; a custódia é para
                # arquivo REGULAR, onde a identidade é o hash.
                if (
                    expected is None
                    or repairable_symlink
                    or undo.get("expectKind")
                    not in {
                        "write",
                        "copy",
                    }
                ):
                    fs.remove_file(target)
                else:
                    # A conferência acima é só triagem barata; a garantia está em
                    # tomar a entrada em custódia ANTES de removê-la, com vinca no
                    # journal, para que um arquivo criado depois do guard volte ao
                    # lugar em vez de sumir.
                    try:
                        _remove_verified_tx(
                            jrnl,
                            action_id,
                            target,
                            expected,
                            holding,
                            mismatch_code="E-TX-ROLLBACK-FAILED",
                        )
                    except SteamZeroError as exc:
                        exc.operation_id = operation_id
                        raise
            else:
                raise SteamZeroError(
                    "E-TX-ROLLBACK-FAILED",
                    operation_id=operation_id,
                    detail=f"undo desconhecido: {undo['op']}",
                )
            restored.append(str(target))

        # zero temporários órfãos (ROLLBACK-TESTS §6)
        fs.remove_tree(paths.staging_for(operation_id))
        jrnl.rollback(reason=reason)
    _record_operation_state(operation_id, "rolled-back")
    return RollbackResult(operation_id, "rolled-back", restored)


def _record_operation_state(operation_id: str, state: str) -> None:
    """Espelha o journal no State Store para histórico/eventos reconectáveis."""
    from steamzero.core.state import StateStore

    with StateStore() as store:
        store.migrate()
        store.save_operation(
            operation_id,
            journal_path=str(paths.journal_path(operation_id)),
            state=state,
            backup_path=str(paths.backup_for(operation_id)),
        )


def _restore_one(
    jrnl: journal.Journal,
    action_id: str,
    operation_id: str,
    target: Path,
    undo: dict[str, Any],
    holding: Path,
) -> None:
    # Restaurar é escrever: só pode acontecer sobre um alvo que reconhecemos.
    # O estado legítimo é o backup (nada mudou) ou o que este plano gravou
    # (apply concluiu). Qualquer outra coisa apareceu de fora, e sobrescrevê-la
    # destruiria dado de terceiro — a mesma classe de defeito que o `delete`
    # incondicional tinha.
    applied = undo.get("appliedHash")
    backup_path = paths.backup_for(operation_id) / undo["backupRel"]
    if not backup_path.exists():
        raise SteamZeroError(
            "E-TX-ROLLBACK-FAILED",
            operation_id=operation_id,
            detail=f"backup ausente para {target}",
        )
    if fs.hash_file(backup_path) != undo["expectHash"]:
        raise SteamZeroError(
            "E-TX-ROLLBACK-FAILED",
            operation_id=operation_id,
            detail=f"backup adulterado para {target}",
        )
    aceitos = {undo["expectHash"]} | ({applied} if applied else set())
    try:
        _restore_verified_tx(
            jrnl,
            action_id,
            operation_id,
            backup_path,
            target,
            aceitos,
            holding,
            undo,
        )
    except SteamZeroError as exc:
        exc.operation_id = operation_id
        raise
    if fs.hash_file(target) != undo["expectHash"]:  # RB-4: rollback verificado
        raise SteamZeroError(
            "E-TX-ROLLBACK-FAILED",
            operation_id=operation_id,
            detail=f"hash pós-restauração divergente em {target}",
        )


def _restore_symlink(
    jrnl: journal.Journal,
    action_id: str,
    target: Path,
    undo: dict[str, Any],
    holding: Path,
    *,
    repair: bool,
) -> None:
    source = Path(str(undo["source"]))
    if source.is_symlink() or not source.is_file():
        raise SteamZeroError(
            "E-TX-ROLLBACK-FAILED",
            detail=f"origem do symlink não está íntegra: {source}",
        )
    # O destino legítimo é o link que O PLANO criou (appliedFingerprint) — no
    # modo repair, qualquer symlink é aceitável. A identificação e a troca são
    # atômicas via custódia; um destino recriado por terceiro sobrevive.
    expected_readlink: str | None = None
    if not repair:
        applied = undo.get("appliedFingerprint")
        if applied is not None:
            prefix = "symlink:"
            expected_readlink = applied[len(prefix) :] if applied.startswith(prefix) else applied
    _publish_symlink_tx(
        jrnl,
        action_id,
        source,
        target,
        holding,
        expected_readlink=expected_readlink,
        purpose="restore",
    )
    if not target.is_symlink() or Path(os.path.realpath(target)) != source.resolve():
        raise SteamZeroError(
            "E-TX-ROLLBACK-FAILED",
            detail=f"symlink não foi restaurado: {target}",
        )


def _restore_move(
    jrnl: journal.Journal,
    action_id: str,
    operation_id: str,
    undo: dict[str, Any],
    holding: Path,
) -> None:
    source = Path(undo["source"])
    target = Path(undo["target"])
    expected = str(undo["expectHash"])
    backup = paths.backup_for(operation_id) / str(undo["backupRel"])
    if not backup.exists() or fs.hash_file(backup) != expected:
        raise SteamZeroError(
            "E-TX-ROLLBACK-FAILED",
            operation_id=operation_id,
            detail=f"backup ausente ou adulterado para {source}",
        )
    if source.exists():
        if fs.hash_file(source) != expected:
            raise SteamZeroError(
                "E-TX-ROLLBACK-FAILED",
                operation_id=operation_id,
                detail=f"origem foi recriada com outro conteúdo: {source}",
            )
    else:
        # Publicação exclusiva: um intruso que apareça no lugar vazio da origem
        # sobrevive (o link falha) em vez de ser substituído pelo backup.
        fs.copy_exclusive(backup, source)
    if target.exists():
        if fs.hash_file(target) != expected:
            raise SteamZeroError(
                "E-TX-ROLLBACK-FAILED",
                operation_id=operation_id,
                detail=f"destino mudou após a operação: {target}",
            )
        try:
            _remove_verified_tx(
                jrnl,
                action_id,
                target,
                expected,
                holding,
                mismatch_code="E-TX-ROLLBACK-FAILED",
            )
        except SteamZeroError as exc:
            exc.operation_id = operation_id
            raise
    if fs.hash_file(source) != expected:
        raise SteamZeroError(
            "E-TX-ROLLBACK-FAILED",
            operation_id=operation_id,
            detail=f"hash pós-restauração divergente em {source}",
        )


def recover_operation(operation_id: str) -> RecoveryResult:
    """Recupera uma operação após crash: commit=>mantém; senão=>rollback.

    Uma operação commitada NUNCA é declarada kept quando há evidência de
    trabalho interrompido: custódia pendente, restos de liberação ou registros
    de propósito remove/restore significam que um rollback começou e precisa
    terminar — declarar kept nesse estado mentiria sobre arquivos que já
    saíram do lugar (FI-06).
    """
    records = journal.read_records(operation_id)
    if not records:
        return RecoveryResult(operation_id, "clean")
    if journal.has_type(records, journal.ROLLBACK):
        return RecoveryResult(operation_id, "already-terminal")
    if journal.has_type(records, journal.COMMIT):
        if _has_rollback_evidence(records):
            try:
                _do_rollback(operation_id, reason="crash-recovery")
                return RecoveryResult(operation_id, "rolled-back")
            except SteamZeroError as exc:
                if exc.code == "E-TX-ROLLBACK-FAILED":
                    return RecoveryResult(operation_id, "rollback-failed")
                raise
        fs.remove_tree(paths.staging_for(operation_id))
        return RecoveryResult(operation_id, "kept")
    try:
        _do_rollback(operation_id, reason="crash-recovery")
        return RecoveryResult(operation_id, "rolled-back")
    except SteamZeroError as exc:
        if exc.code == "E-TX-ROLLBACK-FAILED":
            return RecoveryResult(operation_id, "rollback-failed")
        raise


def _operation_ids_for_plan(plan_id: str) -> list[str]:
    """Localiza operações iniciadas pela identidade durável do plano."""
    journal_dir = paths.journal_dir()
    if not journal_dir.is_dir():
        return []
    operation_ids: list[str] = []
    for entry in sorted(journal_dir.glob("*.jsonl")):
        records = journal.read_records(entry.stem)
        if any(
            record.get("type") == "operation.begin" and record.get("planId") == plan_id
            for record in records
        ):
            operation_ids.append(entry.stem)
    return operation_ids


def recover_plan(plan_id: str) -> list[RecoveryResult]:
    """Recupera somente operações de um plano e encerra sua autorização.

    Usado por owners que persistem uma referência ao plano delegado. Um crash
    real (``BaseException``/SIGKILL) deixa o plano pending até este ponto; após
    reconciliar os journals correspondentes, o plano vira applied quando o
    commit foi mantido e aborted em qualquer outra saída.
    """
    plan = load_plan(plan_id)
    if plan.status != "pending":
        return []
    results = [recover_operation(operation_id) for operation_id in _operation_ids_for_plan(plan_id)]
    current = load_plan(plan_id)
    if current.status == "pending":
        terminal = "applied" if any(result.outcome == "kept" for result in results) else "aborted"
        _mark_plan(current, terminal)
    return results


def recover_all() -> list[RecoveryResult]:
    """Varre o journal dir e recupera toda operação não-terminal (pós-reboot)."""
    jdir = paths.journal_dir()
    if not jdir.is_dir():
        return []
    results: list[RecoveryResult] = []
    for entry in sorted(jdir.glob("*.jsonl")):
        results.append(recover_operation(entry.stem))
    return results
