# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Aplicação de componente como job persistente e não bloqueante."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from steamzero.adapters import flatpak as flatpak_module
from steamzero.adapters.component_jobs import ComponentJobService
from steamzero.core import fs, net, state
from steamzero.core.errors import SteamZeroError
from steamzero.jobs.manager import JobManager


class BlockingLifecycle:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.apply_calls = 0
        self.store: state.StateStore | None = None
        self.plan_status = {"01M000000000000000000000AA": "pending"}
        self.retry_count = 0
        self.recover_as_applied = False

    def bind(self, store: state.StateStore) -> BlockingLifecycle:
        self.store = store
        return self

    def validate_apply(self, plan_id: str, confirm_token: str) -> dict[str, str]:
        assert plan_id == "01M000000000000000000000AA"
        assert confirm_token == "confirm-token"
        return {"adapterId": "demo-emulator", "action": "install", "executor": "engine"}

    def apply(self, plan_id: str, confirm_token: str) -> dict[str, str]:
        self.apply_calls += 1
        self.started.set()
        if not self.release.wait(timeout=5):
            raise RuntimeError("teste não liberou o lifecycle")
        assert self.store is not None
        self.store.save_operation("01M000000000000000000000BB", state="committed")
        self.plan_status[plan_id] = "applied"
        return {
            "status": "ok",
            "operationId": "01M000000000000000000000BB",
            "adapterId": "demo-emulator",
        }

    def _apply_validated(self, plan_id: str) -> dict[str, str]:
        return self.apply(plan_id, "confirm-token")

    def _abort_apply(self, plan_id: str) -> None:
        if self.plan_status.get(plan_id) == "pending":
            self.plan_status[plan_id] = "aborted"

    def _retry_apply(self, plan_id: str) -> dict[str, str]:
        self._abort_apply(plan_id)
        assert self.plan_status.get(plan_id) == "aborted"
        self.retry_count += 1
        replacement = f"01M000000000000000000000A{self.retry_count}"
        self.plan_status[replacement] = "pending"
        return {
            "planId": replacement,
            "adapterId": "demo-emulator",
            "action": "install",
            "executor": "engine",
        }

    def _apply_status(self, plan_id: str) -> str:
        return self.plan_status[plan_id]

    def recover(self) -> list[dict[str, object]]:
        if self.recover_as_applied:
            self.plan_status["01M000000000000000000000AA"] = "applied"
            return [{"status": "reconciled"}]
        return []


class RetryLifecycle(BlockingLifecycle):
    def __init__(self) -> None:
        super().__init__()
        self.release.set()

    def apply(self, plan_id: str, confirm_token: str) -> dict[str, str]:
        self.apply_calls += 1
        if self.apply_calls == 1:
            raise SteamZeroError("E-SUPPLY-OFFLINE", detail="rede indisponível")
        self.plan_status[plan_id] = "applied"
        return {"status": "ok", "operationId": "", "adapterId": "demo-emulator"}


class PausingResponse(net.FakeResponse):
    def __init__(self) -> None:
        super().__init__(
            b"abcdef",
            "https://downloads.example/artifact",
            headers={"Content-Length": "6"},
            chunk_size=2,
        )
        self.blocked = threading.Event()
        self.release = threading.Event()
        self.bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        if self.bytes_read:
            self.blocked.set()
            if not self.release.wait(timeout=5):
                raise RuntimeError("teste não liberou o segundo chunk")
        chunk = super().read(size)
        self.bytes_read += len(chunk)
        return chunk


class DownloadingLifecycle(BlockingLifecycle):
    def __init__(self, response: PausingResponse) -> None:
        super().__init__()
        self.response = response
        self.applied = False

    def apply(self, plan_id: str, confirm_token: str) -> dict[str, str]:
        self.apply_calls += 1
        self.started.set()
        net.fetch_bytes(
            "https://downloads.example/artifact",
            max_bytes=8,
            client=net.HttpClient(transport=net.FakeTransport([self.response])),
        )
        self.applied = True
        self.plan_status[plan_id] = "applied"
        assert self.store is not None
        self.store.save_operation("01M000000000000000000000BB", state="committed")
        self.plan_status[plan_id] = "applied"
        return {
            "status": "ok",
            "operationId": "01M000000000000000000000BB",
            "adapterId": "demo-emulator",
        }


class StagedFlatpakLifecycle(BlockingLifecycle):
    def apply(self, plan_id: str, confirm_token: str) -> dict[str, str]:
        self.apply_calls += 1
        flatpak_module.report_flatpak_stage("installing", current=1, total=5)
        self.started.set()
        if not self.release.wait(timeout=5):
            raise RuntimeError("teste não liberou o lifecycle Flatpak")
        assert self.store is not None
        self.store.save_operation("01M000000000000000000000BB", state="committed")
        return {
            "status": "ok",
            "operationId": "01M000000000000000000000BB",
            "adapterId": "demo-emulator",
        }


