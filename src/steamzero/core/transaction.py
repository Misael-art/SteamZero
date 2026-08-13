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
    rollback_guarantee: str = "G-FULL",
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
        rollback_guarantee=rollback_guarantee,
        requirements=requirements,
        actions=actions,
        preconditions=preconditions,
        preview=_render_preview(kind, actions, rollback_guarantee),
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
            }
        else:
            undo_map[a.action_id] = {
                "op": "delete",
                "target": a.target,
                "backupRel": None,
                "expectHash": (
                    a.new_hash
                    if a.kind == "copy"
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


def _apply_actions(
    op_id: str, plan: Plan, jrnl: journal.Journal, undo_map: dict[str, dict[str, Any]]
) -> None:
    jrnl.stage("apply")
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
            fs.move_file(source, target)
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
            fs.symlink_atomic(source, target)
        elif a.kind == "delete":
            fs.remove_file(Path(a.target))
        else:
            fs.write_atomic(Path(a.target), a.new_content())
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

    intents = [r for r in records if r.get("type") == "action.intent"]
    restored: list[str] = []
    for rec in reversed(intents):
        undo = rec["undo"]
        target = Path(undo["target"])
        if undo["op"] == "restore":
            _restore_one(operation_id, target, undo)
        elif undo["op"] == "restore-symlink":
            _restore_symlink(
                target,
                undo,
                repair=reason in _REPAIR_ROLLBACK_REASONS,
            )
        elif undo["op"] == "move-restore":
            _restore_move(operation_id, undo)
        elif undo["op"] == "delete":
            expected = undo.get("expectHash")
            current = _fingerprint(target)
            repairable_symlink = (
                reason in _REPAIR_ROLLBACK_REASONS
                and undo.get("expectKind") == "symlink"
                and target.is_symlink()
            )
            if expected is not None and current not in {None, expected} and not repairable_symlink:
                raise SteamZeroError(
                    "E-TX-ROLLBACK-FAILED",
                    operation_id=operation_id,
                    detail=f"rollback recusou remover arquivo alterado: {target}",
                )
            fs.remove_file(target)
        else:
            raise SteamZeroError(
                "E-TX-ROLLBACK-FAILED",
                operation_id=operation_id,
                detail=f"undo desconhecido: {undo['op']}",
            )
        restored.append(str(target))

    # zero temporários órfãos (ROLLBACK-TESTS §6)
    fs.remove_tree(paths.staging_for(operation_id))
    with journal.Journal(operation_id) as jrnl:
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


def _restore_one(operation_id: str, target: Path, undo: dict[str, Any]) -> None:
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
    fs.copy_file_atomic(backup_path, target)
    if fs.hash_file(target) != undo["expectHash"]:  # RB-4: rollback verificado
        raise SteamZeroError(
            "E-TX-ROLLBACK-FAILED",
            operation_id=operation_id,
            detail=f"hash pós-restauração divergente em {target}",
        )


def _restore_symlink(target: Path, undo: dict[str, Any], *, repair: bool) -> None:
    if target.exists() or target.is_symlink():
        applied = undo.get("appliedFingerprint")
        if (applied is None or _fingerprint(target) != applied) and not (
            repair and target.is_symlink()
        ):
            raise SteamZeroError(
                "E-TX-ROLLBACK-FAILED",
                detail=f"rollback recusou substituir destino recriado: {target}",
            )
        fs.remove_file(target)
    source = Path(str(undo["source"]))
    if source.is_symlink() or not source.is_file():
        raise SteamZeroError(
            "E-TX-ROLLBACK-FAILED",
            detail=f"origem do symlink não está íntegra: {source}",
        )
    fs.symlink_atomic(source, target)
    if not target.is_symlink() or Path(os.path.realpath(target)) != source.resolve():
        raise SteamZeroError(
            "E-TX-ROLLBACK-FAILED",
            detail=f"symlink não foi restaurado: {target}",
        )


def _restore_move(operation_id: str, undo: dict[str, Any]) -> None:
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
        fs.copy_file_atomic(backup, source)
    if target.exists():
        if fs.hash_file(target) != expected:
            raise SteamZeroError(
                "E-TX-ROLLBACK-FAILED",
                operation_id=operation_id,
                detail=f"destino mudou após a operação: {target}",
            )
        fs.remove_file(target)
    if fs.hash_file(source) != expected:
        raise SteamZeroError(
            "E-TX-ROLLBACK-FAILED",
            operation_id=operation_id,
            detail=f"hash pós-restauração divergente em {source}",
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
