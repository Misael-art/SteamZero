# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Aplicação de componente como job persistente e não bloqueante."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from steamzero.adapters.component_jobs import ComponentJobService
from steamzero.core import fs, net, state
from steamzero.core.errors import SteamZeroError


class BlockingLifecycle:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()
        self.apply_calls = 0
        self.store: state.StateStore | None = None

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
        return {
            "status": "ok",
            "operationId": "01M000000000000000000000BB",
            "adapterId": "demo-emulator",
        }


class RetryLifecycle(BlockingLifecycle):
    def __init__(self) -> None:
        super().__init__()
        self.release.set()

    def apply(self, plan_id: str, confirm_token: str) -> dict[str, str]:
        self.apply_calls += 1
        if self.apply_calls == 1:
            raise SteamZeroError("E-SUPPLY-OFFLINE", detail="rede indisponível")
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


def test_start_returns_immediately_and_deduplicates_repeated_confirmation(job_env: None) -> None:
    lifecycle = BlockingLifecycle()
    service = ComponentJobService(lifecycle_factory=lifecycle.bind)

    started_at = time.monotonic()
    first = service.start("01M000000000000000000000AA", "confirm-token")
    elapsed = time.monotonic() - started_at

    assert elapsed < 0.2
    assert first["jobId"]
    assert first["state"] in {"queued", "running"}
    assert lifecycle.started.wait(timeout=1)

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

    retried = service.retry(str(first["jobId"]))
    assert retried["jobId"] != first["jobId"]
    completed = _wait_terminal(service, str(retried["jobId"]))
    assert completed["state"] == "succeeded"
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
    assert _wait_terminal(service, str(job["jobId"]))["state"] == "succeeded"


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
