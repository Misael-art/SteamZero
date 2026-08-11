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
from steamzero.adapters.flatpak import CommandResult, FlatpakCLI, FlatpakExecutor, FlatpakState
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

    def smoke(
        self,
        ref: str,
        arguments: Sequence[str],
        environment: Sequence[tuple[str, str]] = (),
        exit_codes: Sequence[int] = (0,),
        match: str | None = None,
    ) -> None:
        self.calls.append(("smoke", ref, arguments, environment, exit_codes, match))
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
    *,
    end_of_life: bool = False,
    capabilities: list[str] | None = None,
    verify_extra: dict[str, object] | None = None,
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
    verify: dict[str, object] = {"smokeTest": ["--version"]}
    if verify_extra:
        verify.update(verify_extra)
    return {
        "schemaVersion": 1,
        "id": "demo-flatpak",
        "kind": "emulator",
        "platforms": ["demo"],
        "capabilities": capabilities or ["detect", "status", "install", "update", "verify"],
        "sources": [source],
        "verify": verify,
        "license": "MIT",
        "upstream": "https://example.invalid/demo",
    }


def executor(
    store: state.StateStore, flatpak: FakeFlatpak, *, eol: bool = False
) -> FlatpakExecutor:
    item = load_manifest(manifest(end_of_life=eol))
    return FlatpakExecutor(store, AdapterRegistry([item]), flatpak)


def test_cli_smoke_sets_manifest_environment_before_the_flatpak_ref() -> None:
    calls: list[tuple[tuple[str, ...], float]] = []

    def runner(argv: Sequence[str], timeout: float) -> CommandResult:
        calls.append((tuple(argv), timeout))
        return CommandResult(0, "", "")

    FlatpakCLI(runner=runner).smoke(
        REF,
        ("-nogui", "--version"),
        (("QT_QPA_PLATFORM", "offscreen"), ("QT_QPA_PLATFORMTHEME", "none")),
    )

    assert calls == [
        (
            (
                "flatpak",
                "run",
                "--user",
                "--die-with-parent",
                "--env=QT_QPA_PLATFORM=offscreen",
                "--env=QT_QPA_PLATFORMTHEME=none",
                REF,
                "-nogui",
                "--version",
            ),
            flatpak_module._SMOKE_TIMEOUT,
        )
    ]


def test_cli_smoke_failure_preserves_full_payload() -> None:
    def runner(argv: Sequence[str], timeout: float) -> CommandResult:
        assert timeout == flatpak_module._SMOKE_TIMEOUT
        return CommandResult(1, "linha de stdout\n", "linha de stderr\n")

    with pytest.raises(SteamZeroError) as error:
        FlatpakCLI(runner=runner).smoke(
            REF,
            ("-nogui", "--version"),
            (("QT_QPA_PLATFORM", "offscreen"), ("QT_QPA_PLATFORMTHEME", "none")),
        )

    assert error.value.code == "E-COMPONENT-DEGRADED"
    detail = error.value.detail
    assert detail is not None
    assert "falha ao smoke test de org.example.Emulator" in detail
    assert "comando: flatpak run --user --die-with-parent" in detail
    assert "--env=QT_QPA_PLATFORM=offscreen" in detail
    assert "--env=QT_QPA_PLATFORMTHEME=none" in detail
    assert "org.example.Emulator -nogui --version" in detail
    assert "retorno: 1" in detail
    assert "linha de stdout" in detail
    assert "linha de stderr" in detail


def test_cli_smoke_failure_truncation_keeps_tail() -> None:
    huge_stderr = "".join(f"linha {i:04d}\n" for i in range(20_000))

    def runner(argv: Sequence[str], timeout: float) -> CommandResult:
        return CommandResult(1, "", huge_stderr)

    with pytest.raises(SteamZeroError) as error:
        FlatpakCLI(runner=runner).smoke(REF, ("--version",))

    detail = error.value.detail
    assert detail is not None
    assert "saída truncada" in detail
    assert "limite" in detail
    assert len(detail) <= flatpak_module._SMOKE_PAYLOAD_LIMIT
    assert detail.endswith("linha 19999\n")


def test_cli_smoke_accepts_allowlisted_exit_code_with_output_match() -> None:
    def runner(argv: Sequence[str], timeout: float) -> CommandResult:
        return CommandResult(1, "", "PCSX2 v2.6.3\nhttps://pcsx2.net/\n")

    FlatpakCLI(runner=runner).smoke(REF, ("-version",), (), (1,), "^PCSX2 v")


def test_cli_smoke_rejects_allowed_exit_code_when_output_misses_pattern() -> None:
    def runner(argv: Sequence[str], timeout: float) -> CommandResult:
        return CommandResult(1, "", "boot falhou\n")

    with pytest.raises(SteamZeroError) as error:
        FlatpakCLI(runner=runner).smoke(REF, ("-version",), (), (1,), "^PCSX2 v")

    assert error.value.code == "E-COMPONENT-DEGRADED"
    detail = error.value.detail
    assert detail is not None
    assert "retorno: 1" in detail
    assert "saída não corresponde ao padrão" in detail
    assert "boot falhou" in detail


def test_cli_smoke_rejects_exit_code_outside_allowlist_even_with_match() -> None:
    def runner(argv: Sequence[str], timeout: float) -> CommandResult:
        return CommandResult(2, "", "PCSX2 v2.6.3\n")

    with pytest.raises(SteamZeroError) as error:
        FlatpakCLI(runner=runner).smoke(REF, ("-version",), (), (1,), "^PCSX2 v")

    assert error.value.code == "E-COMPONENT-DEGRADED"
    assert error.value.detail is not None
    assert "retorno: 2" in error.value.detail


def test_executor_forwards_smoke_allowlist_and_pattern(store: state.StateStore) -> None:
    item = load_manifest(manifest(verify_extra={"smokeExitCodes": [1], "smokeMatch": "^PCSX2 v"}))
    flatpak = FakeFlatpak(initial=FlatpakState(True, REF, "flathub", PREVIOUS))
    service = FlatpakExecutor(store, AdapterRegistry([item]), flatpak)
    plan = service.plan_install("demo-flatpak")
    assert plan.action == "update"

    applied = service.apply(plan.plan_id, plan.confirm_token)

    assert applied.status == "ok"
    assert ("smoke", REF, ("--version",), (), (1,), "^PCSX2 v") in flatpak.calls


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
    assert ("smoke", REF, ("--version",), (), (0,), None) in flatpak.calls

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
