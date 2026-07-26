# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Experiência Desktop portátil, independente de providers e tolerante a falhas.

O domínio só conhece capacidades e efeitos injetados. KDE, InputPlumber, Steam e
qualquer outro provider são opcionais; sua ausência nunca impede status, plano,
modo seguro ou recuperação do estado já capturado.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol

from steamzero.core import ids, lock
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore

PROFILE_HANDHELD = "handheld-desktop"
PROFILE_DOCKED = "docked-desktop"
PROFILE_SAFE = "safe"
PROFILE_IDS = frozenset({PROFILE_HANDHELD, PROFILE_DOCKED, PROFILE_SAFE})
REQUESTED_PROFILES = frozenset({"auto", "handheld", "dock", "safe"})

_CURRENT_ID = "desktop-current"
_OVERRIDE_ID = "desktop-override"
_RECOVERY_ID = "desktop-recovery"
_OBSERVATION_ID = "desktop-observation"
_PLAN_PREFIX = "desktop-plan-"
_CONFLICT_PLAN_PREFIX = "desktop-conflict-plan-"
_PLAN_TTL = timedelta(hours=1)


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class DisplayState:
    """Estado observável de uma saída gráfica."""

    name: str
    connected: bool
    internal: bool
    width: int | None = None
    height: int | None = None
    refresh_hz: float | None = None
    scale: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "connected": self.connected,
            "internal": self.internal,
            "width": self.width,
            "height": self.height,
            "refreshHz": self.refresh_hz,
            "scale": self.scale,
        }


@dataclass(frozen=True)
class DesktopContext:
    """Snapshot imutável dos sinais usados para escolher a experiência."""

    device_kind: str
    session_type: str
    displays: tuple[DisplayState, ...]
    physical_dock: bool
    external_keyboard: bool
    external_mouse: bool
    capabilities: frozenset[str]
    conflicts: tuple[str, ...] = ()

    @property
    def external_display(self) -> bool:
        return any(display.connected and not display.internal for display in self.displays)

    def to_dict(self) -> dict[str, Any]:
        return {
            "deviceKind": self.device_kind,
            "sessionType": self.session_type,
            "displays": [display.to_dict() for display in self.displays],
            "physicalDock": self.physical_dock,
            "externalKeyboard": self.external_keyboard,
            "externalMouse": self.external_mouse,
            "capabilities": sorted(self.capabilities),
            "conflicts": list(self.conflicts),
        }

    def fingerprint(self) -> str:
        encoded = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


class DesktopContextPort(Protocol):
    def snapshot(self) -> DesktopContext:
        """Obtém um snapshot sem alterar o host."""
        ...


@dataclass(frozen=True)
class DesktopConflictAction:
    """Remediação allowlisted para um owner externo detectado."""

    action_id: str
    unit: str
    scope: str
    summary: str
    requires_privilege: bool
    commands: tuple[tuple[str, ...], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "actionId": self.action_id,
            "unit": self.unit,
            "scope": self.scope,
            "summary": self.summary,
            "requiresPrivilege": self.requires_privilege,
            "commands": [list(command) for command in self.commands],
        }

    @staticmethod
    def from_dict(value: dict[str, Any]) -> DesktopConflictAction:
        text_fields = ("actionId", "unit", "scope", "summary")
        if any(not isinstance(value.get(field), str) or not value[field] for field in text_fields):
            raise ValueError("metadados de remediação inválidos")
        if value["scope"] not in {"user", "system"} or not isinstance(
            value.get("requiresPrivilege"), bool
        ):
            raise ValueError("escopo de remediação inválido")
        commands = value.get("commands")
        if not isinstance(commands, list) or not all(
            isinstance(command, list)
            and command
            and all(isinstance(argument, str) and argument for argument in command)
            for command in commands
        ):
            raise ValueError("comandos de remediação inválidos")
        return DesktopConflictAction(
            action_id=value["actionId"],
            unit=value["unit"],
            scope=value["scope"],
            summary=value["summary"],
            requires_privilege=value["requiresPrivilege"],
            commands=tuple(tuple(command) for command in commands),
        )


