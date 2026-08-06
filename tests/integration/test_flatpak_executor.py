# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""M10: lifecycle Flatpak pinado, rollback e recovery pós-crash."""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from types import TracebackType

import pytest

from steamzero.adapters import flatpak as flatpak_module
from steamzero.adapters.flatpak import FlatpakExecutor, FlatpakState
from steamzero.adapters.registry import AdapterRegistry, load_manifest
from steamzero.api import contracts
from steamzero.core import fs, paths, state
from steamzero.core.errors import SteamZeroError

TARGET = "a" * 64
PREVIOUS = "b" * 64
REF = "org.example.Emulator"


class SimulatedPowerLoss(BaseException):
    pass


class FakeFlatpak:
    def __init__(self, initial: FlatpakState | None = None) -> None:
        self.current = initial or FlatpakState(False, REF)
        self.calls: list[tuple[object, ...]] = []
        self.available = {TARGET, PREVIOUS}
        self.smoke_error: Exception | BaseException | None = None
        self.rollback_error = False
        self.power_loss_on_rollback = False

    def status(self, ref: str) -> FlatpakState:
        assert ref == REF
        return self.current

    def resolve(self, remote: str, ref: str, commit: str) -> str:
        self.calls.append(("resolve", remote, ref, commit))
        if commit not in self.available:
            raise SteamZeroError("E-SUPPLY-UPSTREAM-GONE")
        return commit

    def install(self, remote: str, ref: str) -> None:
        self.calls.append(("install", remote, ref))
        self.current = FlatpakState(True, ref, remote, "f" * 64)

    def deploy(self, ref: str, commit: str) -> None:
        self.calls.append(("deploy", ref, commit))
        if self.rollback_error and commit == PREVIOUS:
            raise SteamZeroError("E-COMPONENT-DEGRADED", detail="rollback indisponível")
        origin = self.current.origin or "flathub"
        self.current = FlatpakState(True, ref, origin, commit)
        if self.power_loss_on_rollback and commit == PREVIOUS:
            raise SimulatedPowerLoss()

    def uninstall(self, ref: str) -> None:
        self.calls.append(("uninstall", ref))
        if self.rollback_error:
            raise SteamZeroError("E-COMPONENT-DEGRADED", detail="uninstall falhou")
        self.current = FlatpakState(False, ref)

    def smoke(self, ref: str, arguments: Sequence[str]) -> None:
        self.calls.append(("smoke", ref, *arguments))
        if self.smoke_error is not None:
            raise self.smoke_error


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[state.StateStore]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    fs.ensure_state_layout()
    opened = state.open_state()
    yield opened
    opened.close()


def manifest(
    *, end_of_life: bool = False, capabilities: list[str] | None = None
) -> dict[str, object]:
    source: dict[str, object] = {
        "type": "flatpak",
        "version": TARGET,
        "priority": 1,
        "ref": REF,
        "remote": "flathub",
    }
    if end_of_life:
        source["endOfLife"] = True
    return {
        "schemaVersion": 1,
        "id": "demo-flatpak",
        "kind": "emulator",
        "platforms": ["demo"],
        "capabilities": capabilities or ["detect", "status", "install", "update", "verify"],
        "sources": [source],
        "verify": {"smokeTest": ["--version"]},
        "license": "MIT",
        "upstream": "https://example.invalid/demo",
    }


def executor(
    store: state.StateStore, flatpak: FakeFlatpak, *, eol: bool = False
) -> FlatpakExecutor:
    item = load_manifest(manifest(end_of_life=eol))
    return FlatpakExecutor(store, AdapterRegistry([item]), flatpak)


def test_plan_is_pinned_schema_valid_and_read_only(store: state.StateStore, tmp_path: Path) -> None:
    flatpak = FakeFlatpak()
    service = executor(store, flatpak)

    plan = service.plan_install("demo-flatpak")

    contracts.validate(plan.to_dict(), "component-plan-v1.schema.json")
    assert plan.action == "install"
    assert plan.target_commit == TARGET
    assert plan.rollback_guarantee == "G-DEPLOYMENT"
    assert [call[0] for call in flatpak.calls] == ["resolve"]
    assert paths.plan_path(plan.plan_id).is_file()
    assert not (tmp_path / "data" / "steamzero" / "components").exists()


