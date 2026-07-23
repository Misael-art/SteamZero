# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import subprocess

import pytest

from steamzero.adapters.secret_service import SecretServiceStore
from steamzero.core.errors import SteamZeroError
from steamzero.core.secret import Secret


def test_secret_service_passes_secret_only_through_stdin(
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[tuple[list[str], str | None]] = []

    def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raw_input = kwargs.get("input")
        input_value = raw_input if isinstance(raw_input, str) else None
        calls.append((argv, input_value))
        return subprocess.CompletedProcess(argv, 0, "secret-value", "secret-value")

    store = SecretServiceStore(runner=runner, which=lambda _name: "/usr/bin/secret-tool")
    with caplog.at_level(logging.DEBUG):
        store.store("steamgriddb", "api_key", Secret("secret-value"))

    argv, secret = calls[0]
    assert secret == "secret-value"
    assert "secret-value" not in argv
    assert "secret-value" not in caplog.text
    assert argv[:3] == ["/usr/bin/secret-tool", "store", "--label=SteamZero scraping credential"]


def test_secret_service_lookup_uses_only_stable_attributes() -> None:
    def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, "stored-secret\n", "")

    store = SecretServiceStore(runner=runner, which=lambda _name: "/usr/bin/secret-tool")
    value = store.retrieve("steamgriddb", "api_key")
    assert value is not None
    assert value.reveal() == "stored-secret"


def test_secret_service_unavailable_propagates_actionable_error() -> None:
    store = SecretServiceStore(which=lambda _name: None)
    with pytest.raises(SteamZeroError, match="E-SCRAPE-VAULT-UNAVAILABLE"):
        store.store("steamgriddb", "api_key", Secret("secret-value"))


def test_secret_service_operational_lookup_error_is_not_treated_as_missing() -> None:
    def runner(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 2, "", "cofre bloqueado")

    store = SecretServiceStore(runner=runner, which=lambda _name: "/usr/bin/secret-tool")
    with pytest.raises(SteamZeroError, match="E-SCRAPE-VAULT-UNAVAILABLE"):
        store.retrieve("steamgriddb", "api_key")


@pytest.mark.parametrize(
    ("provider", "key_name"),
    [
        ("../steamgriddb", "api_key"),
        ("steamgriddb", "../../api_key"),
        ("SteamGridDB", "api_key"),
    ],
)
def test_secret_service_rejects_untrusted_attributes(provider: str, key_name: str) -> None:
    store = SecretServiceStore(which=lambda _name: "/usr/bin/secret-tool")
    with pytest.raises(SteamZeroError, match="E-API-SCHEMA"):
        store.retrieve(provider, key_name)