class DesktopConflictResolverPort(Protocol):
    """Porta restrita para liberar ownership concorrente conhecido."""

    def actions(self, context: DesktopContext) -> tuple[DesktopConflictAction, ...]: ...

    def release(self, action: DesktopConflictAction) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ExperienceProfile:
    """Política completa para uma sessão Desktop."""

    profile_id: str
    scale: float
    touch_mode: bool
    maximize_windows: bool
    panel_height: int
    panel_auto_hide: bool
    shell_actions: tuple[str, ...]
    keyboard_chain: tuple[str, ...]
    preferred_input_owner: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.profile_id,
            "scale": self.scale,
            "touchMode": self.touch_mode,
            "maximizeWindows": self.maximize_windows,
            "panelHeight": self.panel_height,
            "panelAutoHide": self.panel_auto_hide,
            "shellActions": list(self.shell_actions),
            "keyboardChain": list(self.keyboard_chain),
            "preferredInputOwner": self.preferred_input_owner,
        }


@dataclass(frozen=True)
class OwnershipLease:
    """Owner lógico válido somente para o fingerprint de contexto capturado."""

    resource: str
    provider: str
    holder: str
    context_fingerprint: str

    def to_dict(self) -> dict[str, str]:
        return {
            "resource": self.resource,
            "provider": self.provider,
            "holder": self.holder,
            "contextFingerprint": self.context_fingerprint,
        }


class DesktopEffectPort(Protocol):
    """Efeito reversível sobre uma parte da sessão Desktop."""

    name: str

    def available(self, context: DesktopContext) -> bool: ...

    def capture(self, context: DesktopContext) -> dict[str, Any]: ...

    def apply(self, profile: ExperienceProfile, context: DesktopContext) -> None: ...

    def verify(self, profile: ExperienceProfile, context: DesktopContext) -> bool: ...

    def restore(self, snapshot: dict[str, Any]) -> None: ...


def _keyboard_chain(capabilities: frozenset[str]) -> tuple[str, ...]:
    candidates = (
        ("plasma-keyboard", "plasma-keyboard"),
        ("kwin-virtual-keyboard", "kwin-maliit"),
        ("steam-keyboard", "steam"),
        ("wvkbd", "wvkbd"),
        ("onboard", "onboard"),
        ("kde-connect", "kde-connect"),
    )
    return tuple(provider for capability, provider in candidates if capability in capabilities)


def profile_for(profile_id: str, context: DesktopContext) -> ExperienceProfile:
    if profile_id not in PROFILE_IDS:
        raise ValueError(f"perfil Desktop inválido: {profile_id}")
    keyboard_chain = _keyboard_chain(context.capabilities)
    preferred_owner = (
        "inputplumber" if "inputplumber-validated" in context.capabilities else "kde-shortcuts"
    )
    if profile_id == PROFILE_HANDHELD:
        return ExperienceProfile(
            profile_id=profile_id,
            scale=1.35,
            touch_mode=True,
            maximize_windows=True,
            panel_height=48,
            panel_auto_hide=True,
            shell_actions=("overview", "application-dashboard"),
            keyboard_chain=keyboard_chain,
            preferred_input_owner=preferred_owner,
        )
    if profile_id == PROFILE_DOCKED:
        return ExperienceProfile(
            profile_id=profile_id,
            scale=1.0,
            touch_mode=False,
            maximize_windows=False,
            panel_height=40,
            panel_auto_hide=False,
            shell_actions=("overview", "application-dashboard"),
            keyboard_chain=keyboard_chain,
            preferred_input_owner=preferred_owner,
        )
    return ExperienceProfile(
        profile_id=profile_id,
        scale=1.35,
        touch_mode=True,
        maximize_windows=False,
        panel_height=48,
        panel_auto_hide=False,
        shell_actions=("overview",),
        keyboard_chain=keyboard_chain,
        preferred_input_owner="none",
    )