@pytest.fixture
def job_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    fs.ensure_state_layout()
    with state.open_state() as store:
        store.migrate()
    yield


def _wait_terminal(service: ComponentJobService, job_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = service.get(job_id)
        assert job is not None
        if job["rawState"] in {"completed", "cancelled", "rolled-back", "rollback-failed"}:
            return job
        time.sleep(0.01)
    raise AssertionError("job não terminalizou")


def _persist_component_job(raw_state: str = "queued") -> str:
    with state.open_state() as store:
        store.migrate()
        job = JobManager(store).create(
            "component.apply",
            params={
                "planId": "01M000000000000000000000AA",
                "confirmToken": "confirm-token",
                "adapterId": "demo-emulator",
                "action": "install",
                "executor": "engine",
            },
            priority="interactive",
            created_by="ui",
            constraints={"requiresNetwork": True},
        )
        if raw_state != "queued":
            job.state = raw_state
            store.save_job(job.to_row())
        return job.id


def test_start_returns_immediately_and_deduplicates_repeated_confirmation(job_env: None) -> None:
    lifecycle = BlockingLifecycle()
    service = ComponentJobService(lifecycle_factory=lifecycle.bind)

    first = service.start("01M000000000000000000000AA", "confirm-token")

    assert first["jobId"]
    assert first["state"] in {"queued", "running"}

    # Prova de não-bloqueio por causalidade, sem relógio de parede. `apply`
    # sinaliza `started` ao entrar e só retorna quando `release` for sinalizado,
    # o que este teste ainda não fez: se `start` tivesse esperado o lifecycle,
    # não teria retornado acima. O limiar anterior era `elapsed < 0.2` contra um
    # bloqueio de 5 s — 25x de folga — e mesmo assim reprovou o CI com 0,206 s,
    # porque media o agendamento do runner, não o comportamento do produto.
    assert lifecycle.started.wait(timeout=5)
    assert not lifecycle.release.is_set()

    with state.open_state() as store:
        persisted = JobManager(store).get(str(first["jobId"]))
    assert persisted is not None
    assert persisted.params == {
        "planId": "01M000000000000000000000AA",
        "adapterId": "demo-emulator",
        "action": "install",
        "executor": "engine",
    }

    observed = service.get(str(first["jobId"]))
    assert observed is not None
    assert len(observed["diagnostics"]) == 1
    diagnostic = observed["diagnostics"][0]
    assert diagnostic["kind"] == "component-diagnostic"
    assert diagnostic["adapterId"] == "demo-emulator"
    assert diagnostic["executor"] == "engine"
    assert diagnostic["network"]["phase"] == "not-observed"
    assert diagnostic["network"]["host"] is None
    assert diagnostic["network"]["dns"] == "not-observed"
    assert set(diagnostic["network"]["proxy"]) == {"configured", "schemes"}
    assert set(diagnostic["network"]["environment"]) == {"sandboxed", "variables"}

    repeated = service.start("01M000000000000000000000AA", "confirm-token")
    assert repeated["jobId"] == first["jobId"]
    assert lifecycle.apply_calls == 1

    lifecycle.release.set()
    completed = _wait_terminal(service, str(first["jobId"]))
    assert completed["state"] == "succeeded"
    assert completed["result"] == {
        "status": "ok",
        "operationId": "01M000000000000000000000BB",
        "adapterId": "demo-emulator",
    }
    assert completed["progress"] == {
        "stage": "verified",
        "current": 1,
        "total": 1,
        "unit": "steps",
        "currentItem": None,
    }


def test_invalid_confirmation_does_not_create_job(job_env: None) -> None:
    class RejectingLifecycle(BlockingLifecycle):
        def validate_apply(self, plan_id: str, confirm_token: str) -> dict[str, str]:
            raise SteamZeroError("E-TX-CONFIRM-REQUIRED", detail="token incorreto")

    service = ComponentJobService(lifecycle_factory=RejectingLifecycle().bind)

    with pytest.raises(SteamZeroError) as error:
        service.start("01M000000000000000000000AA", "wrong-token")

    assert error.value.code == "E-TX-CONFIRM-REQUIRED"
    assert service.list() == []


def test_failed_job_retries_as_a_new_auditable_job(job_env: None) -> None:
    lifecycle = RetryLifecycle()
    service = ComponentJobService(lifecycle_factory=lifecycle.bind)

    first = service.start("01M000000000000000000000AA", "confirm-token")
    failed = _wait_terminal(service, str(first["jobId"]))
    assert failed["rawState"] == "rolled-back"
    assert failed["errorCode"] == "E-SUPPLY-OFFLINE"
    assert failed["canRetry"] is True
    assert failed["planId"] == "01M000000000000000000000AA"
    assert lifecycle.plan_status[str(failed["planId"])] == "aborted"

    retried = service.retry(str(first["jobId"]))
    assert retried["jobId"] != first["jobId"]
    assert retried["planId"] != failed["planId"]
    assert retried["retryOfJobId"] == first["jobId"]
    assert lifecycle.plan_status[str(failed["planId"])] == "aborted"
    completed = _wait_terminal(service, str(retried["jobId"]))
    assert completed["state"] == "succeeded"
    assert lifecycle.plan_status[str(completed["planId"])] == "applied"
    assert lifecycle.apply_calls == 2


def test_download_persists_real_byte_progress_while_job_is_running(job_env: None) -> None:
    response = PausingResponse()
    lifecycle = DownloadingLifecycle(response)
    service = ComponentJobService(lifecycle_factory=lifecycle.bind)

    job = service.start("01M000000000000000000000AA", "confirm-token")
    assert response.blocked.wait(timeout=1)
    try:
        observed = service.get(str(job["jobId"]))
        assert observed is not None
        assert observed["progress"] == {
            "stage": "downloading",
            "current": 2,
            "total": 6,
            "unit": "bytes",
            "currentItem": "demo-emulator",
        }
    finally:
        response.release.set()
    completed = _wait_terminal(service, str(job["jobId"]))
    assert completed["state"] == "succeeded"
    network = [item["network"] for item in completed["diagnostics"]]
    assert [item["phase"] for item in network] == [
        "not-observed",
        "starting",
        "completed",
    ]
    assert network[-1]["host"] == "downloads.example"
    assert network[-1]["dns"] == "resolved"


def test_cancel_during_download_stops_before_apply_and_terminalizes(job_env: None) -> None:
    response = PausingResponse()
    lifecycle = DownloadingLifecycle(response)
    service = ComponentJobService(lifecycle_factory=lifecycle.bind)

    job = service.start("01M000000000000000000000AA", "confirm-token")
    assert response.blocked.wait(timeout=1)
    service.cancel(str(job["jobId"]))
    response.release.set()

    cancelled = _wait_terminal(service, str(job["jobId"]))
    assert cancelled["state"] == "cancelled"
    assert cancelled["canRetry"] is True
    assert response.bytes_read < 6
    assert lifecycle.applied is False
    assert lifecycle.plan_status["01M000000000000000000000AA"] == "aborted"


def test_recover_resumes_legacy_persisted_component_job(job_env: None) -> None:
    job_id = _persist_component_job()
    lifecycle = BlockingLifecycle()
    lifecycle.release.set()
    service = ComponentJobService(lifecycle_factory=lifecycle.bind)

    recovered = service.recover()

    assert any(job["jobId"] == job_id for job in recovered)
    completed = _wait_terminal(service, job_id)
    assert completed["state"] == "succeeded"
    assert lifecycle.apply_calls == 1


def test_recover_terminalizes_interrupted_component_and_retry_is_auditable(
    job_env: None,
) -> None:
    job_id = _persist_component_job("running")
    lifecycle = BlockingLifecycle()
    lifecycle.release.set()
    service = ComponentJobService(lifecycle_factory=lifecycle.bind)

    recovered = service.recover()

    interrupted = next(job for job in recovered if job["jobId"] == job_id)
    assert interrupted["rawState"] == "cancelled"
    assert interrupted["errorCode"] == "recovered"
    assert lifecycle.plan_status["01M000000000000000000000AA"] == "aborted"
    replacement = service.retry(job_id)
    assert replacement["jobId"] != job_id
    assert replacement["planId"] != interrupted["planId"]
    assert _wait_terminal(service, str(replacement["jobId"]))["state"] == "succeeded"


def test_recover_rolls_forward_job_when_component_commit_is_durable(job_env: None) -> None:
    job_id = _persist_component_job("running")
    lifecycle = BlockingLifecycle()
    lifecycle.recover_as_applied = True
    service = ComponentJobService(lifecycle_factory=lifecycle.bind)

    recovered = service.recover()

    committed = next(job for job in recovered if job["jobId"] == job_id)
    assert committed["rawState"] == "completed"
    assert committed["state"] == "succeeded"
    assert lifecycle.plan_status["01M000000000000000000000AA"] == "applied"


def test_flatpak_stage_is_persisted_by_component_job(job_env: None) -> None:
    lifecycle = StagedFlatpakLifecycle()
    service = ComponentJobService(lifecycle_factory=lifecycle.bind)

    job = service.start("01M000000000000000000000AA", "confirm-token")
    assert lifecycle.started.wait(timeout=1)
    try:
        observed = service.get(str(job["jobId"]))
        assert observed is not None
        assert observed["progress"] == {
            "stage": "installing",
            "current": 1,
            "total": 5,
            "unit": "steps",
            "currentItem": "demo-emulator",
        }
    finally:
        lifecycle.release.set()
    assert _wait_terminal(service, str(job["jobId"]))["state"] == "succeeded"
