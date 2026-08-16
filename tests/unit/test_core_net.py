from __future__ import annotations

import urllib.error
from pathlib import Path

import pytest

from steamzero.core import net
from steamzero.core.net import (
    CancellationToken,
    FakeResponse,
    FakeTransport,
    HttpClient,
    NetworkFailure,
    NetworkPolicy,
    RetryPolicy,
    TokenBucket,
)


def policy(**changes: object) -> NetworkPolicy:
    values: dict[str, object] = {
        "allowed_hosts": frozenset({"downloads.example"}),
        "timeout_seconds": 7.0,
        "max_bytes": 8,
        "retry": RetryPolicy(attempts=1, jitter_ratio=0),
    }
    values.update(changes)
    return NetworkPolicy(**values)  # type: ignore[arg-type]


def test_http_client_validates_policy_and_returns_bounded_body() -> None:
    transport = FakeTransport(
        [FakeResponse(b"payload", "https://downloads.example/file", headers={"X-Test": "1"})]
    )
    result = HttpClient(transport=transport).get(
        "https://downloads.example/file", policy=policy(), headers={"Accept": "x/test"}
    )

    assert result.body == b"payload"
    assert result.status == 200
    assert transport.requests[0][1] == 7.0
    assert transport.requests[0][2]["Accept"] == "x/test"


def test_transfer_observer_reports_declared_bytes_for_each_chunk() -> None:
    progress: list[tuple[int, int | None]] = []
    cancel_checks = 0

    def check_cancelled() -> None:
        nonlocal cancel_checks
        cancel_checks += 1

    response = FakeResponse(
        b"payload",
        "https://downloads.example/file",
        headers={"Content-Length": "7"},
        chunk_size=2,
    )
    with net.transfer_observer(
        progress=lambda current, total: progress.append((current, total)),
        cancel_check=check_cancelled,
    ):
        result = HttpClient(transport=FakeTransport([response])).get(
            "https://downloads.example/file", policy=policy()
        )

    assert result.body == b"payload"
    assert progress == [(0, 7), (2, 7), (4, 7), (6, 7), (7, 7)]
    assert cancel_checks >= len(progress)


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("http://downloads.example/file", "E-NET-INSECURE-URL"),
        ("https://denied.example/file", "E-NET-HOST-DENIED"),
        ("https://user:secret@downloads.example/file", "E-NET-INSECURE-URL"),
    ],
)
def test_http_client_rejects_unsafe_initial_urls(url: str, code: str) -> None:
    with pytest.raises(NetworkFailure, match=code):
        HttpClient(transport=FakeTransport([])).get(url, policy=policy())


def test_http_client_rejects_unsafe_redirect_and_declared_size() -> None:
    redirected = FakeResponse(b"x", "https://other.example/file")
    with pytest.raises(NetworkFailure, match="E-NET-REDIRECT-DENIED"):
        HttpClient(transport=FakeTransport([redirected])).get(
            "https://downloads.example/file", policy=policy()
        )

    oversized = FakeResponse(
        b"x", "https://downloads.example/file", headers={"Content-Length": "9"}
    )
    with pytest.raises(NetworkFailure, match="E-NET-CONTENT-LIMIT"):
        HttpClient(transport=FakeTransport([oversized])).get(
            "https://downloads.example/file", policy=policy()
        )


def test_http_client_enforces_streamed_size_without_content_length() -> None:
    response = FakeResponse(b"123456789", "https://downloads.example/file", chunk_size=3)
    with pytest.raises(NetworkFailure, match="E-NET-CONTENT-LIMIT"):
        HttpClient(transport=FakeTransport([response])).get(
            "https://downloads.example/file", policy=policy()
        )


def test_retry_uses_backoff_only_for_retryable_failures() -> None:
    transport = FakeTransport(
        [
            urllib.error.URLError("offline"),
            FakeResponse(b"ok", "https://downloads.example/file"),
        ]
    )
    sleeps: list[float] = []
    client = HttpClient(transport=transport, sleep=sleeps.append, random_fn=lambda: 0.5)
    result = client.get(
        "https://downloads.example/file",
        policy=policy(retry=RetryPolicy(attempts=2, base_delay_seconds=0.5, jitter_ratio=0)),
    )

    assert result.body == b"ok"
    assert sleeps == [0.5]
    assert len(transport.requests) == 2


def test_http_status_is_normalized_and_not_retried_when_terminal() -> None:
    error = urllib.error.HTTPError("https://downloads.example/file", 404, "not found", {}, None)
    with pytest.raises(NetworkFailure) as raised:
        HttpClient(transport=FakeTransport([error])).get(
            "https://downloads.example/file",
            policy=policy(retry=RetryPolicy(attempts=3)),
        )
    assert raised.value.status == 404
    assert raised.value.retryable is False


def test_cancellation_stops_before_transport() -> None:
    cancel = CancellationToken()
    cancel.cancel()
    transport = FakeTransport([])
    with pytest.raises(NetworkFailure, match="E-NET-CANCELLED"):
        HttpClient(transport=transport).get(
            "https://downloads.example/file", policy=policy(), cancel=cancel
        )
    assert transport.requests == []


def test_download_publishes_atomically_and_cancellation_leaves_no_file(tmp_path: Path) -> None:
    destination = tmp_path / "artifact.bin"
    client = HttpClient(
        transport=FakeTransport(
            [FakeResponse(b"content", "https://downloads.example/file", chunk_size=2)]
        )
    )
    assert client.download("https://downloads.example/file", destination, policy=policy()) == 7
    assert destination.read_bytes() == b"content"

    cancel = CancellationToken()

    class CancellingResponse(FakeResponse):
        def read(self, size: int = -1) -> bytes:
            data = super().read(size)
            cancel.cancel()
            return data

    cancelled_destination = tmp_path / "cancelled.bin"
    cancelling = HttpClient(
        transport=FakeTransport(
            [CancellingResponse(b"content", "https://downloads.example/file", chunk_size=2)]
        )
    )
    with pytest.raises(NetworkFailure, match="E-NET-CANCELLED"):
        cancelling.download(
            "https://downloads.example/file",
            cancelled_destination,
            policy=policy(),
            cancel=cancel,
        )
    assert not cancelled_destination.exists()


def test_token_bucket_waits_for_capacity_and_honors_cancellation() -> None:
    now = [0.0]
    sleeps: list[float] = []

    def advance(delay: float) -> None:
        sleeps.append(delay)
        now[0] += delay

    bucket = TokenBucket(rate_per_second=2.0, burst=1, clock=lambda: now[0], sleep=advance)
    bucket.acquire()
    bucket.acquire()
    assert sleeps == [0.5]

    cancel = CancellationToken()
    cancel.cancel()
    with pytest.raises(NetworkFailure, match="E-NET-CANCELLED"):
        bucket.acquire(cancel)


def test_loopback_http_is_explicitly_opt_in() -> None:
    response = FakeResponse(b"ok", "http://127.0.0.1:8080/health")
    result = HttpClient(transport=FakeTransport([response])).get(
        "http://127.0.0.1:8080/health",
        policy=NetworkPolicy(
            allowed_hosts=frozenset({"127.0.0.1"}),
            allow_http_loopback=True,
            retry=RetryPolicy(attempts=1),
        ),
    )
    assert result.body == b"ok"