def automatic_profile(context: DesktopContext) -> str:
    """Tela externa ou dock muda o perfil; teclado/mouse isolados não mudam."""
    if context.external_display or context.physical_dock:
        return PROFILE_DOCKED
    if context.device_kind.startswith("deck-"):
        return PROFILE_HANDHELD
    return PROFILE_DOCKED


@dataclass
class ExperiencePlan:
    plan_id: str
    confirm_token: str
    requested_profile: str
    target: ExperienceProfile
    context_fingerprint: str
    created_at: str
    expires_at: str
    status: str
    blockers: tuple[str, ...]
    changes: tuple[str, ...]
    rollback_guarantee: str = "G-STATE"
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "planId": self.plan_id,
            "confirmToken": self.confirm_token,
            "requestedProfile": self.requested_profile,
            "target": self.target.to_dict(),
            "contextFingerprint": self.context_fingerprint,
            "createdAt": self.created_at,
            "expiresAt": self.expires_at,
            "status": self.status,
            "blockers": list(self.blockers),
            "changes": list(self.changes),
            "rollbackGuarantee": self.rollback_guarantee,
        }

    @staticmethod
    def from_dict(value: dict[str, Any]) -> ExperiencePlan:
        target = value["target"]
        return ExperiencePlan(
            plan_id=value["planId"],
            confirm_token=value["confirmToken"],
            requested_profile=value["requestedProfile"],
            target=ExperienceProfile(
                profile_id=target["id"],
                scale=float(target["scale"]),
                touch_mode=bool(target["touchMode"]),
                maximize_windows=bool(target["maximizeWindows"]),
                panel_height=int(target["panelHeight"]),
                panel_auto_hide=bool(target.get("panelAutoHide", True)),
                shell_actions=tuple(target["shellActions"]),
                keyboard_chain=tuple(target["keyboardChain"]),
                preferred_input_owner=target["preferredInputOwner"],
            ),
            context_fingerprint=value["contextFingerprint"],
            created_at=value["createdAt"],
            expires_at=value["expiresAt"],
            status=value["status"],
            blockers=tuple(value.get("blockers", [])),
            changes=tuple(value.get("changes", [])),
            rollback_guarantee=value.get("rollbackGuarantee", "G-STATE"),
            schema_version=int(value.get("schemaVersion", 1)),
        )


@dataclass(frozen=True)
class ExperienceApplyResult:
    operation_id: str
    profile: ExperienceProfile
    applied_effects: tuple[str, ...]
    skipped_effects: tuple[str, ...]
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "operationId": self.operation_id,
            "profile": self.profile.to_dict(),
            "appliedEffects": list(self.applied_effects),
            "skippedEffects": list(self.skipped_effects),
            "status": self.status,
        }


@dataclass
class DesktopConflictPlan:
    plan_id: str
    confirm_token: str
    action: DesktopConflictAction
    created_at: str
    expires_at: str
    status: str = "pending"
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "planId": self.plan_id,
            "confirmToken": self.confirm_token,
            "action": self.action.to_dict(),
            "createdAt": self.created_at,
            "expiresAt": self.expires_at,
            "status": self.status,
            "rollbackGuarantee": "G-STATE",
        }

    @staticmethod
    def from_dict(value: dict[str, Any]) -> DesktopConflictPlan:
        action = value.get("action")
        if not isinstance(action, dict):
            raise ValueError("ação de remediação ausente")
        text_fields = ("planId", "confirmToken", "createdAt", "expiresAt", "status")
        if any(not isinstance(value.get(field), str) or not value[field] for field in text_fields):
            raise ValueError("metadados do plano de conflito inválidos")
        if value["status"] not in {"pending", "applied", "aborted"}:
            raise ValueError("status do plano de conflito inválido")
        schema_version = value.get("schemaVersion", 1)
        if not isinstance(schema_version, int) or schema_version != 1:
            raise ValueError("schemaVersion do plano de conflito inválido")
        return DesktopConflictPlan(
            plan_id=value["planId"],
            confirm_token=value["confirmToken"],
            action=DesktopConflictAction.from_dict(action),
            created_at=value["createdAt"],
            expires_at=value["expiresAt"],
            status=value["status"],
            schema_version=schema_version,
        )


