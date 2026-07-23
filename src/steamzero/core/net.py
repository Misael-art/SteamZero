# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 SteamZero contributors
"""Rede HTTP centralizada, limitada e testável.

Este módulo é a única fronteira autorizada a abrir conexões HTTP(S). Consumidores
declaram hosts permitidos e recebem falhas normalizadas; nenhum consumidor precisa
conhecer ``urllib``. Downloads são publicados pela porta ``core.fs``.
"""

from __future__ import annotations

import email.message
import random
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Collection, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import IO, Protocol, cast
from urllib.parse import urlsplit

from steamzero.core import fs

_CHUNK = 1 << 20
_USER_AGENT = "SteamZero/0.1"


@dataclass
class NetworkFailure(Exception):
    """Falha de rede estável, sem incluir segredo, corpo ou URL com query."""

    code: str
    detail: str = ""
    status: int | None = None
    retryable: bool = False

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}" if self.detail else self.code


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 2.0
    jitter_ratio: float = 0.1

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("attempts deve ser >= 1")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("delays não podem ser negativos")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio deve estar entre 0 e 1")

    def delay_for(self, retry_index: int, *, random_value: float) -> float:
        raw = min(self.max_delay_seconds, self.base_delay_seconds * (2.0**retry_index))
        jitter = raw * self.jitter_ratio * ((random_value * 2.0) - 1.0)
        return max(0.0, raw + jitter)


@dataclass(frozen=True)
class NetworkPolicy:
    allowed_hosts: frozenset[str]
    timeout_seconds: float = 30.0
    max_bytes: int = 32 * 1024 * 1024
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    allow_http_loopback: bool = False

    def __post_init__(self) -> None:
        if not self.allowed_hosts:
            raise ValueError("allowed_hosts não pode ser vazio")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout deve ser positivo")
        if self.max_bytes <= 0:
            raise ValueError("max_bytes deve ser positivo")


class CancellationToken:
    """Token thread-safe que permite cancelar espera, retry e download."""

    def __init__(self) -> None:
        self._event = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise NetworkFailure("E-NET-CANCELLED", "operação cancelada")


class ResponsePort(Protocol):
    headers: Mapping[str, str] | email.message.Message

    def read(self, size: int = -1) -> bytes: ...
    def geturl(self) -> str: ...
    def __enter__(self) -> ResponsePort: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...


class TransportPort(Protocol):
    def __call__(
        self, request: urllib.request.Request, timeout: float
    ) -> AbstractContextManager[ResponsePort]: ...


@dataclass(frozen=True)
class HttpResult:
    url: str
    status: int
    headers: Mapping[str, str]
    body: bytes