def test_stale_deployment_is_rejected_before_mutation(store: state.StateStore) -> None:
    flatpak = FakeFlatpak()
    service = executor(store, flatpak)
    plan = service.plan_install("demo-flatpak")
    flatpak.current = FlatpakState(True, REF, "flathub", PREVIOUS)

    with pytest.raises(SteamZeroError) as error:
        service.apply(plan.plan_id, plan.confirm_token)

    assert error.value.code == "E-TX-STALE-PLAN"
    assert not any(call[0] in {"install", "deploy", "uninstall"} for call in flatpak.calls)


def test_apply_revalidates_deployment_after_acquiring_lock(
    store: state.StateStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    flatpak = FakeFlatpak()
    service = executor(store, flatpak)
    plan = service.plan_install("demo-flatpak")

    class ChangeDeploymentOnEnter:
        def __enter__(self) -> ChangeDeploymentOnEnter:
            flatpak.current = FlatpakState(True, REF, "flathub", PREVIOUS)
            return self

        def __exit__(
            self,
            _exc_type: type[BaseException] | None,
            _exc: BaseException | None,
            _traceback: TracebackType | None,
        ) -> None:
            return None

    monkeypatch.setattr(
        flatpak_module, "ResourceLock", lambda *_args, **_kwargs: ChangeDeploymentOnEnter()
    )

    with pytest.raises(SteamZeroError) as error:
        service.apply(plan.plan_id, plan.confirm_token)

    assert error.value.code == "E-TX-STALE-PLAN"
    assert not any(call[0] in {"install", "deploy", "uninstall"} for call in flatpak.calls)


def test_apply_reloads_single_use_plan_after_acquiring_lock(
    store: state.StateStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    flatpak = FakeFlatpak()
    service = executor(store, flatpak)
    plan = service.plan_install("demo-flatpak")

    class ConsumePlanOnEnter:
        def __enter__(self) -> ConsumePlanOnEnter:
            plan_path = paths.plan_path(plan.plan_id)
            data = json.loads(plan_path.read_text(encoding="utf-8"))
            data["status"] = "applied"
            fs.write_atomic_text(plan_path, json.dumps(data, sort_keys=True))
            return self

        def __exit__(
            self,
            _exc_type: type[BaseException] | None,
            _exc: BaseException | None,
            _traceback: TracebackType | None,
        ) -> None:
            return None

    monkeypatch.setattr(
        flatpak_module, "ResourceLock", lambda *_args, **_kwargs: ConsumePlanOnEnter()
    )

    with pytest.raises(SteamZeroError) as error:
        service.apply(plan.plan_id, plan.confirm_token)

    assert error.value.code == "E-TX-STALE-PLAN"
    assert not any(call[0] in {"install", "deploy", "uninstall"} for call in flatpak.calls)


def test_install_apply_and_manual_rollback_preserve_app_data_scope(
    store: state.StateStore,
) -> None:
    flatpak = FakeFlatpak()
    service = executor(store, flatpak)
    plan = service.plan_install("demo-flatpak")

    applied = service.apply(plan.plan_id, plan.confirm_token)

    assert applied.status == "ok"
    assert flatpak.current == FlatpakState(True, REF, "flathub", TARGET)
    assert store.get_component("demo-flatpak")["version"] == TARGET  # type: ignore[index]
    assert ("smoke", REF, "--version") in flatpak.calls

    rolled_back = service.rollback(applied.operation_id)
    assert rolled_back.status == "rolled-back"
    assert flatpak.current == FlatpakState(False, REF)
    assert store.get_component("demo-flatpak")["state"] == "missing"  # type: ignore[index]
    assert ("uninstall", REF) in flatpak.calls


@pytest.mark.rt
def test_update_and_rollback_restore_exact_previous_commit(store: state.StateStore) -> None:
    before = FlatpakState(True, REF, "flathub", PREVIOUS)
    flatpak = FakeFlatpak(before)
    service = executor(store, flatpak)
    plan = service.plan_install("demo-flatpak")

    assert plan.action == "update"
    assert ("resolve", "flathub", REF, PREVIOUS) in flatpak.calls
    applied = service.apply(plan.plan_id, plan.confirm_token)
    assert flatpak.current.commit == TARGET

    service.rollback(applied.operation_id)
    assert flatpak.current == before


@pytest.mark.rt
def test_manual_rollback_revalidates_after_acquiring_lock(
    store: state.StateStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = FlatpakState(True, REF, "flathub", PREVIOUS)
    flatpak = FakeFlatpak(before)
    service = executor(store, flatpak)
    plan = service.plan_install("demo-flatpak")
    applied = service.apply(plan.plan_id, plan.confirm_token)
    external = FlatpakState(True, REF, "flathub", "c" * 64)

    class ChangeDeploymentOnEnter:
        def __enter__(self) -> ChangeDeploymentOnEnter:
            flatpak.current = external
            return self

        def __exit__(
            self,
            _exc_type: type[BaseException] | None,
            _exc: BaseException | None,
            _traceback: TracebackType | None,
        ) -> None:
            return None

    monkeypatch.setattr(
        flatpak_module, "ResourceLock", lambda *_args, **_kwargs: ChangeDeploymentOnEnter()
    )

    with pytest.raises(SteamZeroError) as error:
        service.rollback(applied.operation_id)

    assert error.value.code == "E-TX-STALE-PLAN"
    assert flatpak.current == external


@pytest.mark.rt
def test_smoke_failure_rolls_back_automatically(store: state.StateStore) -> None:
    before = FlatpakState(True, REF, "flathub", PREVIOUS)
    flatpak = FakeFlatpak(before)
    flatpak.smoke_error = RuntimeError("não iniciou")
    service = executor(store, flatpak)
    plan = service.plan_install("demo-flatpak")

    with pytest.raises(SteamZeroError) as error:
        service.apply(plan.plan_id, plan.confirm_token)

    assert error.value.code == "E-COMPONENT-UPDATE-ROLLEDBACK"
    assert error.value.operation_id is not None
    assert flatpak.current == before


@pytest.mark.fi
@pytest.mark.rt
def test_power_loss_after_deploy_is_recovered_to_snapshot(store: state.StateStore) -> None:
    before = FlatpakState(True, REF, "flathub", PREVIOUS)
    flatpak = FakeFlatpak(before)
    flatpak.smoke_error = SimulatedPowerLoss()
    service = executor(store, flatpak)
    plan = service.plan_install("demo-flatpak")

    with pytest.raises(SimulatedPowerLoss):
        service.apply(plan.plan_id, plan.confirm_token)
    assert flatpak.current.commit == TARGET

    flatpak.smoke_error = None
    recovered = executor(store, flatpak).recover()
    assert len(recovered) == 1
    assert recovered[0].status == "rolled-back"
    assert flatpak.current == before
    assert executor(store, flatpak).recover() == []


@pytest.mark.fi
@pytest.mark.rt
def test_power_loss_during_manual_rollback_is_resumed(store: state.StateStore) -> None:
    before = FlatpakState(True, REF, "flathub", PREVIOUS)
    flatpak = FakeFlatpak(before)
    service = executor(store, flatpak)
    plan = service.plan_install("demo-flatpak")
    applied = service.apply(plan.plan_id, plan.confirm_token)
    flatpak.power_loss_on_rollback = True

    with pytest.raises(SimulatedPowerLoss):
        service.rollback(applied.operation_id)

    flatpak.power_loss_on_rollback = False
    recovered = service.recover()
    assert recovered[0].operation_id == applied.operation_id
    assert flatpak.current == before


@pytest.mark.fi
def test_failed_rollback_remains_recoverable(store: state.StateStore) -> None:
    before = FlatpakState(True, REF, "flathub", PREVIOUS)
    flatpak = FakeFlatpak(before)
    flatpak.smoke_error = RuntimeError("smoke falhou")
    flatpak.rollback_error = True
    service = executor(store, flatpak)
    plan = service.plan_install("demo-flatpak")

    with pytest.raises(SteamZeroError) as error:
        service.apply(plan.plan_id, plan.confirm_token)
    assert error.value.code == "E-TX-ROLLBACK-FAILED"

    flatpak.smoke_error = None
    flatpak.rollback_error = False
    assert service.recover()[0].status == "rolled-back"
    assert flatpak.current == before


def test_eol_source_is_blocked_before_remote_or_mutation(store: state.StateStore) -> None:
    flatpak = FakeFlatpak()

    with pytest.raises(SteamZeroError) as error:
        executor(store, flatpak, eol=True).plan_install("demo-flatpak")

    assert error.value.code == "E-SUPPLY-UPSTREAM-GONE"
    assert flatpak.calls == []


def test_update_without_capability_is_blocked_before_mutation(store: state.StateStore) -> None:
    before = FlatpakState(True, REF, "flathub", PREVIOUS)
    flatpak = FakeFlatpak(before)
    item = load_manifest(manifest(capabilities=["detect", "status", "install", "verify"]))
    service = FlatpakExecutor(store, AdapterRegistry([item]), flatpak)

    with pytest.raises(SteamZeroError) as error:
        service.plan_install("demo-flatpak")

    assert error.value.code == "E-COMPONENT-DEGRADED"
    assert not any(call[0] in {"install", "deploy", "uninstall"} for call in flatpak.calls)


def _uninstall_executor(store: state.StateStore, flatpak: FakeFlatpak) -> FlatpakExecutor:
    item = load_manifest(
        manifest(capabilities=["detect", "status", "install", "update", "uninstall", "verify"])
    )
    return FlatpakExecutor(store, AdapterRegistry([item]), flatpak)


def test_uninstall_removes_deployment_and_preserves_application_data(
    store: state.StateStore,
) -> None:
    """Desinstalar não pode ser um caminho para perder save.

    O contrato é o argv: `flatpak uninstall` SEM `--delete-data` mantém
    `~/.var/app/<ref>`. O teste fixa a ausência da flag, porque é ela que
    separa "removi o programa" de "apaguei os saves do usuário".
    """
    flatpak = FakeFlatpak(FlatpakState(True, REF, "flathub", TARGET))
    executor = _uninstall_executor(store, flatpak)

    plan = executor.plan_uninstall("demo-flatpak")
    assert plan.action == "uninstall"
    assert "PRESERVADOS" in plan.preview

    result = executor.apply(plan.plan_id, plan.confirm_token)

    assert result.status == "ok"
    assert flatpak.current.installed is False
    assert ("uninstall", REF) in flatpak.calls
    assert not any("--delete-data" in str(call) for call in flatpak.calls)


def test_uninstall_is_refused_without_the_declared_capability(
    store: state.StateStore,
) -> None:
    flatpak = FakeFlatpak(FlatpakState(True, REF, "flathub", TARGET))
    executor_sem_cap = executor(store, flatpak)
    with pytest.raises(SteamZeroError) as error:
        executor_sem_cap.plan_uninstall("demo-flatpak")
    assert error.value.code == "E-COMPONENT-DEGRADED"
    assert "uninstall" in (error.value.detail or "")


def test_uninstall_is_refused_when_nothing_is_deployed(store: state.StateStore) -> None:
    flatpak = FakeFlatpak()
    with pytest.raises(SteamZeroError) as error:
        _uninstall_executor(store, flatpak).plan_uninstall("demo-flatpak")
    assert error.value.code == "E-COMPONENT-DEGRADED"