class ExperienceCoordinator:
    """Planeja e coordena efeitos com snapshot persistente e rollback."""

    def __init__(
        self,
        context: DesktopContextPort,
        effects: tuple[DesktopEffectPort, ...],
        store: StateStore,
        conflict_resolver: DesktopConflictResolverPort | None = None,
    ) -> None:
        self._context = context
        self._effects = effects
        self._store = store
        self._conflict_resolver = conflict_resolver

    def close(self) -> None:
        self._store.close()

    @property
    def store_path(self) -> Path:
        """Return the state path used to create request-local coordinators."""
        return self._store.path

    def for_store(self, store: StateStore) -> ExperienceCoordinator:
        """Clone the coordinator ports while isolating the SQLite connection."""
        return ExperienceCoordinator(
            self._context,
            self._effects,
            store,
            self._conflict_resolver,
        )

    def __enter__(self) -> ExperienceCoordinator:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def status(self) -> dict[str, Any]:
        context = self._context.snapshot()
        conflict_actions = self._conflict_actions(context)
        override = self._load_payload(_OVERRIDE_ID)
        requested = override.get("requestedProfile") if override else None
        recommended = automatic_profile(context)
        desired = self._resolve_profile(requested or "auto", context)
        current = self._load_payload(_CURRENT_ID)
        recovery = self._load_payload(_RECOVERY_ID)
        recovery_required = bool(recovery and recovery.get("state") == "applying")
        applied = self._applied_profile_id(current)
        observed, observation = self._observe_profile(context)
        if (
            observed is None
            and applied is not None
            and applied in observation["ambiguousCandidates"]
        ):
            # Perfis podem ser observacionalmente idênticos (ex.: docked e safe
            # com dock: mesmo scale interno, painéis visíveis). Quando TODOS os
            # candidatos verificaram consistentes com o estado vivo e o perfil
            # aplicado é um deles, a observação não falsifica a aplicação — o
            # aplicado permanece como observado, com a resolução registrada.
            observed = applied
            observation["resolvedBy"] = "applied-profile"
        reasons: list[str] = []

        applied_fingerprint = current.get("contextFingerprint") if current else None
        context_stale = applied is not None and applied_fingerprint != context.fingerprint()
        desired_stale = applied is not None and desired != applied
        if context_stale:
            reasons.append("o contexto atual diverge do contexto da última aplicação")
        if desired_stale:
            reasons.append("o perfil desejado ainda não está aplicado")
        if observed is not None and applied is not None and observed != applied:
            reasons.append("o estado observado diverge do último perfil aplicado")
        if observation["errors"]:
            reasons.append("uma ou mais capacidades não puderam ser observadas")
        if observation["unavailableEffects"]:
            reasons.append("uma ou mais capacidades configuráveis estão indisponíveis")
        if observation["ambiguousCandidates"] and observed is None:
            reasons.append("o estado observado não identifica um único perfil")
        if context.conflicts:
            reasons.append("há conflito de ownership no Desktop")

        if recovery_required:
            truth_state = "recovery-required"
        elif context.conflicts:
            truth_state = "degraded"
        elif context_stale or desired_stale:
            truth_state = "stale"
        elif applied is None:
            truth_state = "unapplied"
        elif observed != applied or observation["errors"] or observation["unavailableEffects"]:
            truth_state = "degraded"
        else:
            truth_state = "ready"
        return {
            "context": context.to_dict(),
            "truthState": truth_state,
            "recommendedProfile": recommended,
            "desiredProfile": desired,
            "appliedProfile": applied,
            "observedProfile": observed,
            # Compatibilidade temporária: efetivo significa somente o que foi
            # observado, nunca mais uma intenção ainda não aplicada.
            "effectiveProfile": observed,
            "manualOverride": requested,
            "current": current,
            "observation": observation,
            "statusReasons": list(dict.fromkeys(reasons)),
            "recoveryRequired": recovery_required,
            "independentRuntime": True,
            "conflictActions": [action.to_dict() for action in conflict_actions],
        }

    def _applied_profile_id(self, current: dict[str, Any] | None) -> str | None:
        profile = current.get("profile") if current else None
        profile_id = profile.get("id") if isinstance(profile, dict) else None
        return profile_id if profile_id in PROFILE_IDS else None

    def _observe_profile(self, context: DesktopContext) -> tuple[str | None, dict[str, Any]]:
        """Infere o perfil vivo sem converter intenção ou persistência em observação."""
        errors: list[str] = []
        available_effects: list[DesktopEffectPort] = []
        unavailable: list[str] = []
        for effect in self._effects:
            try:
                if effect.available(context):
                    available_effects.append(effect)
                else:
                    unavailable.append(effect.name)
            except Exception as exc:
                unavailable.append(effect.name)
                errors.append(f"{effect.name}: {exc}")
        available = tuple(available_effects)
        candidates: list[str] = []
        if available:
            for profile_id in sorted(PROFILE_IDS):
                profile = profile_for(profile_id, context)
                matches = True
                for effect in available:
                    try:
                        if not effect.verify(profile, context):
                            matches = False
                            break
                    except Exception as exc:
                        matches = False
                        errors.append(f"{effect.name}: {exc}")
                        break
                if matches:
                    candidates.append(profile_id)
        observed = candidates[0] if len(candidates) == 1 else None
        return observed, {
            "checkedEffects": [effect.name for effect in available],
            "unavailableEffects": unavailable,
            "ambiguousCandidates": candidates if len(candidates) != 1 else [],
            "errors": list(dict.fromkeys(errors)),
        }

    def plan_conflict_release(self, action_id: str) -> DesktopConflictPlan:
        context = self._context.snapshot()
        action = next(
            (
                candidate
                for candidate in self._conflict_actions(context)
                if candidate.action_id == action_id
            ),
            None,
        )
        if action is None:
            raise SteamZeroError(
                "E-DESKTOP-OWNER-CONFLICT",
                detail="o conflito não possui remediação automática disponível",
            )
        now = _now()
        plan = DesktopConflictPlan(
            plan_id=ids.new_ulid(),
            confirm_token=secrets.token_urlsafe(24),
            action=action,
            created_at=now.isoformat(),
            expires_at=(now + _PLAN_TTL).isoformat(),
        )
        self._save_payload(
            _CONFLICT_PLAN_PREFIX + plan.plan_id,
            "desktop-plan",
            plan.to_dict(),
            owner="steamzero",
        )
        return plan

    def apply_conflict_release(self, plan_id: str, confirm_token: str) -> dict[str, Any]:
        plan = self._load_conflict_plan(plan_id)
        try:
            expired = _now() > datetime.fromisoformat(plan.expires_at)
        except ValueError as exc:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="expiresAt do plano inválido") from exc
        if plan.status != "pending" or expired:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano expirado ou já consumido")
        if not secrets.compare_digest(confirm_token, plan.confirm_token):
            raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="confirmToken incorreto")

        current = next(
            (
                candidate
                for candidate in self._conflict_actions(self._context.snapshot())
                if candidate.action_id == plan.action.action_id
            ),
            None,
        )
        if current != plan.action:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="o conflito Desktop mudou")
        if self._conflict_resolver is None:
            raise SteamZeroError(
                "E-DESKTOP-CONFLICT-RELEASE", detail="resolver de conflito indisponível"
            )

        with lock.ResourceLock("desktop:conflict", job_id=plan.plan_id):
            try:
                result = self._conflict_resolver.release(plan.action)
                remaining = {
                    action.action_id for action in self._conflict_actions(self._context.snapshot())
                }
                if plan.action.action_id in remaining:
                    raise RuntimeError("o watcher continua ativo após a remediação")
            except Exception as exc:
                plan.status = "aborted"
                self._save_conflict_plan(plan)
                if isinstance(exc, SteamZeroError):
                    raise
                raise SteamZeroError("E-DESKTOP-CONFLICT-RELEASE", detail=str(exc)) from exc

            plan.status = "applied"
            self._save_conflict_plan(plan)
            self._store.append_event(
                "desktop.conflict-released",
                entity="desktop:experience",
                payload={"actionId": plan.action.action_id, "unit": plan.action.unit},
            )
            return {"status": "ok", "action": plan.action.to_dict(), **result}

    def plan(self, requested_profile: str = "auto") -> ExperiencePlan:
        if requested_profile not in REQUESTED_PROFILES:
            raise SteamZeroError(
                "E-API-SCHEMA", detail=f"perfil solicitado inválido: {requested_profile}"
            )
        context = self._context.snapshot()
        target = profile_for(self._resolve_profile(requested_profile, context), context)
        now = _now()
        stability_blockers = self._stability_blockers(requested_profile, target, context, now)
        plan = ExperiencePlan(
            plan_id=ids.new_ulid(),
            confirm_token=secrets.token_urlsafe(24),
            requested_profile=requested_profile,
            target=target,
            context_fingerprint=context.fingerprint(),
            created_at=now.isoformat(),
            expires_at=(now + _PLAN_TTL).isoformat(),
            status="pending",
            blockers=tuple(dict.fromkeys((*context.conflicts, *stability_blockers))),
            changes=self._describe_changes(target),
        )
        self._save_payload(
            _PLAN_PREFIX + plan.plan_id, "desktop-plan", plan.to_dict(), owner="steamzero"
        )
        return plan

    def apply(self, plan_id: str, confirm_token: str) -> ExperienceApplyResult:
        plan = self._load_plan(plan_id)
        try:
            expired = _now() > datetime.fromisoformat(plan.expires_at)
        except ValueError as exc:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="expiresAt do plano inválido") from exc
        if plan.status != "pending" or expired:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="plano expirado ou já consumido")
        if not secrets.compare_digest(confirm_token, plan.confirm_token):
            raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="confirmToken incorreto")

        context = self._context.snapshot()
        if context.fingerprint() != plan.context_fingerprint:
            raise SteamZeroError("E-TX-STALE-PLAN", detail="contexto Desktop mudou")
        blockers = tuple(dict.fromkeys((*plan.blockers, *context.conflicts)))
        if blockers:
            raise SteamZeroError("E-DESKTOP-OWNER-CONFLICT", detail="; ".join(blockers))

        operation_id = ids.new_ulid()
        with lock.ResourceLock("desktop:experience", job_id=operation_id):
            return self._apply_locked(plan, context, operation_id)

    def recover(self) -> dict[str, Any]:
        recovery = self._load_payload(_RECOVERY_ID)
        if not recovery or recovery.get("state") != "applying":
            return {"status": "noop", "restoredEffects": []}
        snapshots = recovery.get("snapshots", {})
        restored, failures = self._restore_snapshots(snapshots, tuple(snapshots))
        recovery["state"] = "rolled-back" if not failures else "rollback-failed"
        recovery["restoreFailures"] = failures
        self._save_payload(_RECOVERY_ID, "desktop-recovery", recovery, owner="steamzero")
        if failures:
            raise SteamZeroError("E-DESKTOP-RECOVERY", detail="; ".join(failures))
        return {"status": "rolled-back", "restoredEffects": restored}

    def reset(self, plan_id: str, confirm_token: str) -> ExperienceApplyResult:
        """Aplica exclusivamente um plano de modo seguro previamente revisado."""
        plan = self._load_plan(plan_id)
        if plan.target.profile_id != PROFILE_SAFE:
            raise SteamZeroError(
                "E-API-SCHEMA", detail="reset exige um plano criado com --profile safe"
            )
        return self.apply(plan_id, confirm_token)

    def _apply_locked(
        self, plan: ExperiencePlan, context: DesktopContext, operation_id: str
    ) -> ExperienceApplyResult:
        available = tuple(effect for effect in self._effects if effect.available(context))
        skipped = tuple(effect.name for effect in self._effects if effect not in available)
        snapshots = {effect.name: effect.capture(context) for effect in available}
        recovery: dict[str, Any] = {
            "operationId": operation_id,
            "planId": plan.plan_id,
            "state": "applying",
            "snapshots": snapshots,
        }
        self._save_payload(_RECOVERY_ID, "desktop-recovery", recovery, owner="steamzero")

        applied: list[str] = []
        try:
            for effect in available:
                effect.apply(plan.target, context)
                applied.append(effect.name)
                if not effect.verify(plan.target, context):
                    raise SteamZeroError(
                        "E-DESKTOP-VERIFY", detail=f"efeito não confirmado: {effect.name}"
                    )
        except Exception as exc:
            _, failures = self._restore_snapshots(snapshots, tuple(applied))
            recovery["state"] = "rolled-back" if not failures else "rollback-failed"
            recovery["restoreFailures"] = failures
            self._save_payload(_RECOVERY_ID, "desktop-recovery", recovery, owner="steamzero")
            plan.status = "aborted"
            self._save_payload(
                _PLAN_PREFIX + plan.plan_id, "desktop-plan", plan.to_dict(), owner="steamzero"
            )
            if failures:
                raise SteamZeroError("E-DESKTOP-RECOVERY", detail="; ".join(failures)) from exc
            if isinstance(exc, SteamZeroError):
                raise
            raise SteamZeroError("E-DESKTOP-VERIFY", detail=str(exc)) from exc

        plan.status = "applied"
        recovery["state"] = "committed"
        self._save_payload(_RECOVERY_ID, "desktop-recovery", recovery, owner="steamzero")
        self._save_payload(
            _PLAN_PREFIX + plan.plan_id, "desktop-plan", plan.to_dict(), owner="steamzero"
        )
        self._save_payload(
            _CURRENT_ID,
            "desktop-current",
            {
                "operationId": operation_id,
                "profile": plan.target.to_dict(),
                "contextFingerprint": context.fingerprint(),
                "ownership": OwnershipLease(
                    resource="desktop-input",
                    provider=plan.target.preferred_input_owner,
                    holder="steamzero",
                    context_fingerprint=context.fingerprint(),
                ).to_dict(),
            },
            owner="steamzero",
        )
        override = None if plan.requested_profile == "auto" else plan.requested_profile
        self._save_payload(
            _OVERRIDE_ID,
            "desktop-override",
            {"requestedProfile": override},
            owner="steamzero",
        )
        self._store.append_event(
            "desktop.profile-applied",
            entity="desktop:experience",
            payload={"profile": plan.target.profile_id, "operationId": operation_id},
        )
        result_status = "ok" if not skipped else "degraded"
        return ExperienceApplyResult(
            operation_id=operation_id,
            profile=plan.target,
            applied_effects=tuple(applied),
            skipped_effects=skipped,
            status=result_status,
        )

    def _restore_snapshots(
        self, snapshots: dict[str, Any], names: tuple[str, ...]
    ) -> tuple[list[str], list[str]]:
        effects = {effect.name: effect for effect in self._effects}
        restored: list[str] = []
        failures: list[str] = []
        for name in reversed(names):
            effect = effects.get(name)
            if effect is None:
                failures.append(f"effect ausente na recuperação: {name}")
                continue
            snapshot = snapshots.get(name)
            if not isinstance(snapshot, dict):
                failures.append(f"snapshot inválido: {name}")
                continue
            try:
                effect.restore(snapshot)
                restored.append(name)
            except Exception as exc:  # cada efeito deve ter chance de restaurar
                failures.append(f"{name}: {exc}")
        return restored, failures

    def _resolve_profile(self, requested: str, context: DesktopContext) -> str:
        if requested == "auto":
            return automatic_profile(context)
        return {"handheld": PROFILE_HANDHELD, "dock": PROFILE_DOCKED, "safe": PROFILE_SAFE}[
            requested
        ]

    def _describe_changes(self, target: ExperienceProfile) -> tuple[str, ...]:
        return (
            f"perfil={target.profile_id}",
            f"escala={target.scale}",
            f"touch={'on' if target.touch_mode else 'off'}",
            f"janelas-maximizadas={'on' if target.maximize_windows else 'off'}",
            f"painel-auto-ocultar={'on' if target.panel_auto_hide else 'off'}",
            f"input-owner={target.preferred_input_owner}",
        )

    def _stability_blockers(
        self,
        requested: str,
        target: ExperienceProfile,
        context: DesktopContext,
        now: datetime,
    ) -> tuple[str, ...]:
        """Exige 3 s apenas para uma transição automática já em operação."""
        if requested != "auto":
            return ()
        current = self._load_payload(_CURRENT_ID)
        current_profile = current.get("profile", {}) if current else {}
        if current_profile.get("id") in {None, target.profile_id}:
            return ()
        observation = self._load_payload(_OBSERVATION_ID)
        fingerprint = context.fingerprint()
        if (
            not observation
            or observation.get("fingerprint") != fingerprint
            or observation.get("targetProfile") != target.profile_id
        ):
            self._save_payload(
                _OBSERVATION_ID,
                "desktop-observation",
                {
                    "fingerprint": fingerprint,
                    "targetProfile": target.profile_id,
                    "firstSeenAt": now.isoformat(),
                },
                owner="steamzero",
            )
            return ("contexto automático ainda não estável por 3 segundos",)
        try:
            first_seen = datetime.fromisoformat(str(observation["firstSeenAt"]))
        except (KeyError, ValueError):
            self._save_payload(
                _OBSERVATION_ID,
                "desktop-observation",
                {
                    "fingerprint": fingerprint,
                    "targetProfile": target.profile_id,
                    "firstSeenAt": now.isoformat(),
                },
                owner="steamzero",
            )
            return ("contexto automático ainda não estável por 3 segundos",)
        if (now - first_seen).total_seconds() < 3.0:
            return ("contexto automático ainda não estável por 3 segundos",)
        return ()

    def _load_plan(self, plan_id: str) -> ExperiencePlan:
        payload = self._load_payload(_PLAN_PREFIX + plan_id)
        if payload is None:
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"plano não encontrado: {plan_id}")
        try:
            return ExperiencePlan.from_dict(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="payload do plano inválido") from exc

    def _load_conflict_plan(self, plan_id: str) -> DesktopConflictPlan:
        payload = self._load_payload(_CONFLICT_PLAN_PREFIX + plan_id)
        if payload is None:
            raise SteamZeroError("E-TX-STALE-PLAN", detail=f"plano não encontrado: {plan_id}")
        try:
            return DesktopConflictPlan.from_dict(payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise SteamZeroError("E-STATE-INTEGRITY", detail="plano de conflito inválido") from exc

    def _save_conflict_plan(self, plan: DesktopConflictPlan) -> None:
        self._save_payload(
            _CONFLICT_PLAN_PREFIX + plan.plan_id,
            "desktop-plan",
            plan.to_dict(),
            owner="steamzero",
        )

    def _conflict_actions(self, context: DesktopContext) -> tuple[DesktopConflictAction, ...]:
        if self._conflict_resolver is None:
            return ()
        return self._conflict_resolver.actions(context)

    def _load_payload(self, profile_id: str) -> dict[str, Any] | None:
        row = self._store.get_profile(profile_id)
        if row is None or not row.get("payload_json"):
            return None
        try:
            value = json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError) as exc:
            raise SteamZeroError(
                "E-STATE-INTEGRITY", detail=f"payload inválido no perfil {profile_id}"
            ) from exc
        if not isinstance(value, dict):
            raise SteamZeroError(
                "E-STATE-INTEGRITY", detail=f"payload não-objeto no perfil {profile_id}"
            )
        loaded: dict[str, Any] = value
        return loaded

    def _save_payload(
        self, profile_id: str, kind: str, payload: dict[str, Any], *, owner: str
    ) -> None:
        self._store.save_profile(
            {
                "id": profile_id,
                "scope": "desktop-experience",
                "kind": kind,
                "payload_json": json.dumps(payload, sort_keys=True, ensure_ascii=False),
                "priority": 0,
                "profile_owner": owner,
            }
        )
