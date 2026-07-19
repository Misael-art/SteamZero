# SPDX-License-Identifier: GPL-3.0-or-later
"""Coordenador Desktop: confirmação, ownership, rollback e recovery."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from steamzero.api import contracts
from steamzero.adapters.desktop_kde import CommandResult
from steamzero.core.errors import SteamZeroError
from steamzero.core.state import StateStore
from steamzero.domain import desktop as desktop_domain
from steamzero.domain.desktop import (
    DesktopConflictAction,
    DesktopContext,
    DisplayState,
    ExperienceCoordinator,
    ExperienceProfile,
)


class FakeContext:
    def __init__(self, value: DesktopContext) -> None:
        self.value = value

    def snapshot(self) -> DesktopContext:
        return self.value


class FakeConflictResolver:
    def __init__(self, context: FakeContext) -> None:
        self.context = context
        self.releases = 0

    def actions(self, context: DesktopContext) -> tuple[DesktopConflictAction, ...]:
        if not context.conflicts:
            return ()
        return (
            DesktopConflictAction(
                action_id="release-test-watcher",
                unit="test-mode-watcher.service",
                scope="user",
                summary="Desativar watcher de teste",
                requires_privilege=False,
                commands=(
                    ("systemctl", "--user", "stop", "test-mode-watcher.service"),
                    ("systemctl", "--user", "disable", "test-mode-watcher.service"),
                ),
            ),
        )

    def release(self, action: DesktopConflictAction) -> dict[str, Any]:
        self.releases += 1
        self.context.value = DesktopContext(**{**self.context.value.__dict__, "conflicts": ()})
        return {"stopped": True, "disabled": True}


class PowerLoss(BaseException):
    pass


class FakeEffect:
    name = "fake-effect"

    def __init__(self, *, available: bool = True) -> None:
        self.is_available = available
        self.state = "original"
        self.verify_ok = True
        self.power_loss = False
        self.restore_fails = False

    def available(self, context: DesktopContext) -> bool:
        return self.is_available

    def capture(self, context: DesktopContext) -> dict[str, Any]:
        return {"state": self.state}

    def apply(self, profile: ExperienceProfile, context: DesktopContext) -> None:
        self.state = profile.profile_id
        if self.power_loss:
            raise PowerLoss

    def verify(self, profile: ExperienceProfile, context: DesktopContext) -> bool:
        return self.verify_ok and self.state == profile.profile_id

    def restore(self, snapshot: dict[str, Any]) -> None:
        if self.restore_fails:
            raise RuntimeError("restore indisponível")
        self.state = str(snapshot["state"])


@pytest.fixture
def deck_context() -> DesktopContext:
    return DesktopContext(
        device_kind="deck-lcd",
        session_type="wayland",
        displays=(DisplayState("eDP-1", True, True, 800, 1280, 60.0, 1.35),),
        physical_dock=False,
        external_keyboard=True,
        external_mouse=True,
        capabilities=frozenset({"kwin-virtual-keyboard"}),
    )


@pytest.fixture
def store(tmp_path: Path) -> StateStore:
    value = StateStore(tmp_path / "state.db")
    value.migrate()
    yield value
    value.close()


def test_plan_schema_and_confirmed_apply(deck_context: DesktopContext, store: StateStore) -> None:
    effect = FakeEffect()
    coordinator = ExperienceCoordinator(FakeContext(deck_context), (effect,), store)
    plan = coordinator.plan("auto")
    contracts.validate(plan.to_dict(), "desktop-plan-v1.schema.json")

    result = coordinator.apply(plan.plan_id, plan.confirm_token)
    assert result.status == "ok"
    assert result.profile.profile_id == "handheld-desktop"
    assert effect.state == "handheld-desktop"
    status = coordinator.status()
    contracts.validate(status, "desktop-status-v1.schema.json")
    assert status["independentRuntime"] is True
    assert status["truthState"] == "ready"
    assert status["recommendedProfile"] == "handheld-desktop"
    assert status["desiredProfile"] == "handheld-desktop"
    assert status["appliedProfile"] == "handheld-desktop"
    assert status["observedProfile"] == "handheld-desktop"


def test_real_dock_to_undock_is_reported_as_stale(
    deck_context: DesktopContext, store: StateStore
) -> None:
    docked = DesktopContext(
        **{
            **deck_context.__dict__,
            "physical_dock": True,
            "displays": (
                *deck_context.displays,
                DisplayState("DP-1", True, False, 1920, 1080, 60.0, 1.0),
            ),
        }
    )
    context = FakeContext(docked)
    effect = FakeEffect()
    coordinator = ExperienceCoordinator(context, (effect,), store)
    plan = coordinator.plan("auto")
    coordinator.apply(plan.plan_id, plan.confirm_token)

    context.value = deck_context
    status = coordinator.status()

    contracts.validate(status, "desktop-status-v1.schema.json")
    assert status["truthState"] == "stale"
    assert status["recommendedProfile"] == "handheld-desktop"
    assert status["desiredProfile"] == "handheld-desktop"
    assert status["appliedProfile"] == "docked-desktop"
    assert status["observedProfile"] == "docked-desktop"
    assert status["effectiveProfile"] == "docked-desktop"
    assert "o contexto atual diverge" in " ".join(status["statusReasons"])


def test_observed_drift_from_applied_profile_is_degraded(
    deck_context: DesktopContext, store: StateStore
) -> None:
    effect = FakeEffect()
    coordinator = ExperienceCoordinator(FakeContext(deck_context), (effect,), store)
    plan = coordinator.plan("auto")
    coordinator.apply(plan.plan_id, plan.confirm_token)

    effect.state = "safe"
    status = coordinator.status()

    assert status["truthState"] == "degraded"
    assert status["desiredProfile"] == "handheld-desktop"
    assert status["appliedProfile"] == "handheld-desktop"
    assert status["observedProfile"] == "safe"
    assert "estado observado diverge" in " ".join(status["statusReasons"])


def test_wrong_confirmation_does_not_apply(deck_context: DesktopContext, store: StateStore) -> None:
    effect = FakeEffect()
    coordinator = ExperienceCoordinator(FakeContext(deck_context), (effect,), store)
    plan = coordinator.plan()
    with pytest.raises(SteamZeroError, match="E-TX-CONFIRM-REQUIRED"):
        coordinator.apply(plan.plan_id, "errado")
    assert effect.state == "original"


def test_context_drift_makes_plan_stale(deck_context: DesktopContext, store: StateStore) -> None:
    context_port = FakeContext(deck_context)
    coordinator = ExperienceCoordinator(context_port, (FakeEffect(),), store)
    plan = coordinator.plan()
    context_port.value = DesktopContext(**{**deck_context.__dict__, "physical_dock": True})
    with pytest.raises(SteamZeroError, match="E-TX-STALE-PLAN"):
        coordinator.apply(plan.plan_id, plan.confirm_token)


@pytest.mark.fi
def test_generic_owner_conflict_blocks_apply(
    deck_context: DesktopContext, store: StateStore
) -> None:
    conflicted = DesktopContext(**{**deck_context.__dict__, "conflicts": ("display instável",)})
    coordinator = ExperienceCoordinator(FakeContext(conflicted), (FakeEffect(),), store)
    plan = coordinator.plan()
    with pytest.raises(SteamZeroError, match="E-DESKTOP-OWNER-CONFLICT"):
        coordinator.apply(plan.plan_id, plan.confirm_token)


def test_conflict_release_requires_plan_confirmation_and_clears_blocker(
    deck_context: DesktopContext, store: StateStore
) -> None:
    context = FakeContext(
        DesktopContext(
            **{
                **deck_context.__dict__,
                "conflicts": ("controlador externo ativo: test-mode-watcher.service",),
            }
        )
    )
    resolver = FakeConflictResolver(context)
    coordinator = ExperienceCoordinator(context, (), store, resolver)

    status = coordinator.status()
    assert status["conflictActions"][0]["scope"] == "user"
    plan = coordinator.plan_conflict_release("release-test-watcher")
    contracts.validate(plan.to_dict(), "desktop-conflict-plan-v1.schema.json")

    with pytest.raises(SteamZeroError, match="E-TX-CONFIRM-REQUIRED"):
        coordinator.apply_conflict_release(plan.plan_id, "token-incorreto")
    assert resolver.releases == 0

    result = coordinator.apply_conflict_release(plan.plan_id, plan.confirm_token)
    assert result["status"] == "ok"
    assert resolver.releases == 1
    assert coordinator.status()["context"]["conflicts"] == []
    assert coordinator.status()["conflictActions"] == []


@pytest.mark.fi
def test_verify_failure_rolls_back(deck_context: DesktopContext, store: StateStore) -> None:
    effect = FakeEffect()
    effect.verify_ok = False
    coordinator = ExperienceCoordinator(FakeContext(deck_context), (effect,), store)
    plan = coordinator.plan()
    with pytest.raises(SteamZeroError, match="E-DESKTOP-VERIFY"):
        coordinator.apply(plan.plan_id, plan.confirm_token)
    assert effect.state == "original"


@pytest.mark.fi
def test_power_loss_leaves_recoverable_snapshot(
    deck_context: DesktopContext, store: StateStore
) -> None:
    effect = FakeEffect()
    effect.power_loss = True
    coordinator = ExperienceCoordinator(FakeContext(deck_context), (effect,), store)
    plan = coordinator.plan()
    with pytest.raises(PowerLoss):
        coordinator.apply(plan.plan_id, plan.confirm_token)
    assert coordinator.status()["recoveryRequired"] is True

    effect.power_loss = False
    recovered = coordinator.recover()
    assert recovered["status"] == "rolled-back"
    assert effect.state == "original"


@pytest.mark.fi
def test_all_optional_effects_missing_is_degraded(
    deck_context: DesktopContext, store: StateStore
) -> None:
    coordinator = ExperienceCoordinator(
        FakeContext(deck_context), (FakeEffect(available=False),), store
    )
    plan = coordinator.plan("safe")
    result = coordinator.reset(plan.plan_id, plan.confirm_token)
    assert result.status == "degraded"
    assert result.skipped_effects == ("fake-effect",)


def test_reset_rejects_non_safe_plan(deck_context: DesktopContext, store: StateStore) -> None:
    coordinator = ExperienceCoordinator(FakeContext(deck_context), (), store)
    plan = coordinator.plan("handheld")
    with pytest.raises(SteamZeroError, match="E-API-SCHEMA"):
        coordinator.reset(plan.plan_id, plan.confirm_token)


def test_state_contains_only_native_profile_data(
    deck_context: DesktopContext, store: StateStore
) -> None:
    coordinator = ExperienceCoordinator(FakeContext(deck_context), (), store)
    plan = coordinator.plan()
    coordinator.apply(plan.plan_id, plan.confirm_token)
    exported = json.dumps(store.export_json(), sort_keys=True).lower()
    assert "/mnt/sdcard/projects/phasezero" not in exported
    assert "$xdg_state_home/phasezero" not in exported


def test_auto_transition_requires_three_seconds_stable(
    deck_context: DesktopContext,
    store: StateStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context_port = FakeContext(deck_context)
    coordinator = ExperienceCoordinator(context_port, (), store)
    initial = coordinator.plan("auto")
    coordinator.apply(initial.plan_id, initial.confirm_token)
    context_port.value = DesktopContext(
        **{
            **deck_context.__dict__,
            "displays": (
                *deck_context.displays,
                DisplayState("DP-1", True, False, 1920, 1080, 60.0, 1.0),
            ),
        }
    )
    first = coordinator.plan("auto")
    assert first.blockers == ("contexto automático ainda não estável por 3 segundos",)
    later = datetime.fromisoformat(first.created_at) + timedelta(seconds=4)
    monkeypatch.setattr(desktop_domain, "_now", lambda: later)
    second = coordinator.plan("auto")
    assert second.blockers == ()
    assert second.target.profile_id == "docked-desktop"


def test_corrupt_desktop_plan_reports_state_integrity(
    deck_context: DesktopContext, store: StateStore
) -> None:
    store.save_profile(
        {
            "id": "desktop-plan-corrupt",
            "scope": "desktop-experience",
            "kind": "desktop-plan",
            "payload_json": "{not-json",
            "priority": 0,
            "profile_owner": "steamzero",
        }
    )
    coordinator = ExperienceCoordinator(FakeContext(deck_context), (), store)
    with pytest.raises(SteamZeroError, match="E-STATE-INTEGRITY"):
        coordinator.apply("corrupt", "token")


def test_kde_shortcuts_snapshot_rollback(deck_context: DesktopContext, store: StateStore, tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []
    apps_dir = tmp_path / "applications"

    def runner(argv: Sequence[str], _timeout: float) -> CommandResult:
        calls.append(tuple(argv))
        if argv[0] == "kreadconfig6":
            return CommandResult(0, "")
        return CommandResult(0, "")

    from steamzero.adapters.desktop_kde import KDEShortcutsEffect

    effect = KDEShortcutsEffect(
        runner=runner,
        which=lambda command: command,
        applications_dir=apps_dir,
    )
    context = DesktopContext(
        **{
            **deck_context.__dict__,
            "capabilities": frozenset({"kde-config"}),
        }
    )
    coordinator = ExperienceCoordinator(FakeContext(context), (effect,), store)
    plan = coordinator.plan("handheld")
    with pytest.raises(SteamZeroError, match="E-DESKTOP-VERIFY"):
        coordinator.apply(plan.plan_id, plan.confirm_token)

    assert (
        "kwriteconfig6",
        "--file",
        "kglobalshortcutsrc",
        "--group",
        "kwin",
        "--key",
        "ExposeAll",
        "Meta+Ctrl+D,Meta+Ctrl+D,Exposição de todas as áreas de trabalho",
    ) in calls
    # Rollback automático removeu o .desktop criado durante apply.
    assert not (apps_dir / "steamzero-desktop-keyboard.desktop").exists()