class TokenBucket:
    """Rate limit em memória limitada, com relógio e espera injetáveis."""

    def __init__(
        self,
        *,
        rate_per_second: float,
        burst: int = 1,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate_per_second <= 0 or burst < 1:
            raise ValueError("rate e burst devem ser positivos")
        self._rate = rate_per_second
        self._burst = float(burst)
        self._tokens = float(burst)
        self._updated = clock()
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()

    def acquire(self, cancel: CancellationToken | None = None) -> None:
        while True:
            if cancel is not None:
                cancel.raise_if_cancelled()
            with self._lock:
                now = self._clock()
                elapsed = max(0.0, now - self._updated)
                self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
                self._updated = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self._rate
            self._sleep(wait)


def _default_transport(
    request: urllib.request.Request, timeout: float
) -> AbstractContextManager[ResponsePort]:
    # ``urllib`` usa o contexto TLS verificado do sistema (hostname + CAs).
    response = urllib.request.urlopen(request, timeout=timeout)  # noqa: S310
    return cast(AbstractContextManager[ResponsePort], response)


class HttpClient:
    """Cliente síncrono seguro. Instâncias não guardam cookies nem credenciais."""

    def __init__(
        self,
        *,
        transport: TransportPort = _default_transport,
        sleep: Callable[[float], None] = time.sleep,
        random_fn: Callable[[], float] = random.random,
        limiter: TokenBucket | None = None,
    ) -> None:
        self._transport = transport
        self._sleep = sleep
        self._random = random_fn
        self._limiter = limiter

    def get(
        self,
        url: str,
        *,
        policy: NetworkPolicy,
        headers: Mapping[str, str] | None = None,
        cancel: CancellationToken | None = None,
    ) -> HttpResult:
        with self.open(url, policy=policy, headers=headers, cancel=cancel) as response:
            body = _read_limited(response, policy.max_bytes, cancel)
            return HttpResult(
                url=_response_url(response, url),
                status=int(getattr(response, "status", 200)),
                headers=dict(_response_headers(response).items()),
                body=body,
            )

    @contextmanager
    def open(
        self,
        url: str,
        *,
        policy: NetworkPolicy,
        headers: Mapping[str, str] | None = None,
        cancel: CancellationToken | None = None,
    ) -> Iterator[ResponsePort]:
        _validate_url(url, policy)
        merged_headers = {"User-Agent": _USER_AGENT, **dict(headers or {})}
        request = urllib.request.Request(url, headers=merged_headers)  # noqa: S310
        for attempt in range(policy.retry.attempts):
            if cancel is not None:
                cancel.raise_if_cancelled()
            if self._limiter is not None:
                self._limiter.acquire(cancel)
            try:
                with self._transport(request, policy.timeout_seconds) as response:
                    _validate_url(_response_url(response, url), policy, redirect=True)
                    _validate_declared_size(response, policy.max_bytes)
                    yield response
                    return
            except NetworkFailure:
                raise
            except urllib.error.HTTPError as exc:
                retryable = exc.code in {408, 425, 429, 500, 502, 503, 504}
                failure = NetworkFailure(
                    "E-NET-HTTP",
                    f"HTTP {exc.code}",
                    status=exc.code,
                    retryable=retryable,
                )
            except TimeoutError as exc:
                failure = NetworkFailure("E-NET-TIMEOUT", "tempo limite excedido", retryable=True)
                failure.__cause__ = exc
            except (OSError, urllib.error.URLError) as exc:
                failure = NetworkFailure("E-NET-OFFLINE", "conexão indisponível", retryable=True)
                failure.__cause__ = exc
            if not failure.retryable or attempt + 1 >= policy.retry.attempts:
                raise failure
            if cancel is not None:
                cancel.raise_if_cancelled()
            delay = policy.retry.delay_for(attempt, random_value=self._random())
            self._sleep(delay)
        raise AssertionError("retry loop sem resultado")  # pragma: no cover

    def download(
        self,
        url: str,
        destination: Path,
        *,
        policy: NetworkPolicy,
        headers: Mapping[str, str] | None = None,
        cancel: CancellationToken | None = None,
    ) -> int:
        with self.open(url, policy=policy, headers=headers, cancel=cancel) as response:
            reader = _CancelableReader(response, cancel)
            try:
                return fs.write_stream_atomic(
                    destination, cast(IO[bytes], reader), max_bytes=policy.max_bytes
                )
            except NetworkFailure:
                raise
            except Exception as exc:
                if getattr(exc, "code", "") == "E-CONTENT-LIMIT":
                    raise NetworkFailure(
                        "E-NET-CONTENT-LIMIT", "download excedeu o limite"
                    ) from exc
                raise


def fetch_bytes(
    url: str,
    *,
    max_bytes: int,
    timeout_seconds: float = 30.0,
    headers: Mapping[str, str] | None = None,
    allowed_redirect_hosts: Collection[str] = (),
    retry: RetryPolicy | None = None,
    cancel: CancellationToken | None = None,
    client: HttpClient | None = None,
) -> bytes:
    """Atalho seguro para adapters síncronos que precisam do corpo em memória."""
    host = (urlsplit(url).hostname or "").casefold().rstrip(".")
    allowed = frozenset({host, *allowed_redirect_hosts})
    policy = NetworkPolicy(
        allowed_hosts=allowed,
        timeout_seconds=timeout_seconds,
        max_bytes=max_bytes,
        retry=retry or RetryPolicy(attempts=1),
    )
    return (client or HttpClient()).get(
        url, policy=policy, headers=headers, cancel=cancel
    ).body


class _CancelableReader:
    def __init__(self, source: ResponsePort, cancel: CancellationToken | None) -> None:
        self._source = source
        self._cancel = cancel

    def read(self, size: int = -1) -> bytes:
        if self._cancel is not None:
            self._cancel.raise_if_cancelled()
        return self._source.read(size)


def _validate_url(url: str, policy: NetworkPolicy, *, redirect: bool = False) -> None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold().rstrip(".")
    scheme_ok = parsed.scheme.casefold() == "https"
    loopback_http = (
        policy.allow_http_loopback
        and parsed.scheme.casefold() == "http"
        and host in {"127.0.0.1", "::1", "localhost"}
    )
    if not scheme_ok and not loopback_http:
        code = "E-NET-REDIRECT-DENIED" if redirect else "E-NET-INSECURE-URL"
        raise NetworkFailure(code, "somente HTTPS é permitido")
    if parsed.username is not None or parsed.password is not None:
        raise NetworkFailure("E-NET-INSECURE-URL", "userinfo em URL é proibido")
    if host not in {item.casefold().rstrip(".") for item in policy.allowed_hosts}:
        code = "E-NET-REDIRECT-DENIED" if redirect else "E-NET-HOST-DENIED"
        raise NetworkFailure(code, f"host não permitido: {host}")


def _response_url(response: ResponsePort, requested_url: str) -> str:
    getter = getattr(response, "geturl", None)
    if not callable(getter):
        return requested_url
    value = getter()
    return value if isinstance(value, str) and value else requested_url


def _validate_declared_size(response: ResponsePort, max_bytes: int) -> None:
    declared = _response_headers(response).get("Content-Length")
    if declared is None:
        return
    try:
        value = int(declared)
    except ValueError as exc:
        raise NetworkFailure("E-NET-CONTENT-LIMIT", "Content-Length inválido") from exc
    if value < 0 or value > max_bytes:
        raise NetworkFailure("E-NET-CONTENT-LIMIT", "conteúdo declarado excede o limite")


def _response_headers(response: ResponsePort) -> Mapping[str, str]:
    headers = getattr(response, "headers", None)
    return headers if isinstance(headers, Mapping) else {}


def _read_limited(
    response: ResponsePort, max_bytes: int, cancel: CancellationToken | None
) -> bytes:
    chunks: list[bytes] = []
    received = 0
    while True:
        if cancel is not None:
            cancel.raise_if_cancelled()
        chunk = response.read(min(_CHUNK, max_bytes + 1 - received))
        if not chunk:
            return b"".join(chunks)
        received += len(chunk)
        if received > max_bytes:
            raise NetworkFailure("E-NET-CONTENT-LIMIT", "download excedeu o limite")
        chunks.append(chunk)


@dataclass
class FakeResponse:
    """Resposta fake determinística para testes e adapters offline."""

    body: bytes
    url: str
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    chunk_size: int | None = None
    _offset: int = field(default=0, init=False)

    def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self.body):
            return b""
        limit = size if size >= 0 else len(self.body)
        if self.chunk_size is not None:
            limit = min(limit, self.chunk_size)
        result = self.body[self._offset : self._offset + limit]
        self._offset += len(result)
        return result

    def geturl(self) -> str:
        return self.url

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class FakeTransport:
    """Fila finita de respostas/exceções; registra requisições sem rede."""

    def __init__(self, outcomes: Collection[ResponsePort | BaseException]) -> None:
        self._outcomes = list(outcomes)
        self.requests: list[tuple[str, float, Mapping[str, str]]] = []

    def __call__(
        self, request: urllib.request.Request, timeout: float
    ) -> AbstractContextManager[ResponsePort]:
        self.requests.append((request.full_url, timeout, dict(request.header_items())))
        if not self._outcomes:
            raise AssertionError("fake transport sem resposta")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return cast(AbstractContextManager[ResponsePort], outcome)
